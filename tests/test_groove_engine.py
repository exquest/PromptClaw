"""Tests for groove_engine.py -- rhythm craft beyond duration cells."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.groove_engine import (
    GROOVE_TYPES,
    GrooveProfile,
    apply_groove_to_ioi,
    breath_points_for_phrase,
    entrainment_tempo_nudge,
    friberg_short_note_ms,
    friberg_swing_ratio,
    groove_for_section,
    groove_metadata_for_step,
    ioi_ratios_for_subdivision,
    is_breath_beat,
    meter_policy_for_phase,
    meter_rows_per_bar,
    microtiming_offset_ms,
    polymeter_phase_offset,
    polyrhythm_cycle_length,
    polyrhythm_accent_mask,
    swing_offset_for_step,
    swing_ioi_pair,
    tempo_swing_ratio,
)


# ---------------------------------------------------------------------------
# GrooveProfile basics
# ---------------------------------------------------------------------------


class TestGrooveProfile:
    def test_frozen(self):
        p = GrooveProfile(groove_type="swing", swing_ratio=1.5)
        try:
            p.swing_ratio = 2.0  # type: ignore[misc]
            assert False, "should be frozen"
        except AttributeError:
            pass

    def test_defaults(self):
        p = GrooveProfile(groove_type="straight")
        assert p.swing_ratio == 1.0
        assert p.push_pull_ms == 0.0
        assert p.microtiming_depth == 0.0
        assert p.polyrhythm is None
        assert p.polymeter is None
        assert p.entrainment_bpm is None
        assert p.breath_points == ()
        assert p.section_identity == ""


# ---------------------------------------------------------------------------
# groove_for_section lookup
# ---------------------------------------------------------------------------


class TestGrooveForSection:
    def test_identity_takes_priority(self):
        p = groove_for_section(
            groove_identity="dance",
            groove_state="drone",
            groove_family="lyric",
        )
        assert p.section_identity == "dance"
        assert p.groove_type == "swing"

    def test_state_fallback(self):
        p = groove_for_section(groove_state="drive")
        assert p.section_identity == "drive"
        assert p.groove_type == "push"

    def test_family_fallback(self):
        p = groove_for_section(groove_family="rolling")
        assert p.section_identity == "rolling"
        assert p.groove_type == "lilt"

    def test_default_when_unknown(self):
        p = groove_for_section(groove_identity="nonexistent_groove")
        assert p.section_identity == "default"
        assert p.groove_type == "straight"

    def test_entrainment_bpm_attached(self):
        p = groove_for_section(groove_identity="dance", entrainment_bpm=72.0)
        assert p.entrainment_bpm == 72.0
        assert p.section_identity == "dance"

    def test_entrainment_on_default(self):
        p = groove_for_section(entrainment_bpm=60.0)
        assert p.entrainment_bpm == 60.0
        assert p.section_identity == "default"

    def test_zero_entrainment_ignored(self):
        p = groove_for_section(groove_identity="pulse", entrainment_bpm=0.0)
        assert p.entrainment_bpm is None

    def test_all_known_identities_resolve(self):
        known = [
            "drift", "ritual_ostinato", "broken", "procession", "dance", "pulse",
            "drone", "static", "sustain", "pad", "lift", "drive",
            "lyric", "rolling", "suspended", "study",
        ]
        for identity in known:
            p = groove_for_section(groove_identity=identity)
            assert p.section_identity == identity, f"{identity} didn't resolve"
            assert p.groove_type in GROOVE_TYPES, f"{identity} has bad type {p.groove_type}"


# ---------------------------------------------------------------------------
# Swing IOI pairs
# ---------------------------------------------------------------------------


class TestSwingIOIPair:
    def test_straight(self):
        long, short = swing_ioi_pair(0.5, 1.0)
        assert long == short == 0.5

    def test_triplet_swing(self):
        long, short = swing_ioi_pair(0.5, 1.5)
        assert abs(long / short - 1.5) < 0.001
        assert abs(long + short - 1.0) < 1e-9

    def test_dotted_swing(self):
        long, short = swing_ioi_pair(0.5, 2.0)
        assert abs(long / short - 2.0) < 0.001
        assert abs(long + short - 1.0) < 1e-9

    def test_total_preserved(self):
        for ratio in (1.0, 1.2, 1.5, 1.8, 2.0, 3.0):
            long, short = swing_ioi_pair(1.0, ratio)
            assert abs(long + short - 2.0) < 1e-6, f"total broken for ratio {ratio}"

    def test_ratio_below_one_clamped(self):
        long, short = swing_ioi_pair(0.5, 0.5)
        assert long == short == 0.5  # clamped to 1.0

    def test_swing_offsets_are_deterministic_pair_offsets(self):
        assert swing_offset_for_step(0, 1.5) == 0.2
        assert swing_offset_for_step(1, 1.5) == -0.2
        assert swing_offset_for_step(2, 1.5) == 0.2


# ---------------------------------------------------------------------------
# Meter and subdivision policies
# ---------------------------------------------------------------------------


class TestMeterPolicies:
    def test_supported_meters_quantize_to_deterministic_rows(self):
        assert meter_rows_per_bar("4/4", rows_per_beat=4) == 16
        assert meter_rows_per_bar("3/4", rows_per_beat=4) == 12
        assert meter_rows_per_bar("6/8", rows_per_beat=4) == 12
        assert meter_rows_per_bar("5/4", rows_per_beat=4) == 20
        assert meter_rows_per_bar("7/8", rows_per_beat=4) == 14
        assert meter_rows_per_bar("free", rows_per_beat=4) == 16

    def test_subdivision_ioi_ratios_cover_swing_shuffle_and_dotted_cells(self):
        swing = ioi_ratios_for_subdivision("swing", swing_ratio=1.5)
        shuffle = ioi_ratios_for_subdivision("shuffle")
        dotted = ioi_ratios_for_subdivision("dotted")

        assert abs(swing[0] / swing[1] - 1.5) < 0.001
        assert abs(sum(swing) - 2.0) < 0.001
        assert abs(shuffle[0] / shuffle[1] - 2.0) < 0.001
        assert abs(dotted[0] / dotted[1] - 3.0) < 0.001

    def test_phase_specific_meter_policies(self):
        free = meter_policy_for_phase("Divination")
        pulse = meter_policy_for_phase("Emergence")
        convergence = meter_policy_for_phase("Convergence")

        assert (free.meter, free.subdivision, free.groove_timing) == ("free", "rubato", "rubato")
        assert (pulse.meter, pulse.subdivision) == ("4/4", "straight")
        assert convergence.meter == "7/8"
        assert convergence.polyrhythm == (3, 4)
        assert convergence.metric_modulation == "7:8"


# ---------------------------------------------------------------------------
# apply_groove_to_ioi
# ---------------------------------------------------------------------------


class TestApplyGrooveToIOI:
    def test_straight_no_change(self):
        p = GrooveProfile(groove_type="straight", swing_ratio=1.0, push_pull_ms=0.0)
        assert apply_groove_to_ioi(1.0, step_index=0, profile=p) == 1.0

    def test_swing_even_gets_long(self):
        p = GrooveProfile(groove_type="swing", swing_ratio=1.5)
        even = apply_groove_to_ioi(0.5, step_index=0, profile=p, tempo_bpm=120.0)
        odd = apply_groove_to_ioi(0.5, step_index=1, profile=p, tempo_bpm=120.0)
        assert even > odd
        assert abs(even + odd - 1.0) < 1e-6

    def test_push_shortens_ioi(self):
        p = GrooveProfile(groove_type="push", push_pull_ms=-10.0)
        result = apply_groove_to_ioi(1.0, step_index=0, profile=p, tempo_bpm=120.0)
        assert result < 1.0

    def test_pull_lengthens_ioi(self):
        p = GrooveProfile(groove_type="pull", push_pull_ms=10.0)
        result = apply_groove_to_ioi(1.0, step_index=0, profile=p, tempo_bpm=120.0)
        assert result > 1.0

    def test_never_negative(self):
        p = GrooveProfile(groove_type="push", push_pull_ms=-500.0)
        result = apply_groove_to_ioi(0.1, step_index=0, profile=p, tempo_bpm=120.0)
        assert result >= 0.0625


# ---------------------------------------------------------------------------
# Microtiming
# ---------------------------------------------------------------------------


class TestMicrotiming:
    def test_zero_depth_zero_offset(self):
        p = GrooveProfile(groove_type="straight", microtiming_depth=0.0)
        assert microtiming_offset_ms(step_index=0, profile=p) == 0.0

    def test_deterministic(self):
        p = GrooveProfile(groove_type="swing", microtiming_depth=0.5)
        a = microtiming_offset_ms(step_index=3, profile=p, seed=42)
        b = microtiming_offset_ms(step_index=3, profile=p, seed=42)
        assert a == b

    def test_different_steps_differ(self):
        p = GrooveProfile(groove_type="swing", microtiming_depth=0.5)
        offsets = {microtiming_offset_ms(step_index=i, profile=p) for i in range(16)}
        assert len(offsets) > 1

    def test_max_range(self):
        p = GrooveProfile(groove_type="straight", microtiming_depth=1.0)
        for i in range(100):
            offset = microtiming_offset_ms(step_index=i, profile=p)
            assert -15.0 <= offset <= 15.0

    def test_depth_scales_range(self):
        p_low = GrooveProfile(groove_type="straight", microtiming_depth=0.1)
        p_high = GrooveProfile(groove_type="straight", microtiming_depth=1.0)
        low_max = max(abs(microtiming_offset_ms(step_index=i, profile=p_low)) for i in range(200))
        high_max = max(abs(microtiming_offset_ms(step_index=i, profile=p_high)) for i in range(200))
        assert high_max > low_max


# ---------------------------------------------------------------------------
# Breath points
# ---------------------------------------------------------------------------


class TestBreathPoints:
    def test_profile_breath_points_filtered(self):
        p = GrooveProfile(groove_type="straight", breath_points=(3, 7, 15))
        bps = breath_points_for_phrase(8, p)
        assert bps == (3, 7)
        assert 15 not in bps

    def test_default_long_phrase(self):
        p = GrooveProfile(groove_type="straight")
        bps = breath_points_for_phrase(16, p)
        assert len(bps) == 2
        assert bps == (4, 12)

    def test_default_medium_phrase(self):
        p = GrooveProfile(groove_type="straight")
        bps = breath_points_for_phrase(6, p)
        assert bps == (3,)

    def test_default_short_phrase(self):
        p = GrooveProfile(groove_type="straight")
        bps = breath_points_for_phrase(2, p)
        assert bps == ()

    def test_is_breath_beat(self):
        assert is_breath_beat(3, (3, 7))
        assert is_breath_beat(7, (3, 7))
        assert not is_breath_beat(4, (3, 7))


# ---------------------------------------------------------------------------
# Polyrhythm
# ---------------------------------------------------------------------------


class TestPolyrhythm:
    def test_3_against_4(self):
        mask = polyrhythm_accent_mask(12, (3, 4))
        assert mask[0] is True   # both grids start here
        assert mask[3] is True   # 3-grid
        assert mask[4] is True   # 4-grid
        assert mask[6] is True   # 3-grid
        assert mask[8] is True   # 4-grid
        assert mask[9] is True   # 3-grid
        # count total accents: 0,3,4,6,8,9 = 6 unique positions
        assert sum(mask) == 6

    def test_all_accented_when_1_1(self):
        mask = polyrhythm_accent_mask(8, (1, 1))
        assert all(mask)

    def test_5_against_4(self):
        mask = polyrhythm_accent_mask(20, (5, 4))
        # At position 0: both fire
        assert mask[0] is True
        # At position 4: 4-grid fires
        assert mask[4] is True
        # At position 5: 5-grid fires
        assert mask[5] is True

    def test_cycle_length_is_lcm(self):
        assert polyrhythm_cycle_length((3, 4)) == 12
        assert polyrhythm_cycle_length((5, 4)) == 20


# ---------------------------------------------------------------------------
# Polymeter
# ---------------------------------------------------------------------------


class TestPolymeter:
    def test_aligned_at_zero(self):
        phase = polymeter_phase_offset(0, (3, 4))
        assert phase == 0.0

    def test_varies_over_cycle(self):
        phases = [polymeter_phase_offset(i, (3, 4)) for i in range(12)]
        assert max(phases) > 0.0
        # Should realign at LCM
        assert phases[0] == 0.0

    def test_same_meter_always_zero(self):
        for i in range(20):
            assert polymeter_phase_offset(i, (4, 4)) == 0.0


# ---------------------------------------------------------------------------
# Entrainment
# ---------------------------------------------------------------------------


class TestEntrainment:
    def test_no_entrainment_passthrough(self):
        assert entrainment_tempo_nudge(120.0, None) == 120.0

    def test_nudge_toward_target(self):
        result = entrainment_tempo_nudge(120.0, 72.0, strength=0.15)
        # 72 * 2 = 144 is nearest harmonic
        assert 120.0 < result < 144.0

    def test_strength_zero_no_change(self):
        result = entrainment_tempo_nudge(120.0, 72.0, strength=0.0)
        assert result == 120.0

    def test_strength_one_snaps(self):
        result = entrainment_tempo_nudge(120.0, 72.0, strength=1.0)
        assert abs(result - 144.0) < 0.01


# ---------------------------------------------------------------------------
# Step metadata
# ---------------------------------------------------------------------------


class TestGrooveMetadataForStep:
    def test_straight_minimal_keys(self):
        p = GrooveProfile(groove_type="straight", section_identity="test")
        meta = groove_metadata_for_step(step_index=0, profile=p)
        assert meta["groove_type"] == "straight"
        assert meta["groove_section_identity"] == "test"
        assert "groove_swing_ratio" not in meta

    def test_swing_includes_ratio_and_position(self):
        p = GrooveProfile(groove_type="swing", swing_ratio=1.5, section_identity="dance")
        even = groove_metadata_for_step(step_index=0, profile=p)
        odd = groove_metadata_for_step(step_index=1, profile=p)
        assert even["groove_swing_ratio"] == "1.500"
        assert even["groove_swing_position"] == "long"
        assert odd["groove_swing_position"] == "short"

    def test_push_pull_present(self):
        p = GrooveProfile(groove_type="push", push_pull_ms=-10.0)
        meta = groove_metadata_for_step(step_index=0, profile=p)
        assert meta["groove_push_pull_ms"] == "-10.0"

    def test_microtiming_present(self):
        p = GrooveProfile(groove_type="straight", microtiming_depth=0.5)
        meta = groove_metadata_for_step(step_index=5, profile=p)
        assert "groove_microtiming_ms" in meta

    def test_breath_marked(self):
        p = GrooveProfile(groove_type="straight", breath_points=(3, 7))
        meta_3 = groove_metadata_for_step(step_index=3, profile=p, phrase_length_beats=8)
        meta_4 = groove_metadata_for_step(step_index=4, profile=p, phrase_length_beats=8)
        assert meta_3.get("groove_breath") == "true"
        assert "groove_breath" not in meta_4

    def test_polyrhythm_metadata(self):
        p = GrooveProfile(groove_type="straight", polyrhythm=(3, 4))
        meta = groove_metadata_for_step(step_index=3, profile=p)
        assert meta["groove_polyrhythm"] == "3:4"
        assert meta.get("groove_polyrhythm_accent") == "true"

    def test_polymeter_metadata(self):
        p = GrooveProfile(groove_type="straight", polymeter=(3, 4))
        meta = groove_metadata_for_step(step_index=2, profile=p)
        assert meta["groove_polymeter"] == "3:4"
        assert "groove_polymeter_phase" in meta

    def test_entrainment_metadata(self):
        p = GrooveProfile(groove_type="straight", entrainment_bpm=72.0)
        meta = groove_metadata_for_step(step_index=0, profile=p)
        assert meta["groove_entrainment_bpm"] == "72.0"

    def test_all_values_are_strings(self):
        p = GrooveProfile(
            groove_type="swing",
            swing_ratio=1.5,
            push_pull_ms=-5.0,
            microtiming_depth=0.4,
            polyrhythm=(3, 4),
            polymeter=(3, 4),
            entrainment_bpm=72.0,
            breath_points=(0,),
            section_identity="full",
        )
        meta = groove_metadata_for_step(step_index=0, profile=p, phrase_length_beats=8)
        for key, value in meta.items():
            assert isinstance(key, str), f"key {key!r} is not str"
            assert isinstance(value, str), f"value for {key!r} is not str: {value!r}"


# ---------------------------------------------------------------------------
# Friberg/Sundström tempo-dependent swing
# ---------------------------------------------------------------------------


class TestFribergSwingRatio:
    def test_slow_tempo_high_ratio(self):
        ratio = friberg_swing_ratio(80.0)
        assert ratio == 3.5  # clamped at max

    def test_moderate_tempo(self):
        ratio = friberg_swing_ratio(150.0)
        assert 2.5 < ratio < 3.5

    def test_fast_tempo_approaches_straight(self):
        ratio = friberg_swing_ratio(280.0)
        assert 1.0 < ratio < 1.5

    def test_very_fast_is_straight(self):
        assert friberg_swing_ratio(600.0) == 1.0

    def test_ratio_decreases_with_tempo(self):
        tempi = [80, 100, 120, 150, 200, 250, 300]
        ratios = [friberg_swing_ratio(t) for t in tempi]
        for i in range(len(ratios) - 1):
            assert ratios[i] >= ratios[i + 1], (
                f"ratio should decrease: {tempi[i]}={ratios[i]} vs "
                f"{tempi[i+1]}={ratios[i+1]}"
            )

    def test_max_ratio_clamp(self):
        assert friberg_swing_ratio(40.0) == 3.5

    def test_custom_max_ratio(self):
        assert friberg_swing_ratio(40.0, max_ratio=2.0) == 2.0

    def test_custom_short_note(self):
        ratio_100 = friberg_swing_ratio(200.0, short_note_ms=100.0)
        ratio_80 = friberg_swing_ratio(200.0, short_note_ms=80.0)
        assert ratio_80 > ratio_100

    def test_zero_tempo_returns_max(self):
        assert friberg_swing_ratio(0.0) == 3.5


class TestFribergShortNoteInvariance:
    def test_short_note_near_100ms_in_unclamped_range(self):
        for bpm in (140, 150, 180, 200, 250):
            ratio = friberg_swing_ratio(float(bpm))
            short_ms = friberg_short_note_ms(float(bpm), ratio)
            assert 90.0 <= short_ms <= 110.0, (
                f"short note at {bpm} BPM = {short_ms:.1f} ms (ratio {ratio:.2f})"
            )

    def test_short_note_exact_at_unclamped_tempi(self):
        for bpm in (150, 180, 200, 250):
            ratio = friberg_swing_ratio(float(bpm))
            if ratio < 3.5:
                short_ms = friberg_short_note_ms(float(bpm), ratio)
                assert abs(short_ms - 100.0) < 0.01, (
                    f"unclamped short note at {bpm} BPM = {short_ms:.1f} ms"
                )

    def test_clamped_tempi_short_note_degrades_gracefully(self):
        for bpm in (80, 100, 120):
            ratio = friberg_swing_ratio(float(bpm))
            short_ms = friberg_short_note_ms(float(bpm), ratio)
            assert short_ms >= 100.0, (
                f"clamped short note at {bpm} BPM should be >= 100 ms, got {short_ms:.1f}"
            )


class TestTempoSwingRatio:
    def test_default_role_matches_friberg(self):
        for bpm in (100, 150, 200):
            assert tempo_swing_ratio(float(bpm)) == friberg_swing_ratio(float(bpm))

    def test_ride_role_wider(self):
        base = friberg_swing_ratio(150.0)
        ride = tempo_swing_ratio(150.0, role="ride")
        assert ride > base

    def test_cymbal_uses_ride_style(self):
        assert tempo_swing_ratio(150.0, role="cymbal") == tempo_swing_ratio(
            150.0, role="ride"
        )

    def test_benadon_clamp_low(self):
        ratio = tempo_swing_ratio(280.0, role="melody")
        assert ratio >= 1.2

    def test_benadon_clamp_high(self):
        ratio = tempo_swing_ratio(100.0, role="solo")
        assert ratio <= 1.7

    def test_unknown_role_uses_default(self):
        assert tempo_swing_ratio(150.0, role="bass") == friberg_swing_ratio(150.0)


class TestApplyGrooveTempoDependent:
    def test_tempo_dependent_varies_with_tempo(self):
        p = GrooveProfile(groove_type="swing", tempo_dependent_swing=True)
        slow = apply_groove_to_ioi(0.5, step_index=0, profile=p, tempo_bpm=80.0)
        fast = apply_groove_to_ioi(0.5, step_index=0, profile=p, tempo_bpm=250.0)
        assert slow > fast

    def test_tempo_dependent_straight_at_high_tempo(self):
        p = GrooveProfile(groove_type="swing", tempo_dependent_swing=True)
        even = apply_groove_to_ioi(0.5, step_index=0, profile=p, tempo_bpm=600.0)
        odd = apply_groove_to_ioi(0.5, step_index=1, profile=p, tempo_bpm=600.0)
        assert even == odd == 0.5

    def test_role_override_in_apply(self):
        p = GrooveProfile(groove_type="swing", tempo_dependent_swing=True)
        default = apply_groove_to_ioi(
            0.5, step_index=0, profile=p, tempo_bpm=150.0,
        )
        ride = apply_groove_to_ioi(
            0.5, step_index=0, profile=p, tempo_bpm=150.0, role="ride",
        )
        assert ride > default

    def test_fixed_profile_ignores_tempo(self):
        p = GrooveProfile(groove_type="swing", swing_ratio=1.5)
        slow = apply_groove_to_ioi(0.5, step_index=0, profile=p, tempo_bpm=80.0)
        fast = apply_groove_to_ioi(0.5, step_index=0, profile=p, tempo_bpm=250.0)
        assert slow == fast

    def test_metadata_shows_tempo_swing(self):
        p = GrooveProfile(
            groove_type="swing",
            tempo_dependent_swing=True,
            section_identity="test",
        )
        meta = groove_metadata_for_step(step_index=0, profile=p, tempo_bpm=120.0)
        assert meta.get("groove_tempo_swing") == "true"
        assert "groove_swing_ratio" in meta
        expected_ratio = friberg_swing_ratio(120.0)
        assert abs(float(meta["groove_swing_ratio"]) - expected_ratio) < 0.001


# ---------------------------------------------------------------------------
# Integration: groove flows through tracker scene
# ---------------------------------------------------------------------------


class TestTrackerGrooveIntegration:
    """Verify groove metadata propagates through build_scene_from_score."""

    def _sample_score(self):  # -> Score
        from senseweave.generative_scores import Note, Phrase, Score
        return Score(
            phrases=[
                Phrase(
                    notes=[Note(1, 1.0, False), Note(3, 0.5, True), Note(5, 1.5, False)],
                    voice="pluck",
                    dynamic="mf",
                    role="melody",
                ),
            ],
            key="C",
            tempo_bpm=96.0,
            mood="calm",
            created_at=0.0,
        )

    def test_scene_has_groove_type(self):
        from senseweave.music_tracker import build_scene_from_score
        scene = build_scene_from_score(
            self._sample_score(),
            name="Test",
            scene_metadata={"groove_family": "rolling"},
        )
        assert scene.metadata.get("groove_type") == "lilt"
        assert scene.metadata.get("groove_section_identity") == "rolling"

    def test_steps_carry_groove_metadata(self):
        from senseweave.music_tracker import build_scene_from_score
        scene = build_scene_from_score(
            self._sample_score(),
            name="Test",
            scene_metadata={"groove_identity": "dance"},
        )
        for lane in scene.pattern.lanes:
            for step in lane.steps:
                assert "groove_type" in step.metadata
                assert step.metadata["groove_type"] == "swing"

    def test_swing_ratio_in_scene_metadata(self):
        from senseweave.music_tracker import build_scene_from_score
        scene = build_scene_from_score(
            self._sample_score(),
            name="Test",
            scene_metadata={"groove_identity": "dance"},
        )
        assert "groove_swing_ratio" in scene.metadata

    def test_no_swing_ratio_for_straight(self):
        from senseweave.music_tracker import build_scene_from_score
        scene = build_scene_from_score(
            self._sample_score(),
            name="Test",
            scene_metadata={"groove_state": "static"},
        )
        assert "groove_swing_ratio" not in scene.metadata

    def test_default_groove_when_no_metadata(self):
        from senseweave.music_tracker import build_scene_from_score
        scene = build_scene_from_score(
            self._sample_score(),
            name="Test",
        )
        assert scene.metadata.get("groove_type") == "straight"
        assert scene.metadata.get("groove_section_identity") == "default"


# ---------------------------------------------------------------------------
# End-to-end: one groove profile through timing, metadata, and tracker scene
# ---------------------------------------------------------------------------


class GrooveEngineEndToEndTests:
    """Drive the public groove path through a deterministic tracker scene."""

    __test__ = True

    def _multi_lane_score(self):  # -> Score
        from senseweave.generative_scores import Note, Phrase, Score

        return Score(
            phrases=[
                Phrase(
                    notes=[
                        Note(1, 1.0, True),
                        Note(3, 1.0, False),
                        Note(5, 2.0, True),
                    ],
                    voice="pluck",
                    dynamic="mf",
                    role="melody",
                ),
                Phrase(
                    notes=[
                        Note(1, 2.0, False),
                        Note(5, 2.0, True),
                    ],
                    voice="pad",
                    dynamic="mp",
                    role="color",
                ),
            ],
            key="C",
            tempo_bpm=120.0,
            mood="focused",
            created_at=0.0,
        )

    def test_profile_lookup_with_entrainment_preserves_registered_shape(self):
        profile = groove_for_section(groove_identity="dance", entrainment_bpm=72.0)
        long_ioi = apply_groove_to_ioi(
            0.5,
            step_index=0,
            profile=profile,
            tempo_bpm=120.0,
            role="melody",
        )
        short_ioi = apply_groove_to_ioi(
            0.5,
            step_index=1,
            profile=profile,
            tempo_bpm=120.0,
            role="melody",
        )
        nudged_tempo = entrainment_tempo_nudge(120.0, profile.entrainment_bpm)

        assert profile.section_identity == "dance"
        assert profile.groove_type == "swing"
        assert profile.entrainment_bpm == 72.0
        assert profile.subdivision == "swing"
        assert profile.groove_timing == "swing"
        assert profile.syncopation_intensity > 0.0
        assert profile.lane_phase_offsets == (0, 1, 2, 0, 1)
        assert long_ioi > short_ioi
        assert 120.0 < nudged_tempo < 144.0

    def test_policy_metadata_timing_summary_is_json_safe(self):
        base_profile = groove_for_section(groove_identity="dance", entrainment_bpm=72.0)
        policy = meter_policy_for_phase("Convergence")
        profile = GrooveProfile(
            groove_type=base_profile.groove_type,
            swing_ratio=base_profile.swing_ratio,
            push_pull_ms=base_profile.push_pull_ms,
            microtiming_depth=base_profile.microtiming_depth,
            polyrhythm=policy.polyrhythm,
            polymeter=base_profile.polymeter,
            entrainment_bpm=base_profile.entrainment_bpm,
            breath_points=base_profile.breath_points,
            section_identity=base_profile.section_identity,
            meter=policy.meter,
            subdivision=policy.subdivision,
            groove_timing=policy.groove_timing,
            phrase_breath=policy.phrase_breath,
            metric_modulation=policy.metric_modulation,
            syncopation_intensity=base_profile.syncopation_intensity,
            lane_phase_offsets=base_profile.lane_phase_offsets,
        )
        even_ioi = apply_groove_to_ioi(
            0.5,
            step_index=0,
            profile=profile,
            tempo_bpm=120.0,
            role="melody",
        )
        odd_ioi = apply_groove_to_ioi(
            0.5,
            step_index=1,
            profile=profile,
            tempo_bpm=120.0,
            role="melody",
        )
        metadata = groove_metadata_for_step(
            step_index=0,
            profile=profile,
            tempo_bpm=120.0,
            phrase_length_beats=8,
            role="melody",
        )
        summary = {
            "identity": profile.section_identity,
            "nudged_tempo": entrainment_tempo_nudge(120.0, profile.entrainment_bpm),
            "ioi_pair": [even_ioi, odd_ioi],
            "metadata": metadata,
        }

        round_trip = json.loads(json.dumps(summary, sort_keys=True))
        assert round_trip["identity"] == "dance"
        assert round_trip["metadata"]["groove_meter"] == "7/8"
        assert round_trip["metadata"]["groove_subdivision"] == "polyrhythmic"
        assert round_trip["metadata"]["groove_polyrhythm"] == "3:4"
        assert round_trip["metadata"]["groove_metric_modulation"] == "7:8"
        assert round_trip["metadata"]["groove_entrainment_bpm"] == "72.0"
        assert round_trip["ioi_pair"][0] > round_trip["ioi_pair"][1]

    def test_tracker_scene_uses_profile_offsets_and_arc_meter_policy(self):
        from senseweave.music_tracker import build_scene_from_score

        scene = build_scene_from_score(
            self._multi_lane_score(),
            name="Convergence",
            scene_metadata={
                "groove_identity": "dance",
                "arc_phase": "Convergence",
            },
        )
        melody_lane = next(lane for lane in scene.pattern.lanes if lane.role == "melody")
        color_lane = next(lane for lane in scene.pattern.lanes if lane.role == "color")
        all_step_metadata = [
            step.metadata for lane in scene.pattern.lanes for step in lane.steps
        ]

        assert scene.metadata["groove_type"] == "swing"
        assert scene.metadata["groove_section_identity"] == "dance"
        assert scene.metadata["groove_meter"] == "7/8"
        assert scene.metadata["groove_subdivision"] == "polyrhythmic"
        assert scene.metadata["groove_metric_modulation"] == "7:8"
        assert melody_lane.steps[0].row == 1
        assert color_lane.steps[0].row == 0
        assert all(step.length_rows > 0 for lane in scene.pattern.lanes for step in lane.steps)
        assert any(meta.get("groove_polyrhythm") == "3:4" for meta in all_step_metadata)
        assert all(
            isinstance(key, str) and isinstance(value, str)
            for meta in all_step_metadata
            for key, value in meta.items()
        )
