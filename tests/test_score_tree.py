from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.piece_commission import PieceCommission
from senseweave.piece_brief import PieceBrief
from senseweave.form_grammar import FormPlan, PlannedSection
from senseweave.score_tree import MotifNode, PhraseNode, SectionNode, ScoreTree


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
