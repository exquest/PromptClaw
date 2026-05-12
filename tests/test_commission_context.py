from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from inner_life.world_model import WorldModel
from senseweave.commission_context import commission_context_from_tracker_plan


def test_commission_context_falls_back_to_world_when_tracker_plan_is_minimal() -> None:
    tracker_plan = SimpleNamespace(
        cadence_state="occupied_day",
        occupancy_state="occupied_quiet",
        family="drift",
        progression_profile="lift",
    )
    world = WorldModel(day_phase="late_afternoon", weekly_phase="friday_lift")

    day_phase, weekly_phase = commission_context_from_tracker_plan(
        tracker_plan=tracker_plan,
        world=world,
    )

    assert day_phase == "late_afternoon"
    assert weekly_phase == "friday_lift"


def test_commission_context_prefers_tracker_plan_when_available() -> None:
    tracker_plan = SimpleNamespace(
        cadence_state="occupied_day",
        occupancy_state="occupied_quiet",
        family="drift",
        progression_profile="lift",
        day_phase="midday",
        weekly_phase="core_weekday",
    )
    world = WorldModel(day_phase="late_afternoon", weekly_phase="friday_lift")

    day_phase, weekly_phase = commission_context_from_tracker_plan(
        tracker_plan=tracker_plan,
        world=world,
    )

    assert day_phase == "midday"
    assert weekly_phase == "core_weekday"
