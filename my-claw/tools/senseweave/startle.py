"""Startle Detection — sudden-sound detection and startle response.

Detects sudden loud events (bangs, slams, feedback spikes) and manages
CypherClaw's startle response.  The house should never *produce*
startling sounds, and it should react visually when startled by
external sounds.

Key behaviours:
- Detect RMS spikes above a threshold ratio over baseline
- Cooldown prevents re-triggering too fast
- Face reacts with surprise expression
- Repeated rapid startles suggest a feedback loop -> mute output
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Startle detection
# ---------------------------------------------------------------------------


def detect_startle(
    current_rms: float,
    baseline_rms: float,
    threshold_ratio: float = 6.0,
) -> bool:
    """Return True if current_rms exceeds baseline by more than threshold_ratio.

    Handles zero baseline safely (needs absolute current > 0 to trigger).
    """
    if baseline_rms <= 0.0:
        # With no baseline, only trigger on absurdly high absolute level
        # (effectively: can't compute ratio, so don't startle)
        return False
    return current_rms > baseline_rms * threshold_ratio


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


def startle_cooldown(
    last_startle_time: float,
    cooldown_seconds: float = 5.0,
) -> bool:
    """Return True if enough time has passed since last startle (ready for another).

    A last_startle_time of 0.0 means no previous startle, so always ready.
    """
    if last_startle_time == 0.0:
        return True
    elapsed = time.time() - last_startle_time
    return elapsed >= cooldown_seconds


# ---------------------------------------------------------------------------
# StartleState dataclass
# ---------------------------------------------------------------------------


@dataclass
class StartleState:
    """Tracks the current startle state of the installation."""

    startled: bool = False
    startle_count: int = 0
    last_startle_time: float = 0.0
    cooldown_active: bool = False
    # Internal: timestamps of recent startles for mute-detection window
    _recent_startle_times: list[float] = field(default_factory=list, repr=False)


# ---------------------------------------------------------------------------
# State update
# ---------------------------------------------------------------------------


def update_startle(
    state: StartleState,
    current_rms: float,
    baseline_rms: float,
) -> StartleState:
    """Update startle state: detect startle, manage cooldown, increment count.

    Returns a new StartleState (does not mutate the input).
    """
    now = time.time()

    # Check if cooldown has expired
    ready = startle_cooldown(state.last_startle_time)

    # If in cooldown, block new startles
    if not ready:
        return StartleState(
            startled=False,
            startle_count=state.startle_count,
            last_startle_time=state.last_startle_time,
            cooldown_active=True,
            _recent_startle_times=list(state._recent_startle_times),
        )

    # Detect startle
    is_startled = detect_startle(current_rms, baseline_rms)

    if is_startled:
        new_count = state.startle_count + 1
        # Track recent startle times (keep last 30s window)
        recent = [t for t in state._recent_startle_times if now - t < 30.0]
        recent.append(now)
        return StartleState(
            startled=True,
            startle_count=new_count,
            last_startle_time=now,
            cooldown_active=True,
            _recent_startle_times=recent,
        )

    # No startle
    return StartleState(
        startled=False,
        startle_count=state.startle_count,
        last_startle_time=state.last_startle_time,
        cooldown_active=False,
        _recent_startle_times=list(state._recent_startle_times),
    )


# ---------------------------------------------------------------------------
# Face reaction
# ---------------------------------------------------------------------------


def startle_to_face_reaction(state: StartleState) -> dict:
    """Return face reaction dict based on startle state.

    Startled -> surprised expression with wide eyes for 500ms.
    Not startled -> calm default.
    """
    if state.startled:
        return {
            "expression": "surprised",
            "eye_widen": True,
            "duration_ms": 500,
        }
    return {
        "expression": "calm",
        "eye_widen": False,
        "duration_ms": 0,
    }


# ---------------------------------------------------------------------------
# Mute suggestion (feedback loop detection)
# ---------------------------------------------------------------------------


def should_mute_output(state: StartleState) -> bool:
    """If startled 3+ times in 30 seconds, suggest muting output.

    This indicates something is wrong — likely a feedback loop between
    the installation's speakers and its microphones.
    """
    if state.startle_count < 3:
        return False

    now = time.time()
    # Check if the most recent startle is within the 30s window
    if state.last_startle_time == 0.0:
        return False
    if now - state.last_startle_time > 30.0:
        return False

    # Use _recent_startle_times if available for accurate windowing
    if state._recent_startle_times:
        recent = [t for t in state._recent_startle_times if now - t < 30.0]
        return len(recent) >= 3

    # Fallback: trust startle_count if times aren't tracked
    return state.startle_count >= 3
