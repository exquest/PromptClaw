"""Tests for sample/DSP activity planning."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sample_dsp_activity import build_sample_dsp_activity


def test_room_mic_activity_uses_fresh_capture_and_room_transient() -> None:
    activity = build_sample_dsp_activity(
        timestamp=100.0,
        composer_state={
            "sample_source": "room_mic",
            "sample_capture_path": "/tmp/room_capture.wav",
            "sample_refresh_seconds": 45,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.41,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["freeze_tail", "grain_window"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={"rms": 0.05, "is_playing": True, "has_clicks": False},
        sensor_states={
            "room_activity": {"recent_transient": True, "activity_level": "active"},
            "room_speech": {"speech_detected": False},
            "theramini": {"is_playing": False},
        },
        capture_meta={"exists": True, "age_seconds": 4.0},
    )

    assert activity["capture_ready"] is True
    assert activity["trigger_now"] is True
    assert activity["activity_mode"] == "slice_accents"
    assert activity["pitch_window_semitones"] > 0
    assert activity["grain_density_hz"] > 0.0


def test_theramini_activity_ducks_until_playing_and_requires_capture() -> None:
    quiet = build_sample_dsp_activity(
        timestamp=200.0,
        composer_state={
            "sample_source": "theramini_in",
            "sample_capture_path": "/tmp/theramini_capture.wav",
            "sample_refresh_seconds": 30,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.56,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["cross_synthesis", "parallel_delay"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={"rms": 0.03, "is_playing": True, "has_clicks": False},
        sensor_states={"theramini": {"is_playing": False}},
        capture_meta={"exists": True, "age_seconds": 3.0},
    )
    active = build_sample_dsp_activity(
        timestamp=200.0,
        composer_state={
            "sample_source": "theramini_in",
            "sample_capture_path": "/tmp/theramini_capture.wav",
            "sample_refresh_seconds": 30,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.56,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["cross_synthesis", "parallel_delay"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={"rms": 0.03, "is_playing": True, "has_clicks": False},
        sensor_states={"theramini": {"is_playing": True}},
        capture_meta={"exists": True, "age_seconds": 3.0},
    )

    assert quiet["trigger_now"] is False
    assert active["trigger_now"] is True
    assert active["activity_mode"] == "window_echo"
    assert active["wet_mix"] > quiet["wet_mix"]


def test_missing_capture_disables_activity_even_when_state_is_loud() -> None:
    activity = build_sample_dsp_activity(
        timestamp=300.0,
        composer_state={
            "sample_source": "self_bus",
            "sample_capture_path": "/tmp/self_capture.wav",
            "sample_refresh_seconds": 60,
            "sample_transforms": ["stretch", "spectral_freeze"],
            "sample_density": 0.3,
            "sample_buffer_seconds": 24.0,
            "sample_trigger_threshold": 0.22,
            "dsp_blocks": ["lowpass_bloom"],
        },
        cadence_state={"cadence_state": "sleep"},
        self_state={"rms": 0.09, "is_playing": True, "has_clicks": False},
        sensor_states={},
        capture_meta={"exists": False, "age_seconds": None},
    )

    assert activity["capture_ready"] is False
    assert activity["trigger_now"] is False
    assert activity["activity_mode"] == "freeze_bed"


def test_garden_source_falls_back_to_fresh_room_capture() -> None:
    activity = build_sample_dsp_activity(
        timestamp=400.0,
        composer_state={
            "sample_source": "garden_mic",
            "sample_capture_path": "/tmp/garden_capture.wav",
            "sample_refresh_seconds": 90,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.28,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["spectral_smear", "long_convolution"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={"rms": 0.05, "is_playing": True, "has_clicks": False},
        sensor_states={
            "room_activity": {"recent_transient": True, "activity_level": "active"},
            "room_speech": {"speech_detected": False},
            "theramini": {"is_playing": False},
        },
        capture_meta={"exists": False, "age_seconds": None},
        capture_registry={
            "room_mic": {"exists": True, "age_seconds": 3.0, "path": "/tmp/room_capture.wav"},
            "contact_mic": {"exists": True, "age_seconds": 4.0, "path": "/tmp/contact_capture.wav"},
            "self_bus": {"exists": True, "age_seconds": 2.0, "path": "/tmp/self_capture.wav"},
        },
    )

    assert activity["requested_sample_source"] == "garden_mic"
    assert activity["sample_source"] == "room_mic"
    assert activity["capture_path"] == "/tmp/room_capture.wav"
    assert activity["capture_ready"] is True
    assert activity["trigger_now"] is True


def test_perform_ve_room_bank_uses_contact_fallback_when_room_capture_is_stale() -> None:
    activity = build_sample_dsp_activity(
        timestamp=425.0,
        composer_state={
            "sample_source": "perform_ve_condenser",
            "sample_capture_path": "/tmp/room_capture.wav",
            "sample_refresh_seconds": 45,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.3,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["freeze_tail"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={"rms": 0.03, "is_playing": True, "has_clicks": False},
        sensor_states={
            "room_activity": {"recent_transient": True, "activity_level": "active"},
            "room_speech": {"speech_detected": False},
            "theramini": {"is_playing": False},
        },
        capture_meta={"exists": True, "age_seconds": 90.0},
        capture_registry={
            "contact_mic": {"exists": True, "age_seconds": 5.0, "path": "/tmp/contact_capture.wav"},
            "self_bus": {"exists": True, "age_seconds": 4.0, "path": "/tmp/self_capture.wav"},
        },
    )

    assert activity["requested_sample_source"] == "perform_ve_condenser"
    assert activity["sample_bank"] == "room_mic"
    assert activity["sample_source"] == "contact_mic"
    assert activity["fallback_sources"] == ["contact_mic", "self_bus"]
    assert activity["source_freshness_s"] == 30


def test_missing_theramini_prefers_contact_capture_before_self_bus() -> None:
    activity = build_sample_dsp_activity(
        timestamp=450.0,
        composer_state={
            "sample_source": "theramini_in",
            "sample_capture_path": "/tmp/theramini_capture.wav",
            "sample_refresh_seconds": 30,
            "sample_transforms": ["slice_rearrange", "granular_cloud", "reverse_accents"],
            "sample_density": 0.52,
            "sample_buffer_seconds": 14.0,
            "sample_trigger_threshold": 0.12,
            "dsp_blocks": ["cross_synthesis", "parallel_delay"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={"rms": 0.008, "is_playing": True, "has_clicks": False},
        sensor_states={
            "room_activity": {"recent_transient": True, "activity_level": "active"},
            "room_speech": {"speech_detected": False},
            "theramini": {"is_playing": False},
        },
        capture_meta={"exists": False, "age_seconds": None},
        capture_registry={
            "contact_mic": {"exists": True, "age_seconds": 1.0, "path": "/tmp/contact_capture.wav"},
            "room_mic": {"exists": True, "age_seconds": 1.0, "path": "/tmp/room_capture.wav"},
            "self_bus": {"exists": True, "age_seconds": 1.0, "path": "/tmp/self_capture.wav"},
        },
    )

    assert activity["requested_sample_source"] == "theramini_in"
    assert activity["sample_source"] == "contact_mic"
    assert activity["capture_path"] == "/tmp/contact_capture.wav"
    assert activity["trigger_now"] is True


def test_self_bus_request_prefers_room_mic_for_room_composition_phases() -> None:
    activity = build_sample_dsp_activity(
        timestamp=500.0,
        composer_state={
            "arc_phase": "Crystallization",
            "sample_source": "self_bus",
            "sample_capture_path": "/tmp/self_capture.wav",
            "sample_refresh_seconds": 60,
            "sample_transforms": ["stretch", "spectral_freeze"],
            "sample_density": 0.2,
            "sample_buffer_seconds": 18.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["freeze_tail", "lowpass_bloom"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={"rms": 0.0, "is_playing": False, "has_clicks": False},
        sensor_states={
            "room_activity": {"recent_transient": False, "activity_level": "quiet"},
            "room_speech": {"speech_detected": False},
            "theramini": {"is_playing": False},
        },
        capture_meta={"exists": True, "age_seconds": 2.0},
        capture_registry={
            "room_mic": {"exists": True, "age_seconds": 1.0, "path": "/tmp/room_capture.wav"},
            "self_bus": {"exists": True, "age_seconds": 2.0, "path": "/tmp/self_capture.wav"},
        },
    )

    assert activity["requested_sample_source"] == "self_bus"
    assert activity["sample_source"] == "room_mic"
    assert activity["capture_path"] == "/tmp/room_capture.wav"


def test_room_mic_trigger_does_not_depend_on_self_bus_rms() -> None:
    activity = build_sample_dsp_activity(
        timestamp=600.0,
        composer_state={
            "sample_source": "room_mic",
            "sample_capture_path": "/tmp/room_capture.wav",
            "sample_refresh_seconds": 45,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.32,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.2,
            "dsp_blocks": ["freeze_tail"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={"rms": 0.0, "is_playing": False, "has_clicks": False},
        sensor_states={
            "room_activity": {"recent_transient": True, "activity_level": "active"},
            "room_speech": {"speech_detected": False},
            "theramini": {"is_playing": False},
        },
        capture_meta={"exists": True, "age_seconds": 2.0},
    )

    assert activity["sample_source"] == "room_mic"
    assert activity["trigger_now"] is True


def test_development_scene_pushes_room_sampling_toward_grain_cloud() -> None:
    activity = build_sample_dsp_activity(
        timestamp=700.0,
        composer_state={
            "arc_phase": "Emergence",
            "sample_source": "room_mic",
            "sample_capture_path": "/tmp/room_capture.wav",
            "sample_refresh_seconds": 45,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.34,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["freeze_tail", "grain_window"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={
            "rms": 0.0,
            "is_playing": False,
            "has_clicks": False,
            "tracker_scene_name": "Development",
        },
        sensor_states={
            "room_activity": {"recent_transient": True, "activity_level": "active"},
            "room_speech": {"speech_detected": False},
            "theramini": {"is_playing": False},
        },
        capture_meta={"exists": True, "age_seconds": 2.0},
    )

    assert activity["scene_profile"] == "development_grains"
    assert activity["activity_mode"] == "grain_cloud"
    assert activity["render_duration_s"] >= 2.5
    assert activity["grain_density_hz"] > 5.0


def test_afterglow_scene_turns_room_sampling_into_long_residue() -> None:
    activity = build_sample_dsp_activity(
        timestamp=800.0,
        composer_state={
            "arc_phase": "Crystallization",
            "sample_source": "room_mic",
            "sample_capture_path": "/tmp/room_capture.wav",
            "sample_refresh_seconds": 45,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.18,
            "sample_buffer_seconds": 18.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["freeze_tail", "lowpass_bloom"],
        },
        cadence_state={"cadence_state": "wind_down"},
        self_state={
            "rms": 0.0,
            "is_playing": False,
            "has_clicks": False,
            "tracker_scene_name": "Afterglow",
        },
        sensor_states={
            "room_activity": {"recent_transient": False, "activity_level": "quiet"},
            "room_speech": {"speech_detected": False},
            "theramini": {"is_playing": False},
        },
        capture_meta={"exists": True, "age_seconds": 2.0},
    )

    assert activity["scene_profile"] == "afterglow_residue"
    assert activity["activity_mode"] == "freeze_bed"
    assert activity["render_duration_s"] >= 4.5
    assert activity["peak_target"] < 0.15


def test_tracker_transport_adds_scene_locked_trigger_keys() -> None:
    activity = build_sample_dsp_activity(
        timestamp=900.0,
        composer_state={
            "arc_phase": "Emergence",
            "sample_source": "room_mic",
            "sample_capture_path": "/tmp/room_capture.wav",
            "sample_refresh_seconds": 45,
            "sample_transforms": ["slice_rearrange", "pitch_window"],
            "sample_density": 0.32,
            "sample_buffer_seconds": 12.0,
            "sample_trigger_threshold": 0.15,
            "dsp_blocks": ["freeze_tail"],
        },
        cadence_state={"cadence_state": "occupied_day"},
        self_state={
            "rms": 0.02,
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
        capture_meta={"exists": True, "age_seconds": 1.0},
    )

    assert activity["transport_trigger_now"] is True
    assert activity["transport_quantum_rows"] == 4
    assert activity["transport_trigger_key"] == "Theme:slice_accents:1"
