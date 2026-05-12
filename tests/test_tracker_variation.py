"""Tests for tracker mood freshness and variation helpers."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.tracker_variation import (
    TRACKER_MOOD_MAX_AGE_S,
    TrackerMoodState,
    apply_song_variation,
    choose_rows_per_beat,
    fallback_mood_for_hour,
    resolve_tracker_mood,
)


def test_fallback_mood_for_hour_is_more_active_midday_than_night() -> None:
    midday = fallback_mood_for_hour(13)
    night = fallback_mood_for_hour(2)

    assert midday["energy"] > night["energy"]
    assert midday["arousal"] > night["arousal"]
    assert midday["valence"] >= night["valence"]


def test_resolve_tracker_mood_ignores_stale_organism_state() -> None:
    now = 1_000_000.0
    stale = {
        "timestamp": now - (TRACKER_MOOD_MAX_AGE_S + 10.0),
        "organism_mood": {"energy": 0.1, "valence": 0.3, "arousal": 0.1},
    }

    state = resolve_tracker_mood(
        organism_state=stale,
        room_state={"someone_here": False, "motion": False},
        outdoor_state={},
        inner_state={},
        now=now,
        hour=13,
    )

    assert isinstance(state, TrackerMoodState)
    assert state.source == "fallback"
    assert state.source_fresh is False
    assert state.mood["energy"] > 0.5
    assert state.mood["arousal"] > 0.45


def test_resolve_tracker_mood_uses_fresh_organism_state() -> None:
    now = 1_000_000.0
    fresh = {
        "timestamp": now - 30.0,
        "organism_mood": {"energy": 0.24, "valence": 0.41, "arousal": 0.18},
    }

    state = resolve_tracker_mood(
        organism_state=fresh,
        room_state={"someone_here": False, "motion": False},
        outdoor_state={},
        inner_state={},
        now=now,
        hour=13,
    )

    assert state.source == "organism"
    assert state.source_fresh is True
    assert state.mood == {"energy": 0.24, "valence": 0.41, "arousal": 0.18}


def test_apply_song_variation_adds_repeatable_motion_for_fallback_moods() -> None:
    base = {"energy": 0.4, "valence": 0.54, "arousal": 0.34}

    varied_a = apply_song_variation(
        base,
        song_num=10,
        hour=18,
        occupied_hint=False,
        source_fresh=False,
    )
    varied_b = apply_song_variation(
        base,
        song_num=11,
        hour=18,
        occupied_hint=False,
        source_fresh=False,
    )

    assert varied_a != varied_b
    for mood in (varied_a, varied_b):
        assert 0.0 <= mood["energy"] <= 1.0
        assert 0.0 <= mood["valence"] <= 1.0
        assert 0.0 <= mood["arousal"] <= 1.0


def test_choose_rows_per_beat_varies_with_song_number() -> None:
    mood = {"energy": 0.58, "valence": 0.62, "arousal": 0.55}

    rows = {choose_rows_per_beat(mood, song_num=n) for n in range(1, 7)}

    assert rows.issubset({3, 4, 5, 6})
    assert len(rows) >= 2
