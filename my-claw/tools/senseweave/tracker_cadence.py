"""Tracker cadence planning for CypherClaw's family-based solo songs."""
from __future__ import annotations

from dataclasses import dataclass

from inner_life.world_model import WorldModel

from .generative_scores import Note, Phrase, Score, generate_countermelody


@dataclass(frozen=True)
class TrackerPlan:
    """Resolved cadence and family plan for one tracker song."""

    occupancy_state: str
    cadence_state: str
    family: str
    progression_profile: str
    source: str
    energy_bias: float
    valence_bias: float
    arousal_bias: float


_DYNAMIC_ORDER = ("pp", "p", "mp", "mf", "f", "ff")


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _shift_dynamic(dynamic: str, delta: int) -> str:
    try:
        idx = _DYNAMIC_ORDER.index(dynamic)
    except ValueError:
        idx = _DYNAMIC_ORDER.index("mf")
    return _DYNAMIC_ORDER[max(0, min(len(_DYNAMIC_ORDER) - 1, idx + delta))]


def _presence_sources_fresh(world: WorldModel) -> bool:
    relevant = {"room_presence", "observer", "room_activity", "theramini", "midi"}
    return len(relevant.intersection(world.stale_sources)) < len(relevant)


def _has_canonical_cadence(world: WorldModel) -> bool:
    return bool(getattr(world, "cadence_state", ""))


_WEEKLY_ROTATION_OFFSET = {
    "monday_gentle": 0,
    "core_weekday": 1,
    "friday_lift": 1,
    "weekend_late": 3,
    "sunday_settle": 4,
}

_DAY_PHASE_FAMILY_PALETTES: dict[str, tuple[str, ...]] = {
    "pre_dawn": ("nocturne", "ember", "drift"),
    "morning_activation": ("ember", "bloom", "drift", "ember"),
    "mid_morning": ("bloom", "ember", "pulse", "drift"),
    "midday": ("bloom", "drift", "pulse", "ember"),
    "afternoon_dip": ("drift", "bloom", "ember", "drift"),
    "late_afternoon": ("pulse", "bloom", "drift", "pulse"),
    "evening_settling": ("drift", "bloom", "ember", "drift"),
    "pre_sleep": ("drift", "nocturne", "ember", "drift"),
}


def _rotating_choice(choices: tuple[str, ...], *, song_num: int, weekly_phase: str) -> str:
    if not choices:
        return "bloom"
    offset = _WEEKLY_ROTATION_OFFSET.get(weekly_phase, 0)
    return choices[(song_num - 1 + offset) % len(choices)]


def _family_for_context(
    world: WorldModel,
    *,
    cadence: str,
    occupancy: str,
    song_num: int,
    hour: int,
) -> str:
    weekly_phase = getattr(world, "weekly_phase", "")
    day_phase = getattr(world, "day_phase", "")

    if cadence == "sleep":
        return "nocturne"
    if cadence == "wake_ramp":
        return _rotating_choice(("ember", "ember", "drift", "bloom"), song_num=song_num, weekly_phase=weekly_phase)
    if cadence == "wind_down":
        return _rotating_choice(("drift", "nocturne", "ember", "drift"), song_num=song_num, weekly_phase=weekly_phase)
    if cadence == "away_practice":
        return _rotating_choice(("forge", "forge", "pulse", "forge", "drift"), song_num=song_num, weekly_phase=weekly_phase)
    if getattr(world, "attention_state", "") == "performance":
        return "pulse"

    palette = _DAY_PHASE_FAMILY_PALETTES.get(day_phase, ("bloom", "pulse", "drift", "ember"))
    if occupancy == "occupied_active":
        palette = ("pulse", "bloom", "pulse", "ember", "drift")
    if weekly_phase == "monday_gentle":
        palette = tuple("ember" if family == "pulse" else family for family in palette)
    elif weekly_phase == "friday_lift" and day_phase in {"late_afternoon", "evening_settling"}:
        palette = ("pulse", "bloom", "pulse", "pulse", "drift")
    elif weekly_phase == "sunday_settle" and day_phase in {"afternoon_dip", "evening_settling", "pre_sleep"}:
        palette = ("drift", "ember", "nocturne", "drift")
    elif weekly_phase == "weekend_late" and hour >= 18:
        palette = ("pulse", "bloom", "drift", "pulse")
    return _rotating_choice(palette, song_num=song_num, weekly_phase=weekly_phase)


