"""Depth-2 genre_literacy helpers - locked test surface for frac-0012."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.genre_literacy import (  # noqa: E402
    REQUIRED_GENRES,
    GenreBlend,
    GenreSummary,
    blend_genre_strategies,
    genre_compatibility,
    recommend_genre_sequence,
    summarize_strategy,
)


def test_summarize_strategy_is_stable_and_meaningful() -> None:
    summary = summarize_strategy("ambient_drone_generative")

    assert isinstance(summary, GenreSummary)
    assert summary.genre_id == "ambient_drone_generative"
    assert summary.label == "Ambient / Drone / Generative"
    assert summary.tempo_range == (40.0, 80.0)
    assert summary.texture_density == pytest.approx(0.35)
    assert summary.chromatic_tolerance == pytest.approx(0.4)
    assert summary.voice_count_range == (1, 4)
    assert summary.dominant_grooves == ("straight", "lilt")
    assert summary.top_arc_phases == ("Divination", "Crystallization")
    assert summary.mood_signature == "calm"


def test_summarize_strategy_buckets_intense_and_balanced() -> None:
    intense = summarize_strategy("idm_electronic")
    balanced = summarize_strategy("jazz")

    assert intense.mood_signature == "intense"
    assert balanced.mood_signature == "balanced"
    # Every required genre summarises without raising
    for genre_id in REQUIRED_GENRES:
        assert summarize_strategy(genre_id).genre_id == genre_id


def test_genre_compatibility_is_bounded_and_symmetric() -> None:
    for genre_id in REQUIRED_GENRES:
        assert genre_compatibility(genre_id, genre_id) == pytest.approx(1.0)

    pairs = [
        ("ambient_drone_generative", "spectral"),
        ("jazz", "blues"),
        ("idm_electronic", "minimalism"),
        ("classical_orchestral", "post_rock_experimental"),
        ("musique_concrete", "world_music"),
    ]
    for left, right in pairs:
        forward = genre_compatibility(left, right)
        backward = genre_compatibility(right, left)
        assert 0.0 <= forward <= 1.0
        assert forward == pytest.approx(backward)

    # Closely related ambient/spectral should out-rank ambient vs jazz.
    related = genre_compatibility("ambient_drone_generative", "spectral")
    contrasted = genre_compatibility("ambient_drone_generative", "jazz")
    assert related > contrasted


def test_blend_genre_strategies_interpolates_and_intersects() -> None:
    blend_mid = blend_genre_strategies(
        "minimalism", "idm_electronic", weight=0.5
    )

    assert isinstance(blend_mid, GenreBlend)
    assert blend_mid.left_id == "minimalism"
    assert blend_mid.right_id == "idm_electronic"
    assert blend_mid.weight == pytest.approx(0.5)
    assert blend_mid.tempo_range == pytest.approx((85.0, 155.0))
    assert blend_mid.texture_density == pytest.approx(0.575)
    assert blend_mid.chromatic_tolerance == pytest.approx(0.425)
    assert blend_mid.rubato_tolerance == pytest.approx(0.225)
    assert blend_mid.repetition_tolerance == pytest.approx(0.775)
    assert blend_mid.spatial_width == pytest.approx(0.675)
    assert blend_mid.shared_modes == ()

    # weight clamp + endpoint behaviour
    left_only = blend_genre_strategies("minimalism", "idm_electronic", weight=-1.0)
    right_only = blend_genre_strategies("minimalism", "idm_electronic", weight=2.5)
    assert left_only.weight == pytest.approx(0.0)
    assert right_only.weight == pytest.approx(1.0)
    assert left_only.texture_density == pytest.approx(0.5)
    assert right_only.texture_density == pytest.approx(0.65)

    # Modal intersection is sorted alphabetically.
    shared = blend_genre_strategies(
        "ambient_drone_generative", "idm_electronic", weight=0.5
    )
    assert shared.shared_modes == ("lydian",)


def test_recommend_genre_sequence_picks_per_phase_and_avoids_repeats() -> None:
    phases = ("Divination", "Emergence", "Conversation", "Convergence", "Crystallization")
    sequence = recommend_genre_sequence(phases)

    assert len(sequence) == len(phases)
    assert all(genre in REQUIRED_GENRES for genre in sequence)
    # avoid_repeat default biases against immediate back-to-back duplicates.
    for prior, follow in zip(sequence, sequence[1:], strict=False):
        assert prior != follow

    # Empty input short-circuits.
    assert recommend_genre_sequence(()) == []

    # Carrying recent_genres still produces one genre per supplied phase.
    biased = recommend_genre_sequence(
        ("Conversation", "Conversation"),
        recent_genres=("jazz", "blues"),
    )
    assert len(biased) == 2
    assert all(genre in REQUIRED_GENRES for genre in biased)
