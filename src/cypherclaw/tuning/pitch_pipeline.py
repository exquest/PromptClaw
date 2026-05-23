"""Single entry point for composer-side pitch resolution (T-035 / CC-042).

`pitch_hz(scale_degree, octave, tuning, tonal_center_hz)` returns the Hz value
for the given (scale-degree, octave) coordinate in the supplied tuning system,
anchored on `tonal_center_hz` (the Hz value of degree 0 at octave 0).

Scale degrees outside `[0, tuning.degrees_per_octave)` are normalized via
divmod, with any octave overflow folded into the `octave` offset.
"""

from __future__ import annotations

from .system import TuningSystem


def pitch_hz(
    scale_degree: int,
    octave: int,
    tuning: TuningSystem,
    tonal_center_hz: float,
) -> float:
    """Resolve a (scale_degree, octave) coordinate to Hz under `tuning`."""
    if tonal_center_hz <= 0.0:
        raise ValueError("tonal_center_hz must be positive")
    octave_offset, normalized_degree = divmod(
        int(scale_degree), tuning.degrees_per_octave
    )
    table = tuning.pitch_table(float(tonal_center_hz))
    return table[normalized_degree] * (2.0 ** (int(octave) + octave_offset))
