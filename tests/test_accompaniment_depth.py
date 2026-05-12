"""Depth-2 accompaniment report helpers - locked test surface for frac-0029."""
from __future__ import annotations

import dataclasses
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.synthesis.accompaniment import (  # noqa: E402
    AccompanimentPatternSnapshot,
    AccompanimentPlanReport,
    accompaniment_density_band,
    accompaniment_energy_band,
    accompaniment_pattern_name,
    accompaniment_transition_mode,
    arpeggiated,
    breathing_swell,
    build_accompaniment_plan_report,
    build_pattern_snapshot,
    frequency_register_band,
    get_pattern,
    pedal_note,
    select_accompaniment_type,
    should_pedal,
    should_transition_gradually,
    summarize_accompaniment_plan_report,
)


def test_accompaniment_helper_bands_map_values_to_named_outputs() -> None:
    assert accompaniment_density_band(0.0, True) == "resting"
    assert accompaniment_density_band(0.0, False) == "sparse"
    assert accompaniment_density_band(1.0, False) == "sparse"
    assert accompaniment_density_band(1.001, False) == "balanced"
    assert accompaniment_density_band(2.0, False) == "balanced"
    assert accompaniment_density_band(2.001, False) == "busy"
    assert accompaniment_density_band(3.0, False) == "busy"
    assert accompaniment_density_band(3.001, False) == "dense"

    assert accompaniment_pattern_name(1) == "sustained"
    assert accompaniment_pattern_name(2) == "repeated_chords"
    assert accompaniment_pattern_name(3) == "tremolo"
    assert accompaniment_pattern_name(4) == "arpeggiated"
    assert accompaniment_pattern_name(5) == "broken_figure"
    assert accompaniment_pattern_name(6) == "ostinato_cell"
    assert accompaniment_pattern_name(99) == "repeated_chords"

    assert accompaniment_energy_band(1) == "thin"
    assert accompaniment_energy_band(2) == "supporting"
    assert accompaniment_energy_band(3) == "supporting"
    assert accompaniment_energy_band(4) == "filling"
    assert accompaniment_energy_band(5) == "filling"
    assert accompaniment_energy_band(6) == "foreground"
    assert accompaniment_energy_band(99) == "supporting"

    assert frequency_register_band(65.39) == "pedal"
    assert frequency_register_band(65.4) == "bass"
    assert frequency_register_band(130.79) == "bass"
    assert frequency_register_band(130.8) == "middle"
    assert frequency_register_band(523.29) == "middle"
    assert frequency_register_band(523.3) == "upper"

    assert accompaniment_transition_mode(2, 4) == "gradual"
    assert accompaniment_transition_mode(1, 6) == "section_cut"


def test_build_pattern_snapshot_summarizes_existing_pattern_output() -> None:
    expected_events = tuple(arpeggiated(146.8, 220.0, 0.43, 0.6))

    snapshot = build_pattern_snapshot(4, 146.8, 220.0, 0.43, 0.6)

    assert isinstance(snapshot, AccompanimentPatternSnapshot)
    assert dataclasses.is_dataclass(snapshot)
    assert getattr(snapshot, "__dataclass_params__").frozen
    assert snapshot.pattern_type == 4
    assert snapshot.pattern_name == "arpeggiated"
    assert snapshot.energy_band == "filling"
    assert snapshot.root_hz == 146.8
    assert snapshot.fifth_hz == 220.0
    assert snapshot.beat_seconds == 0.43
    assert snapshot.loud == 0.6
    assert snapshot.events == expected_events
    assert snapshot.event_count == 3
    assert snapshot.total_wait_seconds == pytest.approx(1.29)
    assert snapshot.max_release_seconds == pytest.approx(0.5)
    assert snapshot.mean_amp == pytest.approx(0.052)
    assert snapshot.min_frequency_hz == pytest.approx(73.4)
    assert snapshot.max_frequency_hz == pytest.approx(110.0)
    assert snapshot.register_band_counts == {
        "pedal": 0,
        "bass": 3,
        "middle": 0,
        "upper": 0,
    }


