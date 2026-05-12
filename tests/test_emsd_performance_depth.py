"""Depth-2 EMSD performance report helpers - locked test surface for frac-0027."""
from __future__ import annotations

import dataclasses
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.emsd_performance import (  # noqa: E402
    PerformanceAdjustmentReport,
    PerformanceEventSnapshot,
    PerformanceEventSpec,
    amp_pressure_band,
    brightness_shape_band,
    build_performance_adjustment_report,
    build_performance_event_snapshot,
    release_shape_band,
    render_adjustments_for_event,
    space_amount_band,
    summarize_performance_adjustment_report,
)
from senseweave.emsd_runtime import build_live_emsd_context  # noqa: E402


def _conversation_context():
    return build_live_emsd_context(
        cadence_state="occupied_day",
        occupancy_state="occupied_active",
        family_name="bloom",
        progression_profile="open_day",
        patch_name="house_garden",
        song_num=7,
        theramini_present=True,
        repertoire_songs=[],
        attention_score=0.9,
        now_seconds=14 * 60,
    )


def test_performance_band_helpers_map_values_to_named_bands() -> None:
    assert amp_pressure_band(0.0) == "recessed"
    assert amp_pressure_band(0.749) == "recessed"
    assert amp_pressure_band(0.75) == "balanced"
    assert amp_pressure_band(1.05) == "balanced"
    assert amp_pressure_band(1.051) == "forward"

    assert release_shape_band(0.0) == "tight"
    assert release_shape_band(0.949) == "tight"
    assert release_shape_band(0.95) == "natural"
    assert release_shape_band(1.1) == "natural"
    assert release_shape_band(1.101) == "bloom"

    assert brightness_shape_band(0.0) == "muted"
    assert brightness_shape_band(0.899) == "muted"
    assert brightness_shape_band(0.9) == "clear"
    assert brightness_shape_band(1.02) == "clear"
    assert brightness_shape_band(1.021) == "bright"

    assert space_amount_band(0.0) == "dry"
    assert space_amount_band(0.02) == "dry"
    assert space_amount_band(0.0201) == "open"
    assert space_amount_band(0.07) == "open"
    assert space_amount_band(0.0701) == "washed"


def test_build_performance_event_snapshot_matches_live_adjustments() -> None:
    context = _conversation_context()
    spec = PerformanceEventSpec(
        role="counter",
        voice_name="choir",
        frequency_hz=880.0,
        theramini_active=False,
    )

    snapshot = build_performance_event_snapshot(spec, context=context)
    expected = render_adjustments_for_event(
        role=spec.role,
        voice_name=spec.voice_name,
        frequency_hz=spec.frequency_hz,
        context=context,
        theramini_active=spec.theramini_active,
    )

    assert isinstance(snapshot, PerformanceEventSnapshot)
    assert dataclasses.is_dataclass(snapshot)
    assert getattr(snapshot, "__dataclass_params__").frozen
    assert snapshot.role == spec.role
    assert snapshot.voice_name == spec.voice_name
    assert snapshot.frequency_hz == spec.frequency_hz
    assert snapshot.theramini_active is False
    assert snapshot.amp_multiplier == expected.amp_multiplier
    assert snapshot.amp_band == amp_pressure_band(expected.amp_multiplier)
    assert snapshot.release_multiplier == expected.release_multiplier
    assert snapshot.release_band == release_shape_band(expected.release_multiplier)
    assert snapshot.brightness_multiplier == expected.brightness_multiplier
    assert snapshot.brightness_band == brightness_shape_band(
        expected.brightness_multiplier
    )
    assert snapshot.space_amount == round(expected.verb_add + expected.dly_add, 4)
    assert snapshot.space_band == space_amount_band(snapshot.space_amount)
    assert snapshot.detune_add == expected.detune_add
    assert snapshot.highpass_hz == expected.highpass_hz
    assert snapshot.saturation_add == expected.saturation_add
    assert snapshot.sample_capture_path == expected.sample_capture_path
    assert snapshot.dsp_blocks == expected.dsp_blocks


