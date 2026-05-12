"""Tests for the synthesis-architecture strategy registry.

depth: 2
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.synthesis_architecture_registry import (
    ARCHITECTURE_REGISTRY,
    REQUIRED_ARCHITECTURES,
    REQUIRED_PHASES,
    architectures_for_phase,
    best_architecture_for_phase,
    build_architecture_registry_report,
    covered_architectures,
    get_strategy,
    resolve_architecture,
    summarize_architecture_registry_report,
    strategies_for_role,
)


# === Registry completeness ===


class TestRegistryCompleteness:
    def test_covers_all_required_architectures(self) -> None:
        assert REQUIRED_ARCHITECTURES <= covered_architectures()

    def test_total_entry_count(self) -> None:
        assert len(ARCHITECTURE_REGISTRY) == 6

    def test_required_architectures_match_registry(self) -> None:
        assert set(ARCHITECTURE_REGISTRY.keys()) == REQUIRED_ARCHITECTURES


# === Entry fields ===


class TestEntryFields:
    def test_every_entry_has_role_tags(self) -> None:
        for strategy in ARCHITECTURE_REGISTRY.values():
            assert len(strategy.role_tags) >= 1, (
                f"{strategy.architecture_id} has no role tags"
            )

    def test_every_entry_has_macro_controls(self) -> None:
        for strategy in ARCHITECTURE_REGISTRY.values():
            assert len(strategy.macro_controls) >= 1, (
                f"{strategy.architecture_id} has no macro controls"
            )

    def test_every_macro_has_safe_range(self) -> None:
        for strategy in ARCHITECTURE_REGISTRY.values():
            for ctrl in strategy.macro_controls:
                assert ctrl.min_val <= ctrl.default <= ctrl.max_val, (
                    f"{strategy.architecture_id}.{ctrl.name}: "
                    f"default {ctrl.default} outside [{ctrl.min_val}, {ctrl.max_val}]"
                )

    def test_every_entry_has_arc_affinity(self) -> None:
        for strategy in ARCHITECTURE_REGISTRY.values():
            assert len(strategy.arc_affinity) >= 1, (
                f"{strategy.architecture_id} has no arc affinity"
            )

    def test_arc_affinity_covers_all_phases(self) -> None:
        for strategy in ARCHITECTURE_REGISTRY.values():
            for phase in REQUIRED_PHASES:
                assert phase in strategy.arc_affinity, (
                    f"{strategy.architecture_id} missing affinity for {phase}"
                )

    def test_arc_affinity_values_in_range(self) -> None:
        for strategy in ARCHITECTURE_REGISTRY.values():
            for phase, value in strategy.arc_affinity.items():
                assert 0.0 <= value <= 1.0, (
                    f"{strategy.architecture_id}.{phase}: affinity {value} out of [0, 1]"
                )

    def test_every_entry_has_fallback(self) -> None:
        for strategy in ARCHITECTURE_REGISTRY.values():
            assert strategy.fallback, (
                f"{strategy.architecture_id} has no fallback"
            )
            assert strategy.fallback != strategy.architecture_id, (
                f"{strategy.architecture_id} falls back to itself"
            )
            assert strategy.fallback in ARCHITECTURE_REGISTRY, (
                f"{strategy.architecture_id} fallback {strategy.fallback!r} not in registry"
            )

    def test_every_entry_has_label_and_summary(self) -> None:
        for strategy in ARCHITECTURE_REGISTRY.values():
            assert strategy.label, f"{strategy.architecture_id} missing label"
            assert strategy.summary, f"{strategy.architecture_id} missing summary"


# === Arc-phase affinity ===


class TestArcPhaseAffinity:
    def test_each_phase_has_a_clear_winner(self) -> None:
        for phase in REQUIRED_PHASES:
            best = best_architecture_for_phase(phase)
            assert best.arc_affinity[phase] >= 0.7, (
                f"best for {phase} ({best.architecture_id}) only has "
                f"affinity {best.arc_affinity[phase]}"
            )

    def test_divination_prefers_spectral(self) -> None:
        assert best_architecture_for_phase("Divination").architecture_id == "spectral"

    def test_emergence_prefers_fm(self) -> None:
        assert best_architecture_for_phase("Emergence").architecture_id == "fm"

    def test_conversation_prefers_subtractive(self) -> None:
        assert best_architecture_for_phase("Conversation").architecture_id == "subtractive"

    def test_convergence_prefers_additive(self) -> None:
        assert best_architecture_for_phase("Convergence").architecture_id == "additive"

    def test_crystallization_prefers_granular(self) -> None:
        assert best_architecture_for_phase("Crystallization").architecture_id == "granular"

    def test_architectures_for_phase_respects_threshold(self) -> None:
        high = architectures_for_phase("Divination", threshold=0.8)
        assert len(high) >= 1
        for s in high:
            assert s.arc_affinity["Divination"] > 0.8

    def test_architectures_for_phase_sorted_descending(self) -> None:
        results = architectures_for_phase("Emergence")
        affinities = [s.arc_affinity["Emergence"] for s in results]
        assert affinities == sorted(affinities, reverse=True)


# === Role queries ===


class TestRoleQueries:
    def test_melody_has_multiple_architectures(self) -> None:
        melody = strategies_for_role("melody")
        assert len(melody) >= 3

    def test_color_includes_spectral_and_granular(self) -> None:
        color = strategies_for_role("color")
        ids = {s.architecture_id for s in color}
        assert {"spectral", "granular"} <= ids

    def test_bass_includes_subtractive(self) -> None:
        bass = strategies_for_role("bass")
        ids = {s.architecture_id for s in bass}
        assert "subtractive" in ids

    def test_foundation_has_entries(self) -> None:
        found = strategies_for_role("foundation")
        assert len(found) >= 1

    def test_rhythm_has_physical_model(self) -> None:
        rhythm = strategies_for_role("rhythm")
        ids = {s.architecture_id for s in rhythm}
        assert "physical_model" in ids

    def test_unknown_role_returns_empty(self) -> None:
        assert strategies_for_role("nonexistent") == ()


# === Lookup functions ===


class TestLookups:
    def test_get_strategy_known(self) -> None:
        s = get_strategy("fm")
        assert s.architecture_id == "fm"
        assert s.label == "FM"

    def test_get_strategy_unknown_raises(self) -> None:
        try:
            get_strategy("wavetable")
            assert False, "expected KeyError"
        except KeyError:
            pass

    def test_resolve_known_architecture(self) -> None:
        s = resolve_architecture("granular")
        assert s.architecture_id == "granular"

    def test_resolve_unknown_falls_back_to_subtractive(self) -> None:
        s = resolve_architecture("unknown_synth")
        assert s.architecture_id == "subtractive"

    def test_covered_architectures_matches_required(self) -> None:
        assert covered_architectures() == REQUIRED_ARCHITECTURES


# === Consistency with procedural arc ===


class TestProceduralArcConsistency:
    def test_arc_phase_synthesis_targets_are_registered(self) -> None:
        from senseweave.procedural_arc import ARC_PHASES

        for phase in ARC_PHASES:
            assert phase.synthesis in ARCHITECTURE_REGISTRY, (
                f"ARC_PHASES phase {phase.name} targets {phase.synthesis!r} "
                f"which is not in the architecture registry"
            )

    def test_arc_phase_best_match_agrees_with_procedural_arc(self) -> None:
        from senseweave.procedural_arc import ARC_PHASES

        for phase in ARC_PHASES:
            best = best_architecture_for_phase(phase.name)
            assert best.architecture_id == phase.synthesis, (
                f"phase {phase.name}: procedural_arc says {phase.synthesis}, "
                f"registry best is {best.architecture_id}"
            )


# === Consistency with production course ===


class TestProductionCourseConsistency:
    def test_production_course_concepts_are_registered(self) -> None:
        from senseweave.production_course import course_chapter

        chapter = course_chapter("synthesis_architecture")
        assert chapter is not None
        for concept in chapter.concepts:
            assert concept.value in ARCHITECTURE_REGISTRY, (
                f"production course concept {concept.value!r} "
                f"not in architecture registry"
            )


# === End-to-end depth-2 coverage ===


class SynthesisArchitectureRegistryEndToEndTests:
    """End-to-end diagnostic coverage for the registry test surface."""

    __test__ = True

    def test_registry_lookup_report_and_course_summary_round_trip_json_diagnostic(
        self,
    ) -> None:
        from senseweave.production_course import course_chapter

        report = build_architecture_registry_report()
        summary = summarize_architecture_registry_report(report)

        assert summary["architecture_ids"] == [
            "subtractive",
            "fm",
            "additive",
            "granular",
            "physical_model",
            "spectral",
        ]
        assert summary["phases"] == [
            "Divination",
            "Emergence",
            "Conversation",
            "Convergence",
            "Crystallization",
        ]
        assert summary["missing_required_architectures"] == []
        assert summary["missing_required_phases"] == []

        phase_winners = {
            phase: best_architecture_for_phase(phase).architecture_id
            for phase in report.phases
        }
        assert summary["phase_winners"] == phase_winners
        assert phase_winners == {
            "Divination": "spectral",
            "Emergence": "fm",
            "Conversation": "subtractive",
            "Convergence": "additive",
            "Crystallization": "granular",
        }

        phase_rankings = {
            phase: [
                strategy.architecture_id for strategy in architectures_for_phase(phase)
            ]
            for phase in report.phases
        }
        assert summary["phase_architectures"] == phase_rankings

        role_mappings = {
            role: [strategy.architecture_id for strategy in strategies_for_role(role)]
            for role in report.roles
        }
        assert summary["role_architectures"] == role_mappings
        assert role_mappings["melody"] == [
            "subtractive",
            "fm",
            "additive",
            "physical_model",
        ]
        assert role_mappings["color"] == ["additive", "granular", "spectral"]
        assert role_mappings["foundation"] == ["granular", "physical_model", "spectral"]

        profiles = {
            profile["architecture_id"]: profile for profile in summary["profiles"]
        }
        assert set(profiles) == set(summary["architecture_ids"])
        for architecture_id in summary["architecture_ids"]:
            profile = profiles[architecture_id]
            assert profile["macro_control_count"] == len(
                profile["macro_control_names"]
            )
            assert set(profile["default_controls"]) == set(
                profile["macro_control_names"]
            )
            assert profile["best_phase"] in summary["phases"]
            assert profile["high_affinity_phases"]
            assert profile["fallback_chain"][0] == architecture_id
            assert len(profile["fallback_chain"]) == len(
                set(profile["fallback_chain"])
            )

        chapter = course_chapter("synthesis_architecture")
        assert chapter is not None
        course_values = [concept.value for concept in chapter.concepts]
        assert set(course_values) <= set(summary["architecture_ids"])

        diagnostic = {
            "architecture_ids": summary["architecture_ids"],
            "phase_winners": summary["phase_winners"],
            "course_values": course_values,
            "role_mappings": {
                "melody": role_mappings["melody"],
                "color": role_mappings["color"],
                "foundation": role_mappings["foundation"],
            },
            "profile_diagnostics": {
                architecture_id: {
                    "best_phase": profiles[architecture_id]["best_phase"],
                    "macro_control_names": profiles[architecture_id][
                        "macro_control_names"
                    ],
                    "fallback_chain": profiles[architecture_id]["fallback_chain"],
                }
                for architecture_id in summary["architecture_ids"]
            },
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert round_tripped["phase_winners"]["Divination"] == "spectral"
        assert round_tripped["phase_winners"]["Emergence"] == "fm"
        assert round_tripped["role_mappings"]["melody"] == [
            "subtractive",
            "fm",
            "additive",
            "physical_model",
        ]
        assert "spectral" in round_tripped["course_values"]
        assert (
            round_tripped["profile_diagnostics"]["granular"]["fallback_chain"][0]
            == "granular"
        )
