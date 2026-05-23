from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.piece_commission import PieceCommission
from senseweave.piece_brief import PieceBrief
from senseweave.form_grammar import FormPlan, PlannedSection
from senseweave.score_tree import (
    MeterSceneValue,
    MeterTrajectory,
    MotifNode,
    PhraseNode,
    SectionNode,
    ScoreTree,
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
        reason_tags=("test", "meter-trajectory"),
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
        form_family="family",
        form_class="song",
        composition_mode="hybrid",
        sections=(
            PlannedSection(
                scene_name="Theme",
                function="statement",
                target_duration_s=60.0,
                return_from=None,
                transform_strength="none",
                harmonic_role="tonic",
            ),
        ),
        ending_family="fade",
    )


def _meter_trajectory() -> MeterTrajectory:
    return MeterTrajectory(
        trajectory_id="meter-arc-1",
        arc_plan="ascending_complexity",
        arc_phase="Convergence",
        scene_values=(
            MeterSceneValue(
                scene_name="Theme",
                meter="4/4",
                subdivision="straight",
                groove_timing="grid",
            ),
            MeterSceneValue(
                scene_name="Development",
                meter="15/16",
                subdivision="dotted",
                groove_timing="metric_modulation",
                phrase_breath="asymmetric",
                metric_modulation="5:4",
                polymeter=(3, 4),
            ),
            MeterSceneValue(
                scene_name="Recap",
                meter="7/8",
                subdivision="polyrhythmic",
                groove_timing="metric_modulation",
                metric_modulation="7:8",
            ),
        ),
        rationale="rise into asymmetry before settling",
    )


def _tree_with_meter_metadata() -> ScoreTree:
    trajectory = _meter_trajectory()
    phrases = [
        PhraseNode(
            phrase_id="p-theme",
            function="statement",
            motif_refs=("m-theme",),
            target_duration_s=15.0,
            transform_ops=(),
        )
    ]
    sections = [
        SectionNode(
            section_id="s-theme",
            scene_name="Theme",
            function="statement",
            target_duration_s=60.0,
            phrases=phrases,
            harmonic_role="tonic",
            cadence_type="authentic",
            groove_state="pulse",
            scene_metadata=trajectory.metadata_for_scene("Theme"),
        )
    ]
    return ScoreTree(
        piece_id="piece-meter",
        title="Meter Piece",
        commission=_commission(),
        brief=_brief(),
        form=_form(),
        motifs=[
            MotifNode(
                motif_id="m-theme",
                hook_class="melodic",
                contour=(1, 3, 5),
                rhythm=(1.0, 1.0, 1.0),
                anchor_degrees=(1, 3, 5),
                answer_degrees=(5, 3, 1),
                text_hook="meter hook",
            )
        ],
        sections=sections,
        harmonic_plan={"progression": "I-IV-V-I"},
        arrangement_plan={"layers": 4},
        ending_family="fade",
        narrative_map={"Theme": "statement"},
        metadata={"author": "AI"},
        meter_trajectory=trajectory,
        planned_duration_s=180.0,
        primary_hook_text="meter hook",
    )


