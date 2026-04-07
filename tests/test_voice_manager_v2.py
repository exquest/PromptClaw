"""Tests for Korsakov Ch.5 orchestral voice combination principles."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.synthesis.voice_manager_v2 import (
    VOICES,
    Voice,
    balance_amplitudes,
    enforce_octave_separation,
    plan_crescendo,
    plan_diminuendo,
    select_voices_for_movement,
    suggest_fusion_pair,
    voice_count_for_movement,
)


class TestVoiceDataclass:
    def test_voice_fields(self):
        v = Voice(
            name="gong",
            synth="sw_gong",
            weight=4.0,
            octave_home=1,
            current_octave=1,
            active=True,
            amplitude=0.1,
        )
        assert v.name == "gong"
        assert v.synth == "sw_gong"
        assert v.weight == 4.0
        assert v.octave_home == 1
        assert v.current_octave == 1
        assert v.active is True
        assert v.amplitude == 0.1

    def test_voice_defaults(self):
        v = Voice(
            name="pluck",
            synth="sw_pluck",
            weight=1.0,
            octave_home=2,
        )
        assert v.current_octave == 2  # defaults to octave_home
        assert v.active is False
        assert v.amplitude == 0.0


class TestVoicesRegistry:
    def test_all_seven_voices_present(self):
        assert len(VOICES) == 7
        expected = {"gong", "pluck", "bowed", "bell", "kotekan", "choir", "breath"}
        assert set(VOICES.keys()) == expected

    def test_gong_properties(self):
        g = VOICES["gong"]
        assert g.synth == "sw_gong"
        assert g.weight == 4.0
        assert g.octave_home == 1

    def test_pluck_properties(self):
        p = VOICES["pluck"]
        assert p.synth == "sw_pluck"
        assert p.weight == 1.0
        assert p.octave_home == 2

    def test_bowed_properties(self):
        b = VOICES["bowed"]
        assert b.synth == "sw_bowed"
        assert b.weight == 2.0
        assert b.octave_home == 3

    def test_bell_properties(self):
        b = VOICES["bell"]
        assert b.synth == "sw_bell_warm"
        assert b.weight == 1.5
        assert b.octave_home == 4

    def test_kotekan_properties(self):
        k = VOICES["kotekan"]
        assert k.synth == "sw_kotekan"
        assert k.weight == 1.0
        assert k.octave_home == 5

    def test_choir_properties(self):
        c = VOICES["choir"]
        assert c.synth == "sw_choir"
        assert c.weight == 2.0
        assert c.octave_home == 3

    def test_breath_properties(self):
        b = VOICES["breath"]
        assert b.synth == "sw_breath"
        assert b.weight == 0.5
        assert b.octave_home == 4


class TestBalanceAmplitudes:
    def test_total_sums_to_target(self):
        voices = [
            Voice("gong", "sw_gong", 4.0, 1, active=True),
            Voice("pluck", "sw_pluck", 1.0, 2, active=True),
        ]
        result = balance_amplitudes(voices, target_total=0.5)
        total = sum(v.amplitude for v in result)
        assert abs(total - 0.5) < 1e-6

    def test_heavier_voice_quieter(self):
        voices = [
            Voice("gong", "sw_gong", 4.0, 1, active=True),
            Voice("pluck", "sw_pluck", 1.0, 2, active=True),
        ]
        result = balance_amplitudes(voices)
        gong = next(v for v in result if v.name == "gong")
        pluck = next(v for v in result if v.name == "pluck")
        assert gong.amplitude < pluck.amplitude

    def test_single_voice_gets_full_target(self):
        voices = [Voice("bowed", "sw_bowed", 2.0, 3, active=True)]
        result = balance_amplitudes(voices, target_total=0.5)
        assert abs(result[0].amplitude - 0.5) < 1e-6

    def test_empty_voices_returns_empty(self):
        result = balance_amplitudes([], target_total=0.5)
        assert result == []

    def test_equal_weight_equal_amplitude(self):
        voices = [
            Voice("pluck", "sw_pluck", 1.0, 2, active=True),
            Voice("kotekan", "sw_kotekan", 1.0, 5, active=True),
        ]
        result = balance_amplitudes(voices, target_total=0.6)
        assert abs(result[0].amplitude - result[1].amplitude) < 1e-6
        assert abs(result[0].amplitude - 0.3) < 1e-6

    def test_custom_target_total(self):
        voices = [
            Voice("bowed", "sw_bowed", 2.0, 3, active=True),
            Voice("choir", "sw_choir", 2.0, 3, active=True),
        ]
        result = balance_amplitudes(voices, target_total=0.8)
        total = sum(v.amplitude for v in result)
        assert abs(total - 0.8) < 1e-6


class TestEnforceOctaveSeparation:
    def test_no_conflict_unchanged(self):
        voices = [
            Voice("gong", "sw_gong", 4.0, 1, 1, True, 0.1),
            Voice("pluck", "sw_pluck", 1.0, 2, 2, True, 0.2),
        ]
        result = enforce_octave_separation(voices)
        octaves = [v.current_octave for v in result]
        assert octaves[0] != octaves[1]

    def test_conflict_resolved(self):
        voices = [
            Voice("bowed", "sw_bowed", 2.0, 3, 3, True, 0.1),
            Voice("choir", "sw_choir", 2.0, 3, 3, True, 0.1),
        ]
        result = enforce_octave_separation(voices)
        octaves = [v.current_octave for v in result]
        assert octaves[0] != octaves[1]

    def test_lighter_voice_moves(self):
        voices = [
            Voice("gong", "sw_gong", 4.0, 1, 3, True, 0.1),
            Voice("pluck", "sw_pluck", 1.0, 2, 3, True, 0.2),
        ]
        result = enforce_octave_separation(voices)
        gong = next(v for v in result if v.name == "gong")
        pluck = next(v for v in result if v.name == "pluck")
        # Gong is heavier, should stay; pluck should move
        assert gong.current_octave == 3
        assert pluck.current_octave != 3

    def test_octave_stays_in_range(self):
        """Shifted voice should not go below 1 or above 5."""
        voices = [
            Voice("gong", "sw_gong", 4.0, 1, 5, True, 0.1),
            Voice("pluck", "sw_pluck", 1.0, 2, 5, True, 0.2),
        ]
        result = enforce_octave_separation(voices)
        for v in result:
            assert 1 <= v.current_octave <= 5

    def test_single_voice_unchanged(self):
        voices = [Voice("bowed", "sw_bowed", 2.0, 3, 3, True, 0.1)]
        result = enforce_octave_separation(voices)
        assert result[0].current_octave == 3

    def test_three_voices_all_separated(self):
        voices = [
            Voice("gong", "sw_gong", 4.0, 1, 2, True, 0.1),
            Voice("pluck", "sw_pluck", 1.0, 2, 2, True, 0.2),
            Voice("breath", "sw_breath", 0.5, 4, 2, True, 0.1),
        ]
        result = enforce_octave_separation(voices)
        octaves = [v.current_octave for v in result]
        # All should be distinct
        assert len(set(octaves)) == len(octaves)

    def test_custom_min_separation(self):
        voices = [
            Voice("bowed", "sw_bowed", 2.0, 3, 2, True, 0.1),
            Voice("choir", "sw_choir", 2.0, 3, 3, True, 0.1),
        ]
        result = enforce_octave_separation(voices, min_separation=2)
        o1, o2 = result[0].current_octave, result[1].current_octave
        assert abs(o1 - o2) >= 2


class TestPlanCrescendo:
    def test_starts_with_few_ends_with_many(self):
        plan = plan_crescendo(1, 5, 10)
        assert len(plan[0]) <= 2
        assert len(plan[-1]) >= 4

    def test_length_matches_bars(self):
        plan = plan_crescendo(1, 4, 8)
        assert len(plan) == 8

    def test_voices_only_added_never_removed(self):
        plan = plan_crescendo(1, 5, 10)
        for i in range(len(plan) - 1):
            assert len(plan[i]) <= len(plan[i + 1])

    def test_voices_enter_from_bottom_up(self):
        """First voice should be lower register, later entries higher."""
        plan = plan_crescendo(1, 7, 14)
        # The first bar should have the lowest-register voice (gong)
        assert "gong" in plan[0]

    def test_minimal_crescendo(self):
        plan = plan_crescendo(1, 2, 4)
        assert len(plan) == 4
        assert len(plan[0]) >= 1
        assert len(plan[-1]) >= 2

    def test_start_equals_peak(self):
        plan = plan_crescendo(3, 3, 4)
        assert len(plan) == 4
        for bar in plan:
            assert len(bar) == 3


class TestPlanDiminuendo:
    def test_starts_full_ends_sparse(self):
        voices = ["gong", "pluck", "bowed", "bell", "kotekan"]
        plan = plan_diminuendo(voices, 10)
        assert len(plan[0]) >= 4
        assert len(plan[-1]) <= 2

    def test_length_matches_bars(self):
        plan = plan_diminuendo(["gong", "pluck", "bowed"], 6)
        assert len(plan) == 6

    def test_voices_only_removed_never_added(self):
        plan = plan_diminuendo(["gong", "pluck", "bowed", "bell"], 8)
        for i in range(len(plan) - 1):
            assert len(plan[i]) >= len(plan[i + 1])

    def test_top_voices_leave_first(self):
        """Higher-register voices should exit before lower ones."""
        voices = ["gong", "pluck", "bowed", "kotekan"]
        plan = plan_diminuendo(voices, 8)
        # Last bar should have the lowest voice remaining
        assert "gong" in plan[-1]

    def test_single_voice(self):
        plan = plan_diminuendo(["gong"], 4)
        assert len(plan) == 4
        for bar in plan:
            assert len(bar) == 1


class TestSuggestFusionPair:
    def test_calm(self):
        a, b = suggest_fusion_pair("calm")
        assert a == "bowed"
        assert b == "choir"

    def test_excited(self):
        a, b = suggest_fusion_pair("excited")
        assert a == "pluck"
        assert b == "kotekan"

    def test_anxious(self):
        a, b = suggest_fusion_pair("anxious")
        assert a == "breath"
        assert b == "bell"

    def test_unknown_mood_returns_valid_pair(self):
        a, b = suggest_fusion_pair("mysterious")
        assert a in VOICES
        assert b in VOICES
        assert a != b

    def test_all_results_are_known_voices(self):
        for mood in ["calm", "excited", "anxious", "solemn", "playful"]:
            a, b = suggest_fusion_pair(mood)
            assert a in VOICES, f"{a} not in VOICES for mood={mood}"
            assert b in VOICES, f"{b} not in VOICES for mood={mood}"


class TestVoiceCountForMovement:
    def test_emergence(self):
        count = voice_count_for_movement("Emergence")
        assert 1 <= count <= 2

    def test_theme(self):
        count = voice_count_for_movement("Theme")
        assert 2 <= count <= 3

    def test_development(self):
        count = voice_count_for_movement("Development")
        assert 3 <= count <= 5

    def test_recap(self):
        count = voice_count_for_movement("Recap")
        assert 2 <= count <= 3

    def test_resolution(self):
        count = voice_count_for_movement("Resolution")
        assert 1 <= count <= 2

    def test_unknown_movement_returns_sane_default(self):
        count = voice_count_for_movement("UnknownSection")
        assert 1 <= count <= 5

    def test_case_insensitive(self):
        count = voice_count_for_movement("emergence")
        assert 1 <= count <= 2


class TestSelectVoicesForMovement:
    def test_returns_correct_count(self):
        voices = select_voices_for_movement("Theme")
        assert 2 <= len(voices) <= 3

    def test_all_active(self):
        voices = select_voices_for_movement("Development")
        for v in voices:
            assert v.active is True

    def test_amplitudes_balanced(self):
        voices = select_voices_for_movement("Theme")
        total = sum(v.amplitude for v in voices)
        assert total > 0
        assert total <= 1.0

    def test_octaves_separated(self):
        voices = select_voices_for_movement("Development")
        octaves = [v.current_octave for v in voices]
        assert len(set(octaves)) == len(octaves), "Voices share an octave"

    def test_emergence_sparse(self):
        voices = select_voices_for_movement("Emergence")
        assert len(voices) <= 2

    def test_different_key_still_valid(self):
        voices = select_voices_for_movement("Theme", key="G")
        assert len(voices) >= 2
        for v in voices:
            assert v.active is True

    def test_all_voices_are_known(self):
        voices = select_voices_for_movement("Development")
        for v in voices:
            assert v.name in VOICES
