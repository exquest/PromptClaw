from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.piece_commission import FORM_CLASS_RANGES, commission_piece


def test_commission_prefers_song_class_during_occupied_day() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.42,
        song_num=4,
        hour=14,
    )

    assert commission.form_class == "song"
    lo, hi = FORM_CLASS_RANGES["song"]
    assert lo <= commission.duration_target_s <= hi
    assert commission.composition_mode in {"hook_led", "hybrid", "through_composed"}


def test_commission_biases_longer_when_narrative_pressure_is_high_at_night() -> None:
    commission = commission_piece(
        cadence_state="wind_down",
        day_phase="late_evening",
        weekly_phase="weekend",
        attention_score=0.18,
        narrative_pressure=0.92,
        song_num=19,
        hour=23,
    )

    assert commission.form_class in {"extended", "suite"}
    assert commission.duration_target_s >= FORM_CLASS_RANGES["extended"][0]
    assert commission.sonic_world_count >= 1
    assert commission.ending_family


def test_commission_keeps_first_away_practice_piece_audible_and_bounded() -> None:
    commission = commission_piece(
        cadence_state="away_practice",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.4,
        narrative_pressure=0.85,
        occupancy_state="likely_away",
        repertoire_entries=[object()] * 40,
        song_num=1,
        hour=16,
    )

    assert commission.form_class in {"song", "extended"}
    assert commission.duration_target_s <= FORM_CLASS_RANGES["extended"][1]
    assert commission.composition_mode in {"hook_led", "hybrid"}


def test_commission_uses_repertoire_ear_feedback_for_corrections() -> None:
    baseline = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.42,
        song_num=7,
        hour=14,
    )
    corrected = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.42,
        repertoire_entries=[
            {
                "feedback_scores": {
                    "static_score": 0.8,
                    "harsh_score": 0.7,
                    "muddy_score": 0.75,
                    "underdeveloped_score": 0.85,
                }
            }
        ],
        song_num=7,
        hour=14,
    )

    assert corrected.duration_target_s > baseline.duration_target_s
    assert corrected.hook_pressure >= baseline.hook_pressure
    assert {
        "ear_correct=static",
        "ear_correct=harsh",
        "ear_correct=muddy",
        "ear_correct=underdeveloped",
    } <= set(corrected.reason_tags)
