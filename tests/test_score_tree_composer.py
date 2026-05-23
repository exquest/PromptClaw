from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from cypherclaw import midi_vocabulary_store as store
from cypherclaw.render.events import IntentTag, PerformanceIntent, SectionEnvelope
from inner_life.world_model import WorldModel
from senseweave.composition_gate import evaluate_score_tree
from senseweave.form_grammar import PlannedSection, plan_form
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece
from senseweave.procedural_arc import ArcDirective, ArcPhase, directive_for_elapsed
from senseweave.recursive_composer import (
    compose_score_tree,
    plan_meter_trajectory,
    plan_tuning_trajectory,
)
from senseweave.score_tree import ScoreTree
from senseweave.tracker_compiler import compile_score_tree_to_tracker


def _compose_tree(
    *,
    composition_seed: str | None = None,
    vocabulary_db_path: Path | None = None,
    vocabulary_curiosity: float = 0.15,
):
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.58,
        song_num=8,
        hour=15,
    )
    world = WorldModel(
        observer_description="bright room with one person near the kitchen",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="day",
        occupancy_state="occupied_active",
        attention_score=0.58,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="bloom",
        cadence_state="occupied_day",
        progression_profile="open_day",
    )
    form = plan_form(commission=commission, brief=brief, family="bloom")
    return compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="bloom",
        cadence_state="occupied_day",
        progression_profile="open_day",
        song_num=8,
        mood={"energy": 0.58, "valence": 0.63, "arousal": 0.44},
        composition_seed=composition_seed,
        vocabulary_db_path=vocabulary_db_path,
        vocabulary_curiosity=vocabulary_curiosity,
    )


def _score_tree_hash(tree: ScoreTree) -> str:
    return hashlib.sha256(tree.to_json().encode("utf-8")).hexdigest()


