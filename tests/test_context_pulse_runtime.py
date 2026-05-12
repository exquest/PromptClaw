"""Tests for the CypherClaw context pulse helper."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import context_pulse


def test_pulse_summarizes_runtime_state_and_records_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools_dir = tmp_path / "tools"
    workspace_dir = tools_dir / "workspace"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "artifact.txt").write_text("hello")

    state_file = tools_dir / ".daemon_state.json"
    state_file.write_text(json.dumps({"conversation": [{"role": "user", "text": "hi claw"}]}))

    selector_state = tools_dir / ".agent_selector_state.json"
    selector_state.write_text(json.dumps({"last_lead": "codex", "last_lead_provider": "openai", "task_count": 9}))

    pets_file = tmp_path / "pets.json"
    pets_file.write_text(json.dumps({"pets": {"codex": {"stage": 2, "xp": 77, "mood": 88}}}))

    observatory_db = tmp_path / "observatory.db"
    conn = sqlite3.connect(observatory_db)
    conn.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, timestamp TEXT NOT NULL, data TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO events (event_type, timestamp, data) VALUES (?, ?, ?)",
        ("user_message", "2026-04-01T00:00:00+00:00", '{"text":"hello"}'),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(context_pulse, "TOOLS_DIR", tools_dir)
    monkeypatch.setattr(context_pulse, "WORKSPACE_DIR", workspace_dir)
    monkeypatch.setattr(context_pulse, "STATE_FILE", state_file)
    monkeypatch.setattr(context_pulse, "OBSERVATORY_DB", observatory_db)
    monkeypatch.setattr(context_pulse, "SELECTOR_STATE", selector_state)
    monkeypatch.setattr(context_pulse, "PETS_FILE", pets_file)

    pulse = context_pulse.pulse()

    assert "🔮 CONTEXT PULSE" in pulse
    assert "Conversation Memory: 1 messages" in pulse
    assert "Workspace: 1 artifacts" in pulse
    assert "Observatory: 1 total events" in pulse
    assert "Last lead: codex" in pulse
    assert "Pets: 1 agents" in pulse
    assert "Intelligence footprint:" in pulse

    conn = sqlite3.connect(observatory_db)
    row = conn.execute(
        "SELECT event_type, data FROM events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    assert row == ("context_pulse", '{"source": "pulse_command"}')
