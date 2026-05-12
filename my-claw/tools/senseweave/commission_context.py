"""Helpers for deriving score-tree commission context from runtime state."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inner_life.world_model import WorldModel


@dataclass(frozen=True)
class CommissionInputs:
    """Bundle of fields ``commission_piece`` consumes from runtime state."""

    cadence_state: str
    occupancy_state: str
    day_phase: str
    weekly_phase: str
    attention_score: float
    narrative_pressure: float
    song_num: int
    hour: int


def commission_context_from_tracker_plan(
    *,
    tracker_plan: Any,
    world: WorldModel,
) -> tuple[str, str]:
    """Resolve ``(day_phase, weekly_phase)`` preferring tracker plan over world."""
    day_phase = ""
    for source in (tracker_plan, world):
        candidate = str(getattr(source, "day_phase", "") or "").strip()
        if candidate:
            day_phase = candidate
            break
    if not day_phase:
        day_phase = "day"

    weekly_phase = ""
    for source in (tracker_plan, world):
        candidate = str(getattr(source, "weekly_phase", "") or "").strip()
        if candidate:
            weekly_phase = candidate
            break

    return day_phase, weekly_phase


def attention_pressure_from_world(world: Any) -> tuple[float, float]:
    """Return ``(attention_score, narrative_pressure)`` clamped to ``[0.0, 1.0]``."""
    attention = _clamp_unit(getattr(world, "attention_score", 0.0))
    pressure = _clamp_unit(getattr(world, "experimentation_bias", 0.0))
    return attention, pressure


def commission_inputs_from_tracker_plan(
    *,
    tracker_plan: Any,
    world: WorldModel,
    song_num: Any,
    hour: Any,
) -> CommissionInputs:
    """Bundle the full set of inputs ``commission_piece`` needs from runtime state."""
    day_phase, weekly_phase = commission_context_from_tracker_plan(
        tracker_plan=tracker_plan, world=world,
    )
    attention, pressure = attention_pressure_from_world(world)
    cadence = str(getattr(tracker_plan, "cadence_state", "") or "")
    occupancy = str(getattr(tracker_plan, "occupancy_state", "") or "uncertain")
    return CommissionInputs(
        cadence_state=cadence,
        occupancy_state=occupancy,
        day_phase=day_phase,
        weekly_phase=weekly_phase,
        attention_score=attention,
        narrative_pressure=pressure,
        song_num=int(song_num),
        hour=int(hour),
    )


def summarize_commission_context(inputs: CommissionInputs) -> dict[str, object]:
    """Return an operator-readable snapshot of commission inputs."""
    if inputs.attention_score >= 0.66:
        attention_bucket = "high"
    elif inputs.attention_score >= 0.33:
        attention_bucket = "moderate"
    else:
        attention_bucket = "low"

    return {
        "cadence": inputs.cadence_state or "unknown",
        "occupancy": inputs.occupancy_state or "unknown",
        "day_phase": inputs.day_phase or "day",
        "weekly_phase": inputs.weekly_phase or "unscheduled",
        "song_num": inputs.song_num,
        "hour": inputs.hour,
        "attention": attention_bucket,
        "narrative_pressure": round(inputs.narrative_pressure, 3),
    }


def _clamp_unit(value: Any) -> float:
    try:
        coerced = float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0
    if coerced < 0.0:
        return 0.0
    if coerced > 1.0:
        return 1.0
    return round(coerced, 6)
