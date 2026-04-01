"""Tests for runtime preflight validation."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import preflight


def _write_state_db(db_path: Path, *, running_tasks: int = 0) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE tasks (
            task_id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            tier TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    rows = [
        ("T-001@20260401T000000Z", "Task one", "T1", "pending", "2026-04-01T00:00:00Z", "2026-04-01T00:00:00Z"),
        ("T-002@20260401T000000Z", "Task two", "T1", "complete", "2026-04-01T00:05:00Z", "2026-04-01T00:05:00Z"),
    ]
    for index in range(running_tasks):
        rows.append(
            (
                f"T-RUN-{index}@20260401T010000Z",
                f"Running {index}",
                "T1",
                "running",
                "2026-04-01T01:00:00Z",
                "2026-04-01T01:00:00Z",
            )
        )
    conn.executemany("INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def _healthy_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path
    (project_root / ".git").mkdir()
    (project_root / "AGENTS.md").write_text("home rules\n")
    (project_root / "pyproject.toml").write_text("[project]\nname='cypherclaw'\n")
    (project_root / "sdp.toml").write_text("state_db_path = '.sdp/state.db'\n")
    state_dir = project_root / ".sdp"
    state_dir.mkdir()
    promptclaw_dir = project_root / ".promptclaw"
    promptclaw_dir.mkdir()
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    (workdir / ".git").mkdir()
    (workdir / "AGENTS.md").write_text("rules\n")
    (workdir / "pyproject.toml").write_text("[project]\nname='cypherclaw'\n")
    (workdir / "sdp.toml").symlink_to(project_root / "sdp.toml")
    _write_state_db(state_dir / "state.db")
    (promptclaw_dir / "observatory.db").write_bytes(b"sqlite placeholder")
    return project_root, workdir


def test_preflight_passes_for_healthy_project(tmp_path: Path) -> None:
    project_root, workdir = _healthy_project(tmp_path)

    report = preflight.run_preflight(project_root, workdir=workdir)

    assert report.ok is True
    assert report.summary == "Preflight OK"
    assert report.checks["state_db_integrity"]["ok"] is True
    assert report.checks["workdir_layout"]["ok"] is True


def test_preflight_fails_when_state_db_missing(tmp_path: Path) -> None:
    project_root, workdir = _healthy_project(tmp_path)
    (project_root / ".sdp" / "state.db").unlink()

    report = preflight.run_preflight(project_root, workdir=workdir)

    assert report.ok is False
    assert report.checks["state_db_exists"]["ok"] is False


def test_preflight_detects_stale_run_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root, workdir = _healthy_project(tmp_path)
    lock_path = project_root / ".sdp" / "run.lock"
    lock_path.write_text("999999\n")
    monkeypatch.setattr(preflight, "pid_exists", lambda pid: False)

    report = preflight.run_preflight(project_root, workdir=workdir)

    assert report.ok is False
    assert report.checks["run_lock"]["ok"] is False
    assert "stale" in report.checks["run_lock"]["message"].lower()


def test_preflight_detects_checkpoint_count_mismatch(tmp_path: Path) -> None:
    project_root, workdir = _healthy_project(tmp_path)
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(json.dumps({"queue_counts": {"pending": 99, "complete": 1}}))

    report = preflight.run_preflight(project_root, workdir=workdir, checkpoint_path=checkpoint)

    assert report.ok is False
    assert report.checks["checkpoint_reconciliation"]["ok"] is False


def test_preflight_fails_when_workdir_layout_is_incomplete(tmp_path: Path) -> None:
    project_root, workdir = _healthy_project(tmp_path)
    (workdir / ".git").rmdir()

    report = preflight.run_preflight(project_root, workdir=workdir)

    assert report.ok is False
    assert report.checks["workdir_layout"]["ok"] is False