def _directive_named(phase_name: str) -> ArcDirective:
    phase = ArcPhase(
        phase_name,
        0.0,
        1.0,
        0.5,
        0.3,
        "test transition",
        "mf",
        "modal",
        "pulse",
        "warm",
        "clear",
        0.3,
        0.5,
        "fm",
    )
    return ArcDirective(
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


def test_plan_tuning_trajectory_applies_phase_rule_and_detects_morphs() -> None:
    sections = (
        PlannedSection("ListenScene", "invocation", 20.0, harmonic_role="tonic"),
        PlannedSection("ConversationScene", "development", 20.0, harmonic_role="predominant"),
        PlannedSection("DivinationScene", "turn", 20.0, harmonic_role="borrowed"),
        PlannedSection("ProcessionScene", "recap", 20.0, harmonic_role="authentic"),
    )
    phase_by_scene = {
        "ListenScene": "Listen",
        "ConversationScene": "Conversation",
        "DivinationScene": "Divination",
        "ProcessionScene": "Procession",
    }
    directives = {
        scene_name: _directive_named(phase_name)
        for scene_name, phase_name in phase_by_scene.items()
    }

    trajectory = plan_tuning_trajectory(
        sections,
        directives,
        cadence_state="occupied_day",
        trajectory_seed="t-039-phase-rule",
    )
    repeated = plan_tuning_trajectory(
        sections,
        directives,
        cadence_state="occupied_day",
        trajectory_seed="t-039-phase-rule",
    )

    assert trajectory is not None
    assert trajectory == repeated
    assert trajectory.arc_plan == "cypherclaw_phase_tuning"
    by_scene = {value.scene_name: value for value in trajectory.scene_values}
    assert by_scene["ListenScene"].tuning_system_name == "just_intonation_5_limit"
    assert by_scene["DivinationScene"].tuning_system_name == "just_intonation_5_limit"
    assert by_scene["ConversationScene"].tuning_system_name == "gamelan_slendro"
    assert by_scene["ProcessionScene"].tuning_system_name == "gamelan_slendro"
    assert by_scene["ListenScene"].transition_kind == "steady"
    assert by_scene["ConversationScene"].transition_kind == "stillness_to_motion"
    assert by_scene["ConversationScene"].tuning_morph_source_name == "just_intonation_5_limit"
    assert by_scene["ConversationScene"].tuning_morph_target_name == "gamelan_slendro"
    assert by_scene["DivinationScene"].transition_kind == "motion_to_stillness"
    assert by_scene["DivinationScene"].tuning_morph_source_name == "gamelan_slendro"
    assert by_scene["DivinationScene"].tuning_morph_target_name == "just_intonation_5_limit"
    assert by_scene["ProcessionScene"].transition_kind == "stillness_to_motion"

    metadata = trajectory.metadata_for_scene("ConversationScene")
    assert metadata["tuning_system_name"] == "gamelan_slendro"
    assert metadata["tuning_morph_target_name"] == "gamelan_slendro"
    assert metadata["tuning_morph_curve"] == "linear"
    assert metadata["tuning_transition_kind"] == "stillness_to_motion"
    assert metadata["tuning_morph_source_name"] == "just_intonation_5_limit"

    log_lines = trajectory.composer_log_lines()
    assert len(log_lines) == len(sections)
    assert any(
        "phase=Conversation" in line
        and "tuning_system_name=gamelan_slendro" in line
        and "transition=stillness_to_motion" in line
        for line in log_lines
    )


def test_plan_meter_trajectory_uses_arc_phase_drift_table() -> None:
    sections = (
        PlannedSection("Opening", "invocation", 20.0, harmonic_role="tonic"),
        PlannedSection("Pattern", "statement", 20.0, harmonic_role="tonic"),
        PlannedSection("Dialogue", "development", 20.0, harmonic_role="predominant"),
        PlannedSection("Return", "recap", 20.0, harmonic_role="authentic"),
        PlannedSection("Residue", "afterglow", 20.0, harmonic_role="plagal"),
    )
    elapsed_by_scene = {
        "Opening": 1.0,
        "Pattern": 7.0,
        "Dialogue": 15.0,
        "Return": 22.0,
        "Residue": 28.0,
    }
    directives = {
        scene_name: directive_for_elapsed(
            elapsed,
            cadence_state="occupied_day",
            cycle_minutes=30.0,
        )
        for scene_name, elapsed in elapsed_by_scene.items()
    }

    trajectory = plan_meter_trajectory(
        sections,
        directives,
        cadence_state="occupied_day",
        groove_identity="pulse",
        trajectory_seed="t-022b-fixture",
    )
    repeated = plan_meter_trajectory(
        sections,
        directives,
        cadence_state="occupied_day",
        groove_identity="pulse",
        trajectory_seed="t-022b-fixture",
    )

    assert trajectory is not None
    assert trajectory == repeated
    assert trajectory.arc_plan == "arc_phase_drift"
    assert trajectory.arc_phase == "Divination->Emergence->Conversation->Convergence->Crystallization"
    assert tuple(value.scene_name for value in trajectory.scene_values) == tuple(
        section.scene_name for section in sections
    )
    meters = tuple(value.meter for value in trajectory.scene_values)
    assert len(set(meters)) >= 4
    assert "15/16" in meters
    assert "7/8" in meters
    dialogue = trajectory.scene_value_for("Dialogue")
    assert dialogue is not None
    assert dialogue.subdivision == "polyrhythmic"
    assert dialogue.groove_timing == "metric_modulation"
    assert dialogue.metric_modulation == "5:4"
    assert dialogue.polymeter == (3, 4)
    assert all(
        isinstance(value, str)
        for value in trajectory.metadata_for_scene("Dialogue").values()
    )


def test_plan_meter_trajectory_restarts_phase_drift_per_arc_cycle() -> None:
    sections = (
        PlannedSection("OpeningA", "invocation", 12.0, harmonic_role="tonic"),
        PlannedSection("PatternA", "statement", 12.0, harmonic_role="tonic"),
        PlannedSection("DialogueA", "development", 12.0, harmonic_role="predominant"),
        PlannedSection("ReturnA", "recap", 12.0, harmonic_role="authentic"),
        PlannedSection("ResidueA", "afterglow", 12.0, harmonic_role="plagal"),
        PlannedSection("OpeningB", "invocation", 12.0, harmonic_role="tonic"),
        PlannedSection("PatternB", "statement", 12.0, harmonic_role="tonic"),
    )
    elapsed_by_scene = {
        "OpeningA": 1.0,
        "PatternA": 7.0,
        "DialogueA": 15.0,
        "ReturnA": 22.0,
        "ResidueA": 28.0,
        "OpeningB": 31.0,
        "PatternB": 37.0,
    }
    directives = {
        section.scene_name: directive_for_elapsed(
            elapsed_by_scene[section.scene_name],
            cadence_state="occupied_day",
            cycle_minutes=30.0,
        )
        for section in sections
    }

    trajectory = plan_meter_trajectory(
        sections,
        directives,
        cadence_state="occupied_day",
        groove_identity="pulse",
        trajectory_seed="t-022d-arc-cycle",
    )

    assert trajectory is not None
    assert tuple(directives[section.scene_name].phase.name for section in sections) == (
        "Divination",
        "Emergence",
        "Conversation",
        "Convergence",
        "Crystallization",
        "Divination",
        "Emergence",
    )
    assert tuple(value.meter for value in trajectory.scene_values) == (
        "free",
        "4/4",
        "15/16",
        "7/8",
        "3/4",
        "free",
        "4/4",
    )
    opening_b = trajectory.scene_value_for("OpeningB")
    pattern_b = trajectory.scene_value_for("PatternB")
    assert opening_b is not None
    assert pattern_b is not None
    assert opening_b.subdivision == "rubato"
    assert opening_b.groove_timing == "rubato"
    assert pattern_b.subdivision == "straight"
    assert json.loads(trajectory.metadata_for_scene("OpeningB")["meter_trajectory_path"]) == [
        "free",
        "4/4",
        "15/16",
        "7/8",
        "3/4",
        "free",
        "4/4",
    ]


def test_recursive_composer_builds_complete_score_tree() -> None:
    tree = _compose_tree()

    assert tree.title
    assert tree.motifs
    assert tree.sections
    assert tree.primary_hook_text
    assert tree.planned_duration_s > 0
    assert tree.form.section_functions


def test_recursive_composer_plans_meter_trajectory_for_full_arc() -> None:
    tree = _compose_tree(composition_seed="t-022b-full-arc")

    assert tree.meter_trajectory is not None
    assert len(tree.meter_trajectory.scene_values) == len(tree.sections)
    assert tuple(value.scene_name for value in tree.meter_trajectory.scene_values) == tuple(
        section.scene_name for section in tree.sections
    )
    meter_path = [value.meter for value in tree.meter_trajectory.scene_values]
    assert any(meter in {"7/8", "11/8", "15/16"} for meter in meter_path)
    assert tree.arrangement_plan["meter_trajectory"]["meter_path"] == meter_path
    assert tree.arrangement_plan["meter_trajectory"]["arc_plan"] == "arc_phase_drift"
    for section, value in zip(tree.sections, tree.meter_trajectory.scene_values):
        assert section.scene_metadata["meter_trajectory_id"] == tree.meter_trajectory.trajectory_id
        assert section.scene_metadata["meter_trajectory_scene"] == section.scene_name
        assert section.scene_metadata["meter_trajectory_meter"] == value.meter
        assert json.loads(section.scene_metadata["meter_trajectory_path"]) == meter_path


def test_recursive_composer_records_tuning_selection_log_for_30_minute_arc() -> None:
    tree = _compose_tree(composition_seed="t-039-30-minute-arc")

    assert tree.tuning_trajectory is not None
    payload = tree.arrangement_plan["tuning_trajectory"]
    log_lines = payload["composer_log"]

    assert len(log_lines) == len(tree.sections)
    assert all("composer_tuning_selection" in line for line in log_lines)
    assert all("tuning_system_name=" in line for line in log_lines)
    assert any(
        "phase=Divination" in line
        and "tuning_system_name=just_intonation_5_limit" in line
        for line in log_lines
    )
    assert any(
        "phase=Conversation" in line
        and "tuning_system_name=gamelan_slendro" in line
        for line in log_lines
    )
    assert any("transition=stillness_to_motion" in line for line in log_lines)
    assert any("transition=motion_to_stillness" in line for line in log_lines)

    entries = payload["scene_entries"]
    transition_entries = [
        entry
        for entry in entries
        if entry["transition_kind"] in {"stillness_to_motion", "motion_to_stillness"}
    ]
    assert transition_entries
    assert payload["tuning_path"] == [
        value.tuning_system_name for value in tree.tuning_trajectory.scene_values
    ]


def test_composed_tuning_trajectory_survives_tracker_compile() -> None:
    tree = _compose_tree(composition_seed="t-039-compile")

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.58, "valence": 0.63, "arousal": 0.44},
        family_name="bloom",
        patch_name="house_garden",
        cadence_state="occupied_day",
        progression_profile="open_day",
    )

    assert tree.tuning_trajectory is not None
    scene_by_name = {scene.name: scene for scene in compiled.tracker_song.scenes}
    for section, value in zip(tree.sections, tree.tuning_trajectory.scene_values):
        scene = scene_by_name[section.scene_name]
        assert scene.metadata["tuning_trajectory_id"] == tree.tuning_trajectory.trajectory_id
        assert scene.metadata["tuning_trajectory_scene"] == section.scene_name
        assert scene.metadata["tuning_arc_phase"] == value.arc_phase
        assert scene.metadata["tuning_system_name"] == value.tuning_system_name
        assert scene.metadata["tuning_morph_curve"] == "linear"
        assert "tuning_morph_target_name" in scene.metadata


