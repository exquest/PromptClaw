"""Depth-2 score-tree report helpers - locked test surface for frac-0024."""
from __future__ import annotations

import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.form_grammar import FormPlan, PlannedSection  # noqa: E402
from senseweave.piece_brief import PieceBrief  # noqa: E402
from senseweave.piece_commission import PieceCommission  # noqa: E402
from senseweave.production_course import REQUIRED_CHAPTER_IDS  # noqa: E402
from senseweave.score_tree import (  # noqa: E402
    MOTIF_LIFECYCLE_STATES,
    MotifNode,
    PhraseNode,
    ScoreTree,
    ScoreTreeReport,
    ScoreTreeSectionReport,
    SectionNode,
    build_score_tree_report,
    build_score_tree_section_report,
    count_motif_lifecycle_states,
    motif_lifecycle_band,
    section_phrase_load_band,
    summarize_score_tree_report,
)


def _commission() -> PieceCommission:
    return PieceCommission(
        form_class="song",
        composition_mode="hybrid",
        duration_target_s=180.0,
        sonic_world_count=2,
        hook_pressure=0.8,
        narrative_scale="scene",
        ending_family="fade",
        groove_identity="driving",
        reason_tags=("test", "frac-0024"),
    )


def _brief() -> PieceBrief:
    return PieceBrief(
        image_field=("field1", "field2"),
        dramatic_premise="premise",
        conflict="conflict",
        desired_payoff="payoff",
        residue="residue",
        ending_feeling="feeling",
        motion_character="motion",
        hook_pressure=0.8,
        through_composed_pressure=0.5,
        section_beats=("beat1", "beat2"),
        narrative_scale="scene",
    )


def _form() -> FormPlan:
    return FormPlan(
        form_family="ballad",
        form_class="song",
        composition_mode="hybrid",
        sections=(
            PlannedSection(
                scene_name="scene1",
                function="verse",
                target_duration_s=60.0,
                return_from="nowhere",
                transform_strength="none",
                harmonic_role="tonic",
            ),
        ),
        ending_family="fade",
    )


def _full_production_course() -> dict[str, str]:
    return {chapter_id: f"chapter:{chapter_id}" for chapter_id in REQUIRED_CHAPTER_IDS}


def _populated_tree() -> ScoreTree:
    motifs = [
        MotifNode(
            motif_id="m1",
            hook_class="melodic",
            contour=(1, -1, 2),
            rhythm=(0.5, 0.5, 1.0),
            anchor_degrees=(1, 5),
            answer_degrees=(4, 1),
            text_hook="hook one",
            lifecycle_state="statement",
        ),
        MotifNode(
            motif_id="m2",
            hook_class="rhythmic",
            contour=(0,),
            rhythm=(0.25,),
            anchor_degrees=(1,),
            answer_degrees=(1,),
            text_hook="hook two",
            lifecycle_state="variation",
        ),
        MotifNode(
            motif_id="m3",
            hook_class="contrapuntal",
            contour=(2, -2),
            rhythm=(0.5, 0.5),
            anchor_degrees=(5,),
            answer_degrees=(1,),
            text_hook="hook three",
            lifecycle_state="contrast",
        ),
        MotifNode(
            motif_id="m4",
            hook_class="textural",
            contour=(0, 0),
            rhythm=(1.0, 1.0),
            anchor_degrees=(3,),
            answer_degrees=(3,),
            text_hook="hook four",
            lifecycle_state="residue",
        ),
        MotifNode(
            motif_id="m5",
            hook_class="orphan",
            contour=(0,),
            rhythm=(1.0,),
            anchor_degrees=(2,),
            answer_degrees=(2,),
            text_hook="hook five",
            lifecycle_state="statement",
        ),
    ]
    sections = [
        SectionNode(
            section_id="s1",
            scene_name="scene1",
            function="verse",
            target_duration_s=60.0,
            phrases=[
                PhraseNode(
                    phrase_id="p1",
                    function="statement",
                    motif_refs=("m1", "m2"),
                    target_duration_s=15.0,
                    transform_ops=("invert",),
                ),
                PhraseNode(
                    phrase_id="p2",
                    function="answer",
                    motif_refs=("m2", "m3"),
                    target_duration_s=15.0,
                    transform_ops=("retrograde",),
                ),
            ],
            harmonic_role="tonic",
            cadence_type="authentic",
            groove_state="driving",
            return_from="nowhere",
            transform_strength="none",
            production_course=_full_production_course(),
            harmonic_function="tonic",
            transition_intent="maintain",
        ),
        SectionNode(
            section_id="s2",
            scene_name="scene2",
            function="chorus",
            target_duration_s=45.0,
            phrases=[
                PhraseNode(
                    phrase_id="p3",
                    function="hook",
                    motif_refs=("m1", "m4"),
                    target_duration_s=20.0,
                    transform_ops=("repeat",),
                ),
            ],
            harmonic_role="dominant",
            cadence_type="half",
            groove_state="lifting",
            return_from=None,
            transform_strength="moderate",
            production_course={"mode_scale": "ionian"},
            harmonic_function="dominant",
            transition_intent="lift",
        ),
    ]
    return ScoreTree(
        piece_id="piece-frac-0024",
        title="Test Tree",
        commission=_commission(),
        brief=_brief(),
        form=_form(),
        motifs=motifs,
        sections=sections,
        harmonic_plan={"progression": "I-IV-V-I"},
        arrangement_plan={"layers": 4},
        ending_family="fade",
        narrative_map={"scene1": "tension"},
        metadata={"author": "AI"},
        planned_duration_s=180.0,
        primary_hook_text="hook one",
    )


