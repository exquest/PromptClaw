"""Tests for narrative beat → SectionEnvelope coupling (T-038)."""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from cypherclaw.render.narrative_envelope import (
    NarrativeBeat,
    ToneVector,
    beat_from_directive,
    envelope_for_beat,
    tone_from_narrative,
)
from cypherclaw.render.events import SectionEnvelope
from senseweave.procedural_arc import ARC_PHASES, ArcDirective, directive_for_elapsed


def _sample_tension_at(envelope: SectionEnvelope, position: float) -> float:
    return envelope.value_at("tension_trajectory", position)


def _make_beat(
    arc_phase: str = "Emergence",
    section_function: str = "statement",
    tension_target: float = 0.5,
    darkness: float = 0.5,
    energy: float = 0.5,
    warmth: float = 0.5,
    density: float = 0.5,
) -> NarrativeBeat:
    return NarrativeBeat(
        arc_phase=arc_phase,
        section_function=section_function,
        tension_target=tension_target,
        tone=ToneVector(
            darkness=darkness,
            energy=energy,
            warmth=warmth,
            density=density,
        ),
    )


class TestEnvelopeForBeat:
    def test_arc_phase_produces_distinct_tension_shapes(self) -> None:
        phases = ["Divination", "Emergence", "Conversation", "Convergence", "Crystallization"]
        envelopes = {
            phase: envelope_for_beat(_make_beat(arc_phase=phase))
            for phase in phases
        }

        div_start = _sample_tension_at(envelopes["Divination"], 0.0)
        div_end = _sample_tension_at(envelopes["Divination"], 1.0)
        assert div_end > div_start, "Divination should rise"

        conv_mid = _sample_tension_at(envelopes["Conversation"], 0.5)
        assert conv_mid >= 0.55, "Conversation mid should be high tension"

        cryst_start = _sample_tension_at(envelopes["Crystallization"], 0.0)
        cryst_end = _sample_tension_at(envelopes["Crystallization"], 1.0)
        assert cryst_end < cryst_start, "Crystallization should settle"

        emerg_end = _sample_tension_at(envelopes["Emergence"], 1.0)
        assert emerg_end > div_end * 0.8, "Emergence should rise higher than Divination"

        conv_peak = max(
            _sample_tension_at(envelopes["Convergence"], p)
            for p in [0.0, 0.25, 0.35, 0.5, 0.75, 1.0]
        )
        cryst_peak = max(
            _sample_tension_at(envelopes["Crystallization"], p)
            for p in [0.0, 0.25, 0.5, 0.75, 1.0]
        )
        assert conv_peak > cryst_peak, "Convergence peak should exceed Crystallization peak"

    def test_section_function_modifies_tension(self) -> None:
        base = envelope_for_beat(_make_beat(section_function="statement"))
        dev = envelope_for_beat(_make_beat(section_function="development"))
        turn = envelope_for_beat(_make_beat(section_function="turn"))
        recap = envelope_for_beat(_make_beat(section_function="recap"))
        coda = envelope_for_beat(_make_beat(section_function="coda"))

        base_peak = max(_sample_tension_at(base, p) for p in [0.0, 0.25, 0.5, 0.75, 1.0])
        dev_peak = max(_sample_tension_at(dev, p) for p in [0.0, 0.25, 0.5, 0.75, 1.0])
        turn_peak = max(_sample_tension_at(turn, p) for p in [0.0, 0.25, 0.5, 0.75, 1.0])
        recap_end = _sample_tension_at(recap, 1.0)
        coda_end = _sample_tension_at(coda, 1.0)

        assert dev_peak > base_peak, "development should push peak higher"
        assert turn_peak > base_peak, "turn should push peak higher"
        assert recap_end < _sample_tension_at(recap, 0.0), "recap should resolve toward end"
        assert coda_end < _sample_tension_at(coda, 0.0), "coda should resolve toward end"

    def test_tone_vector_influences_envelope_parameters(self) -> None:
        bright_beat = _make_beat(darkness=0.1, energy=0.8)
        dark_beat = _make_beat(darkness=0.9, energy=0.2)

        bright_env = envelope_for_beat(bright_beat)
        dark_env = envelope_for_beat(dark_beat)

        bright_sample = bright_env.sample(0.5)
        dark_sample = dark_env.sample(0.5)

        assert bright_sample.brightness > dark_sample.brightness, (
            "low darkness should produce higher brightness"
        )
        assert bright_sample.dynamic_plane > dark_sample.dynamic_plane, (
            "high energy should produce higher dynamic plane"
        )

        dense_beat = _make_beat(density=0.9)
        sparse_beat = _make_beat(density=0.1)
        dense_env = envelope_for_beat(dense_beat)
        sparse_env = envelope_for_beat(sparse_beat)

        assert dense_env.sample(0.5).density_target > sparse_env.sample(0.5).density_target, (
            "higher tone density should produce higher density_target"
        )

    def test_deterministic_output(self) -> None:
        beat = _make_beat(
            arc_phase="Conversation",
            section_function="development",
            tension_target=0.7,
            darkness=0.3,
            energy=0.6,
            warmth=0.5,
            density=0.65,
        )
        env_a = envelope_for_beat(beat)
        env_b = envelope_for_beat(beat)

        for position in [0.0, 0.25, 0.5, 0.75, 1.0]:
            sample_a = env_a.sample(position)
            sample_b = env_b.sample(position)
            assert sample_a == sample_b, f"Envelopes differ at position {position}"

    def test_all_parameters_in_valid_range(self) -> None:
        phases = ["Divination", "Emergence", "Conversation", "Convergence", "Crystallization"]
        functions = ["invocation", "statement", "development", "turn", "recap", "coda", "residue"]
        for phase in phases:
            for func in functions:
                beat = _make_beat(arc_phase=phase, section_function=func)
                env = envelope_for_beat(beat)
                for pos in [0.0, 0.25, 0.5, 0.75, 1.0]:
                    sample = env.sample(pos)
                    assert sample.tempo_base > 0.0, f"tempo_base must be > 0 at {phase}/{func}/{pos}"
                    assert 0.0 <= sample.density_target <= 1.0, f"density_target out of range at {phase}/{func}/{pos}"
                    assert 0.0 <= sample.dynamic_plane <= 1.0, f"dynamic_plane out of range at {phase}/{func}/{pos}"
                    assert 0.0 <= sample.brightness <= 1.0, f"brightness out of range at {phase}/{func}/{pos}"
                    assert 0.0 <= sample.tension_trajectory <= 1.0, f"tension_trajectory out of range at {phase}/{func}/{pos}"

    def test_unknown_phase_uses_emergence_defaults(self) -> None:
        unknown = envelope_for_beat(_make_beat(arc_phase="NonexistentPhase"))
        emergence = envelope_for_beat(_make_beat(arc_phase="Emergence"))
        for pos in [0.0, 0.5, 1.0]:
            assert unknown.sample(pos) == emergence.sample(pos)

    def test_unknown_function_uses_neutral_modifiers(self) -> None:
        unknown = envelope_for_beat(_make_beat(section_function="unknown_func"))
        statement = envelope_for_beat(_make_beat(section_function="statement"))
        for pos in [0.0, 0.5, 1.0]:
            assert unknown.sample(pos) == statement.sample(pos)


