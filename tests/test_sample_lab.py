"""Tests for environmental sampling plans."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sample_lab import plan_environmental_sampling, sample_bank, sample_source


def test_sampling_sources_expose_capture_paths_and_roles() -> None:
    source = sample_source("room_mic")

    assert source.capture_path.endswith("room_capture.wav")
    assert "texture" in source.musical_roles


def test_perform_ve_room_source_exposes_sample_bank_fallback_rules() -> None:
    bank = sample_bank("perform_ve_condenser")

    assert bank.source.name == "room_mic"
    assert bank.source.hardware_label == "room/Perform-VE condenser"
    assert bank.fallback_sources == ("contact_mic", "self_bus")
    assert bank.freshness_seconds == 67


def test_away_practice_sampling_is_more_adventurous_than_sleep() -> None:
    sleep = plan_environmental_sampling(source_name="garden_mic", cadence_state="sleep", intensity=0.4)
    practice = plan_environmental_sampling(source_name="garden_mic", cadence_state="away_practice", intensity=0.4)

    assert len(practice.transforms) > len(sleep.transforms)
    assert practice.density > sleep.density
    assert practice.trigger_threshold < sleep.trigger_threshold


def test_section_function_expands_sampling_into_compositional_transform_set() -> None:
    plan = plan_environmental_sampling(
        source_name="room_mic",
        cadence_state="occupied_day",
        section_function="development",
        intensity=0.5,
    )

    assert plan.section_function == "development"
    assert set(plan.transforms) >= {
        "slice_rearrange",
        "stretch",
        "spectral_freeze",
        "granular_cloud",
        "reverse_accents",
        "pitch_window",
    }
