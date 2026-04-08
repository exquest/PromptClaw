"""Narrative Arc — 30-minute cycle with build/rise/climax/resolve/rest.

Each cycle has a shape. The arc position influences decision weights,
music energy, and art generation timing.
"""
from __future__ import annotations

import time

from .inner_state import InnerState

CYCLE_DURATION_S = 1800.0  # 30 minutes

# Phase boundaries within a cycle (fraction of total)
PHASES = [
    ("build",   0.00, 0.25),   # gathering energy
    ("rise",    0.25, 0.50),   # increasing complexity
    ("climax",  0.50, 0.70),   # peak intensity
    ("resolve", 0.70, 0.90),   # unwinding
    ("rest",    0.90, 1.00),   # near silence
]


def update_arc(inner: InnerState) -> bool:
    """Update arc position and phase. Returns True if cycle completed."""
    now = time.time()
    elapsed = now - inner.cycle_started_at

    if elapsed >= CYCLE_DURATION_S:
        return True  # caller should call complete_cycle()

    inner.arc_position = min(1.0, elapsed / CYCLE_DURATION_S)

    # Determine phase
    for name, start, end in PHASES:
        if start <= inner.arc_position < end:
            inner.arc_phase = name
            break

    return False


def complete_cycle(inner: InnerState) -> dict:
    """Complete the current cycle and return a summary."""
    summary = {
        "cycle_id": inner.cycle_id,
        "duration_s": time.time() - inner.cycle_started_at,
        "events_count": len(inner.today_events),
        "mood_at_end": inner.mood,
        "mode_at_end": inner.mode,
    }
    return summary


def start_new_cycle(inner: InnerState) -> None:
    """Begin a fresh 30-minute cycle."""
    inner.cycle_id += 1
    inner.cycle_started_at = time.time()
    inner.arc_position = 0.0
    inner.arc_phase = "build"


def energy_for_phase(phase: str) -> float:
    """Suggested energy level (0-1) for the current arc phase."""
    return {
        "build": 0.3,
        "rise": 0.6,
        "climax": 0.9,
        "resolve": 0.5,
        "rest": 0.1,
    }.get(phase, 0.5)


def action_weight_for_phase(phase: str) -> float:
    """How likely the decision engine should generate actions (0-1)."""
    return {
        "build": 0.3,    # mostly observe
        "rise": 0.6,     # increasingly active
        "climax": 0.9,   # peak expression
        "resolve": 0.4,  # winding down
        "rest": 0.1,     # near silence
    }.get(phase, 0.5)