class TestToneFromNarrative:
    def test_negative_mood_increases_darkness(self) -> None:
        dark_tone = tone_from_narrative(
            arc_phase="Emergence",
            mood=-0.8,
            creative_energy=0.5,
            curiosity=0.5,
            density_target=0.5,
            dynamic_target="mf",
            timbre_target="warm",
        )
        bright_tone = tone_from_narrative(
            arc_phase="Emergence",
            mood=0.8,
            creative_energy=0.5,
            curiosity=0.5,
            density_target=0.5,
            dynamic_target="mf",
            timbre_target="warm",
        )
        assert dark_tone.darkness > bright_tone.darkness

    def test_energy_maps_to_energy(self) -> None:
        high = tone_from_narrative(
            arc_phase="Emergence",
            mood=0.0,
            creative_energy=0.9,
            curiosity=0.5,
            density_target=0.5,
            dynamic_target="mf",
            timbre_target="warm",
        )
        low = tone_from_narrative(
            arc_phase="Emergence",
            mood=0.0,
            creative_energy=0.1,
            curiosity=0.5,
            density_target=0.5,
            dynamic_target="mf",
            timbre_target="warm",
        )
        assert high.energy > low.energy

    def test_density_target_passes_through(self) -> None:
        tone = tone_from_narrative(
            arc_phase="Emergence",
            mood=0.0,
            creative_energy=0.5,
            curiosity=0.5,
            density_target=0.78,
            dynamic_target="mf",
            timbre_target="warm",
        )
        assert math.isclose(tone.density, 0.78, abs_tol=0.01)


