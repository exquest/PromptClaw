"""Shared protocol and result schema for audio generation clients."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .request import GenerationRequest


@dataclass(frozen=True)
class GenerationResult:
    """Completed audio generation metadata."""

    audio_path: Path
    sample_rate: int
    duration_actual_sec: float
    model_used: str
    cost_usd: float
    latency_ms: int
    api_request_id: str


@dataclass(frozen=True)
class GenerationOutcome:
    """Result of validating a :class:`GenerationResult` against its request."""

    passed: bool
    reasons: tuple[str, ...]


@runtime_checkable
class GenerationClient(Protocol):
    """Structural protocol shared by typed generation backends."""

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate audio for ``request``."""
        ...


def cost_per_second(result: GenerationResult) -> float:
    """Return USD cost per second of generated audio (``0.0`` for empty audio)."""
    duration = float(result.duration_actual_sec)
    if duration <= 0.0:
        return 0.0
    return float(result.cost_usd) / duration


def result_summary(result: GenerationResult) -> dict[str, Any]:
    """Return a stable, operator-readable summary dictionary for ``result``."""
    duration = float(result.duration_actual_sec)
    cost = float(result.cost_usd)
    rate = cost_per_second(result)
    return {
        "model": str(result.model_used),
        "sample_rate": int(result.sample_rate),
        "duration_sec": round(duration, 3),
        "cost_usd": round(cost, 4),
        "cost_per_second_usd": round(rate, 4),
        "latency_ms": int(result.latency_ms),
        "request_id": str(result.api_request_id),
        "audio_path": str(result.audio_path),
    }


def format_result_log_line(result: GenerationResult) -> str:
    """Return a single-line, space-separated operator log entry for ``result``."""
    request_id = str(result.api_request_id)
    if not request_id:
        request_id = "<unknown>"
    parts = [
        f"model={result.model_used}",
        f"dur={float(result.duration_actual_sec):.2f}s",
        f"cost=${float(result.cost_usd):.4f}",
        f"latency={int(result.latency_ms)}ms",
        f"id={request_id}",
    ]
    return " ".join(parts)


def validate_generation_result(
    result: GenerationResult,
    request: GenerationRequest,
    *,
    sample_rate_floor: int = 16_000,
    duration_tolerance_sec: float = 1.0,
) -> GenerationOutcome:
    """Compare ``result`` against ``request`` and return a :class:`GenerationOutcome`.

    Reason strings are accumulated in a stable order: model mismatch, sample
    rate floor, duration drift, negative cost, then negative latency.
    """
    reasons: list[str] = []
    if str(result.model_used) != str(request.model):
        reasons.append(
            f"model mismatch: got {result.model_used!r}, expected {request.model!r}"
        )
    if int(result.sample_rate) < int(sample_rate_floor):
        reasons.append(
            f"sample rate {int(result.sample_rate)} below floor {int(sample_rate_floor)}"
        )
    duration_diff = abs(float(result.duration_actual_sec) - float(request.duration_sec))
    if duration_diff > float(duration_tolerance_sec):
        reasons.append(
            f"duration off by {duration_diff:.2f}s (tolerance {float(duration_tolerance_sec):.2f}s)"
        )
    if float(result.cost_usd) < 0.0:
        reasons.append(f"negative cost {float(result.cost_usd):.4f}")
    if int(result.latency_ms) < 0:
        reasons.append(f"negative latency {int(result.latency_ms)}ms")
    return GenerationOutcome(passed=not reasons, reasons=tuple(reasons))


__all__ = [
    "GenerationClient",
    "GenerationOutcome",
    "GenerationResult",
    "cost_per_second",
    "format_result_log_line",
    "result_summary",
    "validate_generation_result",
]