def test_motif_lifecycle_band_maps_states_to_bands() -> None:
    assert motif_lifecycle_band("statement") == "introduction"
    assert motif_lifecycle_band("variation") == "introduction"
    assert motif_lifecycle_band("contrast") == "development"
    assert motif_lifecycle_band("recall") == "development"
    assert motif_lifecycle_band("answer") == "development"
    assert motif_lifecycle_band("liquidation") == "resolution"
    assert motif_lifecycle_band("residue") == "resolution"
    assert motif_lifecycle_band("not-a-state") == "unclassified"
    assert motif_lifecycle_band("") == "unclassified"


def test_section_phrase_load_band_maps_counts_to_bands() -> None:
    assert section_phrase_load_band(0) == "spare"
    assert section_phrase_load_band(1) == "spare"
    assert section_phrase_load_band(2) == "compact"
    assert section_phrase_load_band(3) == "compact"
    assert section_phrase_load_band(4) == "developed"
    assert section_phrase_load_band(5) == "developed"
    assert section_phrase_load_band(6) == "saturated"
    assert section_phrase_load_band(99) == "saturated"


def test_count_motif_lifecycle_states_counts_canonical_states() -> None:
    tree = _populated_tree()

    counts = count_motif_lifecycle_states(tree)

    assert counts == {
        "statement": 2,
        "variation": 1,
        "contrast": 1,
        "residue": 1,
    }
    for state in counts:
        assert state in MOTIF_LIFECYCLE_STATES