class TestBeatFromDirective:
    def test_directive_to_beat_conversion(self) -> None:
        directive = directive_for_elapsed(15.0, cadence_state="away_practice")
        beat = beat_from_directive(directive, "development")

        assert beat.arc_phase == directive.phase.name
        assert beat.section_function == "development"
        assert 0.0 <= beat.tension_target <= 1.0
        assert 0.0 <= beat.tone.darkness <= 1.0
        assert 0.0 <= beat.tone.energy <= 1.0
        assert 0.0 <= beat.tone.warmth <= 1.0
        assert 0.0 <= beat.tone.density <= 1.0

    def test_all_arc_phases_produce_valid_beats(self) -> None:
        for phase in ARC_PHASES:
            directive = ArcDirective(
                phase=phase,
                density_target=phase.density,
                mutation_rate=phase.mutation_rate,
                max_active_roles=3,
                recovery_bias=0.0,
                dynamic_target=phase.dynamic,
                harmonic_target=phase.harmonic,
                rhythm_target=phase.rhythm,
                timbre_target=phase.timbre,
                spatial_target=phase.spatial,
                compression_target=phase.compression,
                senseweave_target=phase.senseweave,
                synthesis_target=phase.synthesis,
            )
            beat = beat_from_directive(directive, "statement")
            env = envelope_for_beat(beat)
            sample = env.sample(0.5)
            assert 0.0 <= sample.tension_trajectory <= 1.0
            assert sample.tempo_base > 0.0


