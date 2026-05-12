"""Depth-2 motif lifecycle report helpers - locked test surface for frac-0025."""
from __future__ import annotations

import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"),
)

from senseweave.motif_lifecycle import (  # noqa: E402
    MotifLifecycleManager,
    MotifLifecycleReport,
    MotifLifecycleStep,
    build_lifecycle_report,
    build_lifecycle_step,
    canonical_lifecycle_path,
    lifecycle_state_index,
    summarize_lifecycle_report,
)
from senseweave.score_tree import MOTIF_LIFECYCLE_STATES, MotifNode  # noqa: E402


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


def test_lifecycle_state_index_maps_canonical_order() -> None:
    for expected_index, state in enumerate(MOTIF_LIFECYCLE_STATES):
        assert lifecycle_state_index(state) == expected_index
    assert lifecycle_state_index("not-a-state") == -1
    assert lifecycle_state_index("") == -1


def test_build_lifecycle_step_reports_material_shape() -> None:
    step = build_lifecycle_step(_make_motif())

    assert isinstance(step, MotifLifecycleStep)
    assert dataclasses.is_dataclass(step)
    assert getattr(step, "__dataclass_params__").frozen
    assert step.motif_id == "test-motif-001"
    assert step.state == "statement"
    assert step.state_index == 0
    assert step.state_band == "introduction"
    assert step.contour == (1, 3, 5, 3)
    assert step.rhythm == (1.0, 1.0, 1.0, 1.0)
    assert step.contour_span == 4
    assert step.rhythm_total == 4.0
    assert step.material_units == 4


def test_canonical_lifecycle_path_advances_statement_to_residue() -> None:
    motif = _make_motif()
    path = canonical_lifecycle_path(motif)

    assert tuple(step.lifecycle_state for step in path) == MOTIF_LIFECYCLE_STATES
    assert path[0] == motif
    assert path[-1].lifecycle_state == "residue"
    assert len(path) == len(MOTIF_LIFECYCLE_STATES)
    assert len({step.motif_id for step in path}) == len(path)
    assert path[-1].contour != motif.contour
    assert len(path[-1].contour) <= 2
    assert len(path[-1].rhythm) == 1


def test_build_lifecycle_report_summarizes_full_path() -> None:
    path = canonical_lifecycle_path(_make_motif())
    report = build_lifecycle_report(path)

    assert isinstance(report, MotifLifecycleReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert report.origin_motif_id == path[0].motif_id
    assert report.current_motif_id == path[-1].motif_id
    assert report.current_state == "residue"
    assert report.terminal_state == "residue"
    assert report.terminal is True
    assert report.next_states == ()
    assert report.history == MOTIF_LIFECYCLE_STATES
    assert report.step_count == len(MOTIF_LIFECYCLE_STATES)
    assert report.state_counts == {state: 1 for state in MOTIF_LIFECYCLE_STATES}
    assert report.contour_span_delta == -3
    assert report.rhythm_total_delta == -3.0
    assert report.material_ratio == 0.5
    assert tuple(step.state for step in report.steps) == MOTIF_LIFECYCLE_STATES


def test_summarize_lifecycle_report_returns_json_safe_summary() -> None:
    report = build_lifecycle_report(canonical_lifecycle_path(_make_motif()))
    summary = summarize_lifecycle_report(report)

    assert summary["origin_motif_id"] == report.origin_motif_id
    assert summary["current_motif_id"] == report.current_motif_id
    assert summary["current_state"] == "residue"
    assert summary["terminal"] is True
    assert summary["history"] == list(MOTIF_LIFECYCLE_STATES)
    assert summary["next_states"] == []
    assert summary["state_counts"] == {state: 1 for state in MOTIF_LIFECYCLE_STATES}
    assert summary["material_ratio"] == 0.5
    assert summary["steps"][0]["state_band"] == "introduction"
    assert summary["steps"][-1]["state_band"] == "resolution"
    assert summary["steps"][-1]["state"] == "residue"
    json.loads(json.dumps(summary))


def test_lifecycle_report_matches_manager_end_to_end_path() -> None:
    manager = MotifLifecycleManager()
    motif = _make_motif()
    entry = manager.register(motif)
    current_id = motif.motif_id

    for target_state in MOTIF_LIFECYCLE_STATES[1:]:
        current = manager.advance(current_id, target_state)
        current_id = current.motif_id

    path = canonical_lifecycle_path(motif)
    summary = summarize_lifecycle_report(build_lifecycle_report(path))

    assert entry.history == summary["history"]
    assert entry.current.motif_id == summary["current_motif_id"]
    assert entry.current.lifecycle_state == summary["current_state"] == "residue"
    assert summary["terminal"] is True


def test_motif_lifecycle_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/motif_lifecycle.py")
    assert result.depth >= 2, result.reason