def test_build_score_tree_section_report_resolves_section_shape() -> None:
    tree = _populated_tree()
    section = tree.sections[0]

    report = build_score_tree_section_report(section)

    assert isinstance(report, ScoreTreeSectionReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert report.section_id == "s1"
    assert report.scene_name == "scene1"
    assert report.function == "verse"
    assert report.harmonic_role == "tonic"
    assert report.harmonic_function == "tonic"
    assert report.cadence_type == "authentic"
    assert report.groove_state == "driving"
    assert report.transition_intent == "maintain"
    assert report.transform_strength == "none"
    assert report.target_duration_s == 60.0
    assert report.phrase_count == 2
    assert report.phrase_load_band == "compact"
    assert report.motif_refs == ("m1", "m2", "m3")
    assert report.production_course_complete is True


def test_build_score_tree_report_resolves_populated_tree() -> None:
    tree = _populated_tree()

    report = build_score_tree_report(tree)

    assert isinstance(report, ScoreTreeReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert report.piece_id == "piece-frac-0024"
    assert report.title == "Test Tree"
    assert report.form_family == "ballad"
    assert report.form_class == "song"
    assert report.composition_mode == "hybrid"
    assert report.ending_family == "fade"
    assert report.planned_duration_s == 180.0
    assert report.section_count == 2
    assert report.motif_count == 5
    assert report.phrase_count == 3
    assert report.motif_lifecycle_counts == {
        "statement": 2,
        "variation": 1,
        "contrast": 1,
        "recall": 0,
        "answer": 0,
        "liquidation": 0,
        "residue": 1,
    }
    assert tuple(report.motif_lifecycle_counts.keys()) == MOTIF_LIFECYCLE_STATES
    assert report.unreferenced_motif_ids == ("m5",)
    assert len(report.sections) == 2
    assert report.sections[0].section_id == "s1"
    assert report.sections[0].phrase_load_band == "compact"
    assert report.sections[0].motif_refs == ("m1", "m2", "m3")
    assert report.sections[0].production_course_complete is True
    assert report.sections[1].section_id == "s2"
    assert report.sections[1].phrase_load_band == "spare"
    assert report.sections[1].motif_refs == ("m1", "m4")
    assert report.sections[1].production_course_complete is False


def test_summarize_score_tree_report_returns_json_safe_summary() -> None:
    tree = _populated_tree()
    report = build_score_tree_report(tree)

    summary = summarize_score_tree_report(report)

    assert summary["piece_id"] == "piece-frac-0024"
    assert summary["title"] == "Test Tree"
    assert summary["form_family"] == "ballad"
    assert summary["form_class"] == "song"
    assert summary["composition_mode"] == "hybrid"
    assert summary["ending_family"] == "fade"
    assert summary["planned_duration_s"] == 180.0
    assert summary["section_count"] == 2
    assert summary["motif_count"] == 5
    assert summary["phrase_count"] == 3
    assert summary["motif_lifecycle_counts"] == {
        "statement": 2,
        "variation": 1,
        "contrast": 1,
        "recall": 0,
        "answer": 0,
        "liquidation": 0,
        "residue": 1,
    }
    assert summary["unreferenced_motif_ids"] == ["m5"]
    assert isinstance(summary["sections"], list)
    assert summary["sections"][0] == {
        "section_id": "s1",
        "scene_name": "scene1",
        "function": "verse",
        "harmonic_role": "tonic",
        "harmonic_function": "tonic",
        "cadence_type": "authentic",
        "groove_state": "driving",
        "transition_intent": "maintain",
        "transform_strength": "none",
        "target_duration_s": 60.0,
        "phrase_count": 2,
        "phrase_load_band": "compact",
        "motif_refs": ["m1", "m2", "m3"],
        "production_course_complete": True,
    }
    assert summary["sections"][1]["motif_refs"] == ["m1", "m4"]
    assert summary["sections"][1]["production_course_complete"] is False
    # JSON round-trip stability.
    json.loads(json.dumps(summary))


def test_score_tree_report_handles_minimal_tree() -> None:
    tree = ScoreTree.minimal(
        piece_id="piece-minimal",
        title="Minimal",
        commission=_commission(),
    )

    report = build_score_tree_report(tree)
    summary = summarize_score_tree_report(report)

    assert report.section_count == 0
    assert report.motif_count == 0
    assert report.phrase_count == 0
    assert report.unreferenced_motif_ids == ()
    assert report.sections == ()
    assert tuple(report.motif_lifecycle_counts.keys()) == MOTIF_LIFECYCLE_STATES
    assert all(value == 0 for value in report.motif_lifecycle_counts.values())

    assert summary["section_count"] == 0
    assert summary["motif_count"] == 0
    assert summary["phrase_count"] == 0
    assert summary["unreferenced_motif_ids"] == []
    assert summary["sections"] == []
    assert summary["motif_lifecycle_counts"]["statement"] == 0
    json.loads(json.dumps(summary))


def test_score_tree_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/score_tree.py")
    assert result.depth >= 2, result.reason
