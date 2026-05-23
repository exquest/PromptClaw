"""Curve interpolation helpers for single-line instrument morph planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import math


_EXPONENTIAL_STRENGTH = 4.0
_SIGMOID_STRENGTH = 12.0


class MorphInterpolationCurve(str, Enum):
    """Supported composer-side phrase progression curves."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    SIGMOID = "sigmoid"


@dataclass(frozen=True)
class MorphParameterFrame:
    """One endpoint-inclusive frame in a morph parameter trajectory."""

    position: float
    curve_position: float
    parameters: dict[str, float]


def normalize_morph_interpolation_curve(
    curve: MorphInterpolationCurve | str,
) -> MorphInterpolationCurve:
    """Return a canonical interpolation curve enum."""

    if isinstance(curve, MorphInterpolationCurve):
        return curve
    key = str(curve or "").strip().lower().replace("_", "-").replace(" ", "-")
    for candidate in MorphInterpolationCurve:
        if key == candidate.value:
            return candidate
    raise ValueError(
        "curve must be one of "
        f"{tuple(candidate.value for candidate in MorphInterpolationCurve)!r}, "
        f"got {curve!r}"
    )


def morph_curve_position(
    position: float,
    curve: MorphInterpolationCurve | str,
) -> float:
    """Map a normalized phrase position through the requested curve."""

    x = _unit_position("position", position)
    normalized_curve = normalize_morph_interpolation_curve(curve)
    if x == 0.0 or x == 1.0:
        return x
    if normalized_curve is MorphInterpolationCurve.LINEAR:
        return x
    if normalized_curve is MorphInterpolationCurve.EXPONENTIAL:
        return _clamp_unit(
            (math.exp(_EXPONENTIAL_STRENGTH * x) - 1.0)
            / (math.exp(_EXPONENTIAL_STRENGTH) - 1.0)
        )
    return _clamp_unit(_normalized_sigmoid(x))


def interpolate_scalar(
    source_value: float,
    target_value: float,
    position: float,
    curve: MorphInterpolationCurve | str = MorphInterpolationCurve.LINEAR,
) -> float:
    """Interpolate one numeric parameter from source to target."""

    source = _finite_number("source_value", source_value)
    target = _finite_number("target_value", target_value)
    curved = morph_curve_position(position, curve)
    if curved == 0.0:
        return source
    if curved == 1.0:
        return target
    return source + ((target - source) * curved)


def interpolate_voice_parameters(
    source: Mapping[str, float],
    target: Mapping[str, float],
    position: float,
    curve: MorphInterpolationCurve | str = MorphInterpolationCurve.LINEAR,
) -> dict[str, float]:
    """Interpolate numeric voice parameter maps at one phrase position."""

    result: dict[str, float] = {}
    for key in sorted(set(source) | set(target)):
        if key in source and key in target:
            result[key] = interpolate_scalar(
                source[key],
                target[key],
                position,
                curve,
            )
        elif key in source:
            result[key] = _finite_number(f"source[{key!r}]", source[key])
        else:
            result[key] = _finite_number(f"target[{key!r}]", target[key])
    return result


def build_morph_parameter_frames(
    source: Mapping[str, float],
    target: Mapping[str, float],
    *,
    frame_count: int,
    curve: MorphInterpolationCurve | str = MorphInterpolationCurve.LINEAR,
) -> tuple[MorphParameterFrame, ...]:
    """Return an endpoint-inclusive parameter trajectory for later scheduling."""

    if frame_count < 2:
        raise ValueError("frame_count must be at least 2")
    normalized_curve = normalize_morph_interpolation_curve(curve)
    last_index = frame_count - 1
    frames: list[MorphParameterFrame] = []
    for index in range(frame_count):
        position = index / last_index
        frames.append(
            MorphParameterFrame(
                position=position,
                curve_position=morph_curve_position(position, normalized_curve),
                parameters=interpolate_voice_parameters(
                    source,
                    target,
                    position,
                    normalized_curve,
                ),
            )
        )
    return tuple(frames)


def _normalized_sigmoid(position: float) -> float:
    low = 1.0 / (1.0 + math.exp(_SIGMOID_STRENGTH * 0.5))
    high = 1.0 / (1.0 + math.exp(-_SIGMOID_STRENGTH * 0.5))
    raw = 1.0 / (1.0 + math.exp(-_SIGMOID_STRENGTH * (position - 0.5)))
    return (raw - low) / (high - low)


def _unit_position(label: str, value: float) -> float:
    number = _finite_number(label, value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be in [0.0, 1.0]")
    return number


def _finite_number(label: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _clamp_unit(value: float) -> float:
    return min(1.0, max(0.0, value))


__all__ = [
    "MorphInterpolationCurve",
    "MorphParameterFrame",
    "build_morph_parameter_frames",
    "interpolate_scalar",
    "interpolate_voice_parameters",
    "morph_curve_position",
    "normalize_morph_interpolation_curve",
]
