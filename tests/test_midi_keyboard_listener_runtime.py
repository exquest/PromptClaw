"""Tests for midi_keyboard_listener.py -- device discovery, state, and capture."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

import midi_keyboard_listener
from senseweave.phrase_capture import validate_sample_metadata
from senseweave.phrase_capture_runtime import ActiveSongPhraseCapture  # type: ignore[import-not-found]
from senseweave.midi_state import MidiState
from senseweave.phrase_tracker import PhraseTracker


def test_discover_keyboard_devices_prefers_named_keyboards() -> None:
    listing = """
Dir Device    Name
IO  hw:0,0,0  Scarlett 4i4 USB MIDI 1
IO  hw:4,0,0  Akai MAX25 Port A
IO  hw:4,0,1  Akai MAX25 Port B
IO  hw:6,0,0  microKEY-25 _ KEYBOARD
IO  hw:8,0,0  Moog Theremini Moog Music, Inc.
"""
    assert midi_keyboard_listener.discover_keyboard_devices(listing) == [
        "/dev/midi4",
        "/dev/midi6",
    ]


def test_apply_midi_message_tracks_notes_and_controls() -> None:
    midi_state = MidiState()
    active_notes: dict[int, dict[str, float | int | str]] = {}
    recent_pedal_events: list[tuple[float, bool]] = []
    last_activity = 0.0

    for when, (status, data1, data2) in (
        (100.0, (0x90, 69, 100)),
        (100.1, (0x90, 72, 96)),
        (100.2, (0x90, 76, 92)),
        (100.3, (0xB0, 64, 127)),
        (100.4, (0xB0, 11, 110)),
    ):
        last_activity = midi_keyboard_listener.apply_midi_message(
            midi_state,
            active_notes,
            recent_pedal_events,
            status=status,
            data1=data1,
            data2=data2,
            now=when,
            last_activity=last_activity,
        )

    state = midi_keyboard_listener.build_state(
        midi_state,
        active_notes,
        recent_pedal_events,
        last_activity=last_activity,
        now=100.5,
    )

    assert state["playing"] is True
    assert state["notes"] == ["A4", "C5", "E5"]
    assert state["sustain_pedal"] is True
    assert state["expression"] == 110
    assert state["suggested_key"] == "A:harmonic_minor"
    assert state["modulation_intent"] == "steady"
    assert state["chord_palette"] == "extended"
    assert state["last_activity"] == 100.4


def test_build_state_drops_stale_notes_from_serialized_notes_on() -> None:
    midi_state = MidiState()
    midi_state.note_on(55, 127)
    active_notes: dict[int, dict[str, float | int | str]] = {
        55: {
            "freq": midi_keyboard_listener.midi_to_freq(55),
            "name": "G3",
            "velocity": 127,
            "time": 10.0,
        }
    }

    state = midi_keyboard_listener.build_state(
        midi_state,
        active_notes,
        [],
        last_activity=12.0,
        now=20.5,
    )

    assert state["playing"] is False
    assert state["notes_on"] == []
    assert state["notes"] == []


def test_build_state_emits_phrase_event_after_5s_of_continuous_play() -> None:
    midi_state = MidiState()
    tracker = PhraseTracker()

    midi_state.note_on(60, 100)
    active_notes: dict[int, dict[str, float | int | str]] = {
        60: {
            "freq": midi_keyboard_listener.midi_to_freq(60),
            "name": "C4",
            "velocity": 100,
            "time": 1000.0,
        }
    }

    # First tick: starts the play timer at t=1000.
    midi_keyboard_listener.build_state(
        midi_state,
        active_notes,
        [],
        last_activity=1000.0,
        now=1000.0,
        phrase_tracker=tracker,
    )

    early = midi_keyboard_listener.build_state(
        midi_state,
        active_notes,
        [],
        last_activity=1000.0,
        now=1003.0,
        phrase_tracker=tracker,
    )
    assert "phrase_event" not in early
    assert early["phrase_active"] is False

    crossed = midi_keyboard_listener.build_state(
        midi_state,
        active_notes,
        [],
        last_activity=1000.0,
        now=1005.0,
        phrase_tracker=tracker,
    )
    assert crossed["phrase_event"] == "phrase_started"
    assert crossed["phrase_active"] is True
    assert crossed["phrase_duration_seconds"] == 5.0

    midi_state.note_off(60)
    active_notes.clear()
    ended = midi_keyboard_listener.build_state(
        midi_state,
        active_notes,
        [],
        last_activity=1006.0,
        now=1006.0,
        phrase_tracker=tracker,
    )
    assert ended["phrase_event"] == "phrase_ended"
    assert ended["phrase_active"] is False


def test_capture_phrase_writes_keyboard_phrase_during_active_song(tmp_path: Path) -> None:
    composer_state = tmp_path / "composer_state.json"
    composer_state.write_text(
        json.dumps(
            {
                "song": 7,
                "key": "Dm",
                "tempo": 96,
                "updated": 100.0,
            }
        )
    )
    capture = ActiveSongPhraseCapture(
        "keyboard",
        capture_root=tmp_path,
        composer_state_path=composer_state,
        active_song_max_age_seconds=999.0,
    )

    stream = [
        (bytes([0x90, 60, 100]), {"playing": True, "timestamp": 100.0}),
        (None, {"playing": True, "timestamp": 103.0}),
        (None, {"playing": True, "timestamp": 105.0}),
        (bytes([0x80, 60, 0]), {"playing": False, "timestamp": 106.0}),
    ]

    written = None
    for chunk, state in stream:
        written = midi_keyboard_listener.capture_phrase_from_state(
            capture,
            chunk=chunk,
            state=state,
        )

    assert written is not None
    assert written.parent == tmp_path / "keyboard"
    assert written.suffix == ".mid"

    meta = json.loads(written.with_suffix(".json").read_text())
    validate_sample_metadata(meta)
    assert meta["instrument"] == "midi_keyboard"
    assert meta["song_id"] == "7"
    assert meta["key"] == "Dm"
    assert meta["tempo"] == 96
