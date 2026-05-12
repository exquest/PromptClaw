"""Tests for per-mode sampler density gates (CCS-023 / T-017)."""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave")
)

from senseweave.render.antipatterns import DEFAULT_SAMPLER_DENSITY_BY_MODE
from senseweave.sampler_scheduler import (
    count_sampler_events,
    density_for_mode,
    plan_sampler_phrase_indices,
)


def test_count_floor_plus_bernoulli_math() -> None:
    # density 0.5, 10 phrases -> floor(5) + Bernoulli(0.5)
    # rng.random() < 0.5 -> bonus = 1 -> 6
    rng = random.Random()
    rng.random = lambda: 0.4  # type: ignore[method-assign]
    assert count_sampler_events(0.5, 10, rng) == 6

    rng2 = random.Random()
    rng2.random = lambda: 0.9  # type: ignore[method-assign]
    assert count_sampler_events(0.5, 10, rng2) == 5


def test_count_clamps_density_above_one() -> None:
    rng = random.Random()
    rng.random = lambda: 0.99  # type: ignore[method-assign]
    # density 1.5 clamped to 1.0 -> floor(20) + Bernoulli(1.0)=1 -> clamp to 20
    assert count_sampler_events(1.5, 20, rng) == 20


def test_count_clamps_density_below_zero() -> None:
    rng = random.Random()
    rng.random = lambda: 0.0  # type: ignore[method-assign]
    assert count_sampler_events(-0.3, 20, rng) == 0


def test_count_never_exceeds_total_phrases() -> None:
    rng = random.Random()
    rng.random = lambda: 0.0  # bonus always fires  # type: ignore[method-assign]
    # density 1.0, 8 phrases -> floor(8) + 1 = 9, clamp to 8
    assert count_sampler_events(1.0, 8, rng) == 8


def test_count_returns_zero_for_empty_piece() -> None:
    assert count_sampler_events(0.65, 0) == 0


def test_plan_returns_sorted_unique_indices_within_range() -> None:
    rng = random.Random(1234)
    indices = plan_sampler_phrase_indices(0.5, 16, rng)
    assert indices == sorted(indices)
    assert len(set(indices)) == len(indices)
    assert all(0 <= i < 16 for i in indices)


def test_plan_count_never_exceeds_total_phrases() -> None:
    rng = random.Random(7)
    for _ in range(50):
        indices = plan_sampler_phrase_indices(1.0, 5, rng)
        assert len(indices) <= 5


def test_density_for_mode_uses_default_when_unknown() -> None:
    assert density_for_mode("not_a_real_mode", default=0.33) == 0.33


def test_density_for_mode_uses_default_when_none() -> None:
    assert density_for_mode(None, default=0.33) == 0.33


def test_density_for_mode_known_modes() -> None:
    assert density_for_mode("evening_reflection") == 0.65
    assert density_for_mode("working_ambience") == 0.10
    assert density_for_mode("solitary") == 0.7


def test_per_mode_separation_in_simulated_runs() -> None:
    """evening_reflection at 0.65 fires noticeably more sampler events than
    working_ambience at 0.10 across 100 simulated 16-phrase pieces."""
    total_phrases = 16
    pieces = 100

    evening_density = DEFAULT_SAMPLER_DENSITY_BY_MODE["evening_reflection"]
    working_density = DEFAULT_SAMPLER_DENSITY_BY_MODE["working_ambience"]

    rng_evening = random.Random(42)
    rng_working = random.Random(42)

    evening_total = sum(
        count_sampler_events(evening_density, total_phrases, rng_evening)
        for _ in range(pieces)
    )
    working_total = sum(
        count_sampler_events(working_density, total_phrases, rng_working)
        for _ in range(pieces)
    )

    expected_evening = pieces * (
        math.floor(evening_density * total_phrases) + evening_density
    )
    expected_working = pieces * (
        math.floor(working_density * total_phrases) + working_density
    )

    # Sanity: each total is within 25% of its expected value.
    assert abs(evening_total - expected_evening) / expected_evening < 0.25
    assert abs(working_total - expected_working) / expected_working < 0.25

    # Evening should be at least 4x the working total at these densities.
    assert evening_total > working_total * 4


class SamplerSchedulerEndToEndTests:
    """End-to-end diagnostic coverage for the sampler scheduler surface."""

    __test__ = True

    def test_sampler_scheduler_density_count_plan_round_trip_json_diagnostic(
        self,
    ) -> None:
        mode = "evening_reflection"
        total_phrases = 16
        seed = 42

        density = density_for_mode(mode)
        assert density == DEFAULT_SAMPLER_DENSITY_BY_MODE[mode]
        assert density == 0.65

        floor_term = math.floor(density * total_phrases)
        bonus_probe = random.Random(seed).random()
        expected_bonus = 1 if bonus_probe < density else 0
        expected_count = max(0, min(total_phrases, floor_term + expected_bonus))

        rng_count = random.Random(seed)
        count = count_sampler_events(density, total_phrases, rng_count)
        assert count == expected_count

        rng_plan = random.Random(seed)
        indices = plan_sampler_phrase_indices(density, total_phrases, rng_plan)
        assert len(indices) == count
        assert indices == sorted(indices)
        assert len(set(indices)) == len(indices)
        assert all(0 <= i < total_phrases for i in indices)

        diagnostic = {
            "mode": mode,
            "density": density,
            "total_phrases": total_phrases,
            "seed": seed,
            "floor_term": floor_term,
            "bonus_probe": bonus_probe,
            "expected_bonus": expected_bonus,
            "count": count,
            "indices": indices,
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert round_tripped["mode"] == "evening_reflection"
        assert round_tripped["density"] == 0.65
        assert round_tripped["floor_term"] == 10
        assert round_tripped["count"] == count
        assert round_tripped["indices"] == indices
        assert round_tripped["count"] == floor_term + expected_bonus
