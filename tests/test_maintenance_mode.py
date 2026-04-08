"""Tests for maintenance mode state handling."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import maintenance_mode


def test_enter_maintenance_writes_authority_flag(tmp_path: Path) -> None:
    project_root = tmp_path
    (project_root / ".sdp").mkdir()

    maintenance_path = maintenance_mode.enter_maintenance(
        project_root,
        reason="reboot",
        actor="test-suite",
    )

    payload = json.loads(maintenance_path.read_text())
    assert maintenance_path == project_root / ".sdp" / "MAINTENANCE"
    assert payload["reason"] == "reboot"
    assert payload["actor"] == "test-suite"
    assert payload["active"] is True
    assert Path(payload["checkpoint_path"]).exists()


def test_enter_maintenance_ignores_unscoped_runner_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path
    (project_root / ".sdp").mkdir()
    monkeypatch.setattr(maintenance_mode, "_runner_pids", lambda: [43210])

    maintenance_path = maintenance_mode.enter_maintenance(
        project_root,
        reason="reboot",
        actor="test-suite",
    )

    assert maintenance_path.exists()


def test_exit_maintenance_clears_flag_and_restores_circuit(tmp_path: Path) -> None:
    project_root = tmp_path
    (project_root / ".sdp").mkdir()
    maintenance_mode.enter_maintenance(project_root, reason="reboot", actor="test-suite")

    previous = maintenance_mode.exit_maintenance(project_root, actor="test-suite")

    assert previous is not None
    assert not (project_root / ".sdp" / "MAINTENANCE").exists()
    circuit_payload = json.loads((project_root / ".sdp" / "circuit_breaker.json").read_text())
    assert circuit_payload["status"] == "closed"
    assert previous["released_by"] == "test-suite"

def test_read_status_returns_none_when_not_enabled(tmp_path: Path) -> None:
    assert maintenance_mode.read_maintenance_status(tmp_path) is None


def test_enter_maintenance_refuses_active_runner_without_override(tmp_path: Path) -> None:
    project_root = tmp_path
    sdp_dir = project_root / ".sdp"
    sdp_dir.mkdir()
    conn = sqlite3.connect(sdp_dir / "state.db")
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
    conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "T-001@20260402T000000Z",
            "Active task",
            "T1",
            "running",
            "2026-04-02T00:00:00Z",
            "2026-04-02T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="allow-runner-stop"):
        maintenance_mode.enter_maintenance(
            project_root,
            reason="unsafe",
            actor="test-suite",
        )

    assert not (project_root / ".sdp" / "MAINTENANCE").exists()
