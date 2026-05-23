"""Composer-side instrument morph helpers."""

from __future__ import annotations

from .curves import (
    MorphInterpolationCurve,
    MorphParameterFrame,
    build_morph_parameter_frames,
    interpolate_scalar,
    interpolate_voice_parameters,
    morph_curve_position,
    normalize_morph_interpolation_curve,
)

__all__ = [
    "MorphInterpolationCurve",
    "MorphParameterFrame",
    "build_morph_parameter_frames",
    "interpolate_scalar",
    "interpolate_voice_parameters",
    "morph_curve_position",
    "normalize_morph_interpolation_curve",
]
