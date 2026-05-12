"""Canonical presence fusion for CypherClaw.

This engine reads the existing sensor state files and publishes a higher-level
presence state for the rest of the system to trust.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any


ROOM_PRESENCE_STATE = "/tmp/room_presence.json"
OBSERVER_STATE = "/tmp/observer_state.json"
ROOM_ACTIVITY_STATE = "/tmp/room_activity.json"
ROOM_SPEECH_STATE = "/tmp/room_speech.json"
THERAMINI_STATE = "/tmp/theramini_state.json"
MIDI_STATE = "/tmp/midi_keyboard_state.json"
INPUT_LEVELS_STATE = "/tmp/input_levels.json"
DEFAULT_OUTPUT = "/tmp/presence_state.json"

STALE_S = 30.0
ACTIVE_HOLD_S = 120.0
AWAY_TIMEOUT_S = 300.0
WIND_DOWN_HOME_HOLD_S = 1_800.0
SLEEP_SETTLE_S = 1_200.0
SLEEP_HOME_MEMORY_S = 6 * 3_600.0


def read_state(path: str, max_age_s: float | None = STALE_S) -> dict[str, Any]:
    """Read a JSON state file, optionally enforcing freshness."""
    try:
        if not os.path.isfile(path):
            return {}
        if max_age_s is not None:
            age = time.time() - os.path.getmtime(path)
            if age > max_age_s:
                return {}
        with open(path, "r") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def gather_presence_inputs() -> dict[str, dict[str, Any]]:
    """Read all sensor inputs relevant to presence."""
    room_presence = read_state(ROOM_PRESENCE_STATE)
    observer = read_state(OBSERVER_STATE)
    room_activity = read_state(ROOM_ACTIVITY_STATE)
    room_speech = read_state(ROOM_SPEECH_STATE)
    theramini = read_state(THERAMINI_STATE)
    midi = read_state(MIDI_STATE)
    input_levels = read_state(INPUT_LEVELS_STATE)
    return {
        "room_presence": {**room_presence, "_fresh": bool(room_presence)},
        "observer": {**observer, "_fresh": bool(observer)},
        "room_activity": {**room_activity, "_fresh": bool(room_activity)},
        "room_speech": {**room_speech, "_fresh": bool(room_speech)},
        "theramini": {**theramini, "_fresh": bool(theramini)},
        "midi": {**midi, "_fresh": bool(midi)},
        "input_levels": {**input_levels, "_fresh": bool(input_levels)},
        "direct_interaction": {},
    }


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _bool_score(value: bool, weight: float) -> float:
    return weight if value else 0.0


def _activity_active(room_activity: dict[str, Any]) -> bool:
    return room_activity.get("activity_level") in {"moderate", "active"} or bool(
        room_activity.get("recent_transient")
    )


def _source_fresh(source: dict[str, Any]) -> bool:
    if not source.get("_fresh", True):
        return False
    if source.get("error"):
        return False
    return True


def _wind_down_window(hour: int) -> bool:
    return hour >= 22 or hour < 6


def resolve_presence_state(
    inputs: dict[str, dict[str, Any]],
    *,
    previous_state: dict[str, Any] | None = None,
    now: float | None = None,
    hour: int | None = None,
) -> dict[str, Any]:
    """Resolve the canonical occupancy and attention state."""
    previous_state = previous_state or {}
    now = time.time() if now is None else now
    hour = time.localtime(now).tm_hour if hour is None else hour

    room_presence = inputs.get("room_presence", {})
    observer = inputs.get("observer", {})
    room_activity = inputs.get("room_activity", {})
    room_speech = inputs.get("room_speech", {})
    theramini = inputs.get("theramini", {})
    midi = inputs.get("midi", {})
    input_levels = inputs.get("input_levels", {})
    direct_interaction_state = inputs.get("direct_interaction", {})

    room_motion = bool(room_presence.get("motion") or room_presence.get("someone_here"))
    observer_motion = bool(observer.get("ok", True) and observer.get("someone_here"))
    speech = bool(room_speech.get("speech_detected"))
    room_activity_level = room_activity.get("activity_level", "quiet")
    room_activity_active = _activity_active(room_activity)
    instrument_active = bool(theramini.get("is_playing") or midi.get("playing"))
    direct_interaction = bool(direct_interaction_state.get("active")) or instrument_active
    contact_rms = float(input_levels.get("contact_rms", 0.0) or 0.0)
    window_rms = float(input_levels.get("window_rms", 0.0) or 0.0)
    input_spike = max(contact_rms, window_rms) >= 0.05
    fresh_sources = {
        "room_presence": _source_fresh(room_presence),
        "observer": _source_fresh(observer),
        "room_activity": _source_fresh(room_activity),
        "room_speech": _source_fresh(room_speech),
        "theramini": _source_fresh(theramini),
        "midi": _source_fresh(midi),
        "input_levels": _source_fresh(input_levels),
    }
    presence_sources_fresh = any(fresh_sources.values())

    reliable_now = (
        speech
        or direct_interaction
        or (room_motion and room_activity_active)
        or (observer_motion and room_activity_active)
        or (input_spike and (room_motion or observer_motion))
    )

    last_reliable = float(previous_state.get("last_reliable_presence_at", 0.0) or 0.0)
    if reliable_now:
        last_reliable = now

    last_direct = float(previous_state.get("last_direct_interaction_at", 0.0) or 0.0)
    if direct_interaction:
        last_direct = now

    if last_reliable > 0.0:
        seconds_since_reliable = max(0.0, now - last_reliable)
    else:
        seconds_since_reliable = float("inf")

    had_recent_home_presence = (
        previous_state.get("occupancy_state") in {"occupied_active", "occupied_quiet", "likely_asleep"}
        or seconds_since_reliable <= SLEEP_HOME_MEMORY_S
    )
    quiet_now = not any(
        (
            speech,
            direct_interaction,
            room_motion,
            observer_motion,
            room_activity_active,
            input_spike,
        )
    )
    sleep_window = 0 <= hour < 6
    wind_down_window = _wind_down_window(hour)

    reasons: list[str] = []

    if direct_interaction or speech or (room_motion and room_activity_active) or (observer_motion and room_activity_active):
        occupancy_state = "occupied_active"
        reasons.append("reliable live presence signal")
    elif sleep_window and had_recent_home_presence and quiet_now and seconds_since_reliable >= SLEEP_SETTLE_S:
        occupancy_state = "likely_asleep"
        reasons.append("quiet overnight home occupancy")
    elif wind_down_window and had_recent_home_presence and quiet_now and seconds_since_reliable <= WIND_DOWN_HOME_HOLD_S:
        occupancy_state = "occupied_quiet"
        reasons.append("wind-down home memory holding quiet occupancy")
    elif not presence_sources_fresh:
        occupancy_state = "occupied_quiet"
        reasons.append("presence sources stale; failing safe to occupied")
    elif room_motion or observer_motion or input_spike or seconds_since_reliable <= ACTIVE_HOLD_S:
        occupancy_state = "occupied_quiet"
        reasons.append("recent or weak presence held as occupied")
    elif seconds_since_reliable >= AWAY_TIMEOUT_S:
        occupancy_state = "likely_away"
        reasons.append("no reliable presence for 5 minutes")
    else:
        occupancy_state = "uncertain"
        reasons.append("signals weak or conflicting")

    confidence = (
        _bool_score(speech, 0.42)
        + _bool_score(direct_interaction, 0.36)
        + _bool_score(room_motion, 0.16)
        + _bool_score(observer_motion, 0.14)
        + _bool_score(room_activity_active, 0.14)
        + _bool_score(input_spike, 0.08)
        + _bool_score(seconds_since_reliable <= ACTIVE_HOLD_S, 0.12)
    )
    if occupancy_state == "likely_asleep":
        confidence = max(confidence, 0.45)
    if occupancy_state == "likely_away":
        confidence = max(confidence, 0.6)
    confidence = round(_clamp(confidence), 3)

    if direct_interaction:
        attention_state = "performance"
        attention_score = 0.92
        reasons.append("direct interaction")
    elif speech or (room_motion and room_activity_active) or (observer_motion and room_activity_active):
        attention_state = "attending"
        attention_score = 0.58
    else:
        attention_state = "ambient"
        attention_score = 0.18 if occupancy_state in {"occupied_active", "occupied_quiet", "likely_asleep"} else 0.05

    return {
        "timestamp": now,
        "occupancy_state": occupancy_state,
        "confidence": confidence,
        "attention_state": attention_state,
        "attention_score": round(attention_score, 3),
        "identity_hint": previous_state.get("identity_hint", "unknown"),
        "identity_confidence": float(previous_state.get("identity_confidence", 0.0) or 0.0),
        "last_reliable_presence_at": last_reliable if last_reliable else 0.0,
        "last_direct_interaction_at": last_direct if last_direct else 0.0,
        "signals": {
            "speech": speech,
            "room_motion": room_motion,
            "observer_motion": observer_motion,
            "room_activity": room_activity_level,
            "instrument_active": instrument_active,
            "direct_interaction": direct_interaction,
        },
        "reasons": reasons,
    }


def write_presence_state(state: dict[str, Any], output_path: str = DEFAULT_OUTPUT) -> None:
    """Atomically write the canonical presence state."""
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, output_path)


def run_presence_loop(interval: float = 2.0, max_iterations: int = 0) -> None:
    """Run the presence engine continuously."""
    iteration = 0
    while True:
        try:
            previous_state = read_state(DEFAULT_OUTPUT, max_age_s=None)
            state = resolve_presence_state(gather_presence_inputs(), previous_state=previous_state)
            write_presence_state(state, DEFAULT_OUTPUT)
        except Exception:
            pass
        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            break
        time.sleep(interval)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CypherClaw canonical presence engine")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    run_presence_loop(interval=args.interval)
