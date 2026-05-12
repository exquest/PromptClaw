from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from cypherclaw.render.events import IntentTag, PerformanceIntent, SectionEnvelope
from inner_life.world_model import WorldModel
from senseweave.composition_gate import evaluate_score_tree
from senseweave.form_grammar import plan_form
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece
from senseweave.recursive_composer import compose_score_tree
from senseweave.score_tree import ScoreTree


def _compose_tree(*, composition_seed: str | None = None):
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
    )


def _score_tree_hash(tree: ScoreTree) -> str:
    return hashlib.sha256(tree.to_json().encode("utf-8")).hexdigest()


def test_recursive_composer_builds_complete_score_tree() -> None:
    tree = _compose_tree()

    assert tree.title
    assert tree.motifs
    assert tree.sections
    assert tree.primary_hook_text
    assert tree.planned_duration_s > 0
    assert tree.form.section_functions


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
