"""Tests for maintenance mode state handling."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import maintenance_mode


def test_enter_maintenance_writes_state_file(tmp_path: Path) -> None:
    project_root = tmp_path
    (project_root / ".sdp").mkdir()

    maintenance_path = maintenance_mode.enter_maintenance(
        project_root,
        reason="reboot",
        actor="test-suite",
    )

    payload = json.loads(maintenance_path.read_text())
    assert payload["reason"] == "reboot"
    assert payload["actor"] == "test-suite"
    assert payload["active"] is True


def test_exit_maintenance_clears_active_flag(tmp_path: Path) -> None:
    project_root = tmp_path
    (project_root / ".sdp").mkdir()
    maintenance_mode.enter_maintenance(project_root, reason="reboot", actor="test-suite")

    previous = maintenance_mode.exit_maintenance(project_root, actor="test-suite")

    assert previous is not None
    payload = json.loads((project_root / ".sdp" / "maintenance-mode.json").read_text())
    assert payload["active"] is False
    assert payload["released_by"] == "test-suite"


def test_read_status_returns_none_when_not_enabled(tmp_path: Path) -> None:
    assert maintenance_mode.read_maintenance_status(tmp_path) is None
