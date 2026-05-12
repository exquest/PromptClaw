"""Tests for EMSD mix planning."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.mix_engine import (
    FREQUENCY_LANES,
    build_dynamics_profile,
    build_mastering_policy,
    build_mix_profile,
    build_spatial_profile,
)
from senseweave.mix_verify import check_masking


def test_sleep_mix_targets_are_quieter_than_day_mix() -> None:
    sleep = build_mix_profile(cadence_state="sleep", patch_name="house_monastery")
    day = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")

    assert sleep.target_lufs < day.target_lufs
    assert sleep.bus_comp_ratio <= day.bus_comp_ratio


def test_mix_profile_allocates_lower_band_to_bass_than_melody() -> None:
    profile = build_mix_profile(cadence_state="occupied_day", patch_name="house_procession")
    bass = next(target for target in profile.voice_targets if target.role == "bass")
    melody = next(target for target in profile.voice_targets if target.role == "melody")

    assert bass.lane.high_hz < melody.lane.low_hz


def test_mix_profile_assigns_complete_production_frequency_lanes() -> None:
    profile = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")

    assigned = {
        lane_name
        for lane_names in profile.role_frequency_lanes.values()
        for lane_name in lane_names
    }

    assert assigned == set(FREQUENCY_LANES)
    assert profile.role_frequency_lanes["bass"] == ("sub", "bass")
    assert "upper-mid" in profile.role_frequency_lanes["lead"]
    assert "air" in profile.role_frequency_lanes["texture"]


def test_production_metadata_includes_filter_and_eq_intent_for_lane_roles() -> None:
    profile = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")

    for role in ("bass", "pad", "lead", "texture", "noise", "sample", "theramini"):
        metadata = profile.production_metadata[role]
        assert metadata["hpf_hz"] > 0.0
        assert metadata["lpf_hz"] > metadata["hpf_hz"]
        assert metadata["eq_intent"]


def test_primary_frequency_lanes_avoid_masking_and_keep_bass_centered() -> None:
    profile = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")
    bass = next(target for target in profile.voice_targets if target.role == "bass")

    assert check_masking(profile.voice_targets, threshold=0.0) == []
    assert bass.stereo_width <= 0.1
    assert profile.production_metadata["bass"]["stereo_policy"] == "mono-center"


def test_theramini_presence_adds_ducking() -> None:
    without = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden", theramini_present=False)
    with_theramini = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden", theramini_present=True)

    assert with_theramini.theramini_duck_db > without.theramini_duck_db


# --- Mastering policy tests ---


def test_mastering_policy_attached_to_mix_profile() -> None:
    profile = build_mix_profile(
        cadence_state="occupied_day",
        patch_name="house_garden",
        phase_name="Conversation",
    )

    assert profile.mastering is not None
    assert profile.mastering.target_lufs == profile.target_lufs
    assert profile.mastering.limiter_ceiling_dbtp == profile.peak_ceiling_dbtp
    assert profile.mastering.eq_intent.low_cut_hz >= 30.0


def test_mastering_policy_installation_safe_for_all_cadences() -> None:
    for cadence_state in ("sleep", "wind_down", "wake_ramp", "occupied_day", "away_practice"):
        policy = build_mastering_policy(cadence_state=cadence_state)
        min_lufs, max_lufs = policy.target_lufs_range
        min_peak, max_peak = policy.true_peak_range_dbtp

        assert -26.0 <= min_lufs <= policy.target_lufs <= max_lufs <= -13.0
        assert -8.0 <= min_peak <= policy.limiter_ceiling_dbtp <= max_peak <= -1.0
        assert policy.eq_intent.low_shelf_db <= 0.0


def test_mastering_dynamic_contrast_is_phase_specific() -> None:
    divination = build_mastering_policy(cadence_state="occupied_day", phase_name="Divination")
    conversation = build_mastering_policy(cadence_state="occupied_day", phase_name="Conversation")
    crystallization = build_mastering_policy(cadence_state="occupied_day", phase_name="Crystallization")

    assert conversation.dynamic_contrast_db < divination.dynamic_contrast_db
    assert conversation.dynamic_contrast_db < crystallization.dynamic_contrast_db


# --- Dynamics, compression, sidechain, and deference tests ---


def test_dynamics_profile_attached_when_phase_provided() -> None:
    profile = build_mix_profile(
        cadence_state="occupied_day",
        patch_name="house_garden",
        phase_name="Conversation",
    )
    assert profile.dynamics is not None
    assert profile.dynamics.phase_name == "Conversation"


def test_dynamics_profile_absent_without_phase() -> None:
    profile = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")
    assert profile.dynamics is None


def test_divination_has_gentle_compression() -> None:
    dyn = build_dynamics_profile("Divination")
    assert dyn.comp_ratio <= 1.3
    assert dyn.comp_attack_ms >= 60.0
    assert dyn.transient_policy == "preserve"


def test_crystallization_has_gentle_compression() -> None:
    dyn = build_dynamics_profile("Crystallization")
    assert dyn.comp_ratio <= 1.4
    assert dyn.comp_attack_ms >= 50.0
    assert dyn.transient_policy == "preserve"


def test_no_over_compression_in_sparse_phases() -> None:
    """Divination and Crystallization must not exceed 1.5:1 ratio."""
    for phase in ("Divination", "Crystallization"):
        dyn = build_dynamics_profile(phase)
        assert dyn.comp_ratio < 1.5, f"{phase} comp_ratio {dyn.comp_ratio} too aggressive"
        assert dyn.dynamic_range_db >= 15.0, f"{phase} dynamic range {dyn.dynamic_range_db} too narrow"


def test_conversation_has_tightest_compression() -> None:
    conv = build_dynamics_profile("Conversation")
    div = build_dynamics_profile("Divination")
    crys = build_dynamics_profile("Crystallization")

    assert conv.comp_ratio > div.comp_ratio
    assert conv.comp_ratio > crys.comp_ratio
    assert conv.dynamic_range_db < div.dynamic_range_db
    assert conv.dynamic_range_db < crys.dynamic_range_db


def test_dynamic_range_widens_for_sleep_cadence() -> None:
    day = build_dynamics_profile("Emergence", cadence_state="occupied_day")
    sleep = build_dynamics_profile("Emergence", cadence_state="sleep")

    assert sleep.dynamic_range_db > day.dynamic_range_db
    assert sleep.comp_ratio < day.comp_ratio


def test_sidechain_deference_rules_present_for_all_phases() -> None:
    for phase in ("Divination", "Emergence", "Conversation", "Convergence", "Crystallization"):
        dyn = build_dynamics_profile(phase)
        assert len(dyn.deference_rules) >= 2, f"{phase} has too few deference rules"


def test_theramini_silence_request_rule_in_every_phase() -> None:
    for phase in ("Divination", "Emergence", "Conversation", "Convergence", "Crystallization"):
        dyn = build_dynamics_profile(phase)
        silence_rules = [r for r in dyn.deference_rules if r.trigger == "silence_request"]
        assert len(silence_rules) >= 1, f"{phase} missing silence_request deference rule"
        assert all(r.action == "silence" for r in silence_rules)


def test_theramini_onset_duck_deeper_in_conversation() -> None:
    conv = build_dynamics_profile("Conversation")
    div = build_dynamics_profile("Divination")

    conv_duck = next(r for r in conv.deference_rules if r.source == "theramini" and r.trigger == "onset")
    div_duck = next(r for r in div.deference_rules if r.source == "theramini" and r.trigger == "onset")

    assert conv_duck.duck_db >= div_duck.duck_db


def test_environmental_transient_deference_present() -> None:
    for phase in ("Divination", "Emergence", "Conversation", "Convergence", "Crystallization"):
        dyn = build_dynamics_profile(phase)
        env_rules = [r for r in dyn.deference_rules if r.source == "environmental"]
        assert len(env_rules) >= 1, f"{phase} has no environmental deference rule"


def test_deference_rules_have_valid_priorities() -> None:
    for phase in ("Divination", "Emergence", "Conversation", "Convergence", "Crystallization"):
        dyn = build_dynamics_profile(phase)
        for rule in dyn.deference_rules:
            assert rule.priority > 0
            assert rule.attack_ms > 0
            # silence action should have zero duck_db
            if rule.action == "silence":
                assert rule.duck_db == 0.0


# --- Spatial, reverb, and delay production profile tests ---


def test_spatial_profile_attached_when_phase_provided() -> None:
    profile = build_mix_profile(
        cadence_state="occupied_day",
        patch_name="house_garden",
        phase_name="Conversation",
    )
    assert profile.spatial is not None
    assert profile.spatial.phase_name == "Conversation"


def test_spatial_profile_absent_without_phase() -> None:
    profile = build_mix_profile(cadence_state="occupied_day", patch_name="house_garden")
    assert profile.spatial is None


def test_divination_wide_sparse_opening() -> None:
    """Divination: wide stereo, deep, large reverb -- sparse opening."""
    sp = build_spatial_profile("Divination")
    assert sp.stereo_width >= 0.8, "Divination should be wide"
    assert sp.depth >= 0.7, "Divination should be deep"
    assert sp.reverb_size >= 0.8, "Divination should have large reverb"
    assert sp.reverb_decay_s >= 4.0, "Divination should have long reverb tail"
    assert sp.reverb_damping <= 0.4, "Divination reverb should be bright (low damping)"
    assert sp.delay_style == "none"


def test_conversation_clearer_space() -> None:
    """Conversation: narrower, shorter reverb, higher damping -- clarity."""
    sp = build_spatial_profile("Conversation")
    div = build_spatial_profile("Divination")

    assert sp.stereo_width < div.stereo_width
    assert sp.depth < div.depth
    assert sp.reverb_size < div.reverb_size
    assert sp.reverb_decay_s < div.reverb_decay_s
    assert sp.reverb_damping > div.reverb_damping


def test_convergence_focused() -> None:
    """Convergence: tighter than sparse phases, controlled reverb."""
    sp = build_spatial_profile("Convergence")
    div = build_spatial_profile("Divination")
    crys = build_spatial_profile("Crystallization")

    assert sp.stereo_width < div.stereo_width
    assert sp.stereo_width < crys.stereo_width
    assert sp.reverb_decay_s < div.reverb_decay_s
    assert sp.reverb_decay_s < crys.reverb_decay_s


def test_crystallization_long_tails() -> None:
    """Crystallization: wide, deep, longest reverb tails + tape echo."""
    sp = build_spatial_profile("Crystallization")
    assert sp.stereo_width >= 0.75, "Crystallization should be wide"
    assert sp.reverb_decay_s >= 5.0, "Crystallization should have longest tails"
    assert sp.delay_style == "tape_echo"
    assert sp.delay_send >= 0.15, "Crystallization should have audible delay"


def test_crystallization_has_longest_reverb_of_all_phases() -> None:
    all_phases = ("Divination", "Emergence", "Conversation", "Convergence", "Crystallization")
    crys = build_spatial_profile("Crystallization")
    for phase in all_phases:
        sp = build_spatial_profile(phase)
        assert crys.reverb_decay_s >= sp.reverb_decay_s, (
            f"Crystallization reverb ({crys.reverb_decay_s}s) should be >= {phase} ({sp.reverb_decay_s}s)"
        )


def test_spatial_widens_for_sleep_cadence() -> None:
    day = build_spatial_profile("Emergence", cadence_state="occupied_day")
    sleep = build_spatial_profile("Emergence", cadence_state="sleep")

    assert sleep.stereo_width > day.stereo_width
    assert sleep.depth > day.depth
    assert sleep.reverb_decay_s > day.reverb_decay_s
    assert sleep.reverb_damping < day.reverb_damping


def test_all_phases_have_spatial_profiles() -> None:
    for phase in ("Divination", "Emergence", "Conversation", "Convergence", "Crystallization"):
        sp = build_spatial_profile(phase)
        assert sp.phase_name == phase
        assert 0.0 <= sp.stereo_width <= 1.0
        assert 0.0 <= sp.depth <= 1.0
        assert 0.0 <= sp.reverb_size <= 1.0
        assert sp.reverb_decay_s > 0.0
        assert 0.0 <= sp.reverb_damping <= 1.0
        assert 0.0 <= sp.delay_send <= 1.0
