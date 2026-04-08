"""Presence — mode state machine for solitary/aware/engaged/performing.

Transitions based on room presence, instrument activity, and duration.
"""
from __future__ import annotations

import time

from .inner_state import InnerState
from .world_model import WorldModel


# Transition thresholds (seconds)
AWARE_TO_ENGAGED_S = 30.0
ENGAGED_TO_AWARE_S = 120.0
AWARE_TO_SOLITARY_S = 60.0
PERFORMING_EXIT_S = 60.0


def update_presence(world: WorldModel, inner: InnerState) -> str | None:
    """Update mode based on world state. Returns event string if mode changed."""
    now = time.time()
    old_mode = inner.mode
    in_mode_s = now - inner.mode_entered_at

    instrument_active = world.theramini_playing or world.midi_active

    if inner.mode == "solitary":
        if world.someone_here:
            inner.mode = "aware"
            inner.mode_entered_at = now
            inner.presence_duration_s = 0.0

    elif inner.mode == "aware":
        if not world.someone_here and in_mode_s > AWARE_TO_SOLITARY_S:
            inner.mode = "solitary"
            inner.mode_entered_at = now
        elif instrument_active:
            inner.mode = "performing"
            inner.mode_entered_at = now
        elif world.someone_here and in_mode_s > AWARE_TO_ENGAGED_S:
            inner.mode = "engaged"
            inner.mode_entered_at = now

    elif inner.mode == "engaged":
        if instrument_active:
            inner.mode = "performing"
            inner.mode_entered_at = now
        elif not world.someone_here and in_mode_s > ENGAGED_TO_AWARE_S:
            inner.mode = "aware"
            inner.mode_entered_at = now

    elif inner.mode == "performing":
        if not instrument_active and in_mode_s > PERFORMING_EXIT_S:
            inner.mode = "engaged" if world.someone_here else "aware"
            inner.mode_entered_at = now

    # Track presence duration
    if world.someone_here:
        inner.presence_duration_s += 2.0  # fast tick interval
    else:
        inner.presence_duration_s = 0.0

    # Return event if mode changed
    if inner.mode != old_mode:
        return f"{old_mode} -> {inner.mode}"
    return None
