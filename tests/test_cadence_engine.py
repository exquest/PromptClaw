"""Tests for the canonical cadence engine."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from cadence_engine import build_cadence_state, run_cadence_loop


def _presence_state(occupancy_state: str = "occupied_quiet", *, confidence: float = 0.8) -> dict:
    return {
        "timestamp": 1_000.0,
        "occupancy_state": occupancy_state,
        "confidence": confidence,
        "attention_state": "ambient",
        "attention_score": 0.15,
        "identity_hint": "unknown",
        "identity_confidence": 0.0,
        "last_reliable_presence_at": 950.0,
        "last_direct_interaction_at": 900.0,
        "signals": {
            "speech": False,
            "room_motion": occupancy_state.startswith("occupied"),
            "observer_motion": False,
            "room_activity": "quiet",
            "instrument_active": False,
            "direct_interaction": False,
        },
        "reasons": [],
    }


def test_monday_morning_is_gentler_than_midweek() -> None:
    presence = _presence_state("occupied_active")
    previous = {"cadence_state": "sleep", "wake_ramp_started_at": None}

    monday = build_cadence_state(
        presence,
        previous_state=previous,
        now_dt=datetime(2026, 4, 13, 7, 30),
    )
    wednesday = build_cadence_state(
        presence,
        previous_state=previous,
        now_dt=datetime(2026, 4, 15, 7, 30),
    )

    assert monday["weekly_phase"] == "monday_gentle"
    assert monday["cadence_state"] == "wake_ramp"
    assert monday["bpm_target"] < wednesday["bpm_target"]
    assert monday["spectral_centroid_hz"] < wednesday["spectral_centroid_hz"]


def test_weekend_cycle_shifts_later_than_workday() -> None:
    presence = _presence_state("occupied_quiet")

    weekday = build_cadence_state(
        presence,
        now_dt=datetime(2026, 4, 15, 8, 0),
    )
    saturday = build_cadence_state(
        presence,
        now_dt=datetime(2026, 4, 18, 8, 0),
    )

    assert weekday["day_phase"] == "morning_activation"
    assert saturday["weekly_phase"] == "weekend_late"
    assert saturday["bpm_target"] < weekday["bpm_target"]


def test_sunday_evening_settles_earlier_than_friday() -> None:
    presence = _presence_state("occupied_quiet")

    friday = build_cadence_state(
        presence,
        now_dt=datetime(2026, 4, 17, 18, 30),
    )
    sunday = build_cadence_state(
        presence,
        now_dt=datetime(2026, 4, 19, 18, 30),
    )

    assert friday["weekly_phase"] == "friday_lift"
    assert sunday["weekly_phase"] == "sunday_settle"
    assert sunday["bpm_target"] < friday["bpm_target"]
    assert sunday["pulse_clarity"] < friday["pulse_clarity"]


def test_likely_asleep_publishes_sleep_parameters_and_silence_budget() -> None:
    cadence = build_cadence_state(
        _presence_state("likely_asleep"),
        now_dt=datetime(2026, 4, 14, 1, 15),
    )

    assert cadence["cadence_state"] == "sleep"
    assert cadence["bpm_target"] <= 60.0
    assert cadence["silence_budget_s_per_hour"] >= 1_800
    assert cadence["voice_cap"] == 2


def test_stay_lively_override_holds_wind_down_off_until_midnight() -> None:
    presence = _presence_state("occupied_active")
    cadence = build_cadence_state(
        presence,
        now_dt=datetime(2026, 4, 17, 22, 30),
        overrides={"stay_lively_until": "2026-04-18T00:00:00"},
    )

    assert cadence["cadence_state"] == "occupied_day"
    assert cadence["risk_level"] == "medium"


def test_away_presence_enters_practice_mode() -> None:
    cadence = build_cadence_state(
        _presence_state("likely_away"),
        now_dt=datetime(2026, 4, 15, 14, 0),
    )

    assert cadence["cadence_state"] == "away_practice"
    assert cadence["experimentation_bias"] > 0.7


def test_run_cadence_loop_writes_cadence_state(monkeypatch, tmp_path: Path) -> None:
    presence = tmp_path / "presence_state.json"
    presence.write_text(json.dumps(_presence_state("occupied_quiet")))
    output = tmp_path / "cadence_state.json"

    monkeypatch.setattr("cadence_engine.PRESENCE_STATE", str(presence))
    monkeypatch.setattr("cadence_engine.DEFAULT_OUTPUT", str(output))
    monkeypatch.setattr("cadence_engine.OVERRIDE_STATE", str(tmp_path / "override.json"))

    run_cadence_loop(interval=0.0, max_iterations=1, now_dt=datetime(2026, 4, 15, 10, 0))

    written = json.loads(output.read_text())
    assert written["cadence_state"] == "occupied_day"
    assert written["day_phase"] == "mid_morning"
