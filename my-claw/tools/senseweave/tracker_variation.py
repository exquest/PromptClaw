"""Helpers for tracker mood freshness and bounded per-song variation."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Mapping


TRACKER_MOOD_MAX_AGE_S = 180.0


@dataclass(frozen=True)
class TrackerMoodState:
    """Resolved tracker mood plus provenance."""

    mood: dict[str, float]
    source: str
    source_fresh: bool


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _round_mood(mood: Mapping[str, float]) -> dict[str, float]:
    return {name: round(_clamp(float(value)), 3) for name, value in mood.items()}


def _timestamp_is_fresh(
    timestamp: object,
    *,
    now: float,
    max_age_s: float = TRACKER_MOOD_MAX_AGE_S,
) -> bool:
    if not isinstance(timestamp, (int, float)):
        return False
    age = now - float(timestamp)
    return 0.0 <= age <= max_age_s


def fallback_mood_for_hour(hour: int) -> dict[str, float]:
    """Return a time-of-day fallback mood when live fusion data is unavailable."""

    hour = hour % 24
    if 0 <= hour < 5:
        return {"energy": 0.16, "valence": 0.3, "arousal": 0.14}
    if 5 <= hour < 8:
        return {"energy": 0.28, "valence": 0.48, "arousal": 0.25}
    if 8 <= hour < 12:
        return {"energy": 0.46, "valence": 0.58, "arousal": 0.42}
    if 12 <= hour < 17:
        return {"energy": 0.64, "valence": 0.62, "arousal": 0.58}
    if 17 <= hour < 21:
        return {"energy": 0.4, "valence": 0.54, "arousal": 0.34}
    return {"energy": 0.22, "valence": 0.38, "arousal": 0.2}


def resolve_tracker_mood(
    *,
    organism_state: Mapping[str, object] | None,
    room_state: Mapping[str, object] | None,
    outdoor_state: Mapping[str, object] | None,
    inner_state: Mapping[str, object] | None,
    now: float | None = None,
    hour: int | None = None,
) -> TrackerMoodState:
    """Resolve the current tracker mood with stale-state protection."""

    now = time.time() if now is None else now
    hour = time.localtime(now).tm_hour if hour is None else hour
    mood = fallback_mood_for_hour(hour)
    source = "fallback"
    source_fresh = False

    organism_mood: Mapping[str, object] | None = None
    if organism_state is not None and _timestamp_is_fresh(organism_state.get("timestamp"), now=now):
        candidate = organism_state.get("organism_mood")
        if isinstance(candidate, Mapping):
            organism_mood = candidate

    if organism_mood is not None:
        for key in ("energy", "valence", "arousal"):
            value = organism_mood.get(key)
            if isinstance(value, (int, float)):
                mood[key] = float(value)
        source = "organism"
        source_fresh = True

    room_state = room_state or {}
    if room_state.get("someone_here"):
        mood["arousal"] += 0.12
        mood["valence"] += 0.04
    if room_state.get("motion"):
        mood["energy"] += 0.18
        mood["arousal"] += 0.08

    outdoor_state = outdoor_state or {}
    brightness = outdoor_state.get("brightness")
    if isinstance(brightness, (int, float)):
        brightness_f = _clamp(float(brightness))
        mood["valence"] = (mood["valence"] * 0.75) + (brightness_f * 0.25)
        if brightness_f > 0.65:
            mood["energy"] += 0.05

    inner_state = inner_state or {}
    if inner_state.get("suggest_silence"):
        mood["energy"] *= 0.75
        mood["arousal"] *= 0.78

    return TrackerMoodState(
        mood=_round_mood(mood),
        source=source,
        source_fresh=source_fresh,
    )


def apply_song_variation(
    mood: Mapping[str, float],
    *,
    song_num: int,
    hour: int,
    occupied_hint: bool,
    source_fresh: bool,
) -> dict[str, float]:
    """Add repeatable per-song motion so calm periods still produce variety."""

    energy = float(mood.get("energy", 0.5))
    valence = float(mood.get("valence", 0.5))
    arousal = float(mood.get("arousal", 0.5))

    phase = (song_num * 1.371) + (hour * 0.219)
    scale = 0.06 if source_fresh else 0.11
    energy += math.sin(phase) * scale + math.cos(phase * 0.41) * (scale * 0.45)
    arousal += math.cos(phase * 0.79) * scale + math.sin(phase * 0.33) * (scale * 0.35)
    valence += math.sin(phase * 0.57) * (scale * 0.7)

    if occupied_hint:
        energy += 0.05
        arousal += 0.04
        valence += 0.02

    if not source_fresh and 8 <= hour < 22 and energy < 0.42:
        energy_floor = (0.32, 0.38, 0.46, 0.41)[song_num % 4]
        arousal_floor = (0.28, 0.34, 0.4, 0.31)[song_num % 4]
        energy = max(energy, energy_floor)
        arousal = max(arousal, arousal_floor)

    return _round_mood(
        {
            "energy": energy,
            "valence": valence,
            "arousal": arousal,
        }
    )


def choose_rows_per_beat(mood: Mapping[str, float], *, song_num: int) -> int:
    """Pick a small set of rhythmic grids to keep the tracker from feeling static."""

    energy = float(mood.get("energy", 0.5))
    arousal = float(mood.get("arousal", 0.5))

    if energy < 0.22 and arousal < 0.22:
        return 4
    if energy < 0.45:
        choices = (4, 5)
    elif energy < 0.7:
        choices = (3, 4, 5)
    else:
        choices = (4, 5, 6)
    return choices[song_num % len(choices)]
