from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.genre_literacy import (
    REQUIRED_GENRES,
    GenreStrategy,
    all_strategies,
    best_genres_for_phase,
    genre_arc_affinity,
    select_genre,
    strategy_for_genre,
)


def test_all_required_genres_present() -> None:
    strategies = all_strategies()
    assert REQUIRED_GENRES == set(strategies.keys())


def test_no_missing_required_genre_strategy() -> None:
    for genre_id in REQUIRED_GENRES:
        strategy = strategy_for_genre(genre_id)
        assert isinstance(strategy, GenreStrategy)
        assert strategy.genre_id == genre_id
        assert strategy.label


def test_strategy_selection_returns_valid_genre() -> None:
    genre = select_genre(
        arc_phase="Conversation",
        cadence_state="occupied_day",
        groove_identity="pulse",
    )
    assert genre in REQUIRED_GENRES


def test_strategy_selection_penalises_recent_genres() -> None:
    genre_first = select_genre(
        arc_phase="Conversation",
        cadence_state="occupied_day",
        groove_identity="pulse",
    )
    genre_second = select_genre(
        arc_phase="Conversation",
        cadence_state="occupied_day",
        groove_identity="pulse",
        recent_genres=[genre_first] * 5,
    )
    assert genre_second != genre_first


def test_arc_affinity_returns_score_in_range() -> None:
    for genre_id in REQUIRED_GENRES:
        for phase in ("Divination", "Emergence", "Conversation", "Convergence", "Crystallization"):
            score = genre_arc_affinity(genre_id, phase)
            assert 0.0 <= score <= 1.0, f"{genre_id} / {phase} out of range: {score}"


def test_arc_affinity_unknown_phase_returns_zero() -> None:
    score = genre_arc_affinity("ambient_drone_generative", "Nonexistent")
    assert score == 0.0


def test_best_genres_for_phase_returns_ranked_list() -> None:
    ranked = best_genres_for_phase("Conversation", limit=3)
    assert len(ranked) == 3
    assert all(gid in REQUIRED_GENRES for gid, _ in ranked)
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)


def test_best_genres_for_phase_respects_exclude() -> None:
    ranked_all = best_genres_for_phase("Conversation", limit=1)
    top = ranked_all[0][0]
    ranked_excl = best_genres_for_phase("Conversation", limit=1, exclude=[top])
    assert ranked_excl[0][0] != top


def test_every_strategy_has_all_arc_phases() -> None:
    expected_phases = {"Divination", "Emergence", "Conversation", "Convergence", "Crystallization"}
    for genre_id, strategy in all_strategies().items():
        assert set(strategy.arc_affinity.keys()) == expected_phases, (
            f"{genre_id} missing arc phases"
        )


def test_every_strategy_has_all_hint_fields() -> None:
    for genre_id, strategy in all_strategies().items():
        assert strategy.form.preferred_families
        assert strategy.harmony.modal_preferences
        assert strategy.harmony.tension_vocabulary
        assert strategy.rhythm.groove_types
        assert strategy.rhythm.tempo_range[0] <= strategy.rhythm.tempo_range[1]
        assert strategy.synthesis.timbral_character
        assert strategy.arrangement.voice_count_range[0] <= strategy.arrangement.voice_count_range[1]
        assert strategy.mix.reverb_character


def test_sleep_cadence_favours_calm_genres() -> None:
    genre = select_genre(
        arc_phase="Crystallization",
        cadence_state="sleep",
        groove_identity="drift",
    )
    strategy = strategy_for_genre(genre)
    assert strategy.synthesis.texture_density <= 0.6


def test_select_genre_with_away_practice() -> None:
    genre = select_genre(
        arc_phase="Emergence",
        cadence_state="away_practice",
        groove_identity="broken",
    )
    assert genre in REQUIRED_GENRES
