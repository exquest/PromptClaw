"""Depth-2 synthesis_architecture_registry helpers - locked test surface for frac-0031."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.synthesis_architecture_registry import (  # noqa: E402
    ARCHITECTURE_REGISTRY,
    REQUIRED_ARCHITECTURES,
    REQUIRED_PHASES,
    ArchitectureProfile,
    ArchitectureRegistryReport,
    SafeRange,
    affinity_band,
    architectures_for_phase,
    best_architecture_for_phase,
    build_architecture_profile,
    build_architecture_registry_report,
    control_span_band,
    covered_architectures,
    fallback_chain,
    get_strategy,
    resolve_architecture,
    strategies_for_role,
    summarize_architecture_registry_report,
)


def _assert_json_safe(value: Any) -> None:
    assert not isinstance(value, tuple), f"tuple leaked into JSON summary: {value!r}"
    if isinstance(value, dict):
        for key, child in value.items():
            assert isinstance(key, str)
            _assert_json_safe(child)
    elif isinstance(value, list):
        for child in value:
            _assert_json_safe(child)


def test_architecture_helper_bands_and_fallback_chain_are_stable() -> None:
    assert affinity_band(0.0) == "low"
    assert affinity_band(0.399) == "low"
    assert affinity_band(0.4) == "medium"
    assert affinity_band(0.699) == "medium"
    assert affinity_band(0.7) == "high"
    assert affinity_band(1.0) == "high"

    assert control_span_band(SafeRange("narrow", 0.25, 0.0, 0.5)) == "narrow"
    assert control_span_band(SafeRange("standard", 0.5, 0.0, 1.0)) == "standard"
    assert control_span_band(SafeRange("wide", 0.0, -1.0, 1.0)) == "wide"

    assert fallback_chain("subtractive") == ("subtractive", "additive", "fm")
    assert fallback_chain("granular") == ("granular", "spectral")
    assert fallback_chain("unknown_architecture") == (
        "subtractive",
        "additive",
        "fm",
    )


def test_build_architecture_profile_resolves_strategy_diagnostics() -> None:
    strategy = get_strategy("spectral")
    profile = build_architecture_profile(strategy)

    assert isinstance(profile, ArchitectureProfile)
    assert dataclasses.is_dataclass(profile)
    assert getattr(profile, "__dataclass_params__").frozen

    assert profile.architecture_id == "spectral"
    assert profile.label == strategy.label
    assert profile.summary == strategy.summary
    assert profile.role_tags == strategy.role_tags
    assert profile.role_count == len(strategy.role_tags)
    assert profile.macro_control_count == len(strategy.macro_controls)
    assert profile.macro_control_names == tuple(c.name for c in strategy.macro_controls)
    assert profile.default_controls == {
        control.name: control.default for control in strategy.macro_controls
    }
    assert tuple(profile.control_span_bands.keys()) == profile.macro_control_names
    assert profile.control_span_bands["fft_size"] == "standard"
    assert profile.control_span_bands["freeze"] == "standard"
    assert profile.control_span_bands["stretch"] == "standard"
    assert profile.control_span_bands["spectral_shift"] == "wide"

    assert profile.best_phase == "Divination"
    assert profile.best_phase_affinity == strategy.arc_affinity["Divination"]
    assert profile.high_affinity_phases == ("Divination", "Crystallization")
    assert tuple(profile.affinity_bands.keys()) == (
        "Divination",
        "Emergence",
        "Conversation",
        "Convergence",
        "Crystallization",
    )
    assert profile.affinity_bands == {
        "Divination": "high",
        "Emergence": "medium",
        "Conversation": "low",
        "Convergence": "medium",
        "Crystallization": "high",
    }
    assert profile.fallback == "granular"
    assert profile.fallback_chain == ("spectral", "granular")


def test_build_architecture_registry_report_resolves_full_registry() -> None:
    report = build_architecture_registry_report()

    assert isinstance(report, ArchitectureRegistryReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen

    assert report.total_count == len(ARCHITECTURE_REGISTRY)
    assert report.architecture_ids == tuple(ARCHITECTURE_REGISTRY.keys())
    assert report.architecture_ids == (
        "subtractive",
        "fm",
        "additive",
        "granular",
        "physical_model",
        "spectral",
    )
    assert report.phases == (
        "Divination",
        "Emergence",
        "Conversation",
        "Convergence",
        "Crystallization",
    )
    assert set(report.phases) == REQUIRED_PHASES

    assert report.phase_winners == {
        "Divination": "spectral",
        "Emergence": "fm",
        "Conversation": "subtractive",
        "Convergence": "additive",
        "Crystallization": "granular",
    }
    assert tuple(report.phase_architectures.keys()) == report.phases
    assert report.phase_architectures["Divination"] == (
        "spectral",
        "granular",
        "additive",
        "physical_model",
        "fm",
        "subtractive",
    )
    assert report.phase_architectures["Emergence"][0] == "fm"

    assert report.roles == (
        "melody",
        "bass",
        "counter",
        "figuration",
        "color",
        "foundation",
        "rhythm",
    )
    assert report.role_architectures["melody"] == (
        "subtractive",
        "fm",
        "additive",
        "physical_model",
    )
    assert report.role_architectures["color"] == (
        "additive",
        "granular",
        "spectral",
    )
    assert report.role_architectures["rhythm"] == ("physical_model",)

    assert report.fallback_map == {
        "subtractive": "additive",
        "fm": "subtractive",
        "additive": "fm",
        "granular": "spectral",
        "physical_model": "subtractive",
        "spectral": "granular",
    }
    assert report.missing_required_architectures == ()
    assert report.missing_required_phases == ()
    assert tuple(report.macro_control_counts.keys()) == report.architecture_ids
    assert set(report.macro_control_counts.values()) == {4}
    assert set(report.architecture_ids) == REQUIRED_ARCHITECTURES

    assert len(report.profiles) == report.total_count
    assert tuple(profile.architecture_id for profile in report.profiles) == report.architecture_ids
    for profile in report.profiles:
        assert isinstance(profile, ArchitectureProfile)


def test_summarize_architecture_registry_report_returns_json_safe_summary() -> None:
    report = build_architecture_registry_report()
    summary = summarize_architecture_registry_report(report)

    assert summary["total_count"] == report.total_count
    assert summary["architecture_ids"] == list(report.architecture_ids)
    assert summary["phases"] == list(report.phases)
    assert summary["phase_winners"] == dict(report.phase_winners)
    assert summary["phase_architectures"] == {
        phase: list(ids) for phase, ids in report.phase_architectures.items()
    }
    assert summary["roles"] == list(report.roles)
    assert summary["role_architectures"] == {
        role: list(ids) for role, ids in report.role_architectures.items()
    }
    assert summary["fallback_map"] == dict(report.fallback_map)
    assert summary["missing_required_architectures"] == list(
        report.missing_required_architectures
    )
    assert summary["missing_required_phases"] == list(report.missing_required_phases)
    assert summary["macro_control_counts"] == dict(report.macro_control_counts)

    assert isinstance(summary["profiles"], list)
    assert len(summary["profiles"]) == len(report.profiles)
    first = summary["profiles"][0]
    first_profile = report.profiles[0]
    assert first["architecture_id"] == first_profile.architecture_id  # type: ignore[index]
    assert first["label"] == first_profile.label  # type: ignore[index]
    assert first["summary"] == first_profile.summary  # type: ignore[index]
    assert first["role_tags"] == list(first_profile.role_tags)  # type: ignore[index]
    assert first["macro_control_count"] == first_profile.macro_control_count  # type: ignore[index]
    assert first["macro_control_names"] == list(first_profile.macro_control_names)  # type: ignore[index]
    assert first["default_controls"] == dict(first_profile.default_controls)  # type: ignore[index]
    assert first["control_span_bands"] == dict(first_profile.control_span_bands)  # type: ignore[index]
    assert first["best_phase"] == first_profile.best_phase  # type: ignore[index]
    assert first["best_phase_affinity"] == first_profile.best_phase_affinity  # type: ignore[index]
    assert first["high_affinity_phases"] == list(first_profile.high_affinity_phases)  # type: ignore[index]
    assert first["affinity_bands"] == dict(first_profile.affinity_bands)  # type: ignore[index]
    assert first["fallback"] == first_profile.fallback  # type: ignore[index]
    assert first["fallback_chain"] == list(first_profile.fallback_chain)  # type: ignore[index]
    assert first["role_count"] == first_profile.role_count  # type: ignore[index]

    _assert_json_safe(summary)
    encoded = json.dumps(summary)
    decoded = json.loads(encoded)
    assert decoded["total_count"] == report.total_count


def test_architecture_registry_report_agrees_with_existing_lookups() -> None:
    report = build_architecture_registry_report()

    assert set(report.architecture_ids) == covered_architectures()
    assert report.missing_required_architectures == ()
    assert report.missing_required_phases == ()

    for phase in report.phases:
        assert report.phase_winners[phase] == best_architecture_for_phase(
            phase
        ).architecture_id
        assert report.phase_architectures[phase] == tuple(
            strategy.architecture_id for strategy in architectures_for_phase(phase)
        )

    for role, architecture_ids in report.role_architectures.items():
        assert architecture_ids == tuple(
            strategy.architecture_id for strategy in strategies_for_role(role)
        )

    for architecture_id, fallback in report.fallback_map.items():
        assert fallback == resolve_architecture(architecture_id).fallback

    for profile in report.profiles:
        assert profile.fallback_chain[0] == resolve_architecture(
            profile.architecture_id
        ).architecture_id
        assert len(profile.fallback_chain) == len(set(profile.fallback_chain))


def test_synthesis_architecture_registry_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/synthesis_architecture_registry.py")
    assert result.depth >= 2, result.reason
