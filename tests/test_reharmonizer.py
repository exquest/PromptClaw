"""Tests for reharmonizer.py -- functional harmony and section plans."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.reharmonizer import (
    reharm_plan_for_song,
    progression_bank_for_section,
)


def test_reharm_plan_assigns_functions_to_sections() -> None:
    plan = reharm_plan_for_song(
        progression_profile="open_day",
        family="bloom",
        cadence_state="occupied_day",
        mode="ionian",
        song_num=3,
    )

    assert plan.sections["Theme"].function in {"tonic", "predominant"}
    assert plan.sections["Development"].function in {"predominant", "dominant"}
    assert plan.sections["Recap"].cadence in {"authentic", "deceptive", "plagal"}


def test_away_practice_uses_more_adventurous_reharm_strategy() -> None:
    plan = reharm_plan_for_song(
        progression_profile="experiment",
        family="forge",
        cadence_state="away_practice",
        mode="harmonic_minor",
        song_num=7,
    )

    assert plan.strategy in {"modal_interchange", "secondary_push", "approach_chain"}
    assert plan.study_focus in {"harmony_lab", "scene_lab", "ear_lab"}


def test_progression_bank_matches_section_function() -> None:
    plan = reharm_plan_for_song(
        progression_profile="settling",
        family="drift",
        cadence_state="wind_down",
        mode="aeolian",
        song_num=5,
    )

    theme_bank = progression_bank_for_section("Theme", plan)
    resolution_bank = progression_bank_for_section("Resolution", plan)

    assert theme_bank
    assert resolution_bank
    assert any(1 in progression for progression in resolution_bank)
