"""Depth-2 commission_context helpers — locked test surface for frac-0008."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from inner_life.world_model import WorldModel  # noqa: E402
from senseweave.commission_context import (  # noqa: E402
    CommissionInputs,
    attention_pressure_from_world,
    commission_context_from_tracker_plan,
    commission_inputs_from_tracker_plan,
    summarize_commission_context,
)


def test_commission_context_prefers_tracker_then_world_then_default() -> None:
    tracker_only = SimpleNamespace(day_phase="midday", weekly_phase="core_weekday")
    world_only = WorldModel(day_phase="late_afternoon", weekly_phase="friday_lift")
    blank_tracker = SimpleNamespace(day_phase="   ", weekly_phase="   ")
    blank_world = WorldModel(day_phase="", weekly_phase="")

    assert commission_context_from_tracker_plan(
        tracker_plan=tracker_only, world=world_only,
    ) == ("midday", "core_weekday")
    assert commission_context_from_tracker_plan(
        tracker_plan=SimpleNamespace(), world=world_only,
    ) == ("late_afternoon", "friday_lift")
    assert commission_context_from_tracker_plan(
        tracker_plan=blank_tracker, world=world_only,
    ) == ("late_afternoon", "friday_lift")
    assert commission_context_from_tracker_plan(
        tracker_plan=SimpleNamespace(), world=blank_world,
    ) == ("day", "")


def test_attention_pressure_clamps_to_unit_interval() -> None:
    high = WorldModel(attention_score=1.5, experimentation_bias=0.42)
    low = WorldModel(attention_score=-0.2, experimentation_bias=-3.0)
    mid = WorldModel(attention_score=0.5, experimentation_bias=0.25)

    assert attention_pressure_from_world(high) == (1.0, 0.42)
    assert attention_pressure_from_world(low) == (0.0, 0.0)
    assert attention_pressure_from_world(mid) == (0.5, 0.25)


def test_attention_pressure_handles_malformed_inputs() -> None:
    bad = SimpleNamespace(attention_score="oops", experimentation_bias=None)
    missing = SimpleNamespace()

    assert attention_pressure_from_world(bad) == (0.0, 0.0)
    assert attention_pressure_from_world(missing) == (0.0, 0.0)


def test_commission_inputs_bundle_populates_all_fields() -> None:
    tracker_plan = SimpleNamespace(
        cadence_state="occupied_day",
        occupancy_state="occupied_quiet",
        family="bloom",
        progression_profile="open_day",
        day_phase="late_afternoon",
        weekly_phase="friday_lift",
    )
    world = WorldModel(
        day_phase="midday",
        weekly_phase="core_weekday",
        attention_score=0.7,
        experimentation_bias=0.3,
    )

    inputs = commission_inputs_from_tracker_plan(
        tracker_plan=tracker_plan,
        world=world,
        song_num=3,
        hour=17,
    )

    assert isinstance(inputs, CommissionInputs)
    assert inputs.cadence_state == "occupied_day"
    assert inputs.occupancy_state == "occupied_quiet"
    assert inputs.day_phase == "late_afternoon"
    assert inputs.weekly_phase == "friday_lift"
    assert inputs.attention_score == 0.7
    assert inputs.narrative_pressure == 0.3
    assert inputs.song_num == 3
    assert inputs.hour == 17


def test_commission_inputs_defaults_when_tracker_minimal() -> None:
    tracker_plan = SimpleNamespace()
    world = WorldModel(day_phase="", weekly_phase="")

    inputs = commission_inputs_from_tracker_plan(
        tracker_plan=tracker_plan,
        world=world,
        song_num="2",
        hour="9",
    )

    assert inputs.cadence_state == ""
    assert inputs.occupancy_state == "uncertain"
    assert inputs.day_phase == "day"
    assert inputs.weekly_phase == ""
    assert inputs.song_num == 2
    assert inputs.hour == 9


def test_summarize_commission_context_emits_stable_snapshot() -> None:
    inputs = CommissionInputs(
        cadence_state="occupied_day",
        occupancy_state="occupied_quiet",
        day_phase="late_afternoon",
        weekly_phase="friday_lift",
        attention_score=0.72,
        narrative_pressure=0.123456,
        song_num=4,
        hour=17,
    )

    snapshot = summarize_commission_context(inputs)

    assert snapshot == {
        "cadence": "occupied_day",
        "occupancy": "occupied_quiet",
        "day_phase": "late_afternoon",
        "weekly_phase": "friday_lift",
        "song_num": 4,
        "hour": 17,
        "attention": "high",
        "narrative_pressure": 0.123,
    }

    moderate = CommissionInputs(
        cadence_state="",
        occupancy_state="",
        day_phase="",
        weekly_phase="",
        attention_score=0.4,
        narrative_pressure=0.0,
        song_num=1,
        hour=8,
    )
    moderate_snapshot = summarize_commission_context(moderate)
    assert moderate_snapshot["attention"] == "moderate"
    assert moderate_snapshot["cadence"] == "unknown"
    assert moderate_snapshot["occupancy"] == "unknown"
    assert moderate_snapshot["day_phase"] == "day"
    assert moderate_snapshot["weekly_phase"] == "unscheduled"

    low = CommissionInputs(
        cadence_state="sleep",
        occupancy_state="likely_asleep",
        day_phase="pre_dawn",
        weekly_phase="monday_gentle",
        attention_score=0.1,
        narrative_pressure=0.0,
        song_num=1,
        hour=3,
    )
    assert summarize_commission_context(low)["attention"] == "low"