def test_composed_tuning_trajectory_scene_metadata_round_trips_through_json() -> None:
    tree = _compose_tree(composition_seed="t-039-json-roundtrip")
    restored = ScoreTree.from_dict(json.loads(tree.to_json()))

    assert restored.tuning_trajectory == tree.tuning_trajectory
    assert restored.tuning_trajectory is not None
    for section, value in zip(restored.sections, restored.tuning_trajectory.scene_values):
        expected_metadata = restored.tuning_trajectory.metadata_for_scene(section.scene_name)
        assert section.scene_metadata["tuning_trajectory_id"] == expected_metadata["tuning_trajectory_id"]
        assert section.scene_metadata["tuning_system_name"] == value.tuning_system_name
        assert section.scene_metadata["tuning_morph_target_name"] == value.tuning_morph_target_name
        assert json.loads(section.scene_metadata["tuning_trajectory_entry"]) == json.loads(
            expected_metadata["tuning_trajectory_entry"]
        )


def test_recursive_composer_records_meter_trajectory_scene_entries() -> None:
    tree = _compose_tree(composition_seed="t-022c-scene-entries")

    assert tree.meter_trajectory is not None
    payload = tree.arrangement_plan["meter_trajectory"]
    entries = payload["scene_entries"]

    assert len(entries) == len(tree.sections)
    for index, (entry, section, value) in enumerate(
        zip(entries, tree.sections, tree.meter_trajectory.scene_values)
    ):
        assert entry["scene_name"] == section.scene_name
        assert entry["index"] == index
        assert entry["scene_count"] == len(tree.sections)
        assert entry["meter"] == value.meter
        assert entry["subdivision"] == value.subdivision
        assert entry["groove_timing"] == value.groove_timing
        assert entry["phrase_breath"] == value.phrase_breath


