"""Morph operator interpolating between two `TuningSystem` pitch tables.

`MorphOperator.pitch_table_at(t)` returns a linearly interpolated pitch table
for `t in [0.0, 1.0]`, with `t=0` reproducing the source table and `t=1` the
target table (see T-034 / CC-041 in `prd-cypherclaw-v2-2026-05-22.md`).
"""

from __future__ import annotations

from dataclasses import dataclass

from .system import TuningSystem


@dataclass(frozen=True)
class MorphOperator:
    """Linear interpolator between two tuning systems' pitch tables."""

    source: TuningSystem
    target: TuningSystem
    tonal_center_hz: float

    def pitch_table_at(self, t: float) -> dict[int, float]:
        if not 0.0 <= float(t) <= 1.0:
            raise ValueError("t must be in [0.0, 1.0]")
        src = self.source.pitch_table(self.tonal_center_hz)
        tgt = self.target.pitch_table(self.tonal_center_hz)
        if t == 0.0:
            return dict(src)
        if t == 1.0:
            return dict(tgt)
        result: dict[int, float] = {}
        for degree in set(src) | set(tgt):
            if degree in src and degree in tgt:
                result[degree] = src[degree] * (1.0 - t) + tgt[degree] * t
            elif degree in src:
                result[degree] = src[degree]
            else:
                result[degree] = tgt[degree]
        return result
