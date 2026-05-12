"""Tests for SenseWeave render anti-pattern detectors."""
from __future__ import annotations

import json
import os
import random
import sys
from dataclasses import asdict

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.render.antipatterns import (
    AntiPatternResult,
    GENERATED_CONTENT_DOMINANCE_RATIO_THRESHOLD,
    SAMPLER_DOMINATING_CONSECUTIVE_LIMIT,
    detect_antipatterns,
    detect_dead_silence_failure,
    detect_dynamic_compression,
    detect_generated_content_dominance,
    detect_motif_ossification,
    detect_quantization_ghosting,
    detect_random_as_expression,
    detect_sampler_dominating,
    detect_sampler_silent_quintet_member,
    detect_symmetric_arc_uncanny,
    failing_antipatterns,
)


def _generated_content_piece(
    day: int,
    generated: int,
    total: int,
) -> dict[str, object]:
    return {
        "day": day,
        "samples_by_source": {"generated": generated, "field": total - generated},
        "total_sampler_events": total,
    }


def _mixed_antipattern_piece() -> dict[str, object]:
    velocities: list[float] = []
    for index in range(48):
        velocities.append(64.0 + float(index % 5))

    history: list[dict[str, object]] = []
    for _ in range(50):
        history.append(
            {
                "mode": "solitary",
                "sampler_used": False,
                "sampler_density": 0.7,
            }
        )

    return {
        "duration_sec": 150.0,
        "role": "melody",
        "velocities": velocities,
        "timing_deviations_ms": [0.0, 1.0, -1.0, 0.5] * 12,
        "tempo_curve": [118.0 + (index * 0.25) for index in range(48)],
        "section_gs": [0.971, 0.966, 0.982],
        "phrase_worms": [
            [(0.96, 0.2), (1.04, 0.8), (1.0, 1.0), (0.94, 0.4)],
            [(0.95, 0.1), (1.08, 1.0), (1.02, 1.3), (0.93, 0.3)],
            [(0.98, 0.3), (1.02, 0.6), (1.0, 0.7), (0.97, 0.5)],
            [(0.94, 0.2), (1.1, 1.2), (1.01, 1.5), (0.92, 0.2)],
        ],
        "rests_ms": [80.0, 120.0, 160.0],
        "samples_by_source": {"generated": 4, "field": 6},
        "total_sampler_events": 10,
        "sampler_event_count": 8,
        "total_event_count": 10,
        "sampler_dominating_streak": 1,
        "piece_history": history,
    }


def _healthy_antipattern_piece() -> dict[str, object]:
    history: list[dict[str, object]] = []
    for index in range(50):
        history.append(
            {
                "mode": "solitary",
                "sampler_used": index % 4 == 0,
                "sampler_density": 0.7,
            }
        )

    return {
        "duration_sec": 150.0,
        "role": "melody",
        "velocities": [54.0, 73.0, 46.0, 82.0, 64.0, 68.0, 51.0],
        "timing_deviations_ms": [0.0, 4.0, -5.0, 6.0, -4.0, 3.0, -6.0],
        "tempo_curve": [118.0, 120.0, 122.0, 121.0, 119.0, 123.0, 124.0],
        "section_gs": [0.82, 0.91, 0.94],
        "phrase_worms": [
            [(0.96, 0.2), (1.04, 0.8), (1.0, 1.0), (0.94, 0.4)],
            [(0.95, 0.1), (1.08, 1.0), (1.02, 1.3), (0.93, 0.3)],
            [(0.98, 0.3), (1.02, 0.6), (1.0, 0.7), (0.97, 0.5)],
            [(0.94, 0.2), (1.1, 1.2), (1.01, 1.5), (0.92, 0.2)],
        ],
        "rests_ms": [80.0, 240.0, 120.0],
        "samples_by_source": {"generated": 3, "field": 7},
        "total_sampler_events": 10,
        "sampler_event_count": 6,
        "total_event_count": 10,
        "piece_history": history,
    }


def _result_by_name(
    results: tuple[AntiPatternResult, ...],
) -> dict[str, AntiPatternResult]:
    by_name: dict[str, AntiPatternResult] = {}
    for result in results:
        by_name[result.name] = result
    return by_name


def _severity_names(
    results: tuple[AntiPatternResult, ...],
    severity: str,
) -> set[str]:
    names: set[str] = set()
    for result in results:
        if result.severity == severity:
            names.add(result.name)
    return names


