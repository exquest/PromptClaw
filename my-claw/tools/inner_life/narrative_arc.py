"""Narrative Arc — 30-minute cycle with build/rise/climax/resolve/rest.

Each cycle has a shape. The arc position influences decision weights,
music energy, and art generation timing.
"""
from __future__ import annotations

import time
from typing import Any

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

_PHASE_LABELS = {
    "build":   "gathering",
    "rise":    "rising",
    "climax":  "peaking",
    "resolve": "resolving",
    "rest":    "resting",
}


def phase_at(position: float) -> str:
    """Resolve the arc phase name for a (clamped) position in [0, 1]."""
    clamped = max(0.0, min(1.0, position))
    for name, start, end in PHASES:
        if start <= clamped < end:
            return name
    if clamped >= PHASES[-1][1]:
        return PHASES[-1][0]
    return "build"


def update_arc(inner: InnerState) -> bool:
    """Update arc position and phase. Returns True if cycle completed."""
    now = time.time()
    elapsed = now - inner.cycle_started_at

    if elapsed >= CYCLE_DURATION_S:
        return True  # caller should call complete_cycle()

    inner.arc_position = min(1.0, elapsed / CYCLE_DURATION_S)

    for name, start, end in PHASES:
        if start <= inner.arc_position < end:
            inner.arc_phase = name
            break

    return False


def phase_progress(inner: InnerState) -> dict[str, Any]:
    """Return position, phase, and within-phase progress (0..1)."""
    position = max(0.0, min(1.0, inner.arc_position))
    phase = phase_at(position)
    fraction = 0.0
    for name, start, end in PHASES:
        if name == phase:
            span = end - start
            if span > 0:
                fraction = max(0.0, min(1.0, (position - start) / span))
            break
    return {
        "position": position,
        "phase": phase,
        "phase_progress": fraction,
        "cycle_progress": position,
    }


def complete_cycle(inner: InnerState) -> dict[str, Any]:
    """Complete the current cycle and return an aggregate summary."""
    event_type_counts: dict[str, int] = {}
    for event in inner.today_events:
        bucket = event.get("type") if isinstance(event, dict) else None
        key = bucket if isinstance(bucket, str) and bucket else "unknown"
        event_type_counts[key] = event_type_counts.get(key, 0) + 1

    return {
        "cycle_id": inner.cycle_id,
        "duration_s": time.time() - inner.cycle_started_at,
        "events_count": len(inner.today_events),
        "event_type_counts": event_type_counts,
        "opinions_count": len(inner.opinions_formed),
        "final_phase": inner.arc_phase,
        "final_position": inner.arc_position,
        "mood_at_end": inner.mood,
        "mode_at_end": inner.mode,
    }


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


def phase_profile(phase: str) -> dict[str, Any]:
    """Combine energy, action weight, and a stable label for a phase."""
    label = _PHASE_LABELS.get(phase, "unknown")
    if label == "unknown":
        return {
            "phase": phase,
            "energy": 0.5,
            "action_weight": 0.5,
            "label": "unknown",
        }
    return {
        "phase": phase,
        "energy": energy_for_phase(phase),
        "action_weight": action_weight_for_phase(phase),
        "label": label,
    }


def arc_summary(inner: InnerState) -> dict[str, Any]:
    """Compose phase_progress and phase_profile into a diagnostic dict."""
    progress = phase_progress(inner)
    profile = phase_profile(progress["phase"])
    summary = dict(progress)
    summary["energy"] = profile["energy"]
    summary["action_weight"] = profile["action_weight"]
    summary["label"] = profile["label"]
    return summary
