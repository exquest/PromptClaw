"""End-to-end state-flow regression for musical runtime integrations."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

import sample_playback_engine
import self_listener
from sample_playback_engine import EngineState, maybe_launch_event
from senseweave.sample_dsp_activity import build_sample_dsp_activity
from senseweave.sample_event_renderer import write_wav_mono
from senseweave.sample_status import sample_status_text


def test_composer_sampler_listener_and_face_share_one_scene_state(tmp_path, monkeypatch) -> None:
    capture = tmp_path / "room_capture.wav"
    write_wav_mono(capture, [0, 1200, -1200, 800, -800] * 2000)

    activity = build_sample_dsp_activity(
        timestamp=100.0,
        composer_state={
            "arc_phase": "Emergence",
            "sample_source": "room_mic",
            "sample_capture_path": str(capture),
            "sample_refresh_seconds": 45,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.3,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["freeze_tail"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={
            "rms": 0.04,
            "is_playing": True,
            "has_clicks": False,
            "tracker_scene_name": "Theme",
            "tracker_row": 4,
            "tracker_rows_per_beat": 4,
        },
        sensor_states={
            "room_activity": {"recent_transient": True, "activity_level": "active"},
            "room_speech": {"speech_detected": False},
            "theramini": {"is_playing": False},
        },
        capture_meta={"exists": True, "age_seconds": 1.0, "path": str(capture)},
    )

    state_path = tmp_path / "sample_playback_state.json"
    output_dir = tmp_path / "events"
    monkeypatch.setattr(sample_playback_engine, "STATE_PATH", state_path)
    monkeypatch.setattr(sample_playback_engine, "OUTPUT_DIR", output_dir)

    launched_paths: list[Path] = []

    def fake_launch_pw_play(path: Path):
        launched_paths.append(path)

        class _FakeProcess:
            def poll(self):
                return 0

        return _FakeProcess()

    monkeypatch.setattr(sample_playback_engine, "launch_pw_play", fake_launch_pw_play)

    launch = maybe_launch_event(
        activity=activity,
        now=120.0,
        state=EngineState(last_trigger_at=0.0, last_transport_key=""),
        player=None,
    )

    playback_state = json.loads(state_path.read_text())
    glyph = self_listener.build_glyph_audio_state(
        120.0,
        {
            "rms": 0.04,
            "peak": 0.1,
            "pitch_hz": 330.0,
            "pitch_confidence": 0.8,
            "spectral_centroid_hz": 900.0,
            "onset_rate_hz": 1.5,
        },
        {"count": 0},
        composer_state={
            "arc_phase": "Emergence",
            "sample_source": activity["sample_source"],
            "sample_transforms": activity["sample_transforms"],
            "sample_density": activity["sample_density"],
            "dsp_blocks": activity["dsp_blocks"],
            "dsp_source_focus": activity["sample_source"],
            "artistic_identity": "CypherClaw writes with the room.",
        },
        cadence_state={},
    )
    face_text = sample_status_text(
        activity,
        playback_state,
        {"is_playing": True, "capture_backend": "jack"},
    )

    assert launch["launched"] is True
    assert launched_paths
    assert playback_state["sample_source"] == "room_mic"
    assert playback_state["transport_trigger_key"] == activity["transport_trigger_key"]
    assert glyph["sample_source"] == "room_mic"
    assert glyph["brightness"] > 0.0
    assert "playing room mic" in face_text.lower()


class MusicalIntegrationRuntimeEndToEndTests:
    """One end-to-end musical runtime path through every public surface.

    Drives ``build_sample_dsp_activity`` -> ``maybe_launch_event`` ->
    ``build_glyph_audio_state`` -> ``sample_status_text`` in a single pass
    against a deterministic room-mic scene, then proves the combined
    diagnostic payload is JSON-safe.
    """

    __test__ = True

    def test_end_to_end_room_mic_scene_threads_one_diagnostic_payload(
        self, tmp_path, monkeypatch
    ) -> None:
        capture = tmp_path / "room_capture.wav"
        write_wav_mono(capture, [0, 1500, -1500, 900, -900] * 2000)

        composer_state = {
            "arc_phase": "Emergence",
            "sample_source": "room_mic",
            "sample_capture_path": str(capture),
            "sample_refresh_seconds": 45,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.35,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["freeze_tail"],
        }
        activity = build_sample_dsp_activity(
            timestamp=200.0,
            composer_state=composer_state,
            cadence_state={"cadence_state": "occupied_day"},
            self_state={
                "rms": 0.05,
                "is_playing": True,
                "has_clicks": False,
                "tracker_scene_name": "Theme",
                "tracker_row": 4,
                "tracker_rows_per_beat": 4,
            },
            sensor_states={
                "room_activity": {
                    "recent_transient": True,
                    "activity_level": "active",
                },
                "room_speech": {"speech_detected": False},
                "theramini": {"is_playing": False},
            },
            capture_meta={
                "exists": True,
                "age_seconds": 1.0,
                "path": str(capture),
            },
        )

        state_path = tmp_path / "sample_playback_state.json"
        output_dir = tmp_path / "events"
        monkeypatch.setattr(sample_playback_engine, "STATE_PATH", state_path)
        monkeypatch.setattr(sample_playback_engine, "OUTPUT_DIR", output_dir)

        launched_paths: list[Path] = []

        def fake_launch_pw_play(path: Path):
            launched_paths.append(path)

            class _FakeProcess:
                def poll(self):
                    return 0

            return _FakeProcess()

        monkeypatch.setattr(
            sample_playback_engine, "launch_pw_play", fake_launch_pw_play
        )

        launch = maybe_launch_event(
            activity=activity,
            now=240.0,
            state=EngineState(last_trigger_at=0.0, last_transport_key=""),
            player=None,
        )

        assert launch["launched"] is True
        assert launched_paths

        playback_state = json.loads(state_path.read_text())

        glyph = self_listener.build_glyph_audio_state(
            240.0,
            {
                "rms": 0.05,
                "peak": 0.12,
                "pitch_hz": 330.0,
                "pitch_confidence": 0.82,
                "spectral_centroid_hz": 950.0,
                "onset_rate_hz": 1.6,
            },
            {"count": 0},
            composer_state={
                "arc_phase": "Emergence",
                "sample_source": activity["sample_source"],
                "sample_transforms": activity["sample_transforms"],
                "sample_density": activity["sample_density"],
                "dsp_blocks": activity["dsp_blocks"],
                "dsp_source_focus": activity["sample_source"],
                "artistic_identity": "CypherClaw writes with the room.",
            },
            cadence_state={},
        )
        face_text = sample_status_text(
            activity,
            playback_state,
            {"is_playing": True, "capture_backend": "jack"},
        )

        assert playback_state["sample_source"] == "room_mic"
        assert (
            playback_state["transport_trigger_key"]
            == activity["transport_trigger_key"]
        )
        assert glyph["sample_source"] == "room_mic"
        assert glyph["brightness"] > 0.0
        assert glyph["arc_phase"] == "Emergence"
        assert "playing room mic" in face_text.lower()

        diagnostic = {
            "activity": activity,
            "playback_state": playback_state,
            "glyph": glyph,
            "face_text": face_text,
        }
        roundtrip = json.loads(json.dumps(diagnostic, sort_keys=True, default=str))
        assert roundtrip["playback_state"]["sample_source"] == "room_mic"
        assert roundtrip["glyph"]["sample_source"] == "room_mic"
        assert roundtrip["face_text"] == face_text
        assert roundtrip["activity"]["sample_source"] == "room_mic"