class TestComposerIntegration:
    def test_score_tree_sections_have_narrative_envelopes(self) -> None:
        from senseweave.recursive_composer import compose_score_tree
        from senseweave.piece_commission import PieceCommission
        from senseweave.piece_brief import PieceBrief
        from senseweave.form_grammar import FormPlan, PlannedSection

        commission = PieceCommission(
            form_class="song",
            composition_mode="hybrid",
            duration_target_s=180.0,
            sonic_world_count=2,
            hook_pressure=0.6,
            narrative_scale="scene",
            ending_family="afterglow",
            groove_identity="pulse",
            reason_tags=("test",),
            arc_elapsed_minutes=15.0,
            arc_cycle_minutes=30.0,
        )

        brief = PieceBrief(
            image_field=("room", "wire"),
            dramatic_premise="test premise",
            conflict="test conflict",
            desired_payoff="test payoff",
            residue="test residue",
            ending_feeling="afterglow",
            motion_character="pulse",
            hook_pressure=0.6,
            through_composed_pressure=0.4,
            section_beats=("opening image", "statement", "complication", "turn", "payoff", "residue"),
            narrative_scale="scene",
        )

        form = FormPlan(
            form_family="ternary",
            form_class="song",
            composition_mode="hybrid",
            sections=(
                PlannedSection(
                    scene_name="Opening",
                    function="invocation",
                    target_duration_s=30.0,
                    return_from=None,
                    transform_strength="none",
                    harmonic_role="tonic",
                ),
                PlannedSection(
                    scene_name="Statement",
                    function="statement",
                    target_duration_s=45.0,
                    return_from=None,
                    transform_strength="none",
                    harmonic_role="tonic",
                ),
                PlannedSection(
                    scene_name="Development",
                    function="development",
                    target_duration_s=45.0,
                    return_from=None,
                    transform_strength="moderate",
                    harmonic_role="dominant",
                ),
                PlannedSection(
                    scene_name="Recap",
                    function="recap",
                    target_duration_s=35.0,
                    return_from="Statement",
                    transform_strength="none",
                    harmonic_role="tonic",
                ),
                PlannedSection(
                    scene_name="Coda",
                    function="coda",
                    target_duration_s=25.0,
                    return_from=None,
                    transform_strength="none",
                    harmonic_role="plagal",
                ),
            ),
            ending_family="afterglow",
        )

        tree = compose_score_tree(
            commission=commission,
            brief=brief,
            form=form,
            family="test",
            cadence_state="away_practice",
            progression_profile="modal",
            song_num=1,
            mood={"valence": 0.2},
            composition_seed="t038-test-seed",
        )

        for section in tree.sections:
            env = section.section_envelope
            assert env is not None, f"Section {section.scene_name} has no envelope"
            sample = env.sample(0.5)
            assert sample.tempo_base > 0.0, f"Section {section.scene_name} has zero tempo_base"
            has_nondefault = (
                not math.isclose(sample.tension_trajectory, 0.0, abs_tol=0.001)
                or not math.isclose(sample.density_target, 1.0, abs_tol=0.001)
                or not math.isclose(sample.brightness, 1.0, abs_tol=0.001)
                or not math.isclose(sample.dynamic_plane, 1.0, abs_tol=0.001)
            )
            assert has_nondefault, (
                f"Section {section.scene_name} still has all-default envelope parameters"
            )

    def test_different_arc_positions_produce_different_envelopes(self) -> None:
        from senseweave.recursive_composer import compose_score_tree
        from senseweave.piece_commission import PieceCommission
        from senseweave.piece_brief import PieceBrief
        from senseweave.form_grammar import FormPlan, PlannedSection

        sections_spec = (
            PlannedSection(
                scene_name="A",
                function="statement",
                target_duration_s=60.0,
                return_from=None,
                transform_strength="none",
                harmonic_role="tonic",
            ),
        )

        brief = PieceBrief(
            image_field=("room",),
            dramatic_premise="p",
            conflict="c",
            desired_payoff="d",
            residue="r",
            ending_feeling="fade",
            motion_character="pulse",
            hook_pressure=0.5,
            through_composed_pressure=0.3,
            section_beats=("beat",),
            narrative_scale="scene",
        )

        form = FormPlan(
            form_family="minimal",
            form_class="micro",
            composition_mode="hook_led",
            sections=sections_spec,
            ending_family="fade",
        )

        tree_early = compose_score_tree(
            commission=PieceCommission(
                form_class="micro",
                composition_mode="hook_led",
                duration_target_s=60.0,
                sonic_world_count=1,
                hook_pressure=0.7,
                narrative_scale="single_image",
                ending_family="fade",
                groove_identity="pulse",
                reason_tags=("test",),
                arc_elapsed_minutes=0.0,
                arc_cycle_minutes=30.0,
            ),
            brief=brief,
            form=form,
            family="test",
            cadence_state="away_practice",
            progression_profile="modal",
            song_num=1,
            mood={},
            composition_seed="t038-position-test",
        )

        tree_late = compose_score_tree(
            commission=PieceCommission(
                form_class="micro",
                composition_mode="hook_led",
                duration_target_s=60.0,
                sonic_world_count=1,
                hook_pressure=0.7,
                narrative_scale="single_image",
                ending_family="fade",
                groove_identity="pulse",
                reason_tags=("test",),
                arc_elapsed_minutes=13.0,
                arc_cycle_minutes=30.0,
            ),
            brief=brief,
            form=form,
            family="test",
            cadence_state="away_practice",
            progression_profile="modal",
            song_num=1,
            mood={},
            composition_seed="t038-position-test",
        )

        early_sample = tree_early.sections[0].section_envelope.sample(0.5)
        late_sample = tree_late.sections[0].section_envelope.sample(0.5)

        assert early_sample != late_sample, (
            "Envelopes at different arc positions should differ"
        )
