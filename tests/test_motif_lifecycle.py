"""Tests for motif_lifecycle.py -- leitmotif state transitions and transformations."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.motif_lifecycle import (
    MotifLifecycleManager,
    advance,
    recall_shape_from_summary,
    transform_answer,
    transform_contrast,
    transform_liquidation,
    transform_recall,
    transform_residue,
    transform_variation,
    valid_next_states,
)
from senseweave.score_tree import MOTIF_LIFECYCLE_STATES, MotifNode


def _make_motif(*, lifecycle_state: str = "statement") -> MotifNode:
    return MotifNode(
        motif_id="test-motif-001",
        hook_class="contour",
        contour=(1, 3, 5, 3),
        rhythm=(1.0, 1.0, 1.0, 1.0),
        anchor_degrees=(1, 3, 5, 3),
        answer_degrees=(1, 2, 4, 1),
        text_hook="hold the light",
        timbral_tags=("warm", "close"),
        lifecycle_state=lifecycle_state,
    )


# -- lifecycle states ---------------------------------------------------------


def test_lifecycle_states_tuple_has_seven_entries() -> None:
    assert len(MOTIF_LIFECYCLE_STATES) == 7
    assert MOTIF_LIFECYCLE_STATES[0] == "statement"
    assert MOTIF_LIFECYCLE_STATES[-1] == "residue"


def test_motif_node_default_lifecycle_state() -> None:
    motif = MotifNode(
        motif_id="m1",
        hook_class="contour",
        contour=(1, 3),
        rhythm=(1.0,),
        anchor_degrees=(1,),
        answer_degrees=(3,),
        text_hook="test",
        timbral_tags=(),
    )
    assert motif.lifecycle_state == "statement"


# -- valid transitions --------------------------------------------------------


def test_statement_can_reach_variation_contrast_answer() -> None:
    assert "variation" in valid_next_states("statement")
    assert "contrast" in valid_next_states("statement")
    assert "answer" in valid_next_states("statement")


def test_residue_is_terminal() -> None:
    assert valid_next_states("residue") == ()


def test_liquidation_leads_only_to_residue() -> None:
    assert valid_next_states("liquidation") == ("residue",)


# -- transformations ----------------------------------------------------------


def test_variation_shifts_inner_contour_degrees() -> None:
    motif = _make_motif()
    varied = transform_variation(motif)
    assert varied.lifecycle_state == "variation"
    assert varied.contour != motif.contour
    assert varied.contour[0] == motif.contour[0]
    assert varied.contour[-1] == motif.contour[-1]
    assert len(varied.contour) == len(motif.contour)


def test_variation_swaps_first_last_rhythm() -> None:
    motif = _make_motif()
    varied = transform_variation(motif)
    assert varied.rhythm[0] == motif.rhythm[-1]
    assert varied.rhythm[-1] == motif.rhythm[0]


def test_contrast_inverts_contour() -> None:
    motif = _make_motif()
    contrasted = transform_contrast(motif)
    assert contrasted.lifecycle_state == "contrast"
    assert contrasted.contour != motif.contour
    max_deg = max(motif.contour)
    for orig, inv in zip(motif.contour, contrasted.contour):
        assert inv == max(1, min(8, max_deg + 1 - orig))


def test_contrast_reverses_rhythm() -> None:
    motif = MotifNode(
        motif_id="asym",
        hook_class="rhythmic",
        contour=(1, 5, 3, 6),
        rhythm=(0.75, 0.75, 1.0, 1.5),
        anchor_degrees=(1, 5, 3, 6),
        answer_degrees=(1, 4, 2, 5),
        text_hook="test",
        timbral_tags=(),
        lifecycle_state="statement",
    )
    contrasted = transform_contrast(motif)
    assert contrasted.rhythm == tuple(reversed(motif.rhythm))


def test_contrast_swaps_anchor_answer_degrees() -> None:
    motif = _make_motif()
    contrasted = transform_contrast(motif)
    assert contrasted.anchor_degrees == motif.answer_degrees
    assert contrasted.answer_degrees == motif.anchor_degrees


def test_recall_perturbs_contour_toward_center() -> None:
    motif = _make_motif()
    recalled = transform_recall(motif)
    assert recalled.lifecycle_state == "recall"
    assert recalled.contour != motif.contour
    assert len(recalled.contour) == len(motif.contour)


def test_recall_with_external_shape_uses_that_shape() -> None:
    motif = _make_motif()
    shape = (2, 6, 4, 2)
    recalled = transform_recall(motif, shape=shape)
    assert recalled.contour != shape
    assert recalled.contour != motif.contour
    assert len(recalled.contour) == len(shape)


def test_recall_never_produces_exact_copy() -> None:
    motif = _make_motif()
    recalled = transform_recall(motif)
    assert recalled.contour != motif.contour


def test_answer_resolves_last_degree() -> None:
    motif = _make_motif()
    answered = transform_answer(motif)
    assert answered.lifecycle_state == "answer"
    assert answered.contour[-1] in (1, 3)


def test_answer_swaps_anchor_answer() -> None:
    motif = _make_motif()
    answered = transform_answer(motif)
    assert answered.anchor_degrees == motif.answer_degrees
    assert answered.answer_degrees == motif.anchor_degrees


def test_liquidation_halves_material() -> None:
    motif = _make_motif()
    liquidated = transform_liquidation(motif)
    assert liquidated.lifecycle_state == "liquidation"
    assert len(liquidated.contour) == len(motif.contour) // 2
    assert len(liquidated.rhythm) == len(motif.rhythm) // 2


def test_residue_keeps_opening_interval() -> None:
    motif = _make_motif()
    residue = transform_residue(motif)
    assert residue.lifecycle_state == "residue"
    assert len(residue.contour) == 2
    assert residue.contour[0] == motif.contour[0]
    assert residue.contour[1] == motif.contour[1]
    assert len(residue.rhythm) == 1


# -- advance with guard ------------------------------------------------------


def test_advance_statement_to_variation() -> None:
    motif = _make_motif()
    varied = advance(motif, "variation")
    assert varied.lifecycle_state == "variation"


def test_advance_rejects_invalid_transition() -> None:
    motif = _make_motif()
    with pytest.raises(ValueError, match="cannot transition"):
        advance(motif, "residue")


def test_advance_rejects_unknown_state() -> None:
    motif = _make_motif()
    with pytest.raises(ValueError, match="unknown lifecycle state"):
        advance(motif, "nonexistent")


# -- full lifecycle path ------------------------------------------------------


def test_full_lifecycle_statement_through_residue() -> None:
    motif = _make_motif()
    varied = advance(motif, "variation")
    contrasted = advance(varied, "contrast")
    recalled = advance(contrasted, "recall")
    answered = advance(recalled, "answer")
    liquidated = advance(answered, "liquidation")
    residue = advance(liquidated, "residue")
    assert residue.lifecycle_state == "residue"
    assert residue.contour != motif.contour
    states = [m.lifecycle_state for m in [motif, varied, contrasted, recalled, answered, liquidated, residue]]
    assert states == list(MOTIF_LIFECYCLE_STATES)


# -- manager ------------------------------------------------------------------


def test_manager_register_and_advance() -> None:
    mgr = MotifLifecycleManager()
    motif = _make_motif()
    entry = mgr.register(motif)
    assert entry.history == ["statement"]
    mgr.advance(motif.motif_id, "variation")
    assert entry.history == ["statement", "variation"]
    assert entry.current.lifecycle_state == "variation"


def test_manager_recall_from_repertoire_never_exact_copy() -> None:
    mgr = MotifLifecycleManager()
    motif = _make_motif()
    mgr.register(motif)
    mgr.advance(motif.motif_id, "variation")
    recalled = mgr.recall_from_repertoire(
        mgr.get(motif.motif_id).current.motif_id,
        repertoire_shape=[2, 5, 3, 1],
    )
    assert recalled.lifecycle_state == "recall"
    assert recalled.contour != (2, 5, 3, 1)


def test_manager_rejects_recall_from_terminal_state() -> None:
    mgr = MotifLifecycleManager()
    motif = _make_motif(lifecycle_state="answer")
    mgr.register(motif)
    mgr.advance(motif.motif_id, "liquidation")
    liq_id = mgr.get(motif.motif_id).current.motif_id
    mgr.advance(liq_id, "residue")
    res_id = mgr.get(liq_id).current.motif_id
    with pytest.raises(ValueError, match="cannot recall"):
        mgr.recall_from_repertoire(res_id, repertoire_shape=[1, 3, 5])


# -- repertoire shape recall helpers ------------------------------------------


def test_recall_shape_from_summary_extracts_contour() -> None:
    summary = {"motif_contours": [[1, 3, 5, 3], [5, 3, 1, 3]]}
    assert recall_shape_from_summary(summary, motif_index=0) == (1, 3, 5, 3)
    assert recall_shape_from_summary(summary, motif_index=1) == (5, 3, 1, 3)


def test_recall_shape_from_summary_returns_none_when_missing() -> None:
    assert recall_shape_from_summary({}, motif_index=0) is None
    assert recall_shape_from_summary({"motif_contours": []}, motif_index=0) is None


# -- repertoire memory integration -------------------------------------------


def test_repertoire_memory_stores_and_recalls_motif_contours(tmp_path: Path) -> None:
    from senseweave.piece_commission import commission_piece
    from senseweave.repertoire_memory import RepertoireMemory
    from senseweave.score_tree import ScoreTree

    memory = RepertoireMemory(path=str(tmp_path / "rep.json"))
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.55,
        song_num=12,
        hour=15,
    )
    primary = _make_motif()
    tree = ScoreTree.minimal(piece_id="p-1", title="Test Piece", commission=commission)
    tree.motifs.append(primary)

    memory.store_song(
        title="Test Piece",
        family="ember",
        progression_profile="lift",
        cadence_state="occupied_day",
        key="C",
        hook_text="hold the light",
        hook_class="contour",
        practice_block="",
        ear_metrics={"hook_clarity": 0.85},
        score_tree=tree,
    )

    shape = memory.recall_motif_shape(family="ember", cadence_state="occupied_day")
    assert shape is not None
    assert shape == primary.contour


def test_recall_motif_shape_returns_none_when_no_match(tmp_path: Path) -> None:
    from senseweave.repertoire_memory import RepertoireMemory

    memory = RepertoireMemory(path=str(tmp_path / "rep.json"))
    assert memory.recall_motif_shape(family="ember", cadence_state="occupied_day") is None
