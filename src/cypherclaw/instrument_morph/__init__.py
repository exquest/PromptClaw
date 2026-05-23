"""Composer-side instrument morph helpers."""

from __future__ import annotations

from .crossfade import (
    SectionCrossfade,
    SectionTiming,
    schedule_section_crossfades,
)
from .flags import (
    CYPHERCLAW_V2_INSTRUMENT_MORPH_ENV,
    instrument_morph_enabled,
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
from .parameter_walk import (
    ParameterWalkFrame,
    ParameterWalkSpec,
    generate_parameter_walk,
    parameter_walk_depth_band,
)

__all__ = [
    "CYPHERCLAW_V2_INSTRUMENT_MORPH_ENV",
    "MorphInterpolationCurve",
    "MorphParameterFrame",
    "ParameterWalkFrame",
    "ParameterWalkSpec",
    "SectionCrossfade",
    "SectionTiming",
    "build_morph_parameter_frames",
    "generate_parameter_walk",
    "instrument_morph_enabled",
    "interpolate_scalar",
    "interpolate_voice_parameters",
    "morph_curve_position",
    "normalize_morph_interpolation_curve",
    "parameter_walk_depth_band",
    "schedule_section_crossfades",
]
