"""Depth-2 generation client_protocol helpers - locked test surface for frac-0010."""
from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.client_protocol import (  # noqa: E402
    GenerationOutcome,
    GenerationResult,
    cost_per_second,
    format_result_log_line,
    result_summary,
    validate_generation_result,
)
from senseweave.generation.request import (  # noqa: E402
    CLAP_CENTROID_DIM,
    GenerationRequest,
)


def _request(**overrides: object) -> GenerationRequest:
    base = dict(
        prompt="quiet texture",
        clap_centroid=np.zeros(CLAP_CENTROID_DIM, dtype=np.float32),
        duration_sec=10.0,
        seed=1,
        bpm_target=90.0,
        mode_name="quiet",
        arc_phase="Emergence",
        model="musicgen-medium",
    )
    base.update(overrides)
    return GenerationRequest(**base)  # type: ignore[arg-type]


def _result(**overrides: object) -> GenerationResult:
    base = dict(
        audio_path=Path("/tmp/sample.wav"),
        sample_rate=48_000,
        duration_actual_sec=10.0,
        model_used="musicgen-medium",
        cost_usd=0.05,
        latency_ms=2_500,
        api_request_id="pred/abc",
    )
    base.update(overrides)
    return GenerationResult(**base)  # type: ignore[arg-type]


def test_generation_outcome_is_frozen_dataclass() -> None:
    outcome = GenerationOutcome(passed=True, reasons=())

    assert dataclasses.is_dataclass(outcome)
    assert getattr(outcome, "__dataclass_params__").frozen
    assert [field.name for field in dataclasses.fields(outcome)] == [
        "passed",
        "reasons",
    ]
    assert outcome.passed is True
    assert outcome.reasons == ()


def test_cost_per_second_handles_positive_and_zero_durations() -> None:
    assert cost_per_second(_result(cost_usd=0.10, duration_actual_sec=5.0)) == pytest.approx(0.02)
    assert cost_per_second(_result(cost_usd=0.10, duration_actual_sec=0.0)) == 0.0
    assert cost_per_second(_result(cost_usd=0.10, duration_actual_sec=-1.0)) == 0.0


def test_result_summary_is_stable_and_meaningful() -> None:
    summary = result_summary(
        _result(
            audio_path=Path("/tmp/senseweave-generation/pred-abc.wav"),
            sample_rate=48_000,
            duration_actual_sec=10.123456,
            cost_usd=0.054321,
            latency_ms=2_500,
            api_request_id="pred/abc",
        )
    )

    assert summary == {
        "model": "musicgen-medium",
        "sample_rate": 48_000,
        "duration_sec": pytest.approx(10.123),
        "cost_usd": pytest.approx(0.0543),
        "cost_per_second_usd": pytest.approx(0.0054),
        "latency_ms": 2_500,
        "request_id": "pred/abc",
        "audio_path": "/tmp/senseweave-generation/pred-abc.wav",
    }


def test_format_result_log_line_is_single_line_with_id_fallback() -> None:
    populated = format_result_log_line(
        _result(
            duration_actual_sec=10.0,
            cost_usd=0.0543,
            latency_ms=2_500,
            api_request_id="pred/abc",
        )
    )
    missing = format_result_log_line(_result(api_request_id=""))

    assert populated == "model=musicgen-medium dur=10.00s cost=$0.0543 latency=2500ms id=pred/abc"
    assert "\n" not in populated
    assert missing.endswith(" id=<unknown>")


def test_validate_generation_result_accumulates_reasons() -> None:
    request = _request(duration_sec=10.0, model="musicgen-medium")

    passing = validate_generation_result(_result(), request)
    failing = validate_generation_result(
        _result(
            model_used="other-model",
            sample_rate=8_000,
            duration_actual_sec=5.0,
            cost_usd=-0.01,
            latency_ms=-1,
        ),
        request,
        sample_rate_floor=16_000,
        duration_tolerance_sec=1.0,
    )

    assert isinstance(passing, GenerationOutcome)
    assert passing.passed is True
    assert passing.reasons == ()

    assert failing.passed is False
    assert len(failing.reasons) == 5
    assert "model" in failing.reasons[0]
    assert "sample rate" in failing.reasons[1]
    assert "duration" in failing.reasons[2]
    assert "cost" in failing.reasons[3]
    assert "latency" in failing.reasons[4]
