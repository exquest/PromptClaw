"""Tests for Korsakov Ch.6 orchestral form module."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.synthesis.orchestral_form import (
    ArticulationPair,
    EffectBudget,
    TuttiRole,
    assign_tutti_roles,
    plan_converging_diminuendo,
    plan_diverging_crescendo,
    select_sfp_pair,
    should_insert_silence,
    silence_duration_beats,
    suggest_reentry_voice,
    suggest_tint,
    tint_texture,
    voices_for_role,
)


class TestTuttiRoles:
    def test_assign_all_voices(self):
        roles = assign_tutti_roles(["gong", "bowed", "pluck", "kotekan", "choir", "bell", "breath"])
        assert roles["gong"] == TuttiRole.FOUNDATION
        assert roles["pluck"] == TuttiRole.FIGURATION
        assert roles["choir"] == TuttiRole.MELODY
        assert roles["breath"] == TuttiRole.COLOR

    def test_assign_subset(self):
        roles = assign_tutti_roles(["pluck", "bell"])
        assert len(roles) == 2
        assert roles["pluck"] == TuttiRole.FIGURATION
        assert roles["bell"] == TuttiRole.MELODY

    def test_unknown_voice_gets_color(self):
        roles = assign_tutti_roles(["unknown_voice"])
        assert roles["unknown_voice"] == TuttiRole.COLOR

    def test_voices_for_role_foundation(self):
        roles = assign_tutti_roles(["gong", "bowed", "pluck", "choir"])
        found = voices_for_role(roles, TuttiRole.FOUNDATION)
        assert "gong" in found
        assert "bowed" in found
        assert "pluck" not in found

    def test_voices_for_role_empty(self):
        roles = assign_tutti_roles(["pluck", "kotekan"])
        found = voices_for_role(roles, TuttiRole.FOUNDATION)
        assert found == []


class TestDivergingCrescendo:
    def test_basic_crescendo(self):
        plan = plan_diverging_crescendo(8)
        assert len(plan) == 8
        # First bars: center voices only
        assert "bowed" in plan[0]
        assert "choir" in plan[0]
        # Last bars: all voices
        assert len(plan[-1]) >= 5

    def test_center_first(self):
        plan = plan_diverging_crescendo(4)
        # First bar has mid-range voices
        assert "bowed" in plan[0] or "choir" in plan[0]
        # Gong and kotekan appear later
        first_bar_has_extremes = "gong" in plan[0] and "kotekan" in plan[0]
        assert not first_bar_has_extremes

    def test_expands_outward(self):
        plan = plan_diverging_crescendo(12)
        # Voice count should increase
        assert len(plan[0]) <= len(plan[-1])

    def test_zero_bars(self):
        assert plan_diverging_crescendo(0) == []

    def test_one_bar(self):
        plan = plan_diverging_crescendo(1)
        assert len(plan) == 1


class TestConvergingDiminuendo:
    def test_basic_diminuendo(self):
        plan = plan_converging_diminuendo(8)
        assert len(plan) == 8
        # First bars: full voices
        assert len(plan[0]) >= 5
        # Last bars: fewer voices
        assert len(plan[-1]) <= len(plan[0])

    def test_strips_extremes_first(self):
        plan = plan_converging_diminuendo(12)
        # Breath (color) should disappear first
        # Center voices (bowed, choir) should remain longest
        last_bar = plan[-1]
        if last_bar:  # might be empty
            assert "bowed" in last_bar or "choir" in last_bar

    def test_zero_bars(self):
        assert plan_converging_diminuendo(0) == []


class TestSfpPairs:
    def test_default_is_warm(self):
        pair = select_sfp_pair("calm")
        assert pair.attack_voice == "pluck"
        assert pair.sustain_voice == "choir"

    def test_excited_is_dramatic(self):
        pair = select_sfp_pair("excited")
        assert pair.attack_voice == "gong"

    def test_pair_has_amplitude_contrast(self):
        pair = select_sfp_pair()
        assert pair.attack_amp > pair.sustain_amp

    def test_articulation_pair_fields(self):
        pair = ArticulationPair("pluck", "choir")
        assert pair.attack_release < pair.sustain_release


class TestTimbralTinting:
    def test_tint_new_voice(self):
        voice, amp = tint_texture(["pluck", "bowed"], "breath", 0.15)
        assert voice == "breath"
        assert amp == 0.15

    def test_tint_existing_voice_no_effect(self):
        voice, amp = tint_texture(["pluck", "breath"], "breath", 0.15)
        assert amp == 0.0  # Already present

    def test_suggest_tint_per_movement(self):
        assert suggest_tint("Emergence") == "breath"
        assert suggest_tint("Development") == "kotekan"
        assert suggest_tint("Resolution") == "breath"


class TestEffectBudget:
    def test_tremolo_not_available_in_emergence(self):
        budget = EffectBudget()
        assert budget.can_use("tremolo", 0) is False
        assert budget.can_use("tremolo", 2) is True

    def test_tutti_only_in_development(self):
        budget = EffectBudget()
        assert budget.can_use("tutti", 1) is False
        assert budget.can_use("tutti", 2) is True

    def test_new_timbre_reserved_for_resolution(self):
        budget = EffectBudget()
        assert budget.can_use("new_timbre", 3) is False
        assert budget.can_use("new_timbre", 4) is True

    def test_spend_marks_used(self):
        budget = EffectBudget()
        assert budget.tremolo_used is False
        budget.spend("tremolo")
        assert budget.tremolo_used is True

    def test_reset_clears_all(self):
        budget = EffectBudget()
        budget.spend("tremolo")
        budget.spend("fusion")
        budget.reset()
        assert budget.tremolo_used is False
        assert budget.fusion_used is False

    def test_tinting_available_from_theme(self):
        budget = EffectBudget()
        assert budget.can_use("tinting", 0) is False
        assert budget.can_use("tinting", 1) is True


class TestPostTuttiSilence:
    def test_silence_after_tutti(self):
        assert should_insert_silence(7, 2) is True

    def test_no_silence_without_tutti(self):
        assert should_insert_silence(3, 2) is False

    def test_no_silence_staying_in_tutti(self):
        assert should_insert_silence(6, 6) is False

    def test_silence_duration_scales(self):
        assert silence_duration_beats(7) == 3
        assert silence_duration_beats(5) == 2
        assert silence_duration_beats(3) == 1

    def test_reentry_is_lightest(self):
        assert suggest_reentry_voice() == "breath"
