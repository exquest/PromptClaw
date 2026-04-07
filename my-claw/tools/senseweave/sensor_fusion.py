"""SenseWeave Sensor Fusion — reads all sensor JSON files and produces a unified organism state.

Reads:
  /tmp/theramini_state.json   — Theramini pitch/onset detection
  /tmp/room_activity.json     — Contact mic transient detection
  /tmp/room_speech.json       — Speech detection via Whisper
  /tmp/composer_state.json    — Current composer state

Writes:
  /tmp/organism_state.json    — Unified organism state (atomic)
"""
from __future__ import annotations

import json
import os
import sys
import time

# ---------------------------------------------------------------------------
# Default sensor file paths (monkeypatchable in tests)
# ---------------------------------------------------------------------------

THERAMINI_STATE = "/tmp/theramini_state.json"
ROOM_ACTIVITY_STATE = "/tmp/room_activity.json"
ROOM_SPEECH_STATE = "/tmp/room_speech.json"
COMPOSER_STATE = "/tmp/composer_state.json"
DEFAULT_OUTPUT = "/tmp/organism_state.json"


# ---------------------------------------------------------------------------
# read_sensor_state
# ---------------------------------------------------------------------------


def read_sensor_state(state_file: str, max_age_s: float = 10.0) -> dict:
    """Read a JSON sensor state file.

    Returns empty dict if the file is missing, corrupt, empty, or stale
    (modified more than *max_age_s* seconds ago).
    """
    try:
        mtime = os.path.getmtime(state_file)
        if time.time() - mtime > max_age_s:
            return {}
        with open(state_file, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# calculate_mood
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def calculate_mood(theramini: dict, room: dict, speech: dict) -> dict:
    """Derive organism mood from sensor inputs.

    Returns dict with energy, valence, arousal each in [0.0, 1.0].
    - energy:  higher when Theramini playing or room active
    - valence: higher when speech detected (people talking = happy)
    - arousal: higher on transients or fast Theramini playing
    """
    # --- Energy ---
    energy = 0.1  # baseline
    if theramini.get("playing"):
        energy += 0.5
    activity = room.get("activity", "quiet")
    if activity == "active":
        energy += 0.4
    elif activity == "moderate":
        energy += 0.2
    if room.get("transient"):
        energy += 0.1

    # --- Valence ---
    valence = 0.3  # neutral baseline
    if speech.get("detected"):
        valence += 0.4
    if theramini.get("playing"):
        valence += 0.2

    # --- Arousal ---
    arousal = 0.1  # baseline
    if room.get("transient"):
        arousal += 0.5
    if theramini.get("playing"):
        arousal += 0.3
    if speech.get("detected"):
        arousal += 0.1

    return {
        "energy": _clamp(energy),
        "valence": _clamp(valence),
        "arousal": _clamp(arousal),
    }


# ---------------------------------------------------------------------------
# detect_presence
# ---------------------------------------------------------------------------


def detect_presence(theramini: dict, room: dict, speech: dict) -> dict:
    """Determine if someone is in the room.

    Returns dict with someone_here (bool) and activity_level (str).
    """
    signals = 0
    if theramini.get("playing"):
        signals += 1
    if speech.get("detected"):
        signals += 1
    if room.get("transient"):
        signals += 1

    someone_here = signals > 0

    if signals >= 2:
        activity_level = "active"
    elif signals == 1:
        activity_level = "moderate"
    else:
        activity_level = "quiet"

    return {
        "someone_here": someone_here,
        "activity_level": activity_level,
    }


# ---------------------------------------------------------------------------
# fuse_sensors
# ---------------------------------------------------------------------------


def fuse_sensors() -> dict:
    """Read all sensor files and produce a unified organism state."""
    raw_theramini = read_sensor_state(THERAMINI_STATE)
    raw_room = read_sensor_state(ROOM_ACTIVITY_STATE)
    raw_speech = read_sensor_state(ROOM_SPEECH_STATE)
    raw_composer = read_sensor_state(COMPOSER_STATE)

    # --- Theramini ---
    theramini = {
        "playing": raw_theramini.get("is_playing", False),
        "pitch": raw_theramini.get("pitch_note"),
        "key": raw_theramini.get("suggested_key"),
    }

    # --- Room ---
    room = {
        "activity": raw_room.get("activity_level", "quiet"),
        "transient": raw_room.get("recent_transient", False),
    }

    # --- Speech ---
    speech = {
        "detected": raw_speech.get("speech_detected", False),
        "transcript": raw_speech.get("transcript"),
    }

    # --- Composer ---
    composer = {
        "key": raw_composer.get("key", "C"),
        "mode": raw_composer.get("mode", "solo"),
        "movement": raw_composer.get("movement", "idle"),
    }

    # --- Derived ---
    organism_mood = calculate_mood(theramini, room, speech)
    presence = detect_presence(theramini, room, speech)

    return {
        "timestamp": time.time(),
        "theramini": theramini,
        "room": room,
        "speech": speech,
        "composer": composer,
        "organism_mood": organism_mood,
        "presence": presence,
    }


# ---------------------------------------------------------------------------
# write_fused_state
# ---------------------------------------------------------------------------


def write_fused_state(state: dict, output_path: str = DEFAULT_OUTPUT) -> None:
    """Atomic write of fused state — write to tmp file then os.replace."""
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, output_path)


# ---------------------------------------------------------------------------
# run_fusion_loop
# ---------------------------------------------------------------------------


def run_fusion_loop(interval: float = 1.0, max_iterations: int = 0) -> None:
    """Daemon loop: fuse sensors, write state, sleep.

    If *max_iterations* > 0, stop after that many iterations (for testing).
    If *max_iterations* == 0, run forever.
    """
    iteration = 0
    while True:
        try:
            state = fuse_sensors()
            write_fused_state(state, DEFAULT_OUTPUT)
        except Exception:
            pass  # Never crash the daemon loop
        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            break
        time.sleep(interval)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SenseWeave sensor fusion daemon")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Seconds between fusion cycles (default: 1.0)")
    args = parser.parse_args()

    print(f"[sensor_fusion] Starting fusion loop (interval={args.interval}s)")
    print(f"  theramini: {THERAMINI_STATE}")
    print(f"  room:      {ROOM_ACTIVITY_STATE}")
    print(f"  speech:    {ROOM_SPEECH_STATE}")
    print(f"  composer:  {COMPOSER_STATE}")
    print(f"  output:    {DEFAULT_OUTPUT}")

    try:
        run_fusion_loop(interval=args.interval)
    except KeyboardInterrupt:
        print("\n[sensor_fusion] Stopped.")
