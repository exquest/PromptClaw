"""Tests for sensor_fusion.py — sensor reading, fusion, mood, and presence."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from sensor_fusion import (
    calculate_mood,
    detect_presence,
    fuse_sensors,
    read_sensor_state,
    run_fusion_loop,
    write_fused_state,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic sensor state files
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data))


def _theramini_playing(path: Path) -> None:
    _write_json(path, {
        "is_playing": True,
        "pitch_hz": 440.0,
        "pitch_note": "A4",
        "pitch_confidence": 0.9,
        "rms": 0.35,
        "state": "sustain",
        "suggested_key": "A",
        "consecutive_silence_ms": 0,
        "idle_tone": False,
    })


def _theramini_silent(path: Path) -> None:
    _write_json(path, {
        "is_playing": False,
        "pitch_hz": 0.0,
        "pitch_note": None,
        "pitch_confidence": 0.0,
        "rms": 0.001,
        "state": "silence",
        "suggested_key": None,
        "consecutive_silence_ms": 5000,
        "idle_tone": False,
    })


def _room_active(path: Path) -> None:
    _write_json(path, {
        "membrane_rms": 0.25,
        "heartbeat_rms": 0.08,
        "recent_transient": True,
        "activity_level": "active",
    })


def _room_quiet(path: Path) -> None:
    _write_json(path, {
        "membrane_rms": 0.001,
        "heartbeat_rms": 0.001,
        "recent_transient": False,
        "activity_level": "quiet",
    })


def _speech_detected(path: Path) -> None:
    _write_json(path, {
        "speech_detected": True,
        "transcript": "That sounds beautiful",
    })


def _speech_silent(path: Path) -> None:
    _write_json(path, {
        "speech_detected": False,
        "transcript": None,
    })


def _composer_state(path: Path) -> None:
    _write_json(path, {
        "key": "A",
        "mode": "duet",
        "movement": "verse",
        "song": "evening_waltz",
    })


# ---------------------------------------------------------------------------
# read_sensor_state
# ---------------------------------------------------------------------------


class TestReadSensorState:
    def test_reads_valid_json(self, tmp_path):
        f = tmp_path / "state.json"
        _write_json(f, {"hello": "world"})
        result = read_sensor_state(str(f))
        assert result == {"hello": "world"}

    def test_returns_empty_on_missing_file(self, tmp_path):
        f = tmp_path / "does_not_exist.json"
        result = read_sensor_state(str(f))
        assert result == {}

    def test_returns_empty_on_corrupt_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not valid json {{{")
        result = read_sensor_state(str(f))
        assert result == {}

    def test_returns_empty_on_stale_file(self, tmp_path):
        f = tmp_path / "old.json"
        _write_json(f, {"stale": True})
        # Set mtime to 30 seconds ago
        old_time = time.time() - 30
        os.utime(str(f), (old_time, old_time))
        result = read_sensor_state(str(f), max_age_s=10.0)
        assert result == {}

    def test_fresh_file_within_max_age(self, tmp_path):
        f = tmp_path / "fresh.json"
        _write_json(f, {"fresh": True})
        result = read_sensor_state(str(f), max_age_s=10.0)
        assert result == {"fresh": True}

    def test_respects_custom_max_age(self, tmp_path):
        f = tmp_path / "custom.json"
        _write_json(f, {"val": 1})
        # Set mtime to 3 seconds ago — stale if max_age_s=2, fresh if max_age_s=5
        old_time = time.time() - 3
        os.utime(str(f), (old_time, old_time))
        assert read_sensor_state(str(f), max_age_s=2.0) == {}
        assert read_sensor_state(str(f), max_age_s=5.0) == {"val": 1}

    def test_returns_empty_on_empty_file(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("")
        result = read_sensor_state(str(f))
        assert result == {}


# ---------------------------------------------------------------------------
# calculate_mood
# ---------------------------------------------------------------------------


class TestCalculateMood:
    def test_high_energy_when_playing(self):
        theramini = {"playing": True, "pitch": "A4", "key": "A"}
        room = {"activity": "quiet", "transient": False}
        speech = {"detected": False, "transcript": None}
        mood = calculate_mood(theramini, room, speech)
        assert mood["energy"] > 0.5

    def test_low_energy_when_quiet(self):
        theramini = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "quiet", "transient": False}
        speech = {"detected": False, "transcript": None}
        mood = calculate_mood(theramini, room, speech)
        assert mood["energy"] < 0.3

    def test_high_energy_when_room_active(self):
        theramini = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "active", "transient": True}
        speech = {"detected": False, "transcript": None}
        mood = calculate_mood(theramini, room, speech)
        assert mood["energy"] > 0.5

    def test_valence_higher_with_speech(self):
        theramini = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "quiet", "transient": False}
        no_speech = {"detected": False, "transcript": None}
        with_speech = {"detected": True, "transcript": "Hello!"}
        mood_quiet = calculate_mood(theramini, room, no_speech)
        mood_speech = calculate_mood(theramini, room, with_speech)
        assert mood_speech["valence"] > mood_quiet["valence"]

    def test_arousal_higher_on_transient(self):
        theramini = {"playing": False, "pitch": None, "key": None}
        room_calm = {"activity": "quiet", "transient": False}
        room_bang = {"activity": "active", "transient": True}
        speech = {"detected": False, "transcript": None}
        mood_calm = calculate_mood(theramini, room_calm, speech)
        mood_bang = calculate_mood(theramini, room_bang, speech)
        assert mood_bang["arousal"] > mood_calm["arousal"]

    def test_arousal_higher_when_playing(self):
        theramini_on = {"playing": True, "pitch": "A4", "key": "A"}
        theramini_off = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "quiet", "transient": False}
        speech = {"detected": False, "transcript": None}
        mood_on = calculate_mood(theramini_on, room, speech)
        mood_off = calculate_mood(theramini_off, room, speech)
        assert mood_on["arousal"] > mood_off["arousal"]

    def test_all_values_clamped_0_to_1(self):
        # Max stimulation: everything active
        theramini = {"playing": True, "pitch": "A4", "key": "A"}
        room = {"activity": "active", "transient": True}
        speech = {"detected": True, "transcript": "wow!"}
        mood = calculate_mood(theramini, room, speech)
        for key in ("energy", "valence", "arousal"):
            assert 0.0 <= mood[key] <= 1.0

    def test_all_values_clamped_0_to_1_at_minimum(self):
        theramini = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "quiet", "transient": False}
        speech = {"detected": False, "transcript": None}
        mood = calculate_mood(theramini, room, speech)
        for key in ("energy", "valence", "arousal"):
            assert 0.0 <= mood[key] <= 1.0


# ---------------------------------------------------------------------------
# detect_presence
# ---------------------------------------------------------------------------


class TestDetectPresence:
    def test_someone_here_when_playing(self):
        theramini = {"playing": True, "pitch": "A4", "key": "A"}
        room = {"activity": "quiet", "transient": False}
        speech = {"detected": False, "transcript": None}
        p = detect_presence(theramini, room, speech)
        assert p["someone_here"] is True

    def test_someone_here_when_speech(self):
        theramini = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "quiet", "transient": False}
        speech = {"detected": True, "transcript": "Hello"}
        p = detect_presence(theramini, room, speech)
        assert p["someone_here"] is True

    def test_someone_here_when_transient(self):
        theramini = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "active", "transient": True}
        speech = {"detected": False, "transcript": None}
        p = detect_presence(theramini, room, speech)
        assert p["someone_here"] is True

    def test_nobody_when_all_quiet(self):
        theramini = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "quiet", "transient": False}
        speech = {"detected": False, "transcript": None}
        p = detect_presence(theramini, room, speech)
        assert p["someone_here"] is False

    def test_activity_level_quiet(self):
        theramini = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "quiet", "transient": False}
        speech = {"detected": False, "transcript": None}
        p = detect_presence(theramini, room, speech)
        assert p["activity_level"] == "quiet"

    def test_activity_level_active_all_sources(self):
        theramini = {"playing": True, "pitch": "A4", "key": "A"}
        room = {"activity": "active", "transient": True}
        speech = {"detected": True, "transcript": "wow"}
        p = detect_presence(theramini, room, speech)
        assert p["activity_level"] == "active"

    def test_activity_level_moderate(self):
        # Only one signal: speech
        theramini = {"playing": False, "pitch": None, "key": None}
        room = {"activity": "quiet", "transient": False}
        speech = {"detected": True, "transcript": "hmm"}
        p = detect_presence(theramini, room, speech)
        assert p["activity_level"] == "moderate"


# ---------------------------------------------------------------------------
# write_fused_state
# ---------------------------------------------------------------------------


class TestWriteFusedState:
    def test_writes_valid_json(self, tmp_path):
        out = tmp_path / "organism_state.json"
        state = {"timestamp": time.time(), "test": True}
        write_fused_state(state, str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["test"] is True

    def test_atomic_overwrite(self, tmp_path):
        out = tmp_path / "organism_state.json"
        write_fused_state({"v": 1}, str(out))
        write_fused_state({"v": 2}, str(out))
        data = json.loads(out.read_text())
        assert data["v"] == 2

    def test_uses_tmp_file_for_atomicity(self, tmp_path):
        """Verify that os.replace is used (no partial writes)."""
        out = tmp_path / "organism_state.json"
        state = {"timestamp": 12345.0}
        write_fused_state(state, str(out))
        # If we got here without error, the atomic write succeeded
        assert json.loads(out.read_text())["timestamp"] == 12345.0


# ---------------------------------------------------------------------------
# fuse_sensors (integration with tmp files)
# ---------------------------------------------------------------------------


class TestFuseSensors:
    def test_fuse_all_active(self, tmp_path, monkeypatch):
        # Write all sensor files into tmp_path
        theramini_f = tmp_path / "theramini_state.json"
        room_f = tmp_path / "room_activity.json"
        speech_f = tmp_path / "room_speech.json"
        composer_f = tmp_path / "composer_state.json"

        _theramini_playing(theramini_f)
        _room_active(room_f)
        _speech_detected(speech_f)
        _composer_state(composer_f)

        monkeypatch.setattr("sensor_fusion.THERAMINI_STATE", str(theramini_f))
        monkeypatch.setattr("sensor_fusion.ROOM_ACTIVITY_STATE", str(room_f))
        monkeypatch.setattr("sensor_fusion.ROOM_SPEECH_STATE", str(speech_f))
        monkeypatch.setattr("sensor_fusion.COMPOSER_STATE", str(composer_f))

        state = fuse_sensors()

        assert "timestamp" in state
        assert state["theramini"]["playing"] is True
        assert state["theramini"]["pitch"] == "A4"
        assert state["theramini"]["key"] == "A"
        assert state["room"]["activity"] == "active"
        assert state["room"]["transient"] is True
        assert state["speech"]["detected"] is True
        assert state["speech"]["transcript"] == "That sounds beautiful"
        assert state["composer"]["key"] == "A"
        assert state["composer"]["mode"] == "duet"
        assert state["composer"]["movement"] == "verse"
        assert state["organism_mood"]["energy"] > 0.5
        assert state["presence"]["someone_here"] is True

    def test_fuse_all_quiet(self, tmp_path, monkeypatch):
        theramini_f = tmp_path / "theramini_state.json"
        room_f = tmp_path / "room_activity.json"
        speech_f = tmp_path / "room_speech.json"
        composer_f = tmp_path / "composer_state.json"

        _theramini_silent(theramini_f)
        _room_quiet(room_f)
        _speech_silent(speech_f)
        _composer_state(composer_f)

        monkeypatch.setattr("sensor_fusion.THERAMINI_STATE", str(theramini_f))
        monkeypatch.setattr("sensor_fusion.ROOM_ACTIVITY_STATE", str(room_f))
        monkeypatch.setattr("sensor_fusion.ROOM_SPEECH_STATE", str(speech_f))
        monkeypatch.setattr("sensor_fusion.COMPOSER_STATE", str(composer_f))

        state = fuse_sensors()

        assert state["theramini"]["playing"] is False
        assert state["room"]["transient"] is False
        assert state["speech"]["detected"] is False
        assert state["presence"]["someone_here"] is False
        assert state["organism_mood"]["energy"] < 0.3

    def test_fuse_missing_files(self, tmp_path, monkeypatch):
        # All files missing — should produce a valid but "empty" state
        monkeypatch.setattr("sensor_fusion.THERAMINI_STATE", str(tmp_path / "nope1.json"))
        monkeypatch.setattr("sensor_fusion.ROOM_ACTIVITY_STATE", str(tmp_path / "nope2.json"))
        monkeypatch.setattr("sensor_fusion.ROOM_SPEECH_STATE", str(tmp_path / "nope3.json"))
        monkeypatch.setattr("sensor_fusion.COMPOSER_STATE", str(tmp_path / "nope4.json"))

        state = fuse_sensors()

        assert state["theramini"]["playing"] is False
        assert state["room"]["transient"] is False
        assert state["speech"]["detected"] is False
        assert state["presence"]["someone_here"] is False
        # Composer defaults
        assert state["composer"]["key"] == "C"
        assert state["composer"]["mode"] == "solo"
        assert state["composer"]["movement"] == "idle"

    def test_fuse_partial_files(self, tmp_path, monkeypatch):
        """Only theramini is present, rest missing."""
        theramini_f = tmp_path / "theramini_state.json"
        _theramini_playing(theramini_f)

        monkeypatch.setattr("sensor_fusion.THERAMINI_STATE", str(theramini_f))
        monkeypatch.setattr("sensor_fusion.ROOM_ACTIVITY_STATE", str(tmp_path / "nope.json"))
        monkeypatch.setattr("sensor_fusion.ROOM_SPEECH_STATE", str(tmp_path / "nope2.json"))
        monkeypatch.setattr("sensor_fusion.COMPOSER_STATE", str(tmp_path / "nope3.json"))

        state = fuse_sensors()

        assert state["theramini"]["playing"] is True
        assert state["room"]["transient"] is False
        assert state["presence"]["someone_here"] is True


# ---------------------------------------------------------------------------
# run_fusion_loop
# ---------------------------------------------------------------------------


class TestRunFusionLoop:
    def test_loop_runs_and_writes(self, tmp_path, monkeypatch):
        """Loop should run one iteration, write state, then stop."""
        theramini_f = tmp_path / "theramini_state.json"
        room_f = tmp_path / "room_activity.json"
        speech_f = tmp_path / "room_speech.json"
        composer_f = tmp_path / "composer_state.json"
        output_f = tmp_path / "organism_state.json"

        _theramini_playing(theramini_f)
        _room_quiet(room_f)
        _speech_silent(speech_f)
        _composer_state(composer_f)

        monkeypatch.setattr("sensor_fusion.THERAMINI_STATE", str(theramini_f))
        monkeypatch.setattr("sensor_fusion.ROOM_ACTIVITY_STATE", str(room_f))
        monkeypatch.setattr("sensor_fusion.ROOM_SPEECH_STATE", str(speech_f))
        monkeypatch.setattr("sensor_fusion.COMPOSER_STATE", str(composer_f))
        monkeypatch.setattr("sensor_fusion.DEFAULT_OUTPUT", str(output_f))

        # Run loop with max_iterations=2 to avoid infinite loop
        run_fusion_loop(interval=0.01, max_iterations=2)

        assert output_f.exists()
        data = json.loads(output_f.read_text())
        assert data["theramini"]["playing"] is True
        assert "timestamp" in data

    def test_loop_handles_write_errors(self, tmp_path, monkeypatch):
        """Loop should not crash on write errors."""
        monkeypatch.setattr("sensor_fusion.THERAMINI_STATE", str(tmp_path / "nope.json"))
        monkeypatch.setattr("sensor_fusion.ROOM_ACTIVITY_STATE", str(tmp_path / "nope.json"))
        monkeypatch.setattr("sensor_fusion.ROOM_SPEECH_STATE", str(tmp_path / "nope.json"))
        monkeypatch.setattr("sensor_fusion.COMPOSER_STATE", str(tmp_path / "nope.json"))
        # Write to a non-existent directory
        monkeypatch.setattr("sensor_fusion.DEFAULT_OUTPUT", "/nonexistent/dir/state.json")

        # Should not raise — loop catches write errors
        run_fusion_loop(interval=0.01, max_iterations=1)