def test_composed_meter_trajectory_survives_tracker_compile() -> None:
    tree = _compose_tree(composition_seed="t-022b-compile")

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.58, "valence": 0.63, "arousal": 0.44},
        family_name="bloom",
        patch_name="house_garden",
        cadence_state="occupied_day",
        progression_profile="open_day",
    )

    assert tree.meter_trajectory is not None
    meter_path = [value.meter for value in tree.meter_trajectory.scene_values]
    scene_by_name = {scene.name: scene for scene in compiled.tracker_song.scenes}
    for section, value in zip(tree.sections, tree.meter_trajectory.scene_values):
        scene = scene_by_name[section.scene_name]
        assert scene.metadata["meter_trajectory_id"] == tree.meter_trajectory.trajectory_id
        assert scene.metadata["meter_trajectory_scene"] == section.scene_name
        assert scene.metadata["meter_trajectory_meter"] == value.meter
        assert json.loads(scene.metadata["meter_trajectory_path"]) == meter_path


def test_composed_meter_trajectory_scene_metadata_round_trips_through_json_and_tracker() -> None:
    tree = _compose_tree(composition_seed="t-022d-metadata-roundtrip")
    restored = ScoreTree.from_dict(json.loads(tree.to_json()))

    compiled = compile_score_tree_to_tracker(
        restored,
        mood={"energy": 0.58, "valence": 0.63, "arousal": 0.44},
        family_name="bloom",
        patch_name="house_garden",
        cadence_state="occupied_day",
        progression_profile="open_day",
    )

    assert restored.meter_trajectory == tree.meter_trajectory
    assert restored.meter_trajectory is not None
    meter_path = [value.meter for value in restored.meter_trajectory.scene_values]
    scene_by_name = {scene.name: scene for scene in compiled.tracker_song.scenes}
    for section, value in zip(restored.sections, restored.meter_trajectory.scene_values):
        expected_metadata = restored.meter_trajectory.metadata_for_scene(section.scene_name)
        assert section.scene_metadata == expected_metadata

        scene = scene_by_name[section.scene_name]
        assert scene.metadata["meter_trajectory_id"] == restored.meter_trajectory.trajectory_id
        assert scene.metadata["meter_trajectory_scene"] == section.scene_name
        assert scene.metadata["meter_trajectory_meter"] == value.meter
        assert json.loads(scene.metadata["meter_trajectory_path"]) == meter_path
        assert json.loads(scene.metadata["meter_trajectory_entry"]) == json.loads(
            section.scene_metadata["meter_trajectory_entry"]
        )


