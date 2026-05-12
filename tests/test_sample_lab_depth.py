"""Depth-2 sample-lab report helpers - locked test surface for frac-0022."""
from __future__ import annotations

import dataclasses
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.sample_lab import (  # noqa: E402
    SamplePlanReport,
    build_sample_plan_report,
    density_band,
    intensity_band,
    plan_environmental_sampling,
    sample_bank,
    sample_source,
    summarize_sample_plan_report,
    threshold_band,
)


def test_density_band_maps_values_to_named_bands() -> None:
    assert density_band(0.0) == "sparse"
    assert density_band(0.20) == "sparse"
    assert density_band(0.21) == "moderate"
    assert density_band(0.45) == "moderate"
    assert density_band(0.46) == "dense"
    assert density_band(0.70) == "dense"
    assert density_band(0.71) == "saturated"
    assert density_band(0.95) == "saturated"


def test_threshold_band_maps_values_to_named_bands() -> None:
    assert threshold_band(0.0) == "hair"
    assert threshold_band(0.12) == "hair"
    assert threshold_band(0.13) == "soft"
    assert threshold_band(0.18) == "soft"
    assert threshold_band(0.19) == "firm"
    assert threshold_band(0.24) == "firm"
    assert threshold_band(0.25) == "guarded"
    assert threshold_band(0.5) == "guarded"


def test_intensity_band_maps_values_to_named_bands() -> None:
    assert intensity_band(0.0) == "subtle"
    assert intensity_band(0.34) == "subtle"
    assert intensity_band(0.35) == "balanced"
    assert intensity_band(0.67) == "balanced"
    assert intensity_band(0.68) == "vivid"
    assert intensity_band(1.0) == "vivid"


def test_build_sample_plan_report_matches_plan_and_bank() -> None:
    plan = plan_environmental_sampling(
        source_name="garden_mic",
        cadence_state="away_practice",
        intensity=0.4,
    )

    report = build_sample_plan_report(plan, intensity=0.4)
    bank = sample_bank("garden_mic")

    assert isinstance(report, SamplePlanReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert report.source_name == plan.source.name
    assert report.hardware_label == plan.source.hardware_label
    assert report.source_type == plan.source.source_type
    assert report.capture_path == plan.source.capture_path
    assert report.refresh_seconds == plan.source.refresh_seconds
    assert report.freshness_seconds == bank.freshness_seconds
    assert report.fallback_sources == bank.fallback_sources
    assert report.cadence_state == "away_practice"
    assert report.section_function == ""
    assert report.transforms == plan.transforms
    assert report.transform_count == len(plan.transforms)
    assert report.density == plan.density
    assert report.density_band == density_band(plan.density)
    assert report.buffer_seconds == plan.buffer_seconds
    assert report.trigger_threshold == plan.trigger_threshold
    assert report.threshold_band == threshold_band(plan.trigger_threshold)
    assert report.intensity == 0.4
    assert report.intensity_band == intensity_band(0.4)
    assert report.study_focus == plan.study_focus


def test_build_sample_plan_report_carries_section_function() -> None:
    plan = plan_environmental_sampling(
        source_name="room_mic",
        cadence_state="occupied_day",
        section_function="development",
        intensity=0.5,
    )

    report = build_sample_plan_report(plan, intensity=0.5)

    assert report.section_function == "development"
    assert report.cadence_state == "occupied_day"
    assert report.transforms == plan.transforms
    assert report.transform_count == len(plan.transforms)
    assert set(report.transforms) >= {
        "slice_rearrange",
        "stretch",
        "spectral_freeze",
        "granular_cloud",
        "reverse_accents",
        "pitch_window",
    }
    assert report.study_focus == plan.study_focus


def test_build_sample_plan_report_resolves_alias_to_canonical_bank() -> None:
    plan = plan_environmental_sampling(
        source_name="perform_ve_condenser",
        cadence_state="occupied_day",
        intensity=0.5,
    )
    canonical_bank = sample_bank("room_mic")

    report = build_sample_plan_report(plan, intensity=0.5)

    assert report.source_name == "room_mic"
    assert report.hardware_label == sample_source("room_mic").hardware_label
    assert report.fallback_sources == canonical_bank.fallback_sources
    assert report.freshness_seconds == canonical_bank.freshness_seconds


def test_summarize_sample_plan_report_returns_json_safe_summary() -> None:
    plan = plan_environmental_sampling(
        source_name="contact_mic",
        cadence_state="away_practice",
        intensity=0.6,
    )

    report = build_sample_plan_report(plan, intensity=0.6)
    summary = summarize_sample_plan_report(report)

    assert summary == {
        "source_name": report.source_name,
        "hardware_label": report.hardware_label,
        "source_type": report.source_type,
        "capture_path": report.capture_path,
        "refresh_seconds": report.refresh_seconds,
        "freshness_seconds": report.freshness_seconds,
        "fallback_sources": list(report.fallback_sources),
        "cadence_state": report.cadence_state,
        "section_function": report.section_function,
        "transforms": list(report.transforms),
        "transform_count": report.transform_count,
        "density": report.density,
        "density_band": report.density_band,
        "buffer_seconds": report.buffer_seconds,
        "trigger_threshold": report.trigger_threshold,
        "threshold_band": report.threshold_band,
        "intensity": report.intensity,
        "intensity_band": report.intensity_band,
        "study_focus": report.study_focus,
    }
    assert isinstance(summary["transforms"], list)
    assert isinstance(summary["fallback_sources"], list)


def test_sample_plan_report_drives_existing_behavior() -> None:
    plan = plan_environmental_sampling(
        source_name="theramini_in",
        cadence_state="away_practice",
        intensity=0.5,
    )
    report = build_sample_plan_report(plan, intensity=0.5)
    bank = sample_bank("theramini_in")

    assert report.source_name == plan.source.name
    assert report.capture_path == plan.source.capture_path
    assert report.fallback_sources == bank.fallback_sources
    assert report.freshness_seconds == bank.freshness_seconds
    assert report.density == plan.density
    assert report.trigger_threshold == plan.trigger_threshold
    assert report.transforms == plan.transforms


def test_sample_lab_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/sample_lab.py")
    assert result.depth >= 2, result.reason
