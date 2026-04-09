"""Tests for the CypherClaw scheduler heartbeat."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import cypherclaw_daemon
import server_health


def test_format_half_hour_heartbeat_includes_required_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_health,
        "check_health",
        lambda: {
            "healthy": True,
            "checks": {
                "uptime": "up 2 hours",
                "io_wait": "3%",
                "memory": "42% used (1234MB free)",
                "load": "0.4 / 0.3 / 0.2 (8 cores)",
            },
            "warnings": [],
            "actions_taken": [],
        },
    )
    monkeypatch.setattr(
        cypherclaw_daemon,
        "_root_queue_counts",
        lambda: {
            "total": 10,
            "complete": 4,
            "running": 1,
            "pending": 4,
            "needs_split": 0,
            "blocked": 1,
            "needs_attention": 0,
            "skipped": 2,
            "frozen": 1,
        },
    )
    monkeypatch.setattr(cypherclaw_daemon, "_available_agents", lambda agents: ["codex", "gemini"])
    monkeypatch.setattr(
        cypherclaw_daemon.CypherClawArt,
        "pet_xp_summary",
        staticmethod(lambda pets: "🐾 Pet Status\n  🟢 codex · Adult · XP 100 · 😊80 💤"),
    )
    monkeypatch.setattr(cypherclaw_daemon, "pet_manager", SimpleNamespace(pets={}))
    monkeypatch.setenv("CYPHERCLAW_GALLERY_URL", "http://cypherclaw:8080")

    text, payload = cypherclaw_daemon.format_half_hour_heartbeat(datetime(2026, 4, 1, 14, 30))

    assert "CypherClaw Heartbeat" in text
    assert "Uptime: up 2 hours" in text
    assert "I/O: 3%" in text
    assert "Memory: 42% used" in text
    assert "Load: 0.4 / 0.3 / 0.2 (8 cores)" in text
    assert "Agents: 2/3 available (codex, gemini)" in text
    assert "SDP: 4/10 complete (40%) · 4 pending · 1 blocked · 1 running · 1 frozen" in text
    assert "Split parents: 2" in text
    assert "Pet Status" in text
    assert "Gallery: http://cypherclaw:8080" in text
    assert payload["slot"] == "2026-04-01-14-30"
    assert payload["agent_count"] == 2
    assert payload["gallery_url"] == "http://cypherclaw:8080"


def test_scheduler_sends_half_hour_heartbeat_once_per_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_messages: list[str] = []
    events: list[tuple[str, dict[str, object]]] = []
    rollups: list[str] = []

    monkeypatch.setattr(
        server_health,
        "check_health",
        lambda: {
            "healthy": True,
            "checks": {
                "uptime": "up 1 day",
                "io_wait": "1%",
                "memory": "20% used (800MB free)",
                "load": "0.2 / 0.1 / 0.1 (8 cores)",
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
            "complete": 1,
            "running": 1,
            "pending": 2,
            "needs_split": 0,
            "blocked": 1,
            "needs_attention": 0,
            "skipped": 0,
            "frozen": 0,
        },
    )
    monkeypatch.setattr(cypherclaw_daemon, "_available_agents", lambda agents: ["claude", "codex", "gemini"])
    monkeypatch.setattr(
        cypherclaw_daemon.CypherClawArt,
        "pet_xp_summary",
        staticmethod(lambda pets: "🐾 Pet Status\n  🦀 cypherclaw · Adult · XP 50 · 😊70 💤"),
    )
    monkeypatch.setattr(cypherclaw_daemon, "pet_manager", SimpleNamespace(pets={}))
    monkeypatch.setattr(cypherclaw_daemon, "tg_send", sent_messages.append)
    monkeypatch.setattr(
        cypherclaw_daemon,
        "observatory",
        SimpleNamespace(
            rollup_daily=lambda: rollups.append("daily"),
            record=lambda event, data: events.append((event, data)),
        ),
    )
    _ollama_stub = {
        "healthy": False,
        "instances": [
            {"socket": "socket0", "port": 11434, "healthy": False, "status": "unreachable", "models": [], "latency_ms": None},
            {"socket": "socket1", "port": 11435, "healthy": False, "status": "unreachable", "models": [], "latency_ms": None},
        ],
    }
    monkeypatch.setattr(cypherclaw_daemon, "ollama_health", lambda: _ollama_stub)

    scheduler = cypherclaw_daemon.Scheduler()
    slot_time = datetime(2026, 4, 1, 14, 30)

    scheduler._run_time_based_reviews(slot_time)
    scheduler._run_time_based_reviews(slot_time)
    scheduler._run_time_based_reviews(datetime(2026, 4, 1, 14, 31))

    assert rollups == ["daily"]
    assert len(sent_messages) == 1
    assert "CypherClaw Heartbeat" in sent_messages[0]
    assert events == [
        (
            "half_hour_heartbeat_sent",
                {
                    "slot": "2026-04-01-14-30",
                    "complete": 1,
                    "total": 5,
                    "pending": 2,
                    "needs_split": 0,
                    "blocked": 1,
                    "running": 1,
                    "skipped": 0,
                    "frozen": 0,
                "percent": 20,
                "available_agents": ["claude", "codex", "gemini"],
                "agent_count": 3,
                "uptime": "up 1 day",
                "io_wait": "1%",
                "memory": "20% used (800MB free)",
                "load": "0.2 / 0.1 / 0.1 (8 cores)",
                "gallery_url": "",
                "ollama": _ollama_stub,
            },
        ),
    ]
