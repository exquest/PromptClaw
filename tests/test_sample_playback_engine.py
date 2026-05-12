"""Tests for the live sample-playback engine."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

import sample_playback_engine
from sample_playback_engine import (
    EngineState,
    choose_launch,
    maybe_launch_event,
    write_state,
)


def test_choose_launch_triggers_for_live_grain_event() -> None:
    now = 100.0
    state = EngineState(last_trigger_at=90.0)
    activity = {
        "capture_ready": True,
        "trigger_now": True,
        "activity_mode": "grain_cloud",
        "capture_path": "/tmp/room_capture.wav",
        "sample_source": "room_mic",
        "wet_mix": 0.5,
    }

    decision = choose_launch(activity=activity, now=now, state=state, player_running=False)

    assert decision.should_launch is True
    assert decision.cooldown_s >= 4.0


def test_choose_launch_allows_bed_refresh_without_trigger_flag() -> None:
    now = 200.0
    state = EngineState(last_trigger_at=180.0)
    activity = {
        "capture_ready": True,
        "trigger_now": False,
        "activity_mode": "freeze_bed",
        "capture_path": "/tmp/room_capture.wav",
        "sample_source": "room_mic",
        "wet_mix": 0.24,
    }

    decision = choose_launch(activity=activity, now=now, state=state, player_running=False)

    assert decision.should_launch is True
    assert decision.reason == "bed_refresh"


def test_write_state_writes_json_atomically(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "sample_playback_state.json"
    monkeypatch.setattr(sample_playback_engine, "STATE_PATH", state_path)

    write_state({"timestamp": time.time(), "mode": "grain_cloud", "playing": True})

    data = json.loads(state_path.read_text())
    assert data["mode"] == "grain_cloud"
    assert data["playing"] is True


def test_maybe_launch_event_repeats_same_signature_after_cooldown(
    tmp_path: Path, monkeypatch
) -> None:
    capture = tmp_path / "room.wav"
    capture.write_bytes(b"RIFFfake")
    output_dir = tmp_path / "events"
    monkeypatch.setattr(sample_playback_engine, "OUTPUT_DIR", output_dir)
    state_path = tmp_path / "sample_playback_state.json"
    monkeypatch.setattr(sample_playback_engine, "STATE_PATH", state_path)

    launched_paths: list[Path] = []

    def fake_render_sample_event(*, source_path, output_path, activity, seed):
        Path(output_path).write_bytes(b"RIFFevent")
        return {"mode": activity["activity_mode"], "duration_s": 2.0, "peak": 0.2}

    def fake_launch_pw_play(path: Path):
        launched_paths.append(path)

        class _FakeProcess:
            def poll(self):
                return 0

        return _FakeProcess()

    monkeypatch.setattr(sample_playback_engine, "render_sample_event", fake_render_sample_event)
    monkeypatch.setattr(sample_playback_engine, "launch_pw_play", fake_launch_pw_play)

    activity = {
        "capture_ready": True,
        "trigger_now": False,
        "activity_mode": "freeze_bed",
        "capture_path": str(capture),
        "sample_source": "room_mic",
        "requested_sample_source": "room_mic",
        "wet_mix": 0.28,
    }
    state = EngineState(last_trigger_at=100.0, last_signature="same")

    launch1 = maybe_launch_event(
        activity=activity,
        now=120.0,
        state=state,
        player=None,
    )
    launch2 = maybe_launch_event(
        activity=activity,
        now=141.0,
        state=state,
        player=launch1["player"],
    )

    assert launch1["launched"] is True
    assert launch2["launched"] is True
    assert len(launched_paths) == 2


def test_maybe_launch_event_captures_render_failure_in_state(tmp_path: Path, monkeypatch) -> None:
    capture = tmp_path / "room.wav"
    capture.write_bytes(b"RIFFfake")
    state_path = tmp_path / "sample_playback_state.json"
    monkeypatch.setattr(sample_playback_engine, "STATE_PATH", state_path)

    def fake_render_sample_event(*, source_path, output_path, activity, seed):
        raise RuntimeError("render failed")

    monkeypatch.setattr(sample_playback_engine, "render_sample_event", fake_render_sample_event)

    activity = {
        "capture_ready": True,
        "trigger_now": True,
        "activity_mode": "grain_cloud",
        "capture_path": str(capture),
        "sample_source": "room_mic",
        "requested_sample_source": "room_mic",
        "wet_mix": 0.5,
    }
    state = EngineState(last_trigger_at=0.0, last_signature="")

    result = maybe_launch_event(activity=activity, now=10.0, state=state, player=None)

    assert result["launched"] is False
    persisted = json.loads(state_path.read_text())
    assert persisted["reason"] == "render_failed"


def test_choose_launch_uses_transport_trigger_key_once_per_bucket() -> None:
    now = 300.0
    state = EngineState(last_trigger_at=280.0, last_transport_key="Theme:slice_accents:0")
    activity = {
        "capture_ready": True,
        "trigger_now": False,
        "transport_trigger_now": True,
        "transport_trigger_key": "Theme:slice_accents:1",
        "activity_mode": "slice_accents",
        "capture_path": "/tmp/room_capture.wav",
        "sample_source": "room_mic",
        "wet_mix": 0.4,
    }

    decision = choose_launch(activity=activity, now=now, state=state, player_running=False)

    assert decision.should_launch is True
    assert decision.reason == "transport_lock"


def test_choose_launch_suppresses_duplicate_transport_bucket() -> None:
    now = 300.0
    state = EngineState(last_trigger_at=280.0, last_transport_key="Theme:slice_accents:1")
    activity = {
        "capture_ready": True,
        "trigger_now": False,
        "transport_trigger_now": True,
        "transport_trigger_key": "Theme:slice_accents:1",
        "activity_mode": "slice_accents",
        "capture_path": "/tmp/room_capture.wav",
        "sample_source": "room_mic",
        "wet_mix": 0.4,
    }

    decision = choose_launch(activity=activity, now=now, state=state, player_running=False)

    assert decision.should_launch is False
    assert decision.reason == "transport_held"
