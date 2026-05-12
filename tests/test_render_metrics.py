"""Tests for the metric battery."""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.render.pass_ import PerformedPart
from senseweave.render.metrics import (
    PASS_BANDS,
    SAMPLER_LIBRARY_VS_SELF_WINDOW,
    assert_render_gate,
    compute_metrics,
    evaluate_render_gate,
    pass_bands_for_intent,
    sampler_event_count_per_piece,
    sampler_library_vs_self_ratio,
)


def _five_minute_render(
    *,
    velocities: list[float] | None = None,
    intent_tags: list[str] | None = None,
    pitches: list[int] | None = None,
) -> PerformedPart:
    return PerformedPart(
        score={
            "duration_sec": 300.0,
            "intent_tags": intent_tags or ["statement"],
            "velocities": velocities or [55.0, 75.0, 45.0, 80.0, 65.0, 70.0, 50.0],
            "timing_deviations_ms": [0.0, 4.0, -5.0, 6.0, -4.0, 3.0, -6.0],
            "iois": [1.0, 1.05, 0.95, 1.0, 1.1, 0.9, 1.0],
            "pitches": pitches or [60, 62, 64, 65, 67, 69, 60],
            "tempo_curve": [118.0, 120.0, 122.0, 121.0, 119.0],
            "novelty_peaks": 2,
            "silence_ms": 220.0,
            "rests_ms": [80.0, 240.0, 120.0],
            "section_gs": [0.82, 0.91, 0.94],
            "role": "melody",
        },
        applied_rules=("R1", "R2", "R3"),
        quantities={},
    )


CURATED_FIVE_MINUTE_RENDERS = (
    _five_minute_render(intent_tags=["statement"]),
    _five_minute_render(
        velocities=[54.0, 73.0, 46.0, 82.0, 64.0, 68.0, 51.0],
        intent_tags=["development"],
        pitches=[60, 63, 65, 67, 70, 71, 60],
    ),
    _five_minute_render(
        velocities=[57.0, 77.0, 48.0, 83.0, 66.0, 71.0, 52.0],
        intent_tags=["recap"],
        pitches=[62, 64, 65, 67, 69, 71, 62],
    ),
    _five_minute_render(
        velocities=[58.0, 70.0, 77.0, 62.0, 74.0, 66.0, 78.0],
        intent_tags=["withhold"],
        pitches=[59, 60, 62, 64, 65, 67, 59],
    ),
    _five_minute_render(
        velocities=[56.0, 76.0, 47.0, 81.0, 63.0, 69.0, 50.0],
        intent_tags=["release"],
        pitches=[60, 62, 65, 67, 69, 71, 60],
    ),
)

def test_flat_line_control_fails_pass_bands() -> None:
    part = PerformedPart(
        score={
            "velocities": [64.0, 64.0, 64.0, 64.0],  # Constant velocity (127 scale)
            "iois": [1.0, 1.0, 1.0, 1.0],           # Constant timing
            "pitches": [60, 60, 60, 60],            # Constant pitch (entropy 0)
            "tempo_curve": [120.0, 120.0, 120.0, 120.0],
            "novelty_peaks": 0,
            "silence_ms": 0.0,
        },
        applied_rules=(),
        quantities={},
    )
    
    metrics = compute_metrics(part)
    
    # Should fail all metrics since there's zero variation
    for key, (low, high) in PASS_BANDS.items():
        assert not (low <= metrics[key] <= high), f"{key} should fail band {low}-{high} but got {metrics[key]}"

def test_full_stack_render_passes_pass_bands() -> None:
    part = PerformedPart(
        score={
            # σ ~ 15
            "velocities": [55.0, 75.0, 45.0, 80.0, 65.0, 70.0, 50.0],
            # Mean ~ 1.0, stdev ~ 0.08, CoV ~ 0.08
            "iois": [1.0, 1.05, 0.95, 1.0, 1.1, 0.9, 1.0],
            # 6 different pitch classes, H1 ~ 2.5
            "pitches": [60, 62, 64, 65, 67, 69, 60],
            "tempo_curve": [118.0, 120.0, 122.0, 121.0, 119.0],
            "novelty_peaks": 2,
            "silence_ms": 150.0,
            "piece_history": [
                {
                    "sampler_used": True,
                    "sampler_library_count": 2,
                    "sampler_self_count": 1,
                }
                for _ in range(50)
            ],
        },
        applied_rules=("R1", "R2", "R3"),
        quantities={},
    )

    metrics = compute_metrics(part)

    for key, (low, high) in PASS_BANDS.items():
        assert low <= metrics[key] <= high, f"{key} out of bounds: {metrics[key]} not in {low}-{high}"


def test_withhold_intent_allows_lower_velocity_sigma() -> None:
    bands = pass_bands_for_intent(["withhold"])
    report = assert_render_gate(CURATED_FIVE_MINUTE_RENDERS[3])

    assert PASS_BANDS["velocity_sigma"][0] == 12
    assert bands["velocity_sigma"][0] < PASS_BANDS["velocity_sigma"][0]
    assert report.metrics["velocity_sigma"] < PASS_BANDS["velocity_sigma"][0]


def test_curated_five_minute_renders_pass_ci_gate() -> None:
    for part in CURATED_FIVE_MINUTE_RENDERS:
        report = assert_render_gate(part)
        assert report.approved
        assert report.failed_metrics == ()
        assert report.failed_antipatterns == ()


def test_sampler_event_count_per_piece_reads_score_count() -> None:
    score = {"sampler_event_count_per_piece": 14}
    assert sampler_event_count_per_piece(score) == 14.0


