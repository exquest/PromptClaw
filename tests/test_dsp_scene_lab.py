"""Tests for creative DSP scenes and audio-to-visual mapping."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.dsp_scene_lab import (
    AudioFeatureFrame,
    DSPGesture,
    glyph_features_from_audio,
    gestures_from_frame,
    scene_for_phase,
)


def test_conversation_scene_is_more_active_than_divination() -> None:
    divination = scene_for_phase("Divination", cadence_state="occupied_day")
    conversation = scene_for_phase("Conversation", cadence_state="occupied_day")

    assert divination.source_focus == "room_mic"
    assert len(conversation.blocks) >= len(divination.blocks)
    assert conversation.visual_bias["density"] > divination.visual_bias["density"]


def test_audio_feature_mapping_tracks_brightness_and_motion() -> None:
    dim = glyph_features_from_audio(AudioFeatureFrame(0.1, 800.0, 0.12, 0.5))
    bright = glyph_features_from_audio(AudioFeatureFrame(0.4, 3200.0, 0.55, 5.0))

    assert bright["brightness"] > dim["brightness"]
    assert bright["motion"] > dim["motion"]
    assert bright["salience"] > dim["salience"]
    assert bright["texture"] > dim["texture"]
    assert "dsp_blocks" in bright
    assert "mapping_hints" in bright


def test_late_scenes_bias_room_focus_outside_away_practice() -> None:
    convergence = scene_for_phase("Convergence", cadence_state="occupied_day")
    crystallization = scene_for_phase("Crystallization", cadence_state="occupied_day")
    away = scene_for_phase("Crystallization", cadence_state="away_practice")

    assert convergence.source_focus == "room_mic"
    assert crystallization.source_focus == "room_mic"
    assert away.source_focus == "self_bus"


# --- Gesture generation tests ---


def test_gestures_from_frame_produces_six_core_blocks_without_scene() -> None:
    frame = AudioFeatureFrame(0.5, 2000.0, 0.3, 4.0)
    gestures = gestures_from_frame(frame)
    blocks = [g.block for g in gestures]
    assert len(gestures) == 6
    assert "spectral_freeze" in blocks
    assert "spectral_smear" in blocks
    assert "spectral_morph" in blocks
    assert "convolution" in blocks
    assert "delay" in blocks
    assert "physical_model" in blocks


def test_gestures_from_frame_uses_scene_blocks_when_provided() -> None:
    frame = AudioFeatureFrame(0.3, 1000.0, 0.2, 2.0)
    scene = scene_for_phase("Divination", cadence_state="occupied_day")
    gestures = gestures_from_frame(frame, scene)
    assert len(gestures) == len(scene.blocks)
    assert gestures[0].block == "spectral_smear"
    assert gestures[1].block == "long_convolution"


def test_gesture_has_valid_structure() -> None:
    frame = AudioFeatureFrame(0.4, 1500.0, 0.3, 3.0)
    gestures = gestures_from_frame(frame)
    for g in gestures:
        assert isinstance(g, DSPGesture)
        assert 0.0 <= g.intensity <= 1.0
        assert g.time_scale > 0.0
        assert isinstance(g.params, dict)


def test_gesture_intensity_correlates_with_amplitude() -> None:
    quiet = AudioFeatureFrame(0.1, 1000.0, 0.3, 2.0)
    loud = AudioFeatureFrame(0.9, 1000.0, 0.3, 2.0)
    quiet_g = {g.block: g for g in gestures_from_frame(quiet)}
    loud_g = {g.block: g for g in gestures_from_frame(loud)}
    # Physical model and spectral morph intensity increase with amplitude
    assert loud_g["physical_model"].intensity > quiet_g["physical_model"].intensity
    assert loud_g["spectral_morph"].intensity > quiet_g["spectral_morph"].intensity
    # Spectral freeze intensity *decreases* with amplitude (quiet = more freeze)
    assert quiet_g["spectral_freeze"].intensity > loud_g["spectral_freeze"].intensity


def test_gesture_smear_responds_to_brightness() -> None:
    dark = AudioFeatureFrame(0.3, 200.0, 0.3, 2.0)
    bright = AudioFeatureFrame(0.3, 3800.0, 0.3, 2.0)
    dark_g = {g.block: g for g in gestures_from_frame(dark)}
    bright_g = {g.block: g for g in gestures_from_frame(bright)}
    assert bright_g["spectral_smear"].intensity > dark_g["spectral_smear"].intensity
    assert bright_g["spectral_smear"].params["spread"] > dark_g["spectral_smear"].params["spread"]


def test_gesture_delay_responds_to_density() -> None:
    sparse = AudioFeatureFrame(0.3, 1000.0, 0.3, 0.5)
    dense = AudioFeatureFrame(0.3, 1000.0, 0.3, 9.0)
    sparse_g = {g.block: g for g in gestures_from_frame(sparse)}
    dense_g = {g.block: g for g in gestures_from_frame(dense)}
    # Dense audio gets shorter delay times and more feedback
    assert dense_g["delay"].params["time_ms"] < sparse_g["delay"].params["time_ms"]
    assert dense_g["delay"].params["feedback"] > sparse_g["delay"].params["feedback"]


# --- Feature correlation tests with known synthetic inputs ---


def test_brightness_correlates_with_spectral_centroid() -> None:
    low = glyph_features_from_audio(AudioFeatureFrame(0.3, 400.0, 0.3, 2.0))
    mid = glyph_features_from_audio(AudioFeatureFrame(0.3, 2000.0, 0.3, 2.0))
    high = glyph_features_from_audio(AudioFeatureFrame(0.3, 4000.0, 0.3, 2.0))
    assert low["brightness"] < mid["brightness"] < high["brightness"]
    assert low["brightness"] == round(400.0 / 4000.0, 3)
    assert mid["brightness"] == round(2000.0 / 4000.0, 3)
    assert high["brightness"] == 1.0


def test_density_correlates_with_onset_rate() -> None:
    sparse = glyph_features_from_audio(AudioFeatureFrame(0.3, 1000.0, 0.3, 1.0))
    dense = glyph_features_from_audio(AudioFeatureFrame(0.3, 1000.0, 0.3, 8.0))
    assert sparse["density"] < dense["density"]
    assert sparse["density"] == round(1.0 / 10.0, 3)
    assert dense["density"] == round(8.0 / 10.0, 3)


def test_texture_correlates_with_flatness() -> None:
    smooth = glyph_features_from_audio(AudioFeatureFrame(0.3, 1000.0, 0.0, 2.0))
    noisy = glyph_features_from_audio(AudioFeatureFrame(0.3, 1000.0, 1.0, 2.0))
    assert smooth["texture"] < noisy["texture"]
    assert smooth["texture"] == 0.25
    assert noisy["texture"] == 1.0


def test_salience_correlates_with_amplitude_and_motion() -> None:
    quiet = glyph_features_from_audio(AudioFeatureFrame(0.05, 500.0, 0.2, 0.5))
    loud = glyph_features_from_audio(AudioFeatureFrame(0.8, 2000.0, 0.5, 6.0))
    assert loud["salience"] > quiet["salience"]


def test_motion_combines_onset_rate_and_amplitude() -> None:
    still = glyph_features_from_audio(AudioFeatureFrame(0.0, 1000.0, 0.3, 0.0))
    moving = glyph_features_from_audio(AudioFeatureFrame(0.6, 1000.0, 0.3, 6.0))
    assert still["motion"] == 0.0
    assert moving["motion"] > 0.5


def test_glyph_features_include_gestures_without_scene() -> None:
    frame = AudioFeatureFrame(0.4, 1500.0, 0.3, 3.0)
    features = glyph_features_from_audio(frame)
    assert "gestures" in features
    assert len(features["gestures"]) == 6
    for g in features["gestures"]:
        assert "block" in g
        assert "intensity" in g
        assert "time_scale" in g
        assert "params" in g


def test_glyph_features_with_scene_include_gesture_mapping_hints() -> None:
    frame = AudioFeatureFrame(0.4, 1500.0, 0.3, 3.0)
    scene = scene_for_phase("Conversation", cadence_state="occupied_day")
    features = glyph_features_from_audio(frame, scene)
    assert features["mapping_hints"]["focus"] == "theramini_in"
    assert features["mapping_hints"]["gesture_count"] == len(scene.blocks)
    assert "dominant_intensity" in features["mapping_hints"]
