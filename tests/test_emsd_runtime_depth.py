"""Depth-2 EMSD runtime snapshot/report helpers - locked test surface for frac-0026."""
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

from senseweave.emsd_runtime import (  # noqa: E402
    CANONICAL_ARC_PHASES,
    CANONICAL_DENSITY_BANDS,
    EMSDPhaseSnapshot,
    EMSDRuntimeReport,
    arc_phase_band,
    arc_phase_index,
    build_live_emsd_context,
    build_phase_snapshot,
    build_runtime_report,
    density_pressure_band,
    summarize_runtime_report,
)


def _make_context(*, now_seconds: float, family_name: str, patch_name: str):
    return build_live_emsd_context(
        cadence_state="occupied_day",
        occupancy_state="occupied_quiet",
        family_name=family_name,
        progression_profile="open_day",
        patch_name=patch_name,
        song_num=1,
        theramini_present=True,
        repertoire_songs=[
            {
                "title": "Quiet Rooms",
                "family": "bloom",
                "patch_name": "house_garden",
                "hook_text": "keep the room open",
            }
        ],
        base_density_bias=0.04,
        attention_score=0.72,
        now_seconds=now_seconds,
    )


def test_arc_phase_index_maps_canonical_order() -> None:
    assert CANONICAL_ARC_PHASES == (
        "Divination",
        "Emergence",
        "Conversation",
        "Convergence",
        "Crystallization",
    )
    for expected_index, name in enumerate(CANONICAL_ARC_PHASES):
        assert arc_phase_index(name) == expected_index
    assert arc_phase_index("not-a-phase") == -1
    assert arc_phase_index("") == -1


def test_arc_phase_band_maps_phases_to_bands() -> None:
    assert arc_phase_band("Divination") == "opening"
    assert arc_phase_band("Emergence") == "opening"
    assert arc_phase_band("Conversation") == "dialogue"
    assert arc_phase_band("Convergence") == "resolution"
    assert arc_phase_band("Crystallization") == "resolution"
    assert arc_phase_band("not-a-phase") == "unclassified"
    assert arc_phase_band("") == "unclassified"


def test_density_pressure_band_maps_values_to_bands() -> None:
    assert CANONICAL_DENSITY_BANDS == ("calm", "neutral", "intense")
    assert density_pressure_band(-0.25) == "calm"
    assert density_pressure_band(-0.05) == "calm"
    assert density_pressure_band(-0.049) == "neutral"
    assert density_pressure_band(0.0) == "neutral"
    assert density_pressure_band(0.049) == "neutral"
    assert density_pressure_band(0.05) == "intense"
    assert density_pressure_band(0.25) == "intense"


def test_build_phase_snapshot_resolves_live_context() -> None:
    context = _make_context(
        now_seconds=13 * 60,
        family_name="bloom",
        patch_name="house_garden",
    )
    snapshot = build_phase_snapshot(context)

    assert isinstance(snapshot, EMSDPhaseSnapshot)
    assert dataclasses.is_dataclass(snapshot)
    assert getattr(snapshot, "__dataclass_params__").frozen
    assert snapshot.arc_phase == "Conversation"
    assert snapshot.arc_phase_index == 2
    assert snapshot.arc_phase_band == "dialogue"
    assert snapshot.family_name == context.phase_plan.family_name
    assert snapshot.patch_name == context.phase_plan.patch_name
    assert snapshot.sample_source == context.phase_plan.sampling.source.name
    assert snapshot.arc_density_target == context.arc.density_target
    assert snapshot.arc_max_active_roles == context.arc.max_active_roles
    assert snapshot.mix_target_lufs == context.phase_plan.mix.target_lufs
    assert snapshot.density_bias == context.density_bias
    assert snapshot.density_band == density_pressure_band(context.density_bias)
    assert snapshot.artistic_identity == context.identity.statement


