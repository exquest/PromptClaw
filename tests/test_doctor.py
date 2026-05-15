from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from promptclaw.cli import cmd_doctor
from promptclaw.config import default_project_config, save_config
from promptclaw.models import PALConfig
from promptclaw.doctor import run_doctor


def _init_project(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    save_config(project_root, default_project_config("Doctor Test"))
    (project_root / "prompts" / "agents").mkdir(parents=True, exist_ok=True)
    (project_root / ".promptclaw").mkdir(exist_ok=True)
    (project_root / "docs").mkdir(exist_ok=True)
    (project_root / "AGENTS.md").write_text("rules\n")
    (project_root / "pyproject.toml").write_text("[project]\nname='doctor-test'\n")


def _init_runtime_markers(project_root: Path) -> None:
    (project_root / ".git").mkdir()
    (project_root / "sdp.toml").write_text("state_db_path = '.sdp/state.db'\n")
    state_dir = project_root / ".sdp"
    state_dir.mkdir(exist_ok=True)
    promptclaw_dir = project_root / ".promptclaw"
    promptclaw_dir.mkdir(exist_ok=True)
    conn = sqlite3.connect(state_dir / "state.db")
    conn.execute(
        "CREATE TABLE tasks (task_id TEXT PRIMARY KEY, description TEXT, tier TEXT, status TEXT, created_at TEXT, updated_at TEXT)"
    )
    conn.commit()
    conn.close()
    conn = sqlite3.connect(promptclaw_dir / "observatory.db")
    conn.execute("CREATE TABLE observatory_events (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


def test_run_doctor_passes_and_skips_runtime_preflight_for_plain_project(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root)

    report = run_doctor(project_root)

    assert report.ok is True
    assert report.checks["config"]["ok"] is True
    assert report.checks["pal_router"]["status"] == "skipped"
    assert report.checks["runtime_preflight"]["status"] == "skipped"


def test_run_doctor_checks_enabled_pal_router(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root)
    config = default_project_config("PAL Doctor Test")
    config.pal = PALConfig(enabled=True, base_url="http://pal-cloud-a6000:8000")
    save_config(project_root, config)

    class FakeClient:
        @classmethod
        def from_config(cls, loaded_config):
            assert loaded_config.pal.enabled is True
            return cls()

        def health(self):
            return {
                "status": "green",
                "ollama_available": True,
                "phase": "phase-1-a6000",
                "loaded_models": ["llama3.3:70b-instruct-q4_K_M"],
            }

    monkeypatch.setattr("promptclaw.doctor.PALRouterClient", FakeClient)

    report = run_doctor(project_root)

    assert report.ok is True
    assert report.checks["pal_router"]["status"] == "pass"
    assert "phase-1-a6000" in report.checks["pal_router"]["message"]
    assert "llama3.3:70b-instruct-q4_K_M" in report.checks["pal_router"]["details"]


def test_run_doctor_fails_when_enabled_pal_router_is_unreachable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root)
    config = default_project_config("PAL Doctor Failure Test")
    config.pal.enabled = True
    save_config(project_root, config)

    class FakeClient:
        @classmethod
        def from_config(cls, loaded_config):
            return cls()

        def health(self):
            raise RuntimeError("connection refused")

    monkeypatch.setattr("promptclaw.doctor.PALRouterClient", FakeClient)

    report = run_doctor(project_root)

    assert report.ok is False
    assert report.checks["pal_router"]["status"] == "fail"
    assert "connection refused" in report.checks["pal_router"]["message"]


def test_run_doctor_runs_runtime_preflight_when_runtime_root_present(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root)
    _init_runtime_markers(project_root)
    tools_dir = project_root / "tools"
    tools_dir.mkdir()
    (tools_dir / "preflight.py").write_text(
        """
from dataclasses import dataclass

@dataclass
class Report:
    ok: bool
    summary: str
    checks: dict

def run_preflight(project_root, *, workdir=None, checkpoint_path=None):
    return Report(ok=False, summary="Preflight FAILED", checks={"runtime_db": {"ok": False, "message": "bad runtime db"}})
"""
    )

    report = run_doctor(project_root)

    assert report.ok is False
    assert report.checks["runtime_preflight"]["status"] == "fail"
    assert "Preflight FAILED" in report.checks["runtime_preflight"]["message"]


def test_cmd_doctor_returns_nonzero_when_runtime_preflight_fails(tmp_path: Path, capsys) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root)
    _init_runtime_markers(project_root)
    tools_dir = project_root / "tools"
    tools_dir.mkdir()
    (tools_dir / "preflight.py").write_text(
        """
from dataclasses import dataclass

@dataclass
class Report:
    ok: bool
    summary: str
    checks: dict

def run_preflight(project_root, *, workdir=None, checkpoint_path=None):
    return Report(ok=False, summary="Preflight FAILED", checks={"lock": {"ok": False, "message": "stale lock"}})
"""
    )

    rc = cmd_doctor(argparse.Namespace(project_root=project_root))
    output = capsys.readouterr().out

    assert rc == 1
    assert "runtime_preflight" in output
    assert "stale lock" in output
