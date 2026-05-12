from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from inner_life.world_model import WorldModel
from senseweave.form_grammar import minimum_function_count, plan_form
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece


def _brief_for(*, cadence_state: str, hour: int, narrative_pressure: float = 0.35):
    commission = commission_piece(
        cadence_state=cadence_state,
        day_phase="day" if hour < 18 else "late_evening",
        weekly_phase="midweek",
        attention_score=0.48,
        narrative_pressure=narrative_pressure,
        song_num=5,
        hour=hour,
    )
    world = WorldModel(
        observer_description="quiet room, lamp, long hallway",
        cadence_state=cadence_state,
        day_phase="day" if hour < 18 else "late_evening",
        time_of_day="day" if hour < 18 else "night",
        occupancy_state="occupied_quiet",
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="drift",
        cadence_state=cadence_state,
        progression_profile="settling",
    )
    return commission, brief


def test_hook_led_song_form_has_early_arrival_and_minimum_complexity() -> None:
    commission, brief = _brief_for(cadence_state="occupied_day", hour=14)
    plan = plan_form(commission=commission, brief=brief, family="bloom")

    assert len(plan.sections) >= minimum_function_count(plan.form_class)
    arrival_indices = [i for i, section in enumerate(plan.sections) if section.function == "arrival"]
    assert arrival_indices
    assert arrival_indices[0] <= max(1, int(len(plan.sections) * 0.4))
    assert len({section.scene_name for section in plan.sections}) == len(plan.sections)


def test_extended_form_uses_more_sections_than_song_form() -> None:
    long_commission, long_brief = _brief_for(cadence_state="wind_down", hour=23, narrative_pressure=0.9)
    long_plan = plan_form(commission=long_commission, brief=long_brief, family="nocturne")
    short_commission, short_brief = _brief_for(cadence_state="occupied_day", hour=14, narrative_pressure=0.2)
    short_plan = plan_form(commission=short_commission, brief=short_brief, family="ember")

    assert len(long_plan.sections) >= len(short_plan.sections)
    assert sum(section.target_duration_s for section in long_plan.sections) > sum(
        section.target_duration_s for section in short_plan.sections
    )
