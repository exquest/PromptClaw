"""Within-family parameter walk generators for instrument morph voices."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math


_MAX_DEPTH_FRACTION = 1.0


@dataclass(frozen=True)
class ParameterWalkSpec:
    """Continuous low-rate modulation spec for one voice parameter."""

    name: str
    center: float
    depth_fraction: float
    rate_hz: float
    phase: float = 0.0


@dataclass(frozen=True)
class ParameterWalkFrame:
    """One timestamped sample in a parameter walk trace."""

    time: float
    parameters: dict[str, float]


def generate_parameter_walk(
    specs: Sequence[ParameterWalkSpec] | Iterable[ParameterWalkSpec],
    *,
    duration: float,
    sample_rate: float,
) -> tuple[ParameterWalkFrame, ...]:
    """Return a sinusoidal LFO trace per parameter at ``sample_rate`` over ``duration``.

    Each value stays within ``center ± depth_fraction * |center|``. With a
    finite sample rate and bounded rate, adjacent samples are bounded by the
    sine derivative, so the trace is continuous in the sample-to-sample sense
    expected of an OSC modulation stream.
    """

    spec_tuple = tuple(specs)
    if not spec_tuple:
        raise ValueError("at least one parameter walk spec is required")
    if not _is_finite_positive(duration):
        raise ValueError(
            f"duration must be a finite positive number, got {duration!r}"
        )
    if not _is_finite_positive(sample_rate):
        raise ValueError(
            f"sample_rate must be a finite positive number, got {sample_rate!r}"
        )

    seen: set[str] = set()
    for spec in spec_tuple:
        _validate_spec(spec)
        if spec.name in seen:
            raise ValueError(f"duplicate parameter name {spec.name!r}")
        seen.add(spec.name)

    frame_count = int(math.floor(duration * sample_rate)) + 1
    step = 1.0 / sample_rate
    frames: list[ParameterWalkFrame] = []
    for index in range(frame_count):
        time = index * step
        if time > duration:
            time = duration
        parameters = {
            spec.name: _sample(spec, time) for spec in spec_tuple
        }
        frames.append(ParameterWalkFrame(time=time, parameters=parameters))
    return tuple(frames)


def parameter_walk_depth_band(spec: ParameterWalkSpec) -> tuple[float, float]:
    """Return the (low, high) closed band a walk for ``spec`` must stay within."""

    _validate_spec(spec)
    swing = spec.depth_fraction * abs(spec.center)
    return (spec.center - swing, spec.center + swing)


def _sample(spec: ParameterWalkSpec, time: float) -> float:
    angle = 2.0 * math.pi * (spec.rate_hz * time + spec.phase)
    swing = spec.depth_fraction * abs(spec.center)
    return spec.center + swing * math.sin(angle)


def _validate_spec(spec: ParameterWalkSpec) -> None:
    if not isinstance(spec, ParameterWalkSpec):
        raise TypeError(
            f"spec must be a ParameterWalkSpec, got {type(spec).__name__}"
        )
    if not spec.name:
        raise ValueError("spec.name must be a non-empty string")
    if not _is_finite(spec.center):
        raise ValueError(f"spec.center must be finite, got {spec.center!r}")
    if not _is_finite(spec.depth_fraction) or not (
        0.0 <= spec.depth_fraction <= _MAX_DEPTH_FRACTION
    ):
        raise ValueError(
            f"spec.depth_fraction must be in [0.0, {_MAX_DEPTH_FRACTION}], "
            f"got {spec.depth_fraction!r}"
        )
    if not _is_finite_positive(spec.rate_hz):
        raise ValueError(
            f"spec.rate_hz must be a finite positive number, got {spec.rate_hz!r}"
        )
    if not _is_finite(spec.phase):
        raise ValueError(f"spec.phase must be finite, got {spec.phase!r}")


def _is_finite(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _is_finite_positive(value: object) -> bool:
    if not _is_finite(value):
        return False
    assert isinstance(value, (int, float))
    return float(value) > 0.0


__all__ = [
    "ParameterWalkFrame",
    "ParameterWalkSpec",
    "generate_parameter_walk",
    "parameter_walk_depth_band",
]