def _progression_profile_for_context(world: WorldModel, *, cadence: str, family: str) -> str:
    weekly_phase = getattr(world, "weekly_phase", "")
    day_phase = getattr(world, "day_phase", "")

    if cadence == "sleep":
        return "stillness"
    if cadence == "wind_down":
        return "settling"
    if cadence == "away_practice":
        return "experiment"
    if weekly_phase == "friday_lift" and day_phase in {"late_afternoon", "evening_settling"}:
        return "lift"
    if weekly_phase == "sunday_settle" and day_phase in {"afternoon_dip", "evening_settling", "pre_sleep"}:
        return "settling"
    if day_phase in {"pre_dawn", "morning_activation"}:
        return "awakening"
    if day_phase in {"mid_morning", "midday"}:
        return "open_day"
    if day_phase == "late_afternoon":
        return "lift"
    if day_phase in {"afternoon_dip", "evening_settling"}:
        return "shadow_play"
    return {
        "nocturne": "stillness",
        "ember": "awakening",
        "drift": "shadow_play",
        "bloom": "open_day",
        "pulse": "procession",
        "forge": "experiment",
    }.get(family, "open_day")


def _occupancy_state(world: WorldModel, hour: int) -> str:
    if getattr(world, "occupancy_state", "") not in {"", "uncertain"}:
        return world.occupancy_state
    interaction = world.theramini_playing or world.midi_active
    activity = world.room_activity in {"moderate", "active"} or world.recent_transient
    fresh = _presence_sources_fresh(world)

    if interaction or (world.someone_here and activity):
        return "occupied_active"
    if world.someone_here:
        return "occupied_quiet"
    if fresh and not world.someone_here and not activity:
        if 0 <= hour < 6:
            return "likely_asleep"
        if 8 <= hour < 22:
            return "likely_away"
    return "uncertain"


def resolve_tracker_plan(
    world: WorldModel,
    *,
    song_num: int,
    hour: int,
) -> TrackerPlan:
    """Resolve occupancy, cadence, and family from the current world."""

    occupancy = _occupancy_state(world, hour)
    interaction = world.theramini_playing or world.midi_active
    activity = world.room_activity in {"moderate", "active"} or world.recent_transient
    source = "world" if _presence_sources_fresh(world) else "time_of_day"

    if _has_canonical_cadence(world):
        cadence = world.cadence_state
        source = "cadence"
    elif 0 <= hour < 6:
        cadence = "wake_ramp" if interaction else "sleep"
    elif 6 <= hour < 9 and (interaction or world.someone_here or activity):
        cadence = "wake_ramp"
    elif hour >= 22:
        cadence = "wind_down"
    elif occupancy == "likely_away":
        cadence = "away_practice"
    else:
        cadence = "occupied_day"

    family = _family_for_context(
        world,
        cadence=cadence,
        occupancy=occupancy,
        song_num=song_num,
        hour=hour,
    )
    progression_profile = _progression_profile_for_context(world, cadence=cadence, family=family)

    biases = {
        "nocturne": (-0.18, -0.02, -0.18),
        "ember": (0.04, 0.05, 0.04),
        "drift": (-0.03, 0.02, -0.02),
        "bloom": (0.1, 0.08, 0.06),
        "pulse": (0.18, 0.04, 0.2),
        "forge": (0.24, -0.02, 0.28),
    }[family]

    return TrackerPlan(
        occupancy_state=occupancy,
        cadence_state=cadence,
        family=family,
        progression_profile=progression_profile,
        source=source,
        energy_bias=biases[0],
        valence_bias=biases[1],
        arousal_bias=biases[2],
    )


def apply_tracker_plan_to_mood(
    mood: dict[str, float],
    plan: TrackerPlan,
) -> dict[str, float]:
    """Bias a resolved mood into the chosen cadence family."""

    return {
        "energy": round(_clamp(mood.get("energy", 0.5) + plan.energy_bias), 3),
        "valence": round(_clamp(mood.get("valence", 0.5) + plan.valence_bias), 3),
        "arousal": round(_clamp(mood.get("arousal", 0.5) + plan.arousal_bias), 3),
    }


def _copy_phrase(
    phrase: Phrase,
    *,
    duration_scale: float = 1.0,
    accent_mode: str = "keep",
    dynamic_shift: int = 0,
    voice: str | None = None,
) -> Phrase:
    notes: list[Note] = []
    for index, note in enumerate(phrase.notes):
        accent = note.accent
        if accent_mode == "none":
            accent = False
        elif accent_mode == "pulse":
            accent = (index % 2 == 0)
        elif accent_mode == "head":
            accent = index == 0
        notes.append(
            Note(
                scale_degree=note.scale_degree,
                duration_beats=round(max(0.25, note.duration_beats * duration_scale), 2),
                accent=accent,
            )
        )
    return Phrase(
        notes=notes,
        voice=voice or phrase.voice,
        dynamic=_shift_dynamic(phrase.dynamic, dynamic_shift),
        role=phrase.role,
    )


def _ensure_color_phrase(score: Score, *, long: bool) -> Phrase:
    melody = next((phrase for phrase in score.phrases if phrase.role == "melody"), score.phrases[0])
    degrees = [note.scale_degree for note in melody.notes[:3]] or [1, 3, 5]
    duration = 3.0 if long else 2.0
    return Phrase(
        notes=[Note(degree, duration, False) for degree in degrees[:2]],
        voice="pad",
        dynamic="pp" if long else "p",
        role="color",
    )


