"""Canonical cadence engine for CypherClaw."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any


PRESENCE_STATE = "/tmp/presence_state.json"
OVERRIDE_STATE = "/tmp/cadence_override.json"
DEFAULT_OUTPUT = "/tmp/cadence_state.json"

STALE_S = 60.0
WAKE_RAMP_S = 3_600.0
MONDAY_WAKE_RAMP_S = 4_500.0
WEEKEND_SHIFT_MINUTES = 90
SUNDAY_MORNING_SHIFT_MINUTES = 60


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


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _parse_until(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def resolve_weekly_phase(now_dt: datetime) -> str:
    weekday = now_dt.weekday()
    if weekday == 0:
        return "monday_gentle"
    if weekday in {1, 2, 3}:
        return "core_weekday"
    if weekday == 4:
        return "friday_lift"
    if weekday == 5:
        return "weekend_late"
    return "sunday_settle"


def resolve_day_phase(now_dt: datetime, weekly_phase: str) -> str:
    minutes = now_dt.hour * 60 + now_dt.minute
    if weekly_phase == "weekend_late":
        minutes -= WEEKEND_SHIFT_MINUTES
    elif weekly_phase == "sunday_settle" and minutes < 14 * 60:
        minutes -= SUNDAY_MORNING_SHIFT_MINUTES
    minutes %= 24 * 60

    if minutes < 5 * 60:
        return "late_night"
    if minutes < 7 * 60:
        return "pre_dawn"
    if minutes < 9 * 60:
        return "morning_activation"
    if minutes < 11 * 60:
        return "mid_morning"
    if minutes < 13 * 60:
        return "midday"
    if minutes < 15 * 60:
        return "afternoon_dip"
    if minutes < 18 * 60:
        return "late_afternoon"
    if minutes < 21 * 60:
        return "evening_settling"
    return "pre_sleep"


def _base_phase_parameters(day_phase: str) -> dict[str, Any]:
    table: dict[str, dict[str, Any]] = {
        "late_night": {
            "bpm_target": 52.0,
            "bpm_range": [40.0, 60.0],
            "loudness_db_range": [35.0, 40.0],
            "dynamic_range_db": 4.0,
            "spectral_centroid_hz": 650.0,
            "onset_density_range": [0.05, 0.5],
            "attack_ms_range": [800.0, 2000.0],
            "pulse_clarity": 0.05,
            "harmonic_change_s_range": [45.0, 120.0],
            "phrase_arc_s": 12.0,
        },
        "pre_dawn": {
            "bpm_target": 70.0,
            "bpm_range": [60.0, 80.0],
            "loudness_db_range": [40.0, 48.0],
            "dynamic_range_db": 6.0,
            "spectral_centroid_hz": 1000.0,
            "onset_density_range": [0.5, 1.5],
            "attack_ms_range": [400.0, 1200.0],
            "pulse_clarity": 0.15,
            "harmonic_change_s_range": [30.0, 90.0],
            "phrase_arc_s": 11.0,
        },
        "morning_activation": {
            "bpm_target": 86.0,
            "bpm_range": [75.0, 95.0],
            "loudness_db_range": [45.0, 55.0],
            "dynamic_range_db": 8.0,
            "spectral_centroid_hz": 1400.0,
            "onset_density_range": [1.0, 3.0],
            "attack_ms_range": [120.0, 700.0],
            "pulse_clarity": 0.3,
            "harmonic_change_s_range": [15.0, 60.0],
            "phrase_arc_s": 10.0,
        },
        "mid_morning": {
            "bpm_target": 96.0,
            "bpm_range": [85.0, 105.0],
            "loudness_db_range": [48.0, 58.0],
            "dynamic_range_db": 8.0,
            "spectral_centroid_hz": 1700.0,
            "onset_density_range": [2.0, 4.0],
            "attack_ms_range": [80.0, 500.0],
            "pulse_clarity": 0.42,
            "harmonic_change_s_range": [12.0, 45.0],
            "phrase_arc_s": 10.0,
        },
        "midday": {
            "bpm_target": 90.0,
            "bpm_range": [80.0, 100.0],
            "loudness_db_range": [47.0, 55.0],
            "dynamic_range_db": 8.0,
            "spectral_centroid_hz": 1550.0,
            "onset_density_range": [2.0, 3.0],
            "attack_ms_range": [100.0, 600.0],
            "pulse_clarity": 0.38,
            "harmonic_change_s_range": [15.0, 50.0],
            "phrase_arc_s": 10.0,
        },
        "afternoon_dip": {
            "bpm_target": 78.0,
            "bpm_range": [70.0, 85.0],
            "loudness_db_range": [45.0, 52.0],
            "dynamic_range_db": 6.0,
            "spectral_centroid_hz": 1250.0,
            "onset_density_range": [1.0, 2.0],
            "attack_ms_range": [180.0, 800.0],
            "pulse_clarity": 0.22,
            "harmonic_change_s_range": [20.0, 60.0],
            "phrase_arc_s": 10.5,
        },
        "late_afternoon": {
            "bpm_target": 102.0,
            "bpm_range": [85.0, 110.0],
            "loudness_db_range": [50.0, 60.0],
            "dynamic_range_db": 10.0,
            "spectral_centroid_hz": 1900.0,
            "onset_density_range": [2.0, 5.0],
            "attack_ms_range": [60.0, 420.0],
            "pulse_clarity": 0.5,
            "harmonic_change_s_range": [10.0, 35.0],
            "phrase_arc_s": 9.5,
        },
        "evening_settling": {
            "bpm_target": 84.0,
            "bpm_range": [75.0, 95.0],
            "loudness_db_range": [45.0, 55.0],
            "dynamic_range_db": 7.0,
            "spectral_centroid_hz": 1500.0,
            "onset_density_range": [1.5, 3.0],
            "attack_ms_range": [100.0, 600.0],
            "pulse_clarity": 0.35,
            "harmonic_change_s_range": [15.0, 50.0],
            "phrase_arc_s": 10.0,
        },
        "pre_sleep": {
            "bpm_target": 62.0,
            "bpm_range": [55.0, 70.0],
            "loudness_db_range": [38.0, 45.0],
            "dynamic_range_db": 5.0,
            "spectral_centroid_hz": 850.0,
            "onset_density_range": [0.1, 1.0],
            "attack_ms_range": [300.0, 1400.0],
            "pulse_clarity": 0.1,
            "harmonic_change_s_range": [30.0, 90.0],
            "phrase_arc_s": 11.0,
        },
    }
    return dict(table[day_phase])


def _with_weekly_bias(params: dict[str, Any], weekly_phase: str, now_dt: datetime) -> dict[str, Any]:
    params = dict(params)
    if weekly_phase == "monday_gentle":
        params["bpm_target"] -= 6.0
        params["bpm_range"] = [max(40.0, params["bpm_range"][0] - 4.0), max(45.0, params["bpm_range"][1] - 4.0)]
        params["spectral_centroid_hz"] -= 150.0
        params["onset_density_range"] = [
            max(0.05, params["onset_density_range"][0] - 0.2),
            max(0.2, params["onset_density_range"][1] - 0.3),
        ]
    elif weekly_phase == "friday_lift":
        if now_dt.hour >= 15:
            params["bpm_target"] += 6.0
            params["spectral_centroid_hz"] += 120.0
            params["pulse_clarity"] = min(0.7, params["pulse_clarity"] + 0.08)
    elif weekly_phase == "weekend_late":
        params["dynamic_range_db"] += 1.0
    elif weekly_phase == "sunday_settle" and now_dt.hour >= 16:
        params["bpm_target"] -= 8.0
        params["spectral_centroid_hz"] -= 180.0
        params["pulse_clarity"] = max(0.05, params["pulse_clarity"] - 0.08)
        params["loudness_db_range"] = [
            max(35.0, params["loudness_db_range"][0] - 2.0),
            max(40.0, params["loudness_db_range"][1] - 3.0),
        ]
    params["bpm_target"] = round(params["bpm_target"], 1)
    return params


def _stay_lively_active(overrides: dict[str, Any], now_dt: datetime) -> bool:
    until = _parse_until(overrides.get("stay_lively_until"))
    return bool(until and now_dt < until)


def _wake_ramp_start(
    presence_state: dict[str, Any],
    previous_state: dict[str, Any],
    now_dt: datetime,
    day_phase: str,
) -> float | None:
    if previous_state.get("cadence_state") == "wake_ramp":
        started = float(previous_state.get("wake_ramp_started_at", 0.0) or 0.0)
        if started:
            return started

    occupancy_state = presence_state.get("occupancy_state", "uncertain")
    if occupancy_state not in {"occupied_active", "occupied_quiet"}:
        return None
    if day_phase not in {"pre_dawn", "morning_activation"}:
        return None
    if previous_state.get("cadence_state") == "sleep":
        return now_dt.timestamp()
    last_reliable = float(presence_state.get("last_reliable_presence_at", 0.0) or 0.0)
    if last_reliable and now_dt.timestamp() - last_reliable <= 90.0:
        return now_dt.timestamp()
    return None


def build_cadence_state(
    presence_state: dict[str, Any],
    *,
    previous_state: dict[str, Any] | None = None,
    now_dt: datetime | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical cadence state from presence plus time."""
    previous_state = previous_state or {}
    overrides = overrides or {}
    now_dt = datetime.now() if now_dt is None else now_dt
    timestamp = now_dt.timestamp()

    weekly_phase = resolve_weekly_phase(now_dt)
    day_phase = resolve_day_phase(now_dt, weekly_phase)
    occupancy_state = presence_state.get("occupancy_state", "uncertain")
    source = "presence+clock" if float(presence_state.get("confidence", 0.0) or 0.0) >= 0.25 else "clock"

    forced_mode = overrides.get("force_mode")
    wake_ramp_started_at = float(previous_state.get("wake_ramp_started_at", 0.0) or 0.0)

    if overrides.get("force_sleep") or forced_mode == "sleep":
        cadence_state = "sleep"
    elif overrides.get("force_practice") or forced_mode == "away_practice":
        cadence_state = "away_practice"
    else:
        lively_override = _stay_lively_active(overrides, now_dt)
        wake_start = _wake_ramp_start(presence_state, previous_state, now_dt, day_phase)
        if wake_start is not None:
            wake_ramp_started_at = wake_start
        ramp_duration = MONDAY_WAKE_RAMP_S if weekly_phase == "monday_gentle" else WAKE_RAMP_S

        if occupancy_state == "likely_asleep":
            cadence_state = "sleep"
            wake_ramp_started_at = 0.0
        elif wake_ramp_started_at and timestamp - wake_ramp_started_at < ramp_duration:
            cadence_state = "wake_ramp"
        elif now_dt.hour >= 22 and not lively_override:
            cadence_state = "wind_down"
            wake_ramp_started_at = 0.0
        elif occupancy_state == "likely_away" and day_phase not in {"late_night", "pre_sleep"}:
            cadence_state = "away_practice"
            wake_ramp_started_at = 0.0
        else:
            cadence_state = "occupied_day"
            wake_ramp_started_at = 0.0

    params = _with_weekly_bias(_base_phase_parameters(day_phase), weekly_phase, now_dt)

    voice_cap = 4
    experimentation_bias = 0.35
    risk_level = "medium"
    silence_budget = 600
    silence_gap = [20.0, 60.0]
    notes: list[str] = []

    if cadence_state == "sleep":
        params.update(
            {
                "bpm_target": min(params["bpm_target"], 55.0),
                "bpm_range": [40.0, 60.0],
                "loudness_db_range": [35.0, 40.0],
                "dynamic_range_db": 4.0,
                "spectral_centroid_hz": min(params["spectral_centroid_hz"], 800.0),
                "onset_density_range": [0.05, 0.5],
                "attack_ms_range": [700.0, 2000.0],
                "pulse_clarity": 0.05,
                "harmonic_change_s_range": [45.0, 120.0],
                "phrase_arc_s": 12.0,
            }
        )
        voice_cap = 2
        experimentation_bias = 0.05
        risk_level = "minimal"
        silence_budget = 1_800
        silence_gap = [30.0, 120.0]
        notes.append("sleep fade toward near-silence")
    elif cadence_state == "wake_ramp":
        ramp_duration = MONDAY_WAKE_RAMP_S if weekly_phase == "monday_gentle" else WAKE_RAMP_S
        progress = 0.0
        if wake_ramp_started_at:
            progress = _clamp((timestamp - wake_ramp_started_at) / ramp_duration, 0.0, 1.0)
        target_floor = params["bpm_target"]
        start_bpm = 56.0 if weekly_phase == "monday_gentle" else 60.0
        params["bpm_target"] = round(start_bpm + (target_floor - start_bpm) * progress, 1)
        params["bpm_range"] = [max(50.0, params["bpm_target"] - 8.0), min(98.0, params["bpm_target"] + 8.0)]
        params["onset_density_range"] = [
            round(0.5 + 1.5 * progress, 2),
            round(1.5 + 1.5 * progress, 2),
        ]
        params["pulse_clarity"] = round(0.12 + 0.18 * progress, 2)
        params["attack_ms_range"] = [max(120.0, 700.0 - 400.0 * progress), max(350.0, 1200.0 - 500.0 * progress)]
        voice_cap = 3 if progress < 0.5 else 4
        experimentation_bias = 0.18
        risk_level = "low"
        silence_budget = 720
        silence_gap = [12.0, 45.0]
        notes.append("wake ramp active")
    elif cadence_state == "away_practice":
        params["bpm_range"] = [max(40.0, params["bpm_range"][0] - 20.0), min(180.0, params["bpm_range"][1] + 30.0)]
        params["dynamic_range_db"] = max(10.0, params["dynamic_range_db"] + 2.0)
        params["pulse_clarity"] = min(0.75, params["pulse_clarity"] + 0.12)
        voice_cap = 5
        experimentation_bias = 0.82
        risk_level = "high"
        silence_budget = 420
        silence_gap = [10.0, 40.0]
        notes.append("away practice enabled")
    elif cadence_state == "wind_down":
        params["bpm_target"] = round(min(params["bpm_target"], 72.0), 1)
        params["bpm_range"] = [max(50.0, params["bpm_target"] - 8.0), min(80.0, params["bpm_target"] + 6.0)]
        params["spectral_centroid_hz"] = min(params["spectral_centroid_hz"], 1100.0)
        params["onset_density_range"] = [min(params["onset_density_range"][0], 1.0), min(params["onset_density_range"][1], 1.5)]
        params["pulse_clarity"] = min(params["pulse_clarity"], 0.18)
        params["attack_ms_range"] = [max(250.0, params["attack_ms_range"][0]), max(900.0, params["attack_ms_range"][1])]
        voice_cap = 3
        experimentation_bias = 0.12
        risk_level = "low"
        silence_budget = 1_200
        silence_gap = [20.0, 90.0]
        notes.append("wind down active")
    else:
        voice_cap = 4 if day_phase not in {"late_night", "pre_sleep"} else 3
        experimentation_bias = 0.32 if weekly_phase != "friday_lift" else 0.4
        risk_level = "medium"
        silence_budget = 480
        silence_gap = [15.0, 60.0]

    if _stay_lively_active(overrides, now_dt):
        notes.append("stay lively override")

    return {
        "timestamp": timestamp,
        "cadence_state": cadence_state,
        "day_phase": day_phase,
        "weekly_phase": weekly_phase,
        "source": source,
        "bpm_target": round(params["bpm_target"], 1),
        "bpm_range": [round(params["bpm_range"][0], 1), round(params["bpm_range"][1], 1)],
        "loudness_db_range": [round(params["loudness_db_range"][0], 1), round(params["loudness_db_range"][1], 1)],
        "dynamic_range_db": round(params["dynamic_range_db"], 1),
        "spectral_centroid_hz": round(params["spectral_centroid_hz"], 1),
        "onset_density_range": [round(params["onset_density_range"][0], 2), round(params["onset_density_range"][1], 2)],
        "attack_ms_range": [round(params["attack_ms_range"][0], 1), round(params["attack_ms_range"][1], 1)],
        "pulse_clarity": round(params["pulse_clarity"], 2),
        "harmonic_change_s_range": [
            round(params["harmonic_change_s_range"][0], 1),
            round(params["harmonic_change_s_range"][1], 1),
        ],
        "phrase_arc_s": round(params["phrase_arc_s"], 1),
        "silence_budget_s_per_hour": int(silence_budget),
        "silence_gap_s_range": [round(silence_gap[0], 1), round(silence_gap[1], 1)],
        "voice_cap": int(voice_cap),
        "experimentation_bias": round(experimentation_bias, 2),
        "risk_level": risk_level,
        "wake_ramp_started_at": wake_ramp_started_at or None,
        "notes": notes,
    }


def write_cadence_state(state: dict[str, Any], output_path: str = DEFAULT_OUTPUT) -> None:
    """Atomically write cadence state."""
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, output_path)


def run_cadence_loop(
    interval: float = 5.0,
    max_iterations: int = 0,
    *,
    now_dt: datetime | None = None,
) -> None:
    """Run the cadence engine continuously."""
    iteration = 0
    while True:
        try:
            presence_state = read_state(PRESENCE_STATE)
            previous_state = read_state(DEFAULT_OUTPUT, max_age_s=None)
            overrides = read_state(OVERRIDE_STATE, max_age_s=None)
            state = build_cadence_state(
                presence_state,
                previous_state=previous_state,
                now_dt=now_dt,
                overrides=overrides,
            )
            write_cadence_state(state, DEFAULT_OUTPUT)
        except Exception:
            pass
        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            break
        time.sleep(interval)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CypherClaw cadence engine")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    run_cadence_loop(interval=args.interval)
