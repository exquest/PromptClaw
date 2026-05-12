"""Tests for character_registry.py — voice_sampler registration and selection."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.cast_planner import select_cast_ids
from senseweave.character_registry import (
    SAMPLER_DEFAULT_PARAMS,
    SAMPLER_MODE_GAIN_OVERRIDES,
    SAMPLER_SYNTH,
    VOICE_SAMPLER_ID,
    CharacterRegistry,
)


def test_voice_sampler_is_registered_with_expected_voice_metadata() -> None:
    registry = CharacterRegistry()

    voice = registry.get(VOICE_SAMPLER_ID)["voice"]

    assert voice["synth"] == "sw_sampler"
    assert voice["role"] == "sampler"
    assert voice["register"] == [36, 84]


def test_voice_sampler_default_params_cover_grain_density_and_pitch() -> None:
    voice = CharacterRegistry().get(VOICE_SAMPLER_ID)["voice"]

    params = voice["params"]
    assert "grain_size_ms" in params
    assert "density" in params
    assert "pitch_transpose" in params
    assert params == SAMPLER_DEFAULT_PARAMS


def test_voice_sampler_carries_per_mode_gain_overrides() -> None:
    voice = CharacterRegistry().get(VOICE_SAMPLER_ID)["voice"]

    overrides = voice["mode_gain_overrides"]
    expected_modes = {"solitary", "companion", "working_ambience", "evening_reflection", "storm"}
    assert set(overrides.keys()) == expected_modes
    assert overrides == SAMPLER_MODE_GAIN_OVERRIDES


def test_get_all_returns_isolated_copies() -> None:
    registry = CharacterRegistry()

    snapshot = registry.get_all()
    snapshot[VOICE_SAMPLER_ID]["voice"]["synth"] = "tampered"

    # Mutating the snapshot must not corrupt the registry.
    assert registry.get(VOICE_SAMPLER_ID)["voice"]["synth"] == "sw_sampler"


def test_select_cast_ids_picks_voice_sampler_when_sampler_synth_preferred() -> None:
    registry = CharacterRegistry()
    registry.register("mel", {"voice": {"role": "melody", "synth": "sw_bowed"}})
    registry.register("rhythm", {"voice": {"role": "rhythm", "synth": "sw_tabla_tin"}})
    registry.register("harm", {"voice": {"role": "harmony", "synth": "sw_choir"}})

    cast = select_cast_ids(
        registry.get_all(),
        cast_history=[],
        max_chars=4,
        preferred_synths=(SAMPLER_SYNTH,),
        voice_count_target=4,
    )

    assert VOICE_SAMPLER_ID in cast


def test_select_cast_ids_omits_voice_sampler_when_not_preferred_and_slots_tight() -> None:
    registry = CharacterRegistry()
    registry.register("mel", {"voice": {"role": "melody", "synth": "sw_bowed"}})
    registry.register("rhythm", {"voice": {"role": "rhythm", "synth": "sw_tabla_tin"}})
    registry.register("harm", {"voice": {"role": "harmony", "synth": "sw_choir"}})

    cast = select_cast_ids(
        registry.get_all(),
        cast_history=[],
        max_chars=3,
        voice_count_target=3,
    )

    assert cast == ["mel", "rhythm", "harm"]
