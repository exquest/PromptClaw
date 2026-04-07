"""Pedals-to-Key — maps sustain/expression pedal MIDI data to harmony changes.

CypherClaw's Akai MAX25 has sustain and expression pedals.  This module
interprets pedal gestures and maps them to harmonic suggestions:

  - Sustain pedal: hold current chord longer
  - Expression pedal (0-127): harmonic tension (low=consonant, high=extensions)
  - Pedal patterns: rapid on-off-on = key modulation, long hold = pedal point

All analysis is stdlib-only.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Expression pedal threshold for suggesting extensions (7ths, 9ths)
_EXTENSION_THRESHOLD = 80

# Rapid pattern: max time between on-off-on events to count as "rapid"
_RAPID_WINDOW_S = 0.6

# Long hold: minimum duration to suggest pedal point
_LONG_HOLD_S = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# pedal_to_harmonic_shift
# ---------------------------------------------------------------------------


def pedal_to_harmonic_shift(sustain: bool, expression: int) -> dict:
    """Map sustain and expression pedal state to harmonic suggestions.

    Parameters
    ----------
    sustain : bool
        Whether the sustain pedal is currently pressed.
    expression : int
        Expression pedal value (0-127).

    Returns
    -------
    dict with keys:
        hold_chord         : bool   — hold current chord longer
        tension            : float  — 0.0 (consonant) to 1.0 (dissonant)
        suggest_extensions : bool   — add 7ths/9ths/etc
    """
    expression = int(_clamp(float(expression), 0, 127))
    tension = expression / 127.0
    suggest_extensions = expression >= _EXTENSION_THRESHOLD

    return {
        "hold_chord": sustain,
        "tension": round(tension, 4),
        "suggest_extensions": suggest_extensions,
    }


# ---------------------------------------------------------------------------
# expression_to_dynamics
# ---------------------------------------------------------------------------


def expression_to_dynamics(value: int) -> dict:
    """Map expression pedal (0-127) to dynamic parameters.

    Parameters
    ----------
    value : int
        Expression pedal value (0-127).

    Returns
    -------
    dict with keys:
        volume_factor : float  — 0.3 (quiet) to 1.0 (full)
        brightness    : float  — 0.0 (dim) to 1.0 (bright)
    """
    clamped = _clamp(float(value), 0, 127)
    normalized = clamped / 127.0

    # Volume: linear from 0.3 to 1.0
    volume_factor = 0.3 + 0.7 * normalized

    # Brightness: linear from 0.0 to 1.0
    brightness = normalized

    return {
        "volume_factor": round(volume_factor, 4),
        "brightness": round(brightness, 4),
    }


# ---------------------------------------------------------------------------
# key_shift_from_pedal_pattern
# ---------------------------------------------------------------------------


def key_shift_from_pedal_pattern(recent_pedal_events: list[tuple[float, bool]]) -> str | None:
    """Detect pedal gesture patterns and suggest harmonic shifts.

    Parameters
    ----------
    recent_pedal_events : list[tuple[float, bool]]
        List of (timestamp_seconds, is_pressed) events, ordered by time.

    Returns
    -------
    str | None
        "modulate"    — rapid on-off-on detected, suggest key change
        "pedal_point" — long sustained hold detected
        None          — no special pattern
    """
    if len(recent_pedal_events) < 2:
        return None

    # --- Check for rapid on-off-on pattern ---
    # Look for True -> False -> True within _RAPID_WINDOW_S
    if len(recent_pedal_events) >= 3:
        for i in range(len(recent_pedal_events) - 2):
            t0, v0 = recent_pedal_events[i]
            t1, v1 = recent_pedal_events[i + 1]
            t2, v2 = recent_pedal_events[i + 2]

            if v0 is True and v1 is False and v2 is True:
                total_time = t2 - t0
                if total_time <= _RAPID_WINDOW_S:
                    return "modulate"

    # --- Check for long hold ---
    # Find the most recent "on" event and check if it's been held long enough.
    # A long hold means the last two events show the pedal has been on
    # for at least _LONG_HOLD_S.
    last_on_time: float | None = None
    for t, v in recent_pedal_events:
        if v:
            if last_on_time is None:
                last_on_time = t
        else:
            # Pedal was released, reset
            last_on_time = None

    if last_on_time is not None:
        # Use the latest event timestamp as "now"
        latest_time = recent_pedal_events[-1][0]
        hold_duration = latest_time - last_on_time
        if hold_duration >= _LONG_HOLD_S:
            return "pedal_point"

    return None