def test_build_accompaniment_plan_report_resolves_end_to_end_decision() -> None:
    report = build_accompaniment_plan_report(
        melody_density=4.0,
        melody_resting=False,
        current_type=5,
        root=146.8,
        fifth=220.0,
        beat=0.43,
        loud=0.7,
        bar_number=4,
    )

    assert isinstance(report, AccompanimentPlanReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert report.melody_density == 4.0
    assert report.melody_resting is False
    assert report.density_band == "dense"
    assert report.current_type == 5
    assert report.selected_type == 1
    assert report.target_type == 1
    assert report.transition_mode == "section_cut"
    assert report.pedal_enabled is True
    assert report.pedal_event == pytest.approx((36.7, 0.0105, 5.16))
    assert report.pattern.pattern_name == "sustained"
    assert report.total_event_count == 2
    assert report.total_wait_seconds == pytest.approx(1.29)
    assert report.max_release_seconds == pytest.approx(5.16)
    assert report.mean_amp == pytest.approx(0.0262)
    assert report.lowest_frequency_hz == pytest.approx(36.7)
    assert report.highest_frequency_hz == pytest.approx(73.4)
    assert report.active_pattern_names == ("sustained", "pedal_point")


def test_summarize_accompaniment_plan_report_returns_json_safe_summary() -> None:
    report = build_accompaniment_plan_report(
        melody_density=4.0,
        melody_resting=False,
        current_type=5,
        root=146.8,
        fifth=220.0,
        beat=0.43,
        loud=0.7,
        bar_number=4,
    )

    summary = summarize_accompaniment_plan_report(report)

    assert summary["melody_density"] == 4.0
    assert summary["density_band"] == "dense"
    assert summary["current_type"] == 5
    assert summary["selected_type"] == 1
    assert summary["target_type"] == 1
    assert summary["transition_mode"] == "section_cut"
    assert summary["pedal_enabled"] is True
    assert summary["pedal_event"] == [36.7, 0.0105, 5.16]
    assert summary["active_pattern_names"] == ["sustained", "pedal_point"]
    assert summary["pattern"]["pattern_name"] == "sustained"  # type: ignore[index]
    assert summary["pattern"]["events"] == [[73.4, 0.042, 2.58, 1.29]]  # type: ignore[index]
    assert summary["pattern"]["register_band_counts"] == {  # type: ignore[index]
        "pedal": 0,
        "bass": 1,
        "middle": 0,
        "upper": 0,
    }
    json.loads(json.dumps(summary))


def test_accompaniment_plan_report_agrees_with_existing_helpers() -> None:
    density = 2.5
    resting = False
    current_type = 3
    selected = select_accompaniment_type(density, resting)
    target = breathing_swell(density, resting, selected)

    report = build_accompaniment_plan_report(
        melody_density=density,
        melody_resting=resting,
        current_type=current_type,
        root=146.8,
        fifth=220.0,
        beat=0.43,
        loud=0.7,
        bar_number=2,
    )

    assert report.selected_type == selected == 2
    assert report.target_type == target == 1
    assert report.transition_mode == (
        "gradual"
        if should_transition_gradually(current_type, target)
        else "section_cut"
    )
    assert report.pedal_enabled is should_pedal(2)
    assert report.pedal_event is None
    assert report.pattern.events == tuple(get_pattern(target, 146.8, 220.0, 0.43, 0.7))
    assert report.pattern.pattern_name == accompaniment_pattern_name(target)
    assert report.total_event_count == len(report.pattern.events)

    pedal = pedal_note(146.8, 0.43, 0.7)
    assert pedal == pytest.approx((36.7, 0.0105, 5.16))


def test_accompaniment_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/synthesis/accompaniment.py")
    assert result.depth >= 2, result.reason