def test_score_tree_round_trips_through_json() -> None:
    commission = PieceCommission(
        form_class="song",
        composition_mode="hybrid",
        duration_target_s=180.0,
        sonic_world_count=2,
        hook_pressure=0.8,
        narrative_scale="scene",
        ending_family="fade",
        groove_identity="driving",
        reason_tags=("test", "roundtrip"),
    )

    brief = PieceBrief(
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

    form = FormPlan(
        form_family="family",
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

    motifs = [
        MotifNode(
            motif_id="m1",
            hook_class="melodic",
            contour=(1, -1, 2),
            rhythm=(0.5, 0.5, 1.0),
            anchor_degrees=(1, 5),
            answer_degrees=(4, 1),
            text_hook="hook text",
        )
    ]

    phrases = [
        PhraseNode(
            phrase_id="p1",
            function="statement",
            motif_refs=("m1",),
            target_duration_s=15.0,
            transform_ops=("invert",),
        )
    ]

    sections = [
        SectionNode(
            section_id="s1",
            scene_name="scene1",
            function="verse",
            target_duration_s=60.0,
            phrases=phrases,
            harmonic_role="tonic",
            cadence_type="authentic",
            groove_state="driving",
            return_from="nowhere",
            transform_strength="none",
        )
    ]

    tree = ScoreTree(
        piece_id="piece-123",
        title="Test Piece",
        commission=commission,
        brief=brief,
        form=form,
        motifs=motifs,
        sections=sections,
        harmonic_plan={"progression": "I-IV-V-I"},
        arrangement_plan={"layers": 4},
        ending_family="fade",
        narrative_map={"scene1": "tension"},
        metadata={"author": "AI"},
        planned_duration_s=180.0,
        primary_hook_text="hook text",
    )

    serialized = tree.to_json()
    deserialized = ScoreTree.from_dict(json.loads(serialized))

    assert deserialized.piece_id == "piece-123"
    assert deserialized.title == "Test Piece"
    assert deserialized.commission == commission
    assert deserialized.brief == brief
    assert deserialized.form == form
    assert deserialized.motifs == motifs
    assert deserialized.sections == sections
    assert deserialized.harmonic_plan == {"progression": "I-IV-V-I"}
    assert deserialized.arrangement_plan == {"layers": 4}
    assert deserialized.ending_family == "fade"
    assert deserialized.narrative_map == {"scene1": "tension"}
    assert deserialized.metadata == {"author": "AI"}
    assert deserialized.planned_duration_s == 180.0
    assert deserialized.primary_hook_text == "hook text"


def test_meter_trajectory_emits_scene_metadata() -> None:
    trajectory = _meter_trajectory()

    metadata = trajectory.metadata_for_scene("Development")

    assert metadata["meter_trajectory_id"] == "meter-arc-1"
    assert metadata["meter_trajectory_arc_plan"] == "ascending_complexity"
    assert metadata["meter_trajectory_arc_phase"] == "Convergence"
    assert metadata["meter_trajectory_scene"] == "Development"
    assert metadata["meter_trajectory_index"] == "1"
    assert metadata["meter_trajectory_scene_count"] == "3"
    assert metadata["meter_trajectory_meter"] == "15/16"
    assert metadata["meter_trajectory_subdivision"] == "dotted"
    assert metadata["meter_trajectory_groove_timing"] == "metric_modulation"
    assert metadata["meter_trajectory_phrase_breath"] == "asymmetric"
    assert metadata["meter_trajectory_metric_modulation"] == "5:4"
    assert json.loads(metadata["meter_trajectory_polymeter"]) == [3, 4]
    assert json.loads(metadata["meter_trajectory_path"]) == ["4/4", "15/16", "7/8"]
    assert trajectory.metadata_for_scene("Missing") == {}


def test_score_tree_round_trips_meter_trajectory_and_scene_metadata() -> None:
    tree = _tree_with_meter_metadata()

    restored = ScoreTree.from_dict(json.loads(tree.to_json()))

    assert restored.meter_trajectory == tree.meter_trajectory
    assert restored.meter_trajectory is not None
    assert restored.meter_trajectory.scene_values[1].polymeter == (3, 4)
    assert restored.sections[0].scene_metadata == tree.sections[0].scene_metadata
    assert restored.sections[0].scene_metadata["meter_trajectory_meter"] == "4/4"


def test_score_tree_from_legacy_payload_defaults_meter_fields() -> None:
    tree = _tree_with_meter_metadata()
    payload = json.loads(tree.to_json())
    payload.pop("meter_trajectory")
    for section in payload["sections"]:
        section.pop("scene_metadata", None)

    restored = ScoreTree.from_dict(payload)

    assert restored.meter_trajectory is None
    assert restored.sections[0].scene_metadata == {}