def test_sampler_event_count_per_piece_falls_back_to_aliases() -> None:
    assert sampler_event_count_per_piece({"sampler_event_count": 9}) == 9.0
    assert sampler_event_count_per_piece({"sampler_events": [1, 2, 3]}) == 3.0
    assert math.isnan(sampler_event_count_per_piece({}))


def test_sampler_library_vs_self_ratio_uses_last_50_pieces() -> None:
    history = [
        {"sampler_library_count": 100, "sampler_self_count": 100}
    ] + [
        {"sampler_library_count": 2, "sampler_self_count": 1}
        for _ in range(SAMPLER_LIBRARY_VS_SELF_WINDOW)
    ]
    ratio = sampler_library_vs_self_ratio({"piece_history": history})
    assert ratio == 2.0


def test_sampler_library_vs_self_ratio_nan_when_no_history() -> None:
    assert math.isnan(sampler_library_vs_self_ratio({}))
    assert math.isnan(sampler_library_vs_self_ratio({"piece_history": []}))
    assert math.isnan(
        sampler_library_vs_self_ratio(
            {"piece_history": [{"sampler_library_count": 0, "sampler_self_count": 0}]}
        )
    )


def test_sampler_library_vs_self_ratio_inf_when_only_library_plays() -> None:
    history = [{"sampler_library_count": 5, "sampler_self_count": 0}]
    assert sampler_library_vs_self_ratio({"piece_history": history}) == math.inf


def test_render_gate_fails_when_library_self_ratio_out_of_band() -> None:
    starved = PerformedPart(
        score={
            "velocities": [55.0, 75.0, 45.0, 80.0, 65.0, 70.0, 50.0],
            "iois": [1.0, 1.05, 0.95, 1.0, 1.1, 0.9, 1.0],
            "pitches": [60, 62, 64, 65, 67, 69, 60],
            "tempo_curve": [118.0, 120.0, 122.0, 121.0, 119.0],
            "novelty_peaks": 2,
            "silence_ms": 150.0,
            "piece_history": [
                {
                    "sampler_used": True,
                    "sampler_library_count": 1,
                    "sampler_self_count": 9,
                }
                for _ in range(50)
            ],
        },
        applied_rules=(),
        quantities={},
    )

    report = evaluate_render_gate(starved)

    assert not report.approved
    failed = {failure.name: failure for failure in report.failed_metrics}
    assert "sampler_library_vs_self_ratio" in failed
    failure = failed["sampler_library_vs_self_ratio"]
    assert failure.low == 1.5
    assert failure.high == 3.0
    assert failure.value < failure.low


def test_render_gate_passes_when_library_self_ratio_in_band() -> None:
    healthy = PerformedPart(
        score={
            "velocities": [55.0, 75.0, 45.0, 80.0, 65.0, 70.0, 50.0],
            "iois": [1.0, 1.05, 0.95, 1.0, 1.1, 0.9, 1.0],
            "pitches": [60, 62, 64, 65, 67, 69, 60],
            "tempo_curve": [118.0, 120.0, 122.0, 121.0, 119.0],
            "novelty_peaks": 2,
            "silence_ms": 150.0,
            "piece_history": [
                {
                    "sampler_used": True,
                    "sampler_library_count": 2,
                    "sampler_self_count": 1,
                }
                for _ in range(50)
            ],
        },
        applied_rules=(),
        quantities={},
    )

    report = evaluate_render_gate(healthy)

    assert report.approved
    assert report.metrics["sampler_library_vs_self_ratio"] == 2.0


def test_render_gate_skips_sampler_metric_when_history_missing() -> None:
    no_sampler = PerformedPart(
        score={
            "velocities": [55.0, 75.0, 45.0, 80.0, 65.0, 70.0, 50.0],
            "iois": [1.0, 1.05, 0.95, 1.0, 1.1, 0.9, 1.0],
            "pitches": [60, 62, 64, 65, 67, 69, 60],
            "tempo_curve": [118.0, 120.0, 122.0, 121.0, 119.0],
            "novelty_peaks": 2,
            "silence_ms": 150.0,
        },
        applied_rules=(),
        quantities={},
    )

    report = evaluate_render_gate(no_sampler)

    assert report.approved
    assert math.isnan(report.metrics["sampler_library_vs_self_ratio"])


def test_compute_metrics_includes_event_count_per_piece() -> None:
    part = PerformedPart(
        score={
            "velocities": [60.0, 70.0],
            "iois": [1.0, 1.1],
            "pitches": [60, 62],
            "tempo_curve": [120.0, 121.0],
            "sampler_event_count_per_piece": 7,
        },
        applied_rules=(),
        quantities={},
    )

    metrics = compute_metrics(part)

    assert metrics["sampler_event_count_per_piece"] == 7.0


def test_broken_render_fails_ci_gate() -> None:
    broken = PerformedPart(
        score={
            "duration_sec": 300.0,
            "intent_tags": ["statement"],
            "velocities": [64.0, 64.0, 64.0, 64.0],
            "timing_deviations_ms": [0.0, 0.0, 0.0, 0.0],
            "iois": [1.0, 1.0, 1.0, 1.0],
            "pitches": [60, 60, 60, 60],
            "tempo_curve": [120.0, 120.0, 120.0, 120.0],
            "novelty_peaks": 0,
            "silence_ms": 0.0,
            "rests_ms": [40.0, 80.0, 120.0],
            "section_gs": [0.98, 0.97],
            "role": "melody",
        },
        applied_rules=(),
        quantities={},
    )

    report = evaluate_render_gate(broken)

    assert not report.approved
    assert report.failed_metrics
    assert {failure.name for failure in report.failed_antipatterns} == {
        "dynamic_compression",
        "motif_ossification",
        "dead_silence_failure",
    }