def _json_safe_diagnostic(
    results: tuple[AntiPatternResult, ...],
    failures: tuple[AntiPatternResult, ...],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for result in results:
        rows.append(asdict(result))
    return {
        "result_count": len(results),
        "failed": sorted(result.name for result in failures),
        "warnings": sorted(_severity_names(failures, "warning")),
        "blocking": sorted(_severity_names(failures, "fail")),
        "results": rows,
    }


def test_quantization_ghosting_fails_when_dynamics_move_but_timing_is_gridlocked() -> None:
    result = detect_quantization_ghosting(
        {
            "velocities": [58.0, 72.0, 66.0, 81.0],
            "timing_deviations_ms": [0.0, 1.0, -1.0, 0.5],
        }
    )

    assert result.failed


def test_quantization_ghosting_passes_when_timing_variance_is_audible() -> None:
    result = detect_quantization_ghosting(
        {
            "velocities": [58.0, 72.0, 66.0, 81.0],
            "timing_deviations_ms": [0.0, 4.0, -5.0, 6.0],
        }
    )

    assert not result.failed


def test_dynamic_compression_fails_on_velocity_range_below_twenty() -> None:
    result = detect_dynamic_compression({"velocities": [60.0, 66.0, 72.0, 75.0]})

    assert result.failed


def test_dynamic_compression_passes_on_velocity_range_of_twenty_or_more() -> None:
    result = detect_dynamic_compression({"velocities": [50.0, 64.0, 70.0]})

    assert not result.failed


def test_motif_ossification_fails_when_repeated_section_gs_exceeds_threshold() -> None:
    result = detect_motif_ossification({"section_gs": [0.971, 0.966, 0.982]})

    assert result.failed


def test_motif_ossification_passes_when_repeated_sections_vary() -> None:
    result = detect_motif_ossification({"section_gs": [0.82, 0.91, 0.94]})

    assert not result.failed


def test_random_as_expression_fails_when_ljung_box_does_not_reject_noise() -> None:
    rng = random.Random(17)
    result = detect_random_as_expression(
        {
            "tempo_curve": [120.0 + rng.uniform(-2.0, 2.0) for _ in range(48)],
            "velocities": [72.0 + rng.uniform(-11.0, 11.0) for _ in range(48)],
        }
    )

    assert result.failed


def test_random_as_expression_passes_when_series_are_structured() -> None:
    result = detect_random_as_expression(
        {
            "tempo_curve": [120.0 + (i * 0.35) for i in range(48)],
            "velocities": [54.0 + (i * 0.8) for i in range(48)],
        }
    )

    assert not result.failed


def test_symmetric_arc_uncanny_fails_when_worm_hull_variance_is_too_low() -> None:
    phrase_worm = [(0.96, 0.2), (1.04, 0.8), (1.0, 1.0), (0.94, 0.4)]
    result = detect_symmetric_arc_uncanny({"phrase_worms": [phrase_worm] * 4})

    assert result.failed


def test_symmetric_arc_uncanny_passes_when_phrase_worm_shapes_vary() -> None:
    result = detect_symmetric_arc_uncanny(
        {
            "phrase_worms": [
                [(0.96, 0.2), (1.04, 0.8), (1.0, 1.0), (0.94, 0.4)],
                [(0.95, 0.1), (1.08, 1.0), (1.02, 1.3), (0.93, 0.3)],
                [(0.98, 0.3), (1.02, 0.6), (1.0, 0.7), (0.97, 0.5)],
                [(0.94, 0.2), (1.1, 1.2), (1.01, 1.5), (0.92, 0.2)],
            ]
        }
    )

    assert not result.failed


def test_dead_silence_failure_fails_without_long_rests_in_two_minute_melody() -> None:
    result = detect_dead_silence_failure(
        {
            "duration_sec": 120.0,
            "rests_ms": [40.0, 80.0, 150.0, 199.0],
            "role": "melody",
        }
    )

    assert result.failed


def test_dead_silence_failure_passes_with_long_rest_in_two_minute_melody() -> None:
    result = detect_dead_silence_failure(
        {
            "duration_sec": 120.0,
            "rests_ms": [40.0, 250.0],
            "role": "melody",
        }
    )

    assert not result.failed


def test_generated_content_dominance_warns_when_piece_ratio_exceeds_threshold() -> None:
    result = detect_generated_content_dominance(
        {
            "samples_by_source": {"generated": 4, "field": 6},
            "total_sampler_events": 10,
        }
    )

    assert result.failed
    assert result.severity == "warning"
    assert result.value == 0.4
    assert result.threshold == pytest.approx(
        GENERATED_CONTENT_DOMINANCE_RATIO_THRESHOLD
    )


def test_generated_content_dominance_passes_when_piece_ratio_equals_threshold() -> None:
    result = detect_generated_content_dominance(
        {
            "samples_by_source": {"generated": 3, "field": 7},
            "total_sampler_events": 10,
        }
    )

    assert not result.failed
    assert result.severity == "ok"


def test_generated_content_dominance_must_fix_after_seven_rolling_days() -> None:
    history = [
        *(_generated_content_piece(day, 0, 10) for day in range(1, 44)),
        *(_generated_content_piece(day, 4, 10) for day in range(44, 51)),
    ]

    result = detect_generated_content_dominance(
        {
            "samples_by_source": {"generated": 1, "field": 9},
            "total_sampler_events": 10,
            "piece_history": history,
        }
    )

    assert result.failed
    assert result.severity == "fail"


def test_generated_content_dominance_uses_only_last_fifty_pieces() -> None:
    older = [_generated_content_piece(day, 4, 10) for day in range(1, 8)]
    recent = [_generated_content_piece(day, 0, 10) for day in range(8, 58)]

    result = detect_generated_content_dominance({"piece_history": older + recent})

    assert not result.failed
    assert result.severity == "ok"


def test_sampler_dominating_warns_when_ratio_exceeds_threshold_without_streak() -> None:
    result = detect_sampler_dominating(
        {"sampler_event_count": 8, "total_event_count": 10}
    )

    assert result.failed
    assert result.severity == "warning"
    assert result.value == 0.8


def test_sampler_dominating_must_fix_after_three_consecutive_pieces() -> None:
    result = detect_sampler_dominating(
        {
            "sampler_event_count": 8,
            "total_event_count": 10,
            "sampler_dominating_streak": SAMPLER_DOMINATING_CONSECUTIVE_LIMIT,
        }
    )

    assert result.failed
    assert result.severity == "fail"


def test_sampler_dominating_passes_when_ratio_at_or_below_threshold() -> None:
    result = detect_sampler_dominating(
        {"sampler_event_count": 6, "total_event_count": 10}
    )

    assert not result.failed
    assert result.severity == "ok"


def test_sampler_dominating_inert_without_event_counts() -> None:
    result = detect_sampler_dominating({"velocities": [60.0, 70.0]})

    assert not result.failed
    assert result.severity == "ok"


def test_sampler_silent_quintet_member_fails_when_solitary_run_omits_sampler() -> None:
    history = [{"mode": "solitary", "sampler_used": False} for _ in range(50)]

    result = detect_sampler_silent_quintet_member({"piece_history": history})

    assert result.failed
    assert result.value == 0.0
    assert result.threshold == pytest.approx(0.05)


def test_sampler_silent_quintet_member_passes_with_healthy_solitary_usage() -> None:
    history = [
        {"mode": "solitary", "sampler_used": index % 5 == 0}
        for index in range(50)
    ]

    result = detect_sampler_silent_quintet_member({"piece_history": history})

    assert not result.failed
    assert result.value == 0.2


def test_sampler_silent_quintet_member_does_not_trip_for_working_ambience() -> None:
    history = [{"mode": "working_ambience", "sampler_used": False} for _ in range(50)]
    history[0] = {"mode": "working_ambience", "sampler_used": True}

    result = detect_sampler_silent_quintet_member({"piece_history": history})

    assert not result.failed
    assert result.threshold < 0.05


def test_sampler_silent_quintet_member_uses_only_last_fifty_pieces() -> None:
    older = [{"mode": "solitary", "sampler_used": False} for _ in range(20)]
    recent = [{"mode": "solitary", "sampler_used": True} for _ in range(50)]

    result = detect_sampler_silent_quintet_member(
        {"piece_history": older + recent}
    )

    assert not result.failed
    assert result.value == 1.0


def test_sampler_silent_quintet_member_inert_without_history() -> None:
    result = detect_sampler_silent_quintet_member({})

    assert not result.failed
    assert result.severity == "ok"


def test_sampler_silent_quintet_member_threshold_scales_with_explicit_density() -> None:
    history = [
        {"mode": "custom", "sampler_used": False, "sampler_density": 0.7}
        for _ in range(50)
    ]

    result = detect_sampler_silent_quintet_member({"piece_history": history})

    assert result.failed
    assert result.threshold == pytest.approx(0.05)


class RenderAntipatternsEndToEndTests:
    """End-to-end render anti-pattern battery across the public surface."""

    __test__ = True

    def test_full_antipattern_battery_reports_meaningful_json_safe_diagnostics(
        self,
    ) -> None:
        rendered_piece = _mixed_antipattern_piece()

        results = detect_antipatterns(rendered_piece)
        failures = failing_antipatterns(rendered_piece)
        result_by_name = _result_by_name(results)
        failure_by_name = _result_by_name(failures)
        warning_names = _severity_names(failures, "warning")
        blocking_names = _severity_names(failures, "fail")

        assert [result.name for result in results] == [
            "quantization_ghosting",
            "dynamic_compression",
            "motif_ossification",
            "random_as_expression",
            "symmetric_arc_uncanny",
            "dead_silence_failure",
            "generated_content_dominance",
            "sampler_dominating",
            "sampler_silent_quintet_member",
        ]
        assert failure_by_name.keys() == {
            name for name, result in result_by_name.items() if result.failed
        }
        assert warning_names == {
            "generated_content_dominance",
            "sampler_dominating",
        }
        assert blocking_names == {
            "quantization_ghosting",
            "dynamic_compression",
            "motif_ossification",
            "dead_silence_failure",
            "sampler_silent_quintet_member",
        }

        for result in results:
            assert result.detail
            assert result.severity in {"ok", "warning", "fail"}

        assert result_by_name["generated_content_dominance"].value == 0.4
        assert result_by_name["generated_content_dominance"].threshold == pytest.approx(
            GENERATED_CONTENT_DOMINANCE_RATIO_THRESHOLD
        )
        assert result_by_name["sampler_dominating"].value == 0.8
        assert result_by_name["sampler_dominating"].threshold == pytest.approx(
            0.6
        )
        assert result_by_name["sampler_silent_quintet_member"].threshold == (
            pytest.approx(0.05)
        )
        assert not result_by_name["symmetric_arc_uncanny"].failed

        diagnostic = _json_safe_diagnostic(results, failures)
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped["result_count"] == 9
        assert round_tripped["warnings"] == [
            "generated_content_dominance",
            "sampler_dominating",
        ]
        assert round_tripped["blocking"] == [
            "dead_silence_failure",
            "dynamic_compression",
            "motif_ossification",
            "quantization_ghosting",
            "sampler_silent_quintet_member",
        ]
        assert round_tripped["results"][0]["detail"].startswith("velocity_sigma=")

    def test_failure_filter_tracks_full_battery_failed_subset(self) -> None:
        results = detect_antipatterns(_mixed_antipattern_piece())
        failures = failing_antipatterns(_mixed_antipattern_piece())
        expected_failed: set[str] = set()
        for result in results:
            if result.failed:
                expected_failed.add(result.name)

        actual_failed = {result.name for result in failures}

        assert actual_failed == expected_failed
        assert len(actual_failed) == 7
        assert "symmetric_arc_uncanny" not in actual_failed

    def test_warning_detectors_keep_nonblocking_severity(self) -> None:
        failures = failing_antipatterns(_mixed_antipattern_piece())
        warning_names: set[str] = set()
        for result in failures:
            if result.severity == "warning":
                warning_names.add(result.name)

        assert warning_names == {
            "generated_content_dominance",
            "sampler_dominating",
        }
        assert "dead_silence_failure" not in warning_names
        assert "sampler_silent_quintet_member" not in warning_names

    def test_blocking_failures_preserve_fail_severity(self) -> None:
        failures = failing_antipatterns(_mixed_antipattern_piece())
        blocking_names: set[str] = set()
        for result in failures:
            if result.severity == "fail":
                blocking_names.add(result.name)

        assert blocking_names == {
            "quantization_ghosting",
            "dynamic_compression",
            "motif_ossification",
            "dead_silence_failure",
            "sampler_silent_quintet_member",
        }
        assert "generated_content_dominance" not in blocking_names

    def test_clean_piece_reports_all_detectors_ok(self) -> None:
        results = detect_antipatterns(_healthy_antipattern_piece())
        failed_names: list[str] = []
        for result in results:
            if result.failed:
                failed_names.append(result.name)

        result_by_name = _result_by_name(results)

        assert failed_names == []
        assert result_by_name["generated_content_dominance"].severity == "ok"
        assert result_by_name["sampler_dominating"].severity == "ok"
        assert result_by_name["sampler_silent_quintet_member"].severity == "ok"
        assert len(results) == 9

    def test_score_wrapped_object_uses_same_detector_path(self) -> None:
        class RenderEnvelope:
            def __init__(self, score: dict[str, object]) -> None:
                self.score = score

        wrapped = RenderEnvelope(_mixed_antipattern_piece())
        direct_results = detect_antipatterns(wrapped.score)
        wrapped_results = detect_antipatterns(wrapped)
        for direct, via_wrapper in zip(direct_results, wrapped_results):
            assert via_wrapper == direct

        assert failing_antipatterns(wrapped) == failing_antipatterns(wrapped.score)
        assert len(wrapped_results) == 9

    def test_operator_diagnostic_rows_include_values_and_thresholds(self) -> None:
        rendered_piece = _mixed_antipattern_piece()
        results = detect_antipatterns(rendered_piece)
        diagnostic = _json_safe_diagnostic(
            results,
            failing_antipatterns(rendered_piece),
        )
        rows_by_name = {
            str(row["name"]): row
            for row in diagnostic["results"]
            if isinstance(row, dict)
        }

        for name in (
            "generated_content_dominance",
            "sampler_dominating",
            "sampler_silent_quintet_member",
        ):
            assert rows_by_name[name]["value"] is not None
            assert rows_by_name[name]["threshold"] is not None
            assert rows_by_name[name]["detail"]

        assert rows_by_name["sampler_dominating"]["severity"] == "warning"
