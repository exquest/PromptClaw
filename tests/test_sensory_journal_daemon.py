"""Regression tests for the sensory journal daemon."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest


TOOLS_PATH = Path(__file__).parent.parent / "my-claw" / "tools"


def test_module_import_is_side_effect_free() -> None:
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(TOOLS_PATH)!r})
        import sensory_journal_daemon as daemon
        expected = (
            "read_fused_state",
            "snapshot_from_state",
            "events_from_snapshots",
            "process_once",
            "run_daemon",
        )
        print(",".join(name for name in expected if hasattr(daemon, name)))
        """
    )

    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"sensory_journal_daemon import did not return: {exc}")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().split(",") == [
        "read_fused_state",
        "snapshot_from_state",
        "events_from_snapshots",
        "process_once",
        "run_daemon",
    ]


def _daemon_module() -> ModuleType:
    if str(TOOLS_PATH) not in sys.path:
        sys.path.insert(0, str(TOOLS_PATH))
    return importlib.import_module("sensory_journal_daemon")


def test_events_from_snapshots_reports_meaningful_transition_events() -> None:
    daemon = _daemon_module()
    previous = daemon.snapshot_from_state({"organism_mood": {"energy": 0.5}})
    current = daemon.snapshot_from_state(
        {
            "theramini": {"playing": True, "pitch": "A4"},
            "room": {"transient": True, "activity": "active"},
            "organism_mood": {"energy": 0.82, "valence": 0.6},
        }
    )

    events = daemon.events_from_snapshots(current, previous)

    assert [event.event_type for event in events] == [
        "theramini_start",
        "room_transient",
        "mood_shift",
    ]
    assert events[0].sensor_source == "theramini"
    assert "Theramini" in events[0].description
    assert "A4" in events[0].description
    assert events[1].sensor_source == "room"
    assert "active" in events[1].description
    assert events[2].sensor_source == "organism_mood"
    assert events[2].mood == {"energy": 0.82}
    assert "0.50" in events[2].description
    assert "0.82" in events[2].description


def test_process_once_reads_fused_state_and_appends_meaningful_events(tmp_path: Path) -> None:
    daemon = _daemon_module()
    fused_path = tmp_path / "organism_state.json"
    journal_path = tmp_path / "sensory_journal.jsonl"
    fused_path.write_text(
        json.dumps(
            {
                "theramini": {"playing": True, "pitch": "C#5"},
                "room": {"transient": True, "activity": "moderate"},
                "organism_mood": {"energy": 0.83, "arousal": 0.7},
            }
        ),
        encoding="utf-8",
    )
    previous = daemon.snapshot_from_state({"organism_mood": {"energy": 0.45}})

    snapshot, written = daemon.process_once(
        fused_path=fused_path,
        journal_path=journal_path,
        previous=previous,
    )

    assert snapshot.theramini_playing is True
    assert snapshot.theramini_pitch == "C#5"
    assert snapshot.room_activity == "moderate"
    assert snapshot.energy == 0.83
    assert [entry.event_type for entry in written] == [
        "theramini_start",
        "room_transient",
        "mood_shift",
    ]

    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert [record["event_type"] for record in records] == [
        "theramini_start",
        "room_transient",
        "mood_shift",
    ]
    assert records[0]["sensor_source"] == "theramini"
    assert records[0]["description"] == "Theramini started playing near C#5."
    assert records[1]["description"] == "Room transient detected during moderate activity."
    assert records[2]["mood_snapshot"] == {"energy": 0.83}


def test_run_daemon_carries_previous_snapshot_between_cycles(tmp_path: Path) -> None:
    daemon = _daemon_module()
    fused_path = tmp_path / "organism_state.json"
    journal_path = tmp_path / "sensory_journal.jsonl"
    fused_path.write_text(
        json.dumps(
            {
                "theramini": {"playing": True, "pitch": "G4"},
                "room": {"transient": True, "activity": "active"},
                "organism_mood": {"energy": 0.8},
            }
        ),
        encoding="utf-8",
    )

    daemon.run_daemon(
        interval=0.0,
        max_iterations=2,
        fused_path=fused_path,
        journal_path=journal_path,
    )

    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert [record["event_type"] for record in records] == [
        "theramini_start",
        "room_transient",
        "mood_shift",
    ]
