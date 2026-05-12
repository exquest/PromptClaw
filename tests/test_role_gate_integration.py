"""Integration and gate tests for R1–R8 role-filter contract (T-019)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from cypherclaw.render.events import Event, SectionEnvelope
from cypherclaw.render.role_gate import (
    GRID_LOCKED_ROLES,
    MELODIC_ACCENT_ROLES,
    Role,
)
from cypherclaw.render.rules.articulation import ArticulationRule
from cypherclaw.render.rules.final_rit import FinalRitRule
from cypherclaw.render.rules.microtiming import MicrotimingRule
from cypherclaw.render.rules.motif_memory import MotifMemoryRule
from cypherclaw.render.rules.phrase_arch import PhraseArchRule
from senseweave.render.rules.metric_accent import MetricAccentRule
from senseweave.render.rules.agogic import AgogicAccentRule
from senseweave.render.rules.duration_contrast import DurationContrastRule
from senseweave.render.rules.punctuation import PunctuationRule


class TestSharedContract:
    """All R1–R8 rules expose applies_to with the same signature and semantics."""

    RULES = [
        MetricAccentRule(),
        PhraseArchRule(),
        AgogicAccentRule(),
        DurationContrastRule(),
        FinalRitRule(),
        PunctuationRule(),
        ArticulationRule(),
        MicrotimingRule(),
    ]

    @pytest.mark.parametrize("role", sorted(GRID_LOCKED_ROLES))
    def test_all_rules_reject_grid_locked(self, role: str) -> None:
        for rule in self.RULES:
            assert rule.applies_to(role) is False, (
                f"{rule.__class__.__name__} should reject grid-locked role {role!r}"
            )

    @pytest.mark.parametrize("role", sorted(MELODIC_ACCENT_ROLES))
    def test_all_rules_accept_melodic(self, role: str) -> None:
        for rule in self.RULES:
            assert rule.applies_to(role) is True, (
                f"{rule.__class__.__name__} should accept melodic role {role!r}"
            )

    def test_all_rules_reject_unknown_role(self) -> None:
        for rule in self.RULES:
            assert rule.applies_to("unknown_voice") is False

    def test_metadata_grid_lock_overrides_melodic(self) -> None:
        for rule in self.RULES:
            assert rule.applies_to("melody", {"grid_locked": "true"}) is False


class TestRoleEnum:
    def test_grid_locked_flags(self) -> None:
        assert Role.OSTINATO.grid_locked is True
        assert Role.PERC.grid_locked is True
        assert Role.MELODY.grid_locked is False
        assert Role.PAD.grid_locked is False
        assert Role.ACCENT.grid_locked is False
        assert Role.SILENCE.grid_locked is None

    @pytest.mark.parametrize("role", [Role.OSTINATO, Role.PERC, Role.SILENCE])
    def test_rules_reject_quantized_or_silent_enum_roles(self, role: Role) -> None:
        for rule in TestSharedContract.RULES:
            assert rule.applies_to(role) is False

    @pytest.mark.parametrize("role", [Role.MELODY, Role.PAD, Role.ACCENT])
    def test_rules_accept_unlocked_enum_roles(self, role: Role) -> None:
        for rule in TestSharedContract.RULES:
            assert rule.applies_to(role) is True


class _CadentialPhrase:
    is_cadential = True


def _melody_event(position: float = 0.5) -> Event:
    event = Event(
        role="melody",
        normalized_phrase_position=position,
        section_envelope=SectionEnvelope(tempo_base=1.0),
        phrase=_CadentialPhrase(),
    )
    event.articulation_style = "normal"  # type: ignore[attr-defined]
    event.nominal_dur_sec = 0.5  # type: ignore[attr-defined]
    event.pitch = 60  # type: ignore[attr-defined]
    event.step_index = 7  # type: ignore[attr-defined]
    return event


def _ostinato_event(position: float = 0.5) -> Event:
    event = Event(
        role="ostinato",
        normalized_phrase_position=position,
        section_envelope=SectionEnvelope(tempo_base=1.0),
        phrase=_CadentialPhrase(),
    )
    event.articulation_style = "normal"  # type: ignore[attr-defined]
    event.nominal_dur_sec = 0.5  # type: ignore[attr-defined]
    event.pitch = 48  # type: ignore[attr-defined]
    event.step_index = 7  # type: ignore[attr-defined]
    return event


def _melody_motif() -> list[Event]:
    motif = [_melody_event(0.25), _melody_event(0.5), _melody_event(0.75)]
    for offset, event in zip((0, 2, 4), motif):
        event.pitch = 60 + offset  # type: ignore[attr-defined]
    return motif


def _shape_with_r2_r5_r7_r8(motif: list[Event]) -> None:
    rules = [
        PhraseArchRule(),
        FinalRitRule(onset_position=0.0),
        ArticulationRule(),
        MicrotimingRule(seed=42),
    ]
    for event in motif:
        for rule in rules:
            rule.apply(event)


class TestIntegrationMelodyShaped:
    """Melody events are mutated by the per-event rules (R2, R5, R7, R8)."""

    def test_melody_passage_is_shaped(self) -> None:
        rules = [
            PhraseArchRule(),
            FinalRitRule(onset_position=0.0),
            ArticulationRule(),
            MicrotimingRule(seed=42),
        ]
        event = _melody_event(position=0.85)

        for rule in rules:
            rule.apply(event)

        assert event.tempo_mult != 1.0
        assert hasattr(event, "gate_time")
        assert hasattr(event, "timing_deviation_ms")
        assert event.timing_deviation_ms != 0.0  # type: ignore[attr-defined]


class TestIntegrationOstinatoQuantized:
    """Ostinato events pass through all per-event rules completely untouched."""

    def test_ostinato_passage_exactly_quantized(self) -> None:
        rules = [
            PhraseArchRule(),
            FinalRitRule(onset_position=0.0),
            ArticulationRule(),
            MicrotimingRule(seed=42),
        ]
        event = _ostinato_event(position=0.85)
        original_tempo = event.tempo_mult
        original_amp = event.amp_mult

        for rule in rules:
            rule.apply(event)

        assert event.tempo_mult == original_tempo
        assert event.amp_mult == original_amp
        assert not hasattr(event, "gate_time")
        assert event.timing_deviation_ms == 0.0  # type: ignore[attr-defined]

    def test_metadata_grid_locked_melody_remains_exactly_quantized(self) -> None:
        rules = [
            PhraseArchRule(),
            FinalRitRule(onset_position=0.0),
            ArticulationRule(),
            MicrotimingRule(seed=42),
        ]
        event = _melody_event(position=0.85)
        event.metadata["grid_locked"] = "true"
        original_tempo = event.tempo_mult
        original_amp = event.amp_mult

        for rule in rules:
            rule.apply(event)

        assert event.tempo_mult == original_tempo
        assert event.amp_mult == original_amp
        assert not hasattr(event, "gate_time")
        assert event.timing_deviation_ms == 0.0  # type: ignore[attr-defined]


class TestMotifMemoryIntegration:
    """R9 uses the same role gate after the existing per-event R1-R8 contract."""

    def test_repeated_melody_motif_is_varied_after_existing_event_rules(self) -> None:
        first = _melody_motif()
        repeat = _melody_motif()
        rule = MotifMemoryRule(seed=1)

        _shape_with_r2_r5_r7_r8(first)
        _shape_with_r2_r5_r7_r8(repeat)
        rule.apply(first, k=1.0, seeds=None, roles=frozenset({"melody"}))
        rule.apply(repeat, k=1.0, seeds=None, roles=frozenset({"melody"}))

        assert first[0].metadata["motif_memory_variation"] == "original"
        assert repeat[0].metadata["motif_memory_variation"] == "transposition"
        assert repeat[0].pitch == 62  # type: ignore[attr-defined]

    def test_grid_locked_motif_is_not_cached_or_varied(self) -> None:
        first = [_ostinato_event(0.25), _ostinato_event(0.5), _ostinato_event(0.75)]
        repeat = [_ostinato_event(0.25), _ostinato_event(0.5), _ostinato_event(0.75)]
        rule = MotifMemoryRule(seed=1)

        _shape_with_r2_r5_r7_r8(first)
        _shape_with_r2_r5_r7_r8(repeat)
        rule.apply(first, k=1.0, seeds=None, roles=frozenset({"ostinato"}))
        rule.apply(repeat, k=1.0, seeds=None, roles=frozenset({"ostinato"}))

        assert len(rule.memory) == 0
        assert "motif_memory_variation" not in first[0].metadata
        assert "motif_memory_variation" not in repeat[0].metadata


class TestGateLeakDetection:
    """Verify that a non-zero timing_deviation_ms on ostinato indicates a leaked rule."""

    def test_ostinato_nonzero_timing_deviation_fails(self) -> None:
        rule = MicrotimingRule(seed=42)
        for step in range(100):
            event = _ostinato_event()
            event.step_index = step  # type: ignore[attr-defined]
            rule.apply(event)
            assert event.timing_deviation_ms == 0.0, (  # type: ignore[attr-defined]
                f"ostinato leaked at step {step}: "
                f"timing_deviation_ms={event.timing_deviation_ms}"  # type: ignore[attr-defined]
            )

    @pytest.mark.parametrize("role", sorted(GRID_LOCKED_ROLES))
    def test_no_rule_mutates_grid_locked_event(self, role: str) -> None:
        rules = [
            PhraseArchRule(),
            FinalRitRule(onset_position=0.0),
            ArticulationRule(),
            MicrotimingRule(seed=42),
        ]
        event = Event(
            role=role,
            normalized_phrase_position=0.85,
            section_envelope=SectionEnvelope(tempo_base=1.0),
            phrase=_CadentialPhrase(),
        )
        event.articulation_style = "normal"  # type: ignore[attr-defined]
        event.nominal_dur_sec = 0.5  # type: ignore[attr-defined]
        event.pitch = 48  # type: ignore[attr-defined]
        event.step_index = 7  # type: ignore[attr-defined]

        for rule in rules:
            rule.apply(event)

        assert event.tempo_mult == 1.0
        assert event.amp_mult == 1.0
        assert not hasattr(event, "gate_time")
        assert event.timing_deviation_ms == 0.0  # type: ignore[attr-defined]
