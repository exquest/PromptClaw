"""Depth-2 character_registry helpers — locked test surface for frac-0006."""
from __future__ import annotations

import os
import sys

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.character_registry import (  # noqa: E402
    SAMPLER_DEFAULT_PARAMS,
    VOICE_SAMPLER_ID,
    CharacterRegistry,
    find_voices_by_synth,
    mode_gain_for,
    params_for,
    summarize_registry,
    voice_of,
    voices_by_role,
)


def _populated_registry() -> CharacterRegistry:
    registry = CharacterRegistry()
    registry.register("mel", {"voice": {"role": "melody", "synth": "sw_bowed"}})
    registry.register("rhythm", {"voice": {"role": "rhythm", "synth": "sw_tabla_tin"}})
    registry.register("harm", {"voice": {"role": "harmony", "synth": "sw_choir"}})
    registry.register("counter", {"voice": {"role": "melody", "synth": "sw_bowed"}})
    registry.register("ghost", {"not_a_voice": True})  # malformed entry
    return registry


def test_voice_of_returns_voice_mapping() -> None:
    registry = CharacterRegistry()

    voice = voice_of(registry.get(VOICE_SAMPLER_ID))

    assert voice["synth"] == "sw_sampler"
    assert voice["role"] == "sampler"


def test_voice_of_rejects_malformed_input() -> None:
    with pytest.raises(ValueError):
        voice_of("not-a-mapping")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        voice_of({"missing_voice": True})


def test_mode_gain_for_returns_override() -> None:
    voice = CharacterRegistry().get(VOICE_SAMPLER_ID)["voice"]

    assert mode_gain_for(voice, "solitary") == pytest.approx(0.85)
    assert mode_gain_for(voice, "working_ambience") == pytest.approx(0.30)


def test_mode_gain_for_falls_back_to_default() -> None:
    voice = CharacterRegistry().get(VOICE_SAMPLER_ID)["voice"]

    assert mode_gain_for(voice, "no_such_mode") == pytest.approx(1.0)
    assert mode_gain_for(voice, "no_such_mode", default=0.5) == pytest.approx(0.5)
    assert mode_gain_for({"mode_gain_overrides": "broken"}, "solitary", default=0.7) == pytest.approx(0.7)
    assert mode_gain_for({"mode_gain_overrides": {"solitary": "loud"}}, "solitary", default=0.4) == pytest.approx(0.4)


def test_params_for_merges_defaults_with_overrides() -> None:
    voice = CharacterRegistry().get(VOICE_SAMPLER_ID)["voice"]

    merged = params_for(voice, {"density": 6.0, "pitch_transpose": -2.0})

    assert merged["grain_size_ms"] == pytest.approx(SAMPLER_DEFAULT_PARAMS["grain_size_ms"])
    assert merged["density"] == pytest.approx(6.0)
    assert merged["pitch_transpose"] == pytest.approx(-2.0)


def test_params_for_skips_none_overrides() -> None:
    voice = CharacterRegistry().get(VOICE_SAMPLER_ID)["voice"]

    merged = params_for(voice, {"density": None, "pitch_transpose": 1.5})

    assert merged["density"] == pytest.approx(SAMPLER_DEFAULT_PARAMS["density"])
    assert merged["pitch_transpose"] == pytest.approx(1.5)
    assert merged["grain_size_ms"] == pytest.approx(SAMPLER_DEFAULT_PARAMS["grain_size_ms"])


def test_summarize_registry_reports_counts_and_histograms() -> None:
    registry = _populated_registry()

    summary = summarize_registry(registry)

    assert summary["character_count"] == 6
    assert summary["character_ids"] == sorted(["counter", "ghost", "harm", "mel", "rhythm", VOICE_SAMPLER_ID])
    synth_counts = summary["synth_counts"]
    assert synth_counts["sw_bowed"] == 2
    assert synth_counts["sw_sampler"] == 1
    assert synth_counts["sw_choir"] == 1
    assert synth_counts["sw_tabla_tin"] == 1
    role_counts = summary["role_counts"]
    assert role_counts["melody"] == 2
    assert role_counts["sampler"] == 1
    assert role_counts["harmony"] == 1
    assert role_counts["rhythm"] == 1


def test_voices_by_role_groups_sorted_ids() -> None:
    registry = _populated_registry()

    grouped = voices_by_role(registry)

    assert grouped["melody"] == ["counter", "mel"]
    assert grouped["rhythm"] == ["rhythm"]
    assert grouped["harmony"] == ["harm"]
    assert grouped["sampler"] == [VOICE_SAMPLER_ID]
    assert "ghost" not in {cid for ids in grouped.values() for cid in ids}


def test_find_voices_by_synth_returns_sorted_matches() -> None:
    registry = _populated_registry()

    assert find_voices_by_synth(registry, "sw_bowed") == ["counter", "mel"]
    assert find_voices_by_synth(registry, "sw_sampler") == [VOICE_SAMPLER_ID]
    assert find_voices_by_synth(registry, "no_such_synth") == []