def test_recursive_composer_seed_is_deterministic_and_attaches_render_metadata() -> None:
    first = _compose_tree(composition_seed="t-035-seed")
    second = _compose_tree(composition_seed="t-035-seed")

    assert _score_tree_hash(first) == _score_tree_hash(second)
    assert first.to_json().encode("utf-8") == second.to_json().encode("utf-8")
    assert first.metadata["composition_seed"] == "t-035-seed"

    valid_intent_tags = {tag.value for tag in IntentTag}
    for section in first.sections:
        assert isinstance(section.section_envelope, SectionEnvelope)
        assert section.section_envelope.sample(0.5).tempo_base > 0.0
        for phrase in section.phrases:
            assert phrase.intent_tag in valid_intent_tags
            assert isinstance(phrase.performance_intent, PerformanceIntent)
            assert phrase.performance_intent.phrase_id == phrase.phrase_id

    serialized = json.loads(first.to_json())
    assert all("section_envelope" in section for section in serialized["sections"])
    assert all(
        phrase["performance_intent"]["phrase_id"] == phrase["phrase_id"]
        for section in serialized["sections"]
        for phrase in section["phrases"]
    )
    assert ScoreTree.from_dict(serialized).to_json() == first.to_json()


def test_composition_gate_rejects_underbuilt_piece() -> None:
    tree = _compose_tree()
    broken = replace(
        tree,
        sections=tree.sections[:1],
        planned_duration_s=18.0,
    )

    report = evaluate_score_tree(broken)
    assert report.approved is False
    assert report.failures


