"""Mood — emotional drift based on world state.

Changes are tiny per tick but accumulate over minutes and hours.
A good Theramini duet lifts the mood gradually. An empty house
slowly increases loneliness. Nothing jumps.
"""
from __future__ import annotations

from .inner_state import InnerState
from .world_model import WorldModel


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def evolve_mood(world: WorldModel, inner: InnerState) -> None:
    """Evolve emotional state based on current world. Called every slow tick (30s)."""
    drift = 0.0

    # Positive signals
    if world.theramini_playing:
        drift += 0.02  # music-making is joy
    if world.midi_active:
        drift += 0.015  # someone playing keyboard
    if world.someone_here and inner.mode in ("engaged", "performing"):
        drift += 0.01  # welcome company
    if world.outdoor_light in ("bright_sun", "day"):
        drift += 0.005  # nice weather
    if world.is_playing and world.own_amplitude > 0.01:
        drift += 0.003  # I'm making sound

    # Negative signals
    if world.startle_active:
        drift -= 0.05  # startled (sharp, recovers)
    if len(world.stale_sources) > 4:
        drift -= 0.01  # something wrong with my senses
    if inner.mode == "solitary" and inner.presence_duration_s == 0 and inner.mood > -0.5:
        # Been alone — gentle drift toward loneliness (only if not already sad)
        hours_in_solitary = (world.timestamp - inner.mode_entered_at) / 3600.0
        if hours_in_solitary > 2:
            drift -= 0.005

    # Apply with damping
    inner.mood = _clamp(inner.mood + drift * 0.1, -1.0, 1.0)

    # Curiosity recharges during solitude, depletes during interaction
    if inner.mode == "solitary":
        inner.curiosity = _clamp(inner.curiosity + 0.002, 0.0, 1.0)
    elif inner.mode in ("engaged", "performing"):
        inner.curiosity = _clamp(inner.curiosity - 0.001, 0.0, 1.0)

    # Creative energy recharges during rest phase, depletes during climax
    if inner.arc_phase == "rest":
        inner.creative_energy = _clamp(inner.creative_energy + 0.005, 0.0, 1.0)
    elif inner.arc_phase == "climax":
        inner.creative_energy = _clamp(inner.creative_energy - 0.003, 0.0, 1.0)

    # Social appetite increases when alone, decreases when with people
    if inner.mode == "solitary":
        inner.social_appetite = _clamp(inner.social_appetite + 0.001, 0.0, 1.0)
    elif world.someone_here:
        inner.social_appetite = _clamp(inner.social_appetite - 0.002, 0.0, 1.0)
