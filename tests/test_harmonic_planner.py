"""Tests for harmonic_planner.py -- modal key parsing and keyboard grimoire."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.harmonic_planner import (
    display_key_spec,
    key_mode,
    key_root,
    keyboard_grimoire_from_midi_state,
    normalize_key_spec,
    resolve_harmonic_plan,
    scale_semitones_for_key,
)

_ROOT_INDEX = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "Bb": 10,
    "B": 11,
}


def _root_distance(left: str, right: str) -> int:
    raw = abs(_ROOT_INDEX[left] - _ROOT_INDEX[right])
    return min(raw, 12 - raw)


def test_normalize_key_spec_preserves_major_and_minor() -> None:
    assert normalize_key_spec("C") == "C"
    assert normalize_key_spec("Am") == "Am"
    assert normalize_key_spec("Bb") == "Bb"


def test_normalize_key_spec_accepts_modal_spellings() -> None:
    assert normalize_key_spec("D dorian") == "D:dorian"
    assert normalize_key_spec("F# mixolydian") == "F#:mixolydian"
    assert normalize_key_spec("Bb lydian") == "Bb:lydian"
    assert normalize_key_spec("E harmonic minor") == "E:harmonic_minor"


def test_scale_semitones_for_key_supports_modal_families() -> None:
    assert scale_semitones_for_key("D:dorian") == [0, 2, 3, 5, 7, 9, 10]
    assert scale_semitones_for_key("G:mixolydian") == [0, 2, 4, 5, 7, 9, 10]
    assert scale_semitones_for_key("Am") == [0, 2, 3, 5, 7, 8, 10]


def test_keyboard_grimoire_reads_minor_triad_and_pedal_gesture() -> None:
    state = keyboard_grimoire_from_midi_state(
        {
            "playing": True,
            "notes_on": [69, 72, 76],
            "last_activity": 999.5,
            "sustain_pedal": True,
            "expression": 104,
            "recent_pedal_events": [
                (999.0, True),
                (999.2, False),
                (999.4, True),
            ],
        },
        now=1000.0,
    )

    assert state["suggested_key"] == "A:harmonic_minor"
    assert state["root"] == "A"
    assert state["mode"] == "harmonic_minor"
    assert state["modulation_intent"] == "modulate"
    assert state["chord_palette"] == "extended"
    assert state["voicing_profile"] == "pedal_point"


def test_resolve_harmonic_plan_ignores_stale_garden_state() -> None:
    plan = resolve_harmonic_plan(
        "G",
        song_num=7,
        mood={"energy": 0.52, "valence": 0.66, "arousal": 0.48},
        family="pulse",
        garden_state={"music_key": "C", "last_update": 100.0},
        outdoor_state={"brightness": 0.8},
        midi_state={},
        inner_state={},
        now=1000.0,
    )

    assert plan.source == "carry"
    assert key_root(plan.key) == "G"
    assert plan.key != "C"
    assert plan.section_functions["Theme"] in {"tonic", "predominant"}
    assert plan.reharm_strategy


def test_resolve_harmonic_plan_uses_keyboard_grimoire_and_scene_variation() -> None:
    plan = resolve_harmonic_plan(
        "C",
        song_num=8,
        mood={"energy": 0.44, "valence": 0.38, "arousal": 0.31},
        family="forge",
        garden_state={"music_key": "C", "last_update": 995.0},
        outdoor_state={},
        midi_state={
            "playing": True,
            "notes_on": [62, 65, 69],
            "last_activity": 999.2,
            "sustain_pedal": True,
            "expression": 118,
            "recent_pedal_events": [(998.8, True), (999.0, False), (999.2, True)],
        },
        inner_state={},
        now=1000.0,
    )

    assert plan.source == "keyboard"
    assert plan.key == "D:harmonic_minor"
    assert plan.scene_keys["Emergence"] == "D:harmonic_minor"
    assert plan.scene_keys["Development"] != plan.scene_keys["Emergence"]
    assert plan.scene_keys["Recap"] != plan.scene_keys["Development"]
    assert key_mode(plan.scene_keys["Resolution"]) in {"aeolian", "dorian", "harmonic_minor"}
    assert "minor" in display_key_spec(plan.key).lower()
    assert plan.section_cadences["Resolution"] in {"authentic", "plagal", "deceptive"}


def test_resolve_harmonic_plan_exposes_section_chords_and_continuous_modulation() -> None:
    plan = resolve_harmonic_plan(
        "C",
        song_num=12,
        mood={"energy": 0.62, "valence": 0.45, "arousal": 0.58},
        family="pulse",
        cadence_state="occupied_day",
        progression_profile="lift",
        garden_state={},
        outdoor_state={},
        midi_state={
            "playing": True,
            "notes_on": [64, 68, 71],
            "last_activity": 999.8,
            "sustain_pedal": True,
            "expression": 116,
            "recent_pedal_events": [(999.0, True), (999.2, False), (999.4, True)],
        },
        inner_state={},
        now=1000.0,
    )

    assert plan.section_progressions["Theme"]
    assert plan.section_chord_degrees["Theme"]
    assert all(
        1 <= degree <= 7
        for chord in plan.section_chord_degrees["Theme"]
        for degree in chord
    )
    assert plan.section_progressions["Resolution"][-1] == 1
    assert plan.modulation_path[0] == plan.scene_keys["Emergence"]
    assert plan.modulation_path[-1] == plan.scene_keys["Resolution"]

    for left, right in zip(plan.modulation_path, plan.modulation_path[1:]):
        assert _root_distance(key_root(left), key_root(right)) <= 7


def test_resolve_harmonic_plan_advances_root_between_carry_songs() -> None:
    plan = resolve_harmonic_plan(
        "C",
        song_num=9,
        mood={"energy": 0.33, "valence": 0.41, "arousal": 0.28},
        family="drift",
        garden_state={},
        outdoor_state={},
        midi_state={},
        inner_state={},
        now=1000.0,
    )

    assert plan.source == "carry"
    assert key_root(plan.next_key) != key_root(plan.key)

def test_avant_garde_strategies_post_tonal() -> None:
    from senseweave.harmonic_planner import resolve_harmonic_plan
    plan = resolve_harmonic_plan(
        "C",
        song_num=10,
        mood={"energy": 0.8, "valence": 0.1, "arousal": 0.9},
        family="drone",
        cadence_state="occupied_day",
        progression_profile="lift",
        garden_state={},
        outdoor_state={},
        midi_state={},
        inner_state={},
        now=1000.0,
        intent="avant-garde"
    )
    assert plan.strategy in {"post-tonal", "spectral", "microtonal"}