def test_composition_gate_accepts_valid_composed_piece() -> None:
    tree = _compose_tree()
    report = evaluate_score_tree(tree)
    assert report.approved is True
    for metric in (
        "duration_fit",
        "recurrence",
        "transformation",
        "arrangement_contrast",
        "energy_curve",
        "motif_clarity",
    ):
        assert isinstance(report.metrics[metric], float)


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    (
        (
            lambda tree: replace(
                tree,
                sections=tuple(replace(section, return_from=None) for section in tree.sections),
            ),
            "piece has no structural recurrence",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        transform_strength="none",
                        phrases=tuple(replace(phrase, transform_ops=()) for phrase in section.phrases),
                    )
                    for section in tree.sections
                ),
            ),
            "piece has no transformed return or development",
        ),
        (
            lambda tree: replace(tree, ending_family=""),
            "missing ending family",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(section, harmonic_role="tonic", cadence_type="suspended", groove_state="pulse")
                    for section in tree.sections
                ),
            ),
            "arrangement lacks contrast",
        ),
        (
            lambda tree: replace(
                tree,
                narrative_map={section.scene_name: "holding pattern" for section in tree.sections},
            ),
            "piece has no narrative payoff",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        production_course={**section.production_course, "mode_scale": ""}
                    )
                    for section in tree.sections
                ),
            ),
            "missing harmonic metadata",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        production_course={**section.production_course, "meter_groove": ""}
                    )
                    for section in tree.sections
                ),
            ),
            "missing rhythm metadata",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        production_course={**section.production_course, "mix_role": ""}
                    )
                    for section in tree.sections
                ),
            ),
            "missing mix role",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        production_course={**section.production_course, "transition_type": ""}
                    )
                    for section in tree.sections
                ),
            ),
            "missing transition continuity",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        production_course={**section.production_course, "density": "dense", "phase_profile": "sleep"}
                    )
                    for section in tree.sections
                ),
            ),
            "phase-inappropriate density",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        production_course={**section.production_course, "register": "unsafe"}
                    )
                    for section in tree.sections
                ),
            ),
            "unsafe register",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        production_course={**section.production_course, "dynamics": "flat"}
                    )
                    for section in tree.sections
                ),
            ),
            "flat dynamics",
        ),
        (
            lambda tree: replace(
                tree,
                commission=replace(tree.commission, form_class="extended"),
                sections=tuple(
                    replace(
                        section,
                        production_course={**section.production_course, "genre_strategy": ""}
                    )
                    for i, section in enumerate(tree.sections)
                ) + tuple(tree.sections[:3]), # Ensure enough sections for extended
            ),
            "untagged genre/strategy choices for long pieces",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        phrases=[
                            replace(phrase, intent_tag="")
                            for phrase in section.phrases
                        ],
                    )
                    for section in tree.sections
                ),
            ),
            "phrase missing intent_tag",
        ),
        (
            lambda tree: replace(
                tree,
                sections=tuple(
                    replace(
                        section,
                        phrases=[
                            replace(phrase, intent_tag="bogus")
                            for phrase in section.phrases
                        ],
                    )
                    for section in tree.sections
                ),
            ),
            "phrase has invalid intent_tag",
        ),
    ),
)
def test_composition_gate_rejects_missing_song_quality(
    mutation,
    expected_failure: str,
) -> None:
    report = evaluate_score_tree(mutation(_compose_tree()))

    assert report.approved is False
    assert expected_failure in report.failures


def test_composition_gate_rejects_unbalanced_duration() -> None:
    tree = _compose_tree()
    short_duration = (tree.planned_duration_s - 72.0) / (len(tree.sections) - 1)
    sections = [replace(tree.sections[0], target_duration_s=72.0)]
    sections.extend(replace(section, target_duration_s=short_duration) for section in tree.sections[1:])

    report = evaluate_score_tree(replace(tree, sections=tuple(sections)))

    assert report.approved is False
    assert "section durations are unbalanced" in report.failures


