"""Tests for tracker cadence planning and family shaping."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from inner_life.world_model import WorldModel
from senseweave.generative_scores import Note, Phrase, Score
from senseweave.tracker_cadence import (
    constrain_score_to_cadence,
    apply_tracker_plan_to_mood,
    resolve_tracker_plan,
    shape_score_for_family,
)


def _sample_score() -> Score:
    return Score(
        phrases=[
            Phrase(
                notes=[Note(1, 1.0, False), Note(3, 1.0, True), Note(5, 2.0, False)],
                voice="pluck",
                dynamic="mf",
                role="melody",
            ),
            Phrase(
                notes=[Note(1, 2.0, True), Note(5, 2.0, False)],
                voice="gong",
                dynamic="mp",
                role="bass",
            ),
        ],
        key="C",
        tempo_bpm=84.0,
        mood="calm",
        created_at=0.0,
    )


def test_resolve_tracker_plan_prefers_pulse_for_active_occupied_day() -> None:
    world = WorldModel(
        someone_here=True,
        room_activity="active",
        recent_transient=True,
        time_of_day="afternoon",
        stale_sources=[],
    )

    plan = resolve_tracker_plan(world, song_num=3, hour=14)

    assert plan.occupancy_state == "occupied_active"
    assert plan.cadence_state == "occupied_day"
    assert plan.family == "pulse"


def test_resolve_tracker_plan_prefers_forge_when_away() -> None:
    world = WorldModel(
        someone_here=False,
        room_activity="quiet",
        recent_transient=False,
        time_of_day="afternoon",
        stale_sources=[],
    )

    plan = resolve_tracker_plan(world, song_num=4, hour=14)

    assert plan.occupancy_state == "likely_away"
    assert plan.cadence_state == "away_practice"
    assert plan.family == "forge"


def test_resolve_tracker_plan_uses_wake_ramp_for_morning_presence() -> None:
    world = WorldModel(
        someone_here=True,
        room_activity="moderate",
        time_of_day="morning",
        stale_sources=[],
    )

    plan = resolve_tracker_plan(world, song_num=1, hour=7)

    assert plan.cadence_state == "wake_ramp"
    assert plan.family == "ember"


def test_resolve_tracker_plan_prefers_canonical_cadence_when_present() -> None:
    world = WorldModel(
        occupancy_state="occupied_quiet",
        cadence_state="wind_down",
        day_phase="pre_sleep",
        weekly_phase="sunday_settle",
        stale_sources=[],
    )

    plan = resolve_tracker_plan(world, song_num=1, hour=15)

    assert plan.cadence_state == "wind_down"
    assert plan.occupancy_state == "occupied_quiet"
    assert plan.family == "drift"
    assert plan.source == "cadence"
    assert plan.progression_profile == "settling"


def test_resolve_tracker_plan_varies_occupied_day_families_across_songs() -> None:
    world = WorldModel(
        occupancy_state="occupied_quiet",
        cadence_state="occupied_day",
        day_phase="mid_morning",
        weekly_phase="core_weekday",
        stale_sources=[],
    )

    families = {
        resolve_tracker_plan(world, song_num=song_num, hour=10).family
        for song_num in range(1, 7)
    }

    assert len(families) >= 3
    assert {"ember", "bloom", "pulse"}.intersection(families)


def test_resolve_tracker_plan_weekly_phase_changes_family_bias() -> None:
    friday_world = WorldModel(
        occupancy_state="occupied_quiet",
        cadence_state="occupied_day",
        day_phase="late_afternoon",
        weekly_phase="friday_lift",
        stale_sources=[],
    )
    sunday_world = WorldModel(
        occupancy_state="occupied_quiet",
        cadence_state="occupied_day",
        day_phase="evening_settling",
        weekly_phase="sunday_settle",
        stale_sources=[],
    )

    friday = resolve_tracker_plan(friday_world, song_num=2, hour=17)
    sunday = resolve_tracker_plan(sunday_world, song_num=2, hour=17)

    assert friday.family in {"pulse", "bloom"}
    assert friday.progression_profile == "lift"
    assert sunday.family in {"drift", "ember", "nocturne"}
    assert sunday.progression_profile == "settling"


def test_apply_tracker_plan_to_mood_pushes_daytime_energy_up() -> None:
    world = WorldModel(
        someone_here=True,
        room_activity="active",
        recent_transient=True,
        time_of_day="afternoon",
        stale_sources=[],
    )
    plan = resolve_tracker_plan(world, song_num=2, hour=15)

    mood = apply_tracker_plan_to_mood(
        {"energy": 0.35, "valence": 0.48, "arousal": 0.3},
        plan,
    )

    assert mood["energy"] > 0.35
    assert mood["arousal"] > 0.3


def test_shape_score_for_family_pulse_adds_motion() -> None:
    shaped = shape_score_for_family(
        _sample_score(),
        family="pulse",
        cadence_state="occupied_day",
        song_num=2,
    )

    assert shaped.tempo_bpm > 84.0
    assert any(note.accent for phrase in shaped.phrases for note in phrase.notes)
    assert min(note.duration_beats for phrase in shaped.phrases for note in phrase.notes) < 1.0


def test_shape_score_for_family_nocturne_softens_and_slows() -> None:
    shaped = shape_score_for_family(
        _sample_score(),
        family="nocturne",
        cadence_state="sleep",
        song_num=1,
    )

    assert shaped.tempo_bpm < 84.0
    assert all(phrase.dynamic in {"pp", "p", "mp"} for phrase in shaped.phrases)
    assert max(note.duration_beats for phrase in shaped.phrases for note in phrase.notes) > 2.0


def test_shape_score_for_family_preserves_patch_metadata() -> None:
    score = _sample_score()
    score.metadata["patch_name"] = "house_monastery"

    shaped = shape_score_for_family(
        score,
        family="nocturne",
        cadence_state="sleep",
        song_num=1,
    )

    assert shaped.metadata["patch_name"] == "house_monastery"


def test_constrain_score_to_cadence_clamps_tempo_band() -> None:
    world = WorldModel(
        cadence_state="sleep",
        bpm_target=54.0,
        bpm_range=(50.0, 58.0),
    )

    constrained = constrain_score_to_cadence(_sample_score(), world)

    assert 50.0 <= constrained.tempo_bpm <= 58.0


def test_constrain_score_to_cadence_preserves_patch_metadata() -> None:
    score = _sample_score()
    score.metadata["patch_name"] = "house_procession"
    world = WorldModel(
        cadence_state="occupied_day",
        bpm_target=122.0,
        bpm_range=(118.0, 128.0),
    )

    constrained = constrain_score_to_cadence(score, world)

    assert constrained.metadata["patch_name"] == "house_procession"
