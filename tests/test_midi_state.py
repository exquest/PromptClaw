"""Tests for midi_state.py — MIDI input state tracker for CypherClaw installation."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

from midi_state import MidiState, note_to_name, name_to_note


# === MidiState init ===


class TestMidiStateInit:
    def test_initial_state(self):
        ms = MidiState()
        assert ms.notes_on == set()
        assert ms.last_note is None
        assert ms.last_velocity == 0
        assert ms.sustain_pedal is False
        assert ms.pitch_bend == 8192
        assert ms.mod_wheel == 0
        assert ms.activity_rate == 0.0


# === note_on / note_off ===


class TestNoteOnOff:
    def test_note_on_adds_to_set(self):
        ms = MidiState()
        ms.note_on(60, 100)
        assert 60 in ms.notes_on
        assert ms.last_note == 60
        assert ms.last_velocity == 100

    def test_multiple_notes_on(self):
        ms = MidiState()
        ms.note_on(60, 80)
        ms.note_on(64, 90)
        ms.note_on(67, 70)
        assert ms.notes_on == {60, 64, 67}
        assert ms.last_note == 67
        assert ms.last_velocity == 70

    def test_note_off_removes_from_set(self):
        ms = MidiState()
        ms.note_on(60, 100)
        ms.note_on(64, 90)
        ms.note_off(60)
        assert 60 not in ms.notes_on
        assert 64 in ms.notes_on

    def test_note_off_nonexistent_is_safe(self):
        ms = MidiState()
        ms.note_off(60)  # Should not raise
        assert ms.notes_on == set()

    def test_note_on_zero_velocity_acts_as_off(self):
        ms = MidiState()
        ms.note_on(60, 100)
        ms.note_on(60, 0)
        assert 60 not in ms.notes_on

    def test_last_note_persists_after_off(self):
        ms = MidiState()
        ms.note_on(60, 100)
        ms.note_off(60)
        assert ms.last_note == 60


# === control_change ===


class TestControlChange:
    def test_mod_wheel_cc1(self):
        ms = MidiState()
        ms.control_change(1, 64)
        assert ms.mod_wheel == 64

    def test_sustain_on_cc64(self):
        ms = MidiState()
        ms.control_change(64, 127)
        assert ms.sustain_pedal is True

    def test_sustain_off_cc64(self):
        ms = MidiState()
        ms.control_change(64, 127)
        ms.control_change(64, 0)
        assert ms.sustain_pedal is False

    def test_sustain_threshold(self):
        ms = MidiState()
        ms.control_change(64, 63)
        assert ms.sustain_pedal is False
        ms.control_change(64, 64)
        assert ms.sustain_pedal is True

    def test_volume_cc7(self):
        ms = MidiState()
        ms.control_change(7, 100)
        # volume is tracked but as a CC value
        state = ms.to_dict()
        assert state.get("volume", 100) == 100

    def test_unknown_cc_does_not_crash(self):
        ms = MidiState()
        ms.control_change(99, 42)  # Should not raise


# === pitch_bend_change ===


class TestPitchBend:
    def test_pitch_bend_change(self):
        ms = MidiState()
        ms.pitch_bend_change(16383)
        assert ms.pitch_bend == 16383

    def test_pitch_bend_center(self):
        ms = MidiState()
        ms.pitch_bend_change(8192)
        assert ms.pitch_bend == 8192

    def test_pitch_bend_zero(self):
        ms = MidiState()
        ms.pitch_bend_change(0)
        assert ms.pitch_bend == 0


# === activity_rate ===


class TestActivityRate:
    def test_activity_rate_increases_with_notes(self):
        ms = MidiState()
        # Simulate rapid playing
        for i in range(10):
            ms.note_on(60 + i, 100)
        assert ms.activity_rate > 0.0

    def test_activity_rate_zero_initially(self):
        ms = MidiState()
        assert ms.activity_rate == 0.0


# === to_dict / from_dict ===


class TestSerialization:
    def test_round_trip(self):
        ms = MidiState()
        ms.note_on(60, 100)
        ms.note_on(64, 80)
        ms.control_change(1, 42)
        ms.control_change(64, 127)
        ms.pitch_bend_change(10000)

        d = ms.to_dict()
        ms2 = MidiState.from_dict(d)

        assert ms2.notes_on == {60, 64}
        assert ms2.last_note == 64
        assert ms2.last_velocity == 80
        assert ms2.mod_wheel == 42
        assert ms2.sustain_pedal is True
        assert ms2.pitch_bend == 10000

    def test_to_dict_keys(self):
        ms = MidiState()
        d = ms.to_dict()
        assert "notes_on" in d
        assert "last_note" in d
        assert "last_velocity" in d
        assert "sustain_pedal" in d
        assert "pitch_bend" in d
        assert "mod_wheel" in d
        assert "activity_rate" in d

    def test_to_dict_notes_on_is_list(self):
        ms = MidiState()
        ms.note_on(60, 100)
        d = ms.to_dict()
        # JSON-serializable: notes_on should be a list
        assert isinstance(d["notes_on"], list)

    def test_from_dict_empty(self):
        ms = MidiState.from_dict({})
        assert ms.notes_on == set()
        assert ms.last_note is None

    def test_from_dict_returns_midi_state(self):
        ms = MidiState.from_dict({"notes_on": [60, 64], "last_note": 64})
        assert isinstance(ms, MidiState)
        assert ms.notes_on == {60, 64}


# === note_to_name / name_to_note ===


class TestNoteNaming:
    def test_c4(self):
        assert note_to_name(60) == "C4"

    def test_a4(self):
        assert note_to_name(69) == "A4"

    def test_c_neg1(self):
        assert note_to_name(0) == "C-1"

    def test_g9(self):
        assert note_to_name(127) == "G9"

    def test_middle_c_sharp(self):
        assert note_to_name(61) == "C#4"

    def test_b3(self):
        assert note_to_name(59) == "B3"

    def test_f_sharp_2(self):
        assert note_to_name(42) == "F#2"

    def test_name_to_note_c4(self):
        assert name_to_note("C4") == 60

    def test_name_to_note_a4(self):
        assert name_to_note("A4") == 69

    def test_name_to_note_c_sharp_4(self):
        assert name_to_note("C#4") == 61

    def test_name_to_note_b3(self):
        assert name_to_note("B3") == 59

    def test_name_to_note_c_neg1(self):
        assert name_to_note("C-1") == 0

    def test_name_to_note_g9(self):
        assert name_to_note("G9") == 127

    def test_round_trip_all_notes(self):
        for note in range(128):
            name = note_to_name(note)
            assert name_to_note(name) == note

    def test_name_to_note_flat_alias(self):
        # Db4 should equal C#4
        assert name_to_note("Db4") == 61

    def test_name_to_note_bb3(self):
        assert name_to_note("Bb3") == 58
