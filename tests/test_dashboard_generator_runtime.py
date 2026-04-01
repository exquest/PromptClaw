"""Tests for the CypherClaw dashboard generator."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import dashboard_generator


def _create_state_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE tasks (task_id TEXT, status TEXT)")
    conn.executemany(
        "INSERT INTO tasks (task_id, status) VALUES (?, ?)",
        [
            ("T-001", "complete"),
            ("T-002", "complete"),
            ("T-003", "running"),
            ("T-004", "pending"),
            ("T-005", "split"),
        ],
    )
    conn.commit()
    conn.close()


def _create_observatory_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, timestamp TEXT, data TEXT)")
    conn.executemany(
        "INSERT INTO events (event_type, timestamp, data) VALUES (?, ?, ?)",
        [
            ("routing_decision", "2026-04-01T12:00:00+00:00", '{"text":"route codex"}'),
            ("healing", "2026-04-01T12:05:00+00:00", '{"action_taken":"restart daemon"}'),
        ],
    )
    conn.commit()
    conn.close()


def test_get_pipeline_data_aggregates_running_pending_and_split(tmp_path: Path, monkeypatch) -> None:
    state_db = tmp_path / "state.db"
    _create_state_db(state_db)
    monkeypatch.setattr(dashboard_generator, "SDP_STATE_DB", state_db)

    result = dashboard_generator.get_pipeline_data()

    assert result == {
        "total": 5,
        "complete": 2,
        "percent": 40.0,
        "status": "▶️ Running",
    }


def test_get_event_data_formats_recent_events(tmp_path: Path, monkeypatch) -> None:
    observatory_db = tmp_path / "observatory.db"
    _create_observatory_db(observatory_db)
    monkeypatch.setattr(dashboard_generator, "OBSERVATORY_DB", observatory_db)

    events = dashboard_generator.get_event_data()

    assert len(events) == 2
    assert events[0]["type"] == "healing"
    assert events[0]["message"] == "restart daemon"
    assert events[1]["message"] == "route codex"


def test_generate_writes_dashboard_html(tmp_path: Path, monkeypatch) -> None:
    state_db = tmp_path / "state.db"
    observatory_db = tmp_path / "observatory.db"
    output_path = tmp_path / "dashboard.html"
    _create_state_db(state_db)
    _create_observatory_db(observatory_db)

    monkeypatch.setattr(dashboard_generator, "SDP_STATE_DB", state_db)
    monkeypatch.setattr(dashboard_generator, "OBSERVATORY_DB", observatory_db)
    monkeypatch.setattr(dashboard_generator, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(
        dashboard_generator,
        "check_health",
        lambda: {
            "healthy": True,
            "checks": {
                "load": "0.1 / 0.1 / 0.1",
                "memory": "20% used",
                "disk_usage": "25%",
                "temperature": "55C",
                "uptime": "up 2 hours",
                "daemon": "active",
                "postgresql": "active",
                "redis-server": "active",
                "nginx": "inactive",
                "docker": "active",
                "sdp-cli": "running",
                "ollama": "active",
            },
            "warnings": [],
        },
    )

    class FakePetManager:
        def get(self, agent: str) -> SimpleNamespace:
            return SimpleNamespace(stage=1, mood=90, hunger=10, energy=95, xp=123)

    monkeypatch.setattr(dashboard_generator, "PetManager", FakePetManager)
    monkeypatch.setattr(dashboard_generator, "STAGE_NAMES", {1: "Baby"})

    dashboard_generator.generate()

    html = output_path.read_text()
    assert "CypherClaw Status" in html
    assert "Pipeline Progress" in html
    assert "Recent Events" in html
    assert "CLAUDE (Baby)" in html
    assert "HEALING:" in html
