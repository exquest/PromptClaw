"""Runtime coverage for the Telegram /local command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import cypherclaw_daemon


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _healthy_ollama() -> dict[str, object]:
    return {
        "healthy": True,
        "instances": [
            {
                "socket": "socket0",
                "port": 11434,
                "healthy": True,
                "status": "healthy",
                "models": ["deepseek-r1:14b"],
                "latency_ms": 42.0,
            },
            {
                "socket": "socket1",
                "port": 11435,
                "healthy": False,
                "status": "unreachable",
                "models": [],
                "latency_ms": None,
            },
        ],
    }


def _status_snapshot() -> dict[str, object]:
    return {
        "memory": 3,
        "tasks": 1,
        "schedules": 2,
        "artifacts": 4,
        "ollama": _healthy_ollama(),
    }


def test_status_snapshot_includes_guarded_ollama_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cypherclaw_daemon,
        "state",
        type(
            "_State",
            (),
            {
                "tasks": {"t1": {"status": "running"}},
                "schedules": [{"enabled": True}, {"enabled": False}],
                "conversation": ["one", "two", "three"],
            },
        )(),
    )
    monkeypatch.setattr(cypherclaw_daemon, "list_artifacts", lambda: ["a.txt", "b.txt"])
    monkeypatch.setattr(cypherclaw_daemon, "ollama_health", _healthy_ollama)

    snapshot = cypherclaw_daemon.status_snapshot()

    assert snapshot == {
        "memory": 3,
        "tasks": 1,
        "schedules": 1,
        "artifacts": 2,
        "ollama": _healthy_ollama(),
    }


def test_local_command_displays_ollama_from_status_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(cypherclaw_daemon, "tg_send", sent.append)
    monkeypatch.setattr(cypherclaw_daemon, "status_snapshot", _status_snapshot)
    monkeypatch.setattr(
        cypherclaw_daemon,
        "ollama_health",
        lambda: pytest.fail("/local should render from status_snapshot(), not re-probe ollama_health()"),
    )

    handled = cypherclaw_daemon.handle_builtin("/local")

    assert handled is True
    assert sent
    text = sent[-1]
    assert "Local Models" in text
    assert "socket0" in text
    assert "deepseek-r1:14b" in text
    assert "42ms" in text
    assert "unreachable" in text.lower()


def test_local_command_displays_unavailable_when_ollama_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(cypherclaw_daemon, "tg_send", sent.append)
    monkeypatch.setattr(
        cypherclaw_daemon,
        "status_snapshot",
        lambda: {
            "memory": 0,
            "tasks": 0,
            "schedules": 0,
            "artifacts": 0,
            "ollama": {"healthy": False, "instances": []},
        },
    )

    handled = cypherclaw_daemon.handle_builtin("/local")

    assert handled is True
    assert sent
    assert "unavailable" in sent[-1].lower()


def test_local_command_runtime_renders_ollama_health() -> None:
    tools_path = (PROJECT_ROOT / "my-claw" / "tools").resolve()
    snapshot_literal = repr(_status_snapshot())
    code = (
        "import json, sys; "
        f"sys.path.insert(0, {str(tools_path)!r}); "
        "import cypherclaw_daemon; "
        "sent = []; "
        "cypherclaw_daemon.tg_send = sent.append; "
        f"cypherclaw_daemon.status_snapshot = lambda: {snapshot_literal}; "
        "handled = cypherclaw_daemon.handle_builtin('/local'); "
        "print(json.dumps({'handled': handled, 'sent': sent}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["handled"] is True
    assert payload["sent"]
    text = payload["sent"][-1]
    assert "deepseek-r1:14b" in text
    assert "socket1" in text
    assert "unreachable" in text.lower()