def test_build_runtime_report_summarizes_trajectory() -> None:
    contexts = [
        _make_context(
            now_seconds=2 * 60, family_name="drift", patch_name="house_monastery"
        ),
        _make_context(
            now_seconds=2 * 60, family_name="drift", patch_name="house_monastery"
        ),
        _make_context(
            now_seconds=8 * 60, family_name="ember", patch_name="house_chamber"
        ),
        _make_context(
            now_seconds=13 * 60, family_name="bloom", patch_name="house_garden"
        ),
        _make_context(
            now_seconds=22 * 60, family_name="pulse", patch_name="house_procession"
        ),
    ]
    snapshots = [build_phase_snapshot(ctx) for ctx in contexts]

    report = build_runtime_report(snapshots)

    assert isinstance(report, EMSDRuntimeReport)
    assert dataclasses.is_dataclass(report)
    assert getattr(report, "__dataclass_params__").frozen
    assert report.snapshot_count == 5
    assert report.snapshots == tuple(snapshots)
    assert report.arc_phase_history == (
        "Divination",
        "Divination",
        "Emergence",
        "Conversation",
        "Convergence",
    )
    assert report.phase_counts == {
        "Divination": 2,
        "Emergence": 1,
        "Conversation": 1,
        "Convergence": 1,
        "Crystallization": 0,
    }
    assert set(report.band_counts.keys()) == set(CANONICAL_DENSITY_BANDS)
    assert sum(report.band_counts.values()) == 5
    assert report.distinct_families == (
        "drift",
        "ember",
        "bloom",
        "pulse",
    )
    assert report.distinct_patches == (
        "house_monastery",
        "house_chamber",
        "house_garden",
        "house_procession",
    )
    assert report.distinct_sample_sources[0] == snapshots[0].sample_source
    assert report.transitions == (
        ("Divination", "Emergence"),
        ("Emergence", "Conversation"),
        ("Conversation", "Convergence"),
    )
    biases = [s.density_bias for s in snapshots]
    assert report.max_density_bias == round(max(biases), 4)
    assert report.min_density_bias == round(min(biases), 4)
    assert report.mean_density_bias == round(sum(biases) / len(biases), 4)


def test_build_runtime_report_rejects_empty_sequence() -> None:
    import pytest

    with pytest.raises(ValueError):
        build_runtime_report([])


def test_summarize_runtime_report_returns_json_safe_summary() -> None:
    contexts = [
        _make_context(
            now_seconds=2 * 60, family_name="drift", patch_name="house_monastery"
        ),
        _make_context(
            now_seconds=13 * 60, family_name="bloom", patch_name="house_garden"
        ),
    ]
    snapshots = [build_phase_snapshot(ctx) for ctx in contexts]
    report = build_runtime_report(snapshots)
    summary = summarize_runtime_report(report)

    assert summary["snapshot_count"] == 2
    assert summary["arc_phase_history"] == ["Divination", "Conversation"]
    assert summary["phase_counts"] == {
        "Divination": 1,
        "Emergence": 0,
        "Conversation": 1,
        "Convergence": 0,
        "Crystallization": 0,
    }
    assert set(summary["band_counts"].keys()) == set(CANONICAL_DENSITY_BANDS)
    assert summary["transitions"] == [["Divination", "Conversation"]]
    assert summary["distinct_families"] == ["drift", "bloom"]
    assert summary["distinct_patches"] == ["house_monastery", "house_garden"]
    assert summary["mean_density_bias"] == report.mean_density_bias
    assert summary["max_density_bias"] == report.max_density_bias
    assert summary["min_density_bias"] == report.min_density_bias
    assert summary["snapshots"][0]["arc_phase"] == "Divination"
    assert summary["snapshots"][0]["arc_phase_band"] == "opening"
    assert summary["snapshots"][1]["arc_phase"] == "Conversation"
    assert summary["snapshots"][1]["arc_phase_band"] == "dialogue"
    json.loads(json.dumps(summary))


def test_runtime_report_matches_live_contexts_end_to_end() -> None:
    contexts = [
        _make_context(
            now_seconds=2 * 60, family_name="drift", patch_name="house_monastery"
        ),
        _make_context(
            now_seconds=8 * 60, family_name="ember", patch_name="house_chamber"
        ),
        _make_context(
            now_seconds=13 * 60, family_name="bloom", patch_name="house_garden"
        ),
        _make_context(
            now_seconds=22 * 60, family_name="pulse", patch_name="house_procession"
        ),
        _make_context(
            now_seconds=27 * 60, family_name="nocturne", patch_name="house_monastery"
        ),
    ]
    snapshots = [build_phase_snapshot(ctx) for ctx in contexts]
    report = build_runtime_report(snapshots)

    assert report.arc_phase_history == tuple(
        ctx.arc.phase.name for ctx in contexts
    )
    assert tuple(s.arc_phase for s in report.snapshots) == report.arc_phase_history
    assert report.phase_counts["Divination"] == 1
    assert report.phase_counts["Emergence"] == 1
    assert report.phase_counts["Conversation"] == 1
    assert report.phase_counts["Convergence"] == 1
    assert report.phase_counts["Crystallization"] == 1
    assert sum(report.phase_counts.values()) == report.snapshot_count


def test_emsd_runtime_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/emsd_runtime.py")
    assert result.depth >= 2, result.reason
