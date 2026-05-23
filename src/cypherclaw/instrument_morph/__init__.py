"""Composer-side instrument morph helpers."""

from __future__ import annotations

from .crossfade import (
    SectionCrossfade,
    SectionTiming,
    schedule_section_crossfades,
)
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
    "SectionCrossfade",
    "SectionTiming",
    "build_morph_parameter_frames",
    "interpolate_scalar",
    "interpolate_voice_parameters",
    "morph_curve_position",
    "normalize_morph_interpolation_curve",
    "schedule_section_crossfades",
]
