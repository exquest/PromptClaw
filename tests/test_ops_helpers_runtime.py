"""Tests for CypherClaw operational helper scripts and tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import gemini_monitor
import glacier_cleanup


def test_gemini_monitor_state_and_event_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_file = tmp_path / "monitor_state.json"
    log_file = tmp_path / "monitor.log"
    monkeypatch.setattr(gemini_monitor, "STATE_FILE", state_file)
    monkeypatch.setattr(gemini_monitor, "LOG_FILE", log_file)

    gemini_monitor.save_state({"last_ts": 42})
    assert gemini_monitor.load_state() == {"last_ts": 42}

    stdout = '\n'.join([
        json.dumps({"type": "user_message", "ts": 1, "text": "@gemini status"}),
        json.dumps({"type": "chat_cypherclaw", "ts": 2, "text": "CRITICAL disk"}),
    ])
    monkeypatch.setattr(
        gemini_monitor.subprocess,
        "run",
        lambda cmd, **kwargs: SimpleNamespace(returncode=0, stdout=stdout, stderr=""),
    )

    events = gemini_monitor.get_remote_events()

    assert [event["ts"] for event in events] == [1, 2]


def test_gemini_monitor_send_to_inbox_and_dashboard_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_file = tmp_path / "monitor.log"
    monkeypatch.setattr(gemini_monitor, "LOG_FILE", log_file)

    recorded_cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs) -> SimpleNamespace:
        recorded_cmds.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(gemini_monitor.subprocess, "run", fake_run)
    gemini_monitor.send_to_inbox("hello world")

    assert recorded_cmds
    assert recorded_cmds[0][0] == "ssh"
    assert gemini_monitor.INBOX in recorded_cmds[0][-1]
    assert "hello world" in recorded_cmds[0][-1]

    dashboard_script = tmp_path / "dashboard_generator.py"
    dashboard_script.write_text("print('ok')\n")
    monkeypatch.setattr(gemini_monitor, "__file__", str(tmp_path / "gemini_monitor.py"))
    recorded_cmds.clear()

    assert gemini_monitor.run_local_task("update_dashboard") is True
    assert recorded_cmds[0][0] == "python3"
    assert recorded_cmds[0][1].endswith("dashboard_generator.py")


def test_glacier_cleanup_inventory_state_and_dry_run(tmp_path: Path) -> None:
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(
        json.dumps(
            {
                "ArchiveList": [
                    {"ArchiveId": "arch-1"},
                    {"ArchiveId": "arch-2"},
                ]
            }
        )
    )
    state_path = tmp_path / "state.json"

    archives = glacier_cleanup.load_inventory(str(inventory_path))
    assert [archive["ArchiveId"] for archive in archives] == ["arch-1", "arch-2"]

    assert glacier_cleanup.load_state(str(state_path)) == set()

    glacier_cleanup.save_state(str(state_path), {"arch-1"}, total=2)
    saved = json.loads(state_path.read_text())
    assert saved["deleted_count"] == 1
    assert saved["deleted_ids"] == ["arch-1"]


def test_glacier_delete_archive_retries_throttling(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            SimpleNamespace(returncode=1, stderr="ThrottlingException", stdout=""),
            SimpleNamespace(returncode=0, stderr="", stdout=""),
        ]
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr(glacier_cleanup.subprocess, "run", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(glacier_cleanup.time, "sleep", sleep_calls.append)

    archive_id, success, error = glacier_cleanup.delete_archive("vault", "us-west-2", "arch-1")

    assert archive_id == "arch-1"
    assert success is True
    assert error == ""
    assert sleep_calls == [1.0]
