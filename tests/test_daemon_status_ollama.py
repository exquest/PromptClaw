"""Tests for ollama_health() integration in /status and heartbeat."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import cypherclaw_daemon
import server_health


# ── Fixtures ─────────────────────────────────────────────────


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


def _both_down_ollama() -> dict[str, object]:
    return {
        "healthy": False,
        "instances": [
            {
                "socket": "socket0",
                "port": 11434,
                "healthy": False,
                "status": "unreachable",
                "models": [],
                "latency_ms": None,
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


def _stub_common(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub shared dependencies; return the sent-messages list."""
    sent: list[str] = []
    monkeypatch.setattr(cypherclaw_daemon, "tg_send", sent.append)
    monkeypatch.setattr(
        cypherclaw_daemon,
        "state",
        SimpleNamespace(
            tasks={"t1": {"status": "running"}},
            schedules=[{"enabled": True}],
            conversation=["hi"],
        ),
    )
    monkeypatch.setattr(cypherclaw_daemon, "list_artifacts", lambda: ["a.txt"])
    monkeypatch.setattr(cypherclaw_daemon, "pet_manager", SimpleNamespace(pets={}))
    return sent


def _stub_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub heartbeat-specific deps (server_health, queue, agents, pets)."""
    monkeypatch.setattr(
        server_health,
        "check_health",
        lambda: {
            "healthy": True,
            "checks": {
                "uptime": "up 3 hours",
                "io_wait": "2%",
                "memory": "50% used (2048MB free)",
                "load": "1.0 / 0.8 / 0.6 (8 cores)",
            },
            "warnings": [],
            "actions_taken": [],
        },
    )
    monkeypatch.setattr(
        cypherclaw_daemon,
        "_root_queue_counts",
        lambda: {
            "total": 5,
            "complete": 2,
            "running": 1,
            "pending": 1,
            "needs_split": 0,
            "blocked": 1,
            "needs_attention": 0,
            "skipped": 0,
            "frozen": 0,
        },
    )
    monkeypatch.setattr(cypherclaw_daemon, "_available_agents", lambda agents: ["claude"])
    monkeypatch.setattr(
        cypherclaw_daemon.CypherClawArt,
        "pet_xp_summary",
        staticmethod(lambda pets: "🐾 Pet Status\n  idle"),
    )
    monkeypatch.setattr(cypherclaw_daemon, "pet_manager", SimpleNamespace(pets={}))


# ── /status command tests ────────────────────────────────────


def test_status_command_includes_ollama_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1: /status output includes per-socket Ollama health info."""
    sent = _stub_common(monkeypatch)
    monkeypatch.setattr(cypherclaw_daemon, "ollama_health", _healthy_ollama)

    cypherclaw_daemon.handle_builtin("/status")

    assert len(sent) == 1
    text = sent[0]
    # Must mention ollama / local model status
    assert "socket0" in text.lower() or "ollama" in text.lower()
    assert "deepseek-r1:14b" in text
    assert "unreachable" in text.lower()


def test_status_command_both_sockets_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both sockets are down, /status should reflect that."""
    sent = _stub_common(monkeypatch)
    monkeypatch.setattr(cypherclaw_daemon, "ollama_health", _both_down_ollama)

    cypherclaw_daemon.handle_builtin("/status")

    assert len(sent) == 1
    text = sent[0]
    assert "unreachable" in text.lower()


# ── Heartbeat payload tests ─────────────────────────────────


def test_heartbeat_payload_includes_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2: heartbeat payload dict contains 'ollama' key."""
    _stub_heartbeat(monkeypatch)
    monkeypatch.setattr(cypherclaw_daemon, "ollama_health", _healthy_ollama)

    _text, payload = cypherclaw_daemon.format_half_hour_heartbeat(
        datetime(2026, 4, 8, 15, 0),
    )

    assert "ollama" in payload
    assert payload["ollama"]["healthy"] is True
    assert len(payload["ollama"]["instances"]) == 2


def test_heartbeat_text_includes_ollama_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3: heartbeat text includes an Ollama summary line."""
    _stub_heartbeat(monkeypatch)
    monkeypatch.setattr(cypherclaw_daemon, "ollama_health", _healthy_ollama)

    text, _payload = cypherclaw_daemon.format_half_hour_heartbeat(
        datetime(2026, 4, 8, 15, 0),
    )

    # Should contain ollama status and a model name
    lower = text.lower()
    assert "ollama" in lower
    assert "deepseek-r1:14b" in text


def test_heartbeat_text_both_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When both sockets are down, heartbeat text should indicate that."""
    _stub_heartbeat(monkeypatch)
    monkeypatch.setattr(cypherclaw_daemon, "ollama_health", _both_down_ollama)

    text, payload = cypherclaw_daemon.format_half_hour_heartbeat(
        datetime(2026, 4, 8, 15, 0),
    )

    assert payload["ollama"]["healthy"] is False
    lower = text.lower()
    assert "ollama" in lower


# ── Graceful degradation tests ───────────────────────────────


def test_status_degrades_on_ollama_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: /status does not crash when ollama_health() raises."""
    sent = _stub_common(monkeypatch)

    def _boom() -> dict[str, object]:
        raise ConnectionError("ollama socket refused")

    monkeypatch.setattr(cypherclaw_daemon, "ollama_health", _boom)

    # Must not raise
    cypherclaw_daemon.handle_builtin("/status")

    assert len(sent) == 1
    # Should show some fallback text rather than a traceback
    lower = sent[0].lower()
    assert "ollama" in lower or "unavailable" in lower


def test_heartbeat_degrades_on_ollama_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Heartbeat does not crash when ollama_health() raises."""
    _stub_heartbeat(monkeypatch)

    def _boom() -> dict[str, object]:
        raise ConnectionError("ollama socket refused")

    monkeypatch.setattr(cypherclaw_daemon, "ollama_health", _boom)

    text, payload = cypherclaw_daemon.format_half_hour_heartbeat(
        datetime(2026, 4, 8, 15, 0),
    )

    assert "ollama" in payload
    assert payload["ollama"]["healthy"] is False
    assert "ollama" in text.lower() or "unavailable" in text.lower()
