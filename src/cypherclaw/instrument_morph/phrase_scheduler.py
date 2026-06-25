"""Morph-phrase scheduler: phrase progress -> streamed ``morph_x`` value.

The ``morph_voice`` synthdef crossfades source A (saw) <-> source B (pulse) by a
continuous ``morph_x`` in [0, 1]. To turn that static control into a musical
gesture, the composer streams ``morph_x`` along a trajectory across a scene. This
module is the pure trajectory math (no OSC, no I/O) so it can be unit tested; the
composer owns the persistent node and the ``/n_set`` streaming.

A sweep ``shape`` picks the gesture and a ``curve`` (reused from :mod:`curves`)
picks its easing; ``depth`` scales how far toward source B the gesture reaches
(1.0 = full pulse at the peak, smaller = a subtler timbral bend).
"""
from __future__ import annotations

import math
from enum import Enum

from .curves import MorphInterpolationCurve, morph_curve_position


class MorphSweepShape(str, Enum):
    """Supported single-line morph gestures across a phrase."""

    RISE = "rise"  # source A -> B (morph_x 0 -> depth)
    FALL = "fall"  # source B -> A (morph_x depth -> 0)
    ARCH = "arch"  # A -> B -> A; begins and ends on source A (saw)


def normalize_morph_sweep_shape(shape: MorphSweepShape | str) -> MorphSweepShape:
    """Return a canonical sweep-shape enum."""

    if isinstance(shape, MorphSweepShape):
        return shape
    key = str(shape or "").strip().lower()
    for candidate in MorphSweepShape:
        if key == candidate.value:
            return candidate
    raise ValueError(
        "shape must be one of "
        f"{tuple(candidate.value for candidate in MorphSweepShape)!r}, got {shape!r}"
    )


def phrase_morph_x(
    progress: float,
    *,
    shape: MorphSweepShape | str = MorphSweepShape.ARCH,
    curve: MorphInterpolationCurve | str = MorphInterpolationCurve.LINEAR,
    depth: float = 1.0,
) -> float:
    """Return the ``morph_x`` to stream at a normalized phrase ``progress``.

    ``progress`` is the fraction through the phrase in [0, 1]; ``depth`` in
    [0, 1] scales the peak excursion toward source B.
    """

    p = _unit("progress", progress)
    d = _unit("depth", depth)
    sweep = normalize_morph_sweep_shape(shape)
    if sweep is MorphSweepShape.RISE:
        base = p
    elif sweep is MorphSweepShape.FALL:
        base = 1.0 - p
    else:  # ARCH — triangular: 0 at the ends, 1 at the midpoint.
        base = 1.0 - abs((2.0 * p) - 1.0)
    curved = morph_curve_position(base, curve)
    return _clamp_unit(curved * d)


def phrase_morph_x_for_row(
    row: int,
    total_rows: int,
    *,
    shape: MorphSweepShape | str = MorphSweepShape.ARCH,
    curve: MorphInterpolationCurve | str = MorphInterpolationCurve.LINEAR,
    depth: float = 1.0,
) -> float:
    """Map a tracker ``row`` within ``total_rows`` to a streamed ``morph_x``."""

    return phrase_morph_x(
        _row_progress(row, total_rows),
        shape=shape,
        curve=curve,
        depth=depth,
    )


def _row_progress(row: int, total_rows: int) -> float:
    if total_rows is None or total_rows <= 1:
        return 0.0
    last = total_rows - 1
    clamped = max(0, min(int(row), last))
    return clamped / last


def _unit(label: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be in [0.0, 1.0]")
    return number


def _clamp_unit(value: float) -> float:
    return min(1.0, max(0.0, value))


__all__ = [
    "MorphSweepShape",
    "normalize_morph_sweep_shape",
    "phrase_morph_x",
    "phrase_morph_x_for_row",
]