def _ensure_counter_phrase(score: Score) -> Phrase:
    melody = next((phrase for phrase in score.phrases if phrase.role == "melody"), score.phrases[0])
    return Phrase(
        notes=generate_countermelody(melody).notes,
        voice="bell",
        dynamic="mp",
        role="counter",
    )


def shape_score_for_family(
    score: Score,
    *,
    family: str,
    cadence_state: str,
    song_num: int,
) -> Score:
    """Reshape a score so each cadence family feels materially distinct."""

    phrases = list(score.phrases)

    if family == "nocturne":
        filtered = [phrase for phrase in phrases if phrase.role != "counter"]
        shaped = [
            _copy_phrase(
                phrase,
                duration_scale=1.4 if phrase.role != "color" else 1.8,
                accent_mode="none",
                dynamic_shift=-2,
                voice="pad" if phrase.role in {"melody", "color"} else phrase.voice,
            )
            for phrase in filtered
        ]
        if not any(phrase.role == "color" for phrase in shaped):
            shaped.append(_ensure_color_phrase(score, long=True))
        tempo = score.tempo_bpm * 0.84
    elif family == "ember":
        shaped = [
            _copy_phrase(
                phrase,
                duration_scale=1.1 if phrase.role != "counter" else 0.95,
                accent_mode="head",
                dynamic_shift=-1,
            )
            for phrase in phrases
        ]
        if not any(phrase.role == "color" for phrase in shaped):
            shaped.append(_ensure_color_phrase(score, long=False))
        tempo = score.tempo_bpm * (0.94 if cadence_state == "wake_ramp" else 0.98)
    elif family == "bloom":
        shaped = [
            _copy_phrase(
                phrase,
                duration_scale=0.95 if phrase.role == "melody" else 1.0,
                accent_mode="keep",
                dynamic_shift=1 if phrase.role == "melody" else 0,
            )
            for phrase in phrases
        ]
        if not any(phrase.role == "color" for phrase in shaped):
            shaped.append(_ensure_color_phrase(score, long=False))
        if not any(phrase.role == "counter" for phrase in shaped) and song_num % 2 == 0:
            shaped.append(_ensure_counter_phrase(score))
        tempo = score.tempo_bpm * 1.04
    elif family == "pulse":
        shaped = [
            _copy_phrase(
                phrase,
                duration_scale=0.78 if phrase.role in {"melody", "counter"} else 0.9,
                accent_mode="pulse" if phrase.role in {"bass", "melody"} else "keep",
                dynamic_shift=1 if phrase.role in {"bass", "melody"} else 0,
            )
            for phrase in phrases
        ]
        if not any(phrase.role == "counter" for phrase in shaped):
            shaped.append(_ensure_counter_phrase(score))
        tempo = score.tempo_bpm * 1.14
    elif family == "forge":
        shaped = [
            _copy_phrase(
                phrase,
                duration_scale=0.72 if phrase.role == "melody" else 0.84,
                accent_mode="pulse" if phrase.role != "color" else "head",
                dynamic_shift=1,
            )
            for phrase in phrases
        ]
        if not any(phrase.role == "counter" for phrase in shaped):
            shaped.append(_ensure_counter_phrase(score))
        if not any(phrase.role == "color" for phrase in shaped):
            shaped.append(_ensure_color_phrase(score, long=False))
        tempo = score.tempo_bpm * 1.22
    else:
        shaped = [
            _copy_phrase(
                phrase,
                duration_scale=1.08 if phrase.role != "counter" else 0.98,
                accent_mode="head" if phrase.role == "melody" else "keep",
            )
            for phrase in phrases
        ]
        if not any(phrase.role == "color" for phrase in shaped):
            shaped.append(_ensure_color_phrase(score, long=False))
        tempo = score.tempo_bpm * 0.96

    return Score(
        phrases=shaped,
        key=score.key,
        tempo_bpm=round(max(40.0, tempo), 1),
        mood=f"{score.mood}:{family}",
        created_at=score.created_at,
        metadata=dict(score.metadata),
    )


def constrain_score_to_cadence(score: Score, world: WorldModel) -> Score:
    """Clamp score tempo into the canonical cadence envelope when present."""
    bpm_range = getattr(world, "bpm_range", (0.0, 0.0))
    if not bpm_range or len(bpm_range) != 2:
        return score
    lo, hi = float(bpm_range[0]), float(bpm_range[1])
    if lo <= 0.0 or hi <= 0.0 or lo > hi:
        return score
    tempo = round(max(lo, min(hi, score.tempo_bpm)), 1)
    return Score(
        phrases=list(score.phrases),
        key=score.key,
        tempo_bpm=tempo,
        mood=score.mood,
        created_at=score.created_at,
        metadata=dict(score.metadata),
    )