def test_composition_gate_rejects_drone_like_long_section() -> None:
    tree = _compose_tree()
    drone_section = replace(
        tree.sections[0],
        target_duration_s=72.0,
        harmonic_role="tonic",
        cadence_type="suspended",
        groove_state="drone",
        transform_strength="none",
        phrases=tuple(replace(phrase, target_duration_s=36.0, transform_ops=()) for phrase in tree.sections[0].phrases),
    )

    report = evaluate_score_tree(replace(tree, sections=(drone_section, *tree.sections[1:])))

    assert report.approved is False
    assert "section is drone-like for too long" in report.failures


def test_composition_gate_accepts_complete_micro_piece() -> None:
    tree = _compose_tree()
    sections = (
        replace(
            tree.sections[0],
            target_duration_s=8.0,
            harmonic_role="tonic",
            cadence_type="suspended",
            groove_state="pulse",
            return_from=None,
            transform_strength="none",
            production_course={
                "intent": "sparse",
                "dynamics": "flat",
                "density": "dense",
                "phase_profile": "sleep",
                # The following would normally be rejected
            }
        ),
        replace(
            tree.sections[1],
            target_duration_s=10.0,
            harmonic_role="plagal",
            cadence_type="authentic",
            groove_state="lift",
            return_from=None,
            transform_strength="none",
            production_course={
                "intent": "sparse",
                "dynamics": "flat",
            }
        ),
    )
    micro = replace(
        tree,
        commission=replace(tree.commission, form_class="micro", duration_target_s=18.0),
        form=replace(tree.form, form_class="micro"),
        sections=sections,
        narrative_map={
            sections[0].scene_name: "opening image",
            sections[1].scene_name: "payoff",
        },
        planned_duration_s=18.0,
    )

    report = evaluate_score_tree(micro)

    assert report.approved is True


def test_score_tree_round_trip_preserves_nested_nodes() -> None:
    tree = _compose_tree()

    restored = ScoreTree.from_dict(json.loads(json.dumps(tree.to_dict())))

    assert restored.sections
    assert restored.sections[0].phrases
    assert restored.sections[0].phrases[0].phrase_id == tree.sections[0].phrases[0].phrase_id
    assert restored.sections[0].phrases[0].motif_refs == tree.sections[0].phrases[0].motif_refs
    assert restored.motifs[0].anchor_degrees == tree.motifs[0].anchor_degrees
    assert restored.commission.reason_tags == tree.commission.reason_tags


def _single_fragment_vocabulary_db(tmp_path: Path) -> tuple[Path, int]:
    db_path = tmp_path / "midi_vocabulary.sqlite"
    conn = store.connect(db_path)
    try:
        fragment_id = store.insert_fragment(
            conn,
            source_file="seed.mid",
            kind="melodic_motif",
            interval_pattern=[2, 2, 3],
            duration_pattern=[1.0, 0.5, 0.5, 2.0],
            source_key="C major",
            source_tempo=120.0,
            harmonic_context={"pitch_classes": [0, 2, 4, 7]},
        )
    finally:
        conn.close()
    return db_path, fragment_id


def test_score_tree_composer_cites_vocabulary_fragments_from_db(tmp_path: Path) -> None:
    db_path, fragment_id = _single_fragment_vocabulary_db(tmp_path)

    tree = _compose_tree(
        composition_seed="t-016-vocabulary",
        vocabulary_db_path=db_path,
        vocabulary_curiosity=1.0,
    )

    citations = tree.arrangement_plan["vocabulary_fragments"]
    assert set(citations) == {section.scene_name for section in tree.sections}
    assert all(citation["fragment_id"] == fragment_id for citation in citations.values())
    assert all(citation["kind"] == "melodic_motif" for citation in citations.values())
    assert all(citation["degree_pattern"] == [1, 2, 3, 5] for citation in citations.values())
    assert tree.metadata["vocabulary_curiosity"] == "1.000"
    assert tree.metadata["vocabulary_cited_scene_count"] == str(len(tree.sections))
    assert tree.metadata["vocabulary_cited_rate"] == "1.000"
