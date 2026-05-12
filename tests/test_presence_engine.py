"""Tests for the canonical presence engine."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from presence_engine import resolve_presence_state, run_presence_loop


def _empty_inputs() -> dict:
    return {
        "room_presence": {},
        "observer": {},
        "room_activity": {},
        "room_speech": {},
        "theramini": {},
        "midi": {},
        "input_levels": {},
        "direct_interaction": {},
    }


def test_direct_interaction_marks_active_presence_and_performance() -> None:
    inputs = _empty_inputs()
    inputs["theramini"] = {"is_playing": True}

    state = resolve_presence_state(
        inputs,
        previous_state={},
        now=1_000.0,
        hour=14,
    )

    assert state["occupancy_state"] == "occupied_active"
    assert state["attention_state"] == "performance"
    assert state["last_reliable_presence_at"] == 1_000.0
    assert state["last_direct_interaction_at"] == 1_000.0


def test_recent_presence_holds_quiet_before_away_timeout() -> None:
    previous_state = {
        "occupancy_state": "occupied_active",
        "last_reliable_presence_at": 1_000.0,
        "last_direct_interaction_at": 1_000.0,
    }

    state = resolve_presence_state(
        _empty_inputs(),
        previous_state=previous_state,
        now=1_110.0,
        hour=15,
    )

    assert state["occupancy_state"] == "occupied_quiet"
    assert state["confidence"] > 0.0


def test_away_requires_full_five_minute_gap() -> None:
    previous_state = {
        "occupancy_state": "occupied_quiet",
        "last_reliable_presence_at": 1_000.0,
        "last_direct_interaction_at": 950.0,
    }

    state = resolve_presence_state(
        _empty_inputs(),
        previous_state=previous_state,
        now=1_301.0,
        hour=15,
    )

    assert state["occupancy_state"] == "likely_away"
    assert state["attention_state"] == "ambient"


def test_quiet_night_with_recent_home_presence_becomes_likely_asleep() -> None:
    previous_state = {
        "occupancy_state": "occupied_quiet",
        "last_reliable_presence_at": 2_000.0,
        "last_direct_interaction_at": 1_950.0,
    }

    state = resolve_presence_state(
        _empty_inputs(),
        previous_state=previous_state,
        now=3_500.0,
        hour=1,
    )

    assert state["occupancy_state"] == "likely_asleep"
    assert state["confidence"] >= 0.4


def test_weak_conflicting_signals_fail_safe_to_occupied_quiet() -> None:
    inputs = _empty_inputs()
    inputs["observer"] = {"ok": True, "someone_here": True}
    previous_state = {
        "occupancy_state": "occupied_quiet",
        "last_reliable_presence_at": 5_000.0,
        "last_direct_interaction_at": 4_800.0,
    }

    state = resolve_presence_state(
        inputs,
        previous_state=previous_state,
        now=5_120.0,
        hour=20,
    )

    assert state["occupancy_state"] == "occupied_quiet"
    assert state["attention_state"] == "ambient"


def test_all_stale_sources_fail_safe_to_occupied_quiet_not_away() -> None:
    inputs = _empty_inputs()
    for key in inputs:
        inputs[key] = {"_fresh": False}

    state = resolve_presence_state(
        inputs,
        previous_state={},
        now=6_000.0,
        hour=20,
    )

    assert state["occupancy_state"] == "occupied_quiet"
    assert "presence sources stale" in " ".join(state["reasons"])


def test_all_stale_sources_at_night_keep_recent_home_as_asleep() -> None:
    inputs = _empty_inputs()
    for key in inputs:
        inputs[key] = {"_fresh": False}

    state = resolve_presence_state(
        inputs,
        previous_state={
            "occupancy_state": "occupied_quiet",
            "last_reliable_presence_at": 7_000.0,
        },
        now=8_400.0,
        hour=1,
    )

    assert state["occupancy_state"] == "likely_asleep"


def test_error_only_sources_do_not_unlock_away_mode() -> None:
    inputs = _empty_inputs()
    for key in inputs:
        inputs[key] = {"_fresh": False}
    inputs["room_speech"] = {"_fresh": True, "error": "capture_failed", "speech_detected": False}

    state = resolve_presence_state(
        inputs,
        previous_state={},
        now=9_000.0,
        hour=21,
    )

    assert state["occupancy_state"] == "occupied_quiet"


def test_wind_down_with_recent_home_presence_holds_quiet_occupancy() -> None:
    state = resolve_presence_state(
        _empty_inputs(),
        previous_state={
            "occupancy_state": "occupied_quiet",
            "last_reliable_presence_at": 10_000.0,
        },
        now=10_900.0,
        hour=22,
    )

    assert state["occupancy_state"] == "occupied_quiet"
    assert "wind-down home memory" in " ".join(state["reasons"])


def test_late_night_away_still_applies_without_recent_home_presence() -> None:
    state = resolve_presence_state(
        _empty_inputs(),
        previous_state={
            "occupancy_state": "likely_away",
            "last_reliable_presence_at": 10_000.0,
        },
        now=11_900.0,
        hour=22,
    )

    assert state["occupancy_state"] == "likely_away"


def test_contact_mic_loudness_alone_does_not_prevent_away() -> None:
    inputs = _empty_inputs()
    inputs["room_activity"] = {"_fresh": True, "activity_level": "loud", "recent_transient": False}

    state = resolve_presence_state(
        inputs,
        previous_state={
            "occupancy_state": "likely_away",
            "last_reliable_presence_at": 12_000.0,
        },
        now=12_600.0,
        hour=14,
    )

    assert state["occupancy_state"] == "likely_away"


def test_run_presence_loop_writes_presence_state(monkeypatch, tmp_path: Path) -> None:
    room_presence = tmp_path / "room_presence.json"
    room_presence.write_text(json.dumps({"someone_here": True, "motion": True}))
    room_activity = tmp_path / "room_activity.json"
    room_activity.write_text(json.dumps({"activity_level": "moderate", "recent_transient": True}))
    room_speech = tmp_path / "room_speech.json"
    room_speech.write_text(json.dumps({"speech_detected": False}))
    theramini = tmp_path / "theramini_state.json"
    theramini.write_text(json.dumps({"is_playing": False}))
    midi = tmp_path / "midi_state.json"
    midi.write_text(json.dumps({"playing": False}))
    observer = tmp_path / "observer_state.json"
    observer.write_text(json.dumps({"ok": True, "someone_here": False}))
    input_levels = tmp_path / "input_levels.json"
    input_levels.write_text(json.dumps({"contact_rms": 0.0}))
    output = tmp_path / "presence_state.json"

    monkeypatch.setattr("presence_engine.ROOM_PRESENCE_STATE", str(room_presence))
    monkeypatch.setattr("presence_engine.ROOM_ACTIVITY_STATE", str(room_activity))
    monkeypatch.setattr("presence_engine.ROOM_SPEECH_STATE", str(room_speech))
    monkeypatch.setattr("presence_engine.THERAMINI_STATE", str(theramini))
    monkeypatch.setattr("presence_engine.MIDI_STATE", str(midi))
    monkeypatch.setattr("presence_engine.OBSERVER_STATE", str(observer))
    monkeypatch.setattr("presence_engine.INPUT_LEVELS_STATE", str(input_levels))
    monkeypatch.setattr("presence_engine.DEFAULT_OUTPUT", str(output))

    run_presence_loop(interval=0.0, max_iterations=1)

    written = json.loads(output.read_text())
    assert written["occupancy_state"] == "occupied_active"
    assert written["signals"]["room_motion"] is True
