"""Per-mode sampler density gates (CCS-023 / T-017).

Computes how many sampler events the composer should fire in a piece and
which phrase indices receive them. The count formula is

    floor(density * total_phrases) + Bernoulli(density)

clamped to ``[0, total_phrases]``. The deterministic floor guarantees a
baseline density per mode while the Bernoulli term keeps neighbouring
pieces from being identical. ``sampler_density`` is the scheduler's
canonical "how often should ``sw_sampler`` appear?" weight, not a gain
control: solitary=0.70, companion=0.25, working_ambience=0.10,
evening_reflection=0.65, storm=0.45.
"""
from __future__ import annotations

import math
import random
from collections.abc import Mapping

from .render.antipatterns import DEFAULT_SAMPLER_DENSITY_BY_MODE


def density_for_mode(
    mode_name: str | None,
    *,
    default: float = 0.25,
    table: Mapping[str, float] = DEFAULT_SAMPLER_DENSITY_BY_MODE,
) -> float:
    """Return the canonical scheduler weight for ``mode_name``.

    The result is the expected share of phrase slots that may receive
    sampler events for the mode, not an audio mix level.
    """
    if not mode_name:
        return default
    return float(table.get(mode_name, default))


def count_sampler_events(
    density: float,
    total_phrases: int,
    rng: random.Random | None = None,
) -> int:
    """Return how many sampler events to schedule this piece.

    ``floor(density * total_phrases) + Bernoulli(density)``, clamped to
    ``[0, total_phrases]``. Density is clamped to ``[0.0, 1.0]`` first
    and represents the normalized per-piece sampler participation target.
    """
    if total_phrases <= 0:
        return 0
    d = max(0.0, min(1.0, float(density)))
    base = math.floor(d * total_phrases)
    rng = rng or random.Random()
    bonus = 1 if rng.random() < d else 0
    return max(0, min(total_phrases, base + bonus))


def plan_sampler_phrase_indices(
    density: float,
    total_phrases: int,
    rng: random.Random | None = None,
) -> list[int]:
    """Pick the phrase indices that should fire a sampler event.

    Indices are returned sorted so the composer can iterate the timeline
    in order. Selection within the phrase set is uniform-random.
    """
    rng = rng or random.Random()
    count = count_sampler_events(density, total_phrases, rng)
    if count == 0:
        return []
    return sorted(rng.sample(range(total_phrases), count))


__all__ = (
    "DEFAULT_SAMPLER_DENSITY_BY_MODE",
    "count_sampler_events",
    "density_for_mode",
    "plan_sampler_phrase_indices",
)