def test_build_performance_adjustment_report_summarizes_events() -> None:
    context = _conversation_context()
    specs = (
        PerformanceEventSpec("melody", "pluck", 660.0, True),
        PerformanceEventSpec("counter", "choir", 880.0, False),
        PerformanceEventSpec("color", "breath", 1400.0, True),
    )
    snapshots = tuple(
        build_performance_event_snapshot(spec, context=context) for spec in specs
    )

    report = build_performance_adjustment_report(snapshots)

    assert isinstance(report, PerformanceAdjustmentReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert report.snapshots == snapshots
    assert report.snapshot_count == 3
    assert report.roles == ("melody", "counter", "color")
    assert report.voice_names == ("pluck", "choir", "breath")
    assert report.sample_capture_paths == ("/tmp/theramini_capture.wav",)
    assert report.dsp_blocks == ("cross_synthesis", "bin_shift", "parallel_delay")
    assert report.mean_amp_multiplier == round(
        sum(s.amp_multiplier for s in snapshots) / len(snapshots),
        4,
    )
    assert report.max_release_multiplier == max(
        s.release_multiplier for s in snapshots
    )
    assert report.min_brightness_multiplier == min(
        s.brightness_multiplier for s in snapshots
    )
    assert report.space_total == round(sum(s.space_amount for s in snapshots), 4)
    assert report.frontline_ducked_count == len(
        [
            s
            for s in snapshots
            if s.theramini_active
            and s.role in {"melody", "counter", "color"}
            and s.amp_multiplier < 1.0
        ]
    )
    assert report.highpass_roles == tuple(
        dict.fromkeys(s.role for s in snapshots if s.highpass_hz > 0.0)
    )


def test_build_performance_adjustment_report_rejects_empty_sequence() -> None:
    with pytest.raises(ValueError):
        build_performance_adjustment_report([])


def test_summarize_performance_adjustment_report_returns_json_safe_summary() -> None:
    context = _conversation_context()
    snapshots = tuple(
        build_performance_event_snapshot(spec, context=context)
        for spec in (
            PerformanceEventSpec("melody", "pluck", 660.0, False),
            PerformanceEventSpec("melody", "pluck", 660.0, True),
        )
    )
    report = build_performance_adjustment_report(snapshots)

    summary = summarize_performance_adjustment_report(report)

    assert summary["snapshot_count"] == 2
    assert summary["roles"] == ["melody"]
    assert summary["voice_names"] == ["pluck"]
    assert summary["dsp_blocks"] == ["cross_synthesis", "bin_shift", "parallel_delay"]
    assert summary["sample_capture_paths"] == ["/tmp/theramini_capture.wav"]
    assert summary["mean_amp_multiplier"] == report.mean_amp_multiplier
    assert summary["max_release_multiplier"] == report.max_release_multiplier
    assert summary["min_brightness_multiplier"] == report.min_brightness_multiplier
    assert summary["space_total"] == report.space_total
    assert summary["frontline_ducked_count"] == 1
    assert summary["highpass_roles"] == ["melody"]
    assert summary["snapshots"][0]["role"] == "melody"  # type: ignore[index]
    assert summary["snapshots"][0]["theramini_active"] is False  # type: ignore[index]
    assert summary["snapshots"][1]["theramini_active"] is True  # type: ignore[index]
    json.loads(json.dumps(summary))


def test_performance_report_uses_live_context_end_to_end() -> None:
    context = _conversation_context()
    dry = build_performance_event_snapshot(
        PerformanceEventSpec("melody", "pluck", 660.0, False),
        context=context,
    )
    ducked = build_performance_event_snapshot(
        PerformanceEventSpec("melody", "pluck", 660.0, True),
        context=context,
    )
    counter = build_performance_event_snapshot(
        PerformanceEventSpec("counter", "choir", 880.0, False),
        context=context,
    )

    report = build_performance_adjustment_report([dry, ducked, counter])

    assert ducked.amp_multiplier < dry.amp_multiplier
    assert report.frontline_ducked_count == 1
    assert "parallel_delay" in report.dsp_blocks
    assert report.sample_capture_paths == ("/tmp/theramini_capture.wav",)
    assert report.roles == ("melody", "counter")
    assert report.snapshot_count == 3


def test_emsd_performance_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/emsd_performance.py")
    assert result.depth >= 2, result.reason
