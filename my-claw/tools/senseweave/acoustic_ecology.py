"""Installation-aware acoustic ecology policies for SenseWeave.

A pure-function policy layer that translates installation context
(presence, cadence, room activity, dwell time, day phase) into
concrete acoustic constraints: volume ceilings, density limits,
brightness caps, silence windows, source preferences, and keynote
privilege weights.

No I/O, no state files, stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ── Hard ceilings (non-negotiable) ──────────────────────────────

SLEEP_MAX_LOUDNESS_DB = 40.0
SLEEP_MAX_ONSET_DENSITY = 0.5
SLEEP_MAX_CENTROID_HZ = 800.0
SLEEP_DENSITY_CEILING = 0.15
SLEEP_MAX_VOICES = 2

WIND_DOWN_MAX_LOUDNESS_DB = 48.0
WIND_DOWN_MAX_ONSET_DENSITY = 1.5
WIND_DOWN_MAX_CENTROID_HZ = 1200.0
WIND_DOWN_DENSITY_CEILING = 0.35
WIND_DOWN_MAX_VOICES = 3


# ── Policy dataclass ────────────────────────────────────────────


@dataclass(frozen=True)
class AcousticEcologyPolicy:
    """Concrete acoustic ecology constraints for the current moment."""

    ecology_mode: str

    # Hard ceilings
    max_loudness_db: float
    max_onset_density: float
    max_spectral_centroid_hz: float

    # Silence windows
    silence_probability: float
    min_silence_gap_s: float
    max_silence_gap_s: float

    # Source preferences
    preferred_sources: tuple[str, ...]
    keynote_privilege: float
    generated_material_weight: float

    # Density/voice constraints
    max_voices: int
    density_ceiling: float

    # Context
    reasons: tuple[str, ...]


# ── Ecology mode resolution ─────────────────────────────────────


def resolve_ecology_mode(
    *,
    occupancy_state: str,
    cadence_state: str,
    attention_state: str,
    room_activity: str,
) -> str:
    """Map installation context to one of six ecology modes.

    Priority order: sleep > wind_down > performance > away_practice
    > active_day > quiet_occupied.
    """
    if cadence_state == "sleep" or occupancy_state == "likely_asleep":
        return "sleep"
    if cadence_state == "wind_down" and attention_state != "performance":
        return "wind_down"
    if attention_state == "performance":
        return "performance"
    if cadence_state == "away_practice" or occupancy_state == "likely_away":
        return "away_practice"
    if (
        occupancy_state == "occupied_active"
        and room_activity in {"moderate", "active"}
    ):
        return "active_day"
    return "quiet_occupied"


# ── Base policy tables ───────────────────────────────────────────


_BASE_POLICIES: dict[str, dict[str, Any]] = {
    "sleep": {
        "max_loudness_db": SLEEP_MAX_LOUDNESS_DB,
        "max_onset_density": SLEEP_MAX_ONSET_DENSITY,
        "max_spectral_centroid_hz": SLEEP_MAX_CENTROID_HZ,
        "silence_probability": 0.75,
        "min_silence_gap_s": 35.0,
        "max_silence_gap_s": 120.0,
        "preferred_sources": ("room_mic", "garden_mic"),
        "keynote_privilege": 0.85,
        "generated_material_weight": 0.12,
        "max_voices": SLEEP_MAX_VOICES,
        "density_ceiling": SLEEP_DENSITY_CEILING,
    },
    "wind_down": {
        "max_loudness_db": WIND_DOWN_MAX_LOUDNESS_DB,
        "max_onset_density": WIND_DOWN_MAX_ONSET_DENSITY,
        "max_spectral_centroid_hz": WIND_DOWN_MAX_CENTROID_HZ,
        "silence_probability": 0.45,
        "min_silence_gap_s": 20.0,
        "max_silence_gap_s": 90.0,
        "preferred_sources": ("room_mic", "garden_mic", "contact_mic"),
        "keynote_privilege": 0.62,
        "generated_material_weight": 0.35,
        "max_voices": WIND_DOWN_MAX_VOICES,
        "density_ceiling": WIND_DOWN_DENSITY_CEILING,
    },
    "quiet_occupied": {
        "max_loudness_db": 55.0,
        "max_onset_density": 3.0,
        "max_spectral_centroid_hz": 1700.0,
        "silence_probability": 0.25,
        "min_silence_gap_s": 12.0,
        "max_silence_gap_s": 60.0,
        "preferred_sources": ("room_mic", "contact_mic", "theramini_in", "self_bus"),
        "keynote_privilege": 0.38,
        "generated_material_weight": 0.58,
        "max_voices": 4,
        "density_ceiling": 0.60,
    },
    "active_day": {
        "max_loudness_db": 60.0,
        "max_onset_density": 5.0,
        "max_spectral_centroid_hz": 2000.0,
        "silence_probability": 0.12,
        "min_silence_gap_s": 8.0,
        "max_silence_gap_s": 45.0,
        "preferred_sources": (
            "room_mic",
            "contact_mic",
            "theramini_in",
            "self_bus",
            "garden_mic",
        ),
        "keynote_privilege": 0.42,
        "generated_material_weight": 0.55,
        "max_voices": 5,
        "density_ceiling": 0.78,
    },
    "away_practice": {
        "max_loudness_db": 65.0,
        "max_onset_density": 6.0,
        "max_spectral_centroid_hz": 2400.0,
        "silence_probability": 0.08,
        "min_silence_gap_s": 6.0,
        "max_silence_gap_s": 35.0,
        "preferred_sources": (
            "self_bus",
            "room_mic",
            "contact_mic",
            "theramini_in",
            "garden_mic",
        ),
        "keynote_privilege": 0.18,
        "generated_material_weight": 0.82,
        "max_voices": 6,
        "density_ceiling": 0.92,
    },
    "performance": {
        "max_loudness_db": 58.0,
        "max_onset_density": 4.5,
        "max_spectral_centroid_hz": 1900.0,
        "silence_probability": 0.10,
        "min_silence_gap_s": 8.0,
        "max_silence_gap_s": 40.0,
        "preferred_sources": (
            "theramini_in",
            "room_mic",
            "contact_mic",
            "self_bus",
        ),
        "keynote_privilege": 0.30,
        "generated_material_weight": 0.45,
        "max_voices": 5,
        "density_ceiling": 0.72,
    },
}

# ── Day-phase brightness modifiers ──────────────────────────────

_DAY_PHASE_CENTROID_SCALE: dict[str, float] = {
    "late_night": 0.65,
    "pre_dawn": 0.78,
    "morning_activation": 0.92,
    "mid_morning": 1.0,
    "midday": 0.98,
    "afternoon_dip": 0.88,
    "late_afternoon": 1.0,
    "evening_settling": 0.85,
    "pre_sleep": 0.72,
}


# ── Modifier helpers ─────────────────────────────────────────────


def _dwell_modifier(dwell_time_s: float) -> float:
    """Return a multiplier for ceilings based on dwell time.

    Short dwell (<120s) = 0.90 (softened ceilings).
    Settled (120-1800s) = 1.0 (nominal).
    Long dwell (>1800s) = 1.05 (slight relaxation).
    """
    if dwell_time_s < 120.0:
        return 0.90
    if dwell_time_s > 1800.0:
        return 1.05
    return 1.0


def _room_activity_modifier(
    room_activity: str,
) -> tuple[float, float]:
    """Return (keynote_offset, generated_offset) for room activity.

    Active rooms boost keynote privilege and reduce generated weight
    because the room's own soundscape IS the acoustic content.
    """
    if room_activity == "active":
        return 0.15, -0.12
    if room_activity == "moderate":
        return 0.08, -0.06
    return 0.0, 0.0


# ── Main resolver ────────────────────────────────────────────────


def resolve_acoustic_ecology(
    *,
    occupancy_state: str,
    cadence_state: str,
    day_phase: str,
    room_activity: str,
    attention_state: str,
    dwell_time_s: float,
    hour: int,
) -> AcousticEcologyPolicy:
    """Resolve the full acoustic ecology policy for the current moment.

    Consumes presence, cadence, room state, and temporal context
    and returns a frozen policy with hard ceilings, source preferences,
    silence windows, and keynote privilege weights.
    """
    ecology_mode = resolve_ecology_mode(
        occupancy_state=occupancy_state,
        cadence_state=cadence_state,
        attention_state=attention_state,
        room_activity=room_activity,
    )

    base = dict(_BASE_POLICIES[ecology_mode])
    reasons: list[str] = [f"ecology_mode={ecology_mode}"]

    # ── Dwell-time shaping ───────────────────────────────────────
    dwell_mod = _dwell_modifier(dwell_time_s)
    if dwell_mod != 1.0:
        reasons.append(f"dwell_modifier={dwell_mod}")

    # Apply dwell modifier to adjustable parameters (not to sleep/wind-down
    # hard ceilings — those are non-negotiable)
    if ecology_mode not in {"sleep", "wind_down"}:
        base["max_loudness_db"] = round(
            float(base["max_loudness_db"]) * dwell_mod, 1
        )
        base["density_ceiling"] = round(
            _clamp(float(base["density_ceiling"]) * dwell_mod, 0.05, 0.95), 3
        )

    # ── Room activity shaping ────────────────────────────────────
    keynote_offset, gen_offset = _room_activity_modifier(room_activity)
    if keynote_offset != 0.0:
        reasons.append(f"room_activity={room_activity}")
        base["keynote_privilege"] = round(
            _clamp(float(base["keynote_privilege"]) + keynote_offset, 0.0, 1.0), 3
        )
        base["generated_material_weight"] = round(
            _clamp(float(base["generated_material_weight"]) + gen_offset, 0.0, 1.0), 3
        )

    # ── Day-phase brightness shaping ─────────────────────────────
    centroid_scale = _DAY_PHASE_CENTROID_SCALE.get(day_phase, 1.0)
    if centroid_scale != 1.0:
        reasons.append(f"day_phase_centroid_scale={centroid_scale}")
        base["max_spectral_centroid_hz"] = round(
            float(base["max_spectral_centroid_hz"]) * centroid_scale, 1
        )

    # ── Enforce hard ceilings for sleep/wind_down ────────────────
    # These must NEVER be exceeded regardless of modifiers.
    if ecology_mode == "sleep":
        base["max_loudness_db"] = min(
            float(base["max_loudness_db"]), SLEEP_MAX_LOUDNESS_DB
        )
        base["max_onset_density"] = min(
            float(base["max_onset_density"]), SLEEP_MAX_ONSET_DENSITY
        )
        base["max_spectral_centroid_hz"] = min(
            float(base["max_spectral_centroid_hz"]), SLEEP_MAX_CENTROID_HZ
        )
        base["density_ceiling"] = min(
            float(base["density_ceiling"]), SLEEP_DENSITY_CEILING
        )
        base["max_voices"] = min(int(base["max_voices"]), SLEEP_MAX_VOICES)
    elif ecology_mode == "wind_down":
        base["max_loudness_db"] = min(
            float(base["max_loudness_db"]), WIND_DOWN_MAX_LOUDNESS_DB
        )
        base["max_onset_density"] = min(
            float(base["max_onset_density"]), WIND_DOWN_MAX_ONSET_DENSITY
        )
        base["max_spectral_centroid_hz"] = min(
            float(base["max_spectral_centroid_hz"]), WIND_DOWN_MAX_CENTROID_HZ
        )
        base["density_ceiling"] = min(
            float(base["density_ceiling"]), WIND_DOWN_DENSITY_CEILING
        )
        base["max_voices"] = min(int(base["max_voices"]), WIND_DOWN_MAX_VOICES)

    return AcousticEcologyPolicy(
        ecology_mode=ecology_mode,
        max_loudness_db=round(float(base["max_loudness_db"]), 1),
        max_onset_density=round(float(base["max_onset_density"]), 2),
        max_spectral_centroid_hz=round(float(base["max_spectral_centroid_hz"]), 1),
        silence_probability=round(float(base["silence_probability"]), 3),
        min_silence_gap_s=round(float(base["min_silence_gap_s"]), 1),
        max_silence_gap_s=round(float(base["max_silence_gap_s"]), 1),
        preferred_sources=tuple(base["preferred_sources"]),  # type: ignore[arg-type]
        keynote_privilege=round(float(base["keynote_privilege"]), 3),
        generated_material_weight=round(float(base["generated_material_weight"]), 3),
        max_voices=int(base["max_voices"]),
        density_ceiling=round(float(base["density_ceiling"]), 3),
        reasons=tuple(reasons),
    )
