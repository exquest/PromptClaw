"""Tests for hook_engine.py -- title, hook, and phrase-pair planning."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.hook_engine import _answer_hook_text, build_hook_profile


def test_build_hook_profile_is_deterministic_for_same_inputs() -> None:
    first = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=12,
        mood={"energy": 0.5, "valence": 0.62, "arousal": 0.48},
    )
    second = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=12,
        mood={"energy": 0.5, "valence": 0.62, "arousal": 0.48},
    )

    assert first == second


def test_hook_profile_has_answer_material() -> None:
    profile = build_hook_profile(
        family="drift",
        progression_profile="settling",
        cadence_state="wind_down",
        song_num=4,
        mood={"energy": 0.21, "valence": 0.44, "arousal": 0.18},
    )

    assert profile.anchor_degrees
    assert profile.answer_degrees
    assert profile.anchor_degrees != profile.answer_degrees
    assert profile.title
    assert profile.text_hook


def test_repertoire_hint_biases_title_and_hook() -> None:
    base = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=8,
        mood={"energy": 0.48, "valence": 0.58, "arousal": 0.44},
    )
    influenced = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=8,
        mood={"energy": 0.48, "valence": 0.58, "arousal": 0.44},
        repertoire_hint={
            "source_title": "Quiet Machines",
            "hook_text": "hold the light",
            "hook_class": "contour",
            "progression_profile": "settling",
            "mode": "answer",
        },
    )

    assert influenced.title != base.title
    assert influenced.text_hook != base.text_hook
    assert influenced.title.split()[-1] in {"Light", "Lamps", "Windows", "Glass"}


def test_answer_hook_text_uses_phrase_level_transform_for_known_lines() -> None:
    answer = _answer_hook_text(
        "answer the room",
        family="bloom",
        cadence_state="occupied_day",
        song_num=18,
        mood={"energy": 0.58, "valence": 0.66, "arousal": 0.52},
    )
    line = _answer_hook_text(
        "keep the line open",
        family="ember",
        cadence_state="occupied_day",
        song_num=9,
        mood={"energy": 0.42, "valence": 0.55, "arousal": 0.38},
    )

    assert answer in {"keep the room open", "let the room answer", "leave the room awake"}
    assert line in {"leave the line open", "let the line ring", "let the line widen"}


def test_answer_hook_text_preserves_unknown_phrase_grammar() -> None:
    assert (
        _answer_hook_text(
            "carry the lantern",
            family="drift",
            cadence_state="wind_down",
            song_num=5,
            mood={"energy": 0.21, "valence": 0.44, "arousal": 0.18},
        )
        == "carry the lantern"
    )


def test_answer_hook_text_is_deterministic_but_not_single_template() -> None:
    first = _answer_hook_text(
        "answer the room",
        family="bloom",
        cadence_state="occupied_day",
        song_num=18,
        mood={"energy": 0.58, "valence": 0.66, "arousal": 0.52},
    )
    second = _answer_hook_text(
        "answer the room",
        family="bloom",
        cadence_state="occupied_day",
        song_num=18,
        mood={"energy": 0.58, "valence": 0.66, "arousal": 0.52},
    )
    shifted = _answer_hook_text(
        "answer the room",
        family="bloom",
        cadence_state="occupied_day",
        song_num=19,
        mood={"energy": 0.58, "valence": 0.66, "arousal": 0.52},
    )

    assert first == second
    assert shifted in {"keep the room open", "let the room answer", "leave the room awake"}
    assert shifted != first


def test_repertoire_answer_mode_avoids_awkward_again_phrases() -> None:
    profile = build_hook_profile(
        family="drift",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=18,
        mood={"energy": 0.41, "valence": 0.54, "arousal": 0.38},
        repertoire_hint={
            "source_title": "Soft Rooms",
            "hook_text": "answer the room",
            "hook_class": "lyric",
            "mode": "answer",
        },
    )

    assert profile.text_hook in {"keep the room open", "let the room answer", "leave the room awake"}
    assert "again" not in profile.text_hook


def test_answer_hook_text_repairs_rough_legacy_phrases() -> None:
    line = _answer_hook_text(
        "carry the line wide",
        family="drift",
        cadence_state="occupied_day",
        song_num=14,
        mood={"energy": 0.44, "valence": 0.59, "arousal": 0.41},
    )
    room = _answer_hook_text(
        "open the room open",
        family="drift",
        cadence_state="occupied_day",
        song_num=14,
        mood={"energy": 0.44, "valence": 0.59, "arousal": 0.41},
    )

    assert line in {"leave the line open", "let the line ring", "let the line widen"}
    assert room in {"keep the room open", "let the room answer", "leave the room awake"}
    assert line != "carry the line wide"
    assert room != "open the room open"


def test_repertoire_recall_mode_sanitizes_rough_hint_phrases() -> None:
    profile = build_hook_profile(
        family="drift",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=19,
        mood={"energy": 0.44, "valence": 0.59, "arousal": 0.41},
        repertoire_hint={
            "source_title": "Wandering Rooms",
            "hook_text": "carry the line wide",
            "hook_class": "lyric",
            "mode": "recall",
        },
    )

    assert profile.text_hook in {
        "keep the line open",
        "leave the line open",
        "let the line ring",
        "let the line widen",
    }
    assert "carry the line wide" not in profile.text_hook


def test_title_noun_tracks_generated_hook_image_field() -> None:
    profile = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=12,
        mood={"energy": 0.5, "valence": 0.62, "arousal": 0.48},
    )

    noun = profile.title.split()[-1]
    if "light" in profile.text_hook.lower():
        assert noun in {"Light", "Lamps", "Windows", "Glass"}
    elif "line" in profile.text_hook.lower():
        assert noun in {"Lines", "Threads", "Wires", "Circuits"}
    elif "room" in profile.text_hook.lower():
        assert noun in {"Rooms", "Windows", "Corners", "Thresholds"}
    else:
        raise AssertionError(f"unexpected hook text for coherence test: {profile.text_hook}")


def test_title_modifier_tracks_generated_hook_image_field() -> None:
    profile = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=12,
        mood={"energy": 0.5, "valence": 0.62, "arousal": 0.48},
    )

    modifier = profile.title.split()[0]
    if "light" in profile.text_hook.lower():
        assert modifier in {"Bright", "Clear", "Pale", "Glass"}
    elif "line" in profile.text_hook.lower():
        assert modifier in {"Open", "Bright", "Fine", "Electric"}
    elif "room" in profile.text_hook.lower():
        assert modifier in {"Open", "Quiet", "Near", "Inner"}
    else:
        raise AssertionError(f"unexpected hook text for coherence test: {profile.text_hook}")


def test_repertoire_hint_prefers_hook_image_field_over_generic_source_title() -> None:
    profile = build_hook_profile(
        family="drift",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=19,
        mood={"energy": 0.44, "valence": 0.59, "arousal": 0.41},
        repertoire_hint={
            "source_title": "Wandering Machines",
            "hook_text": "keep the line open",
            "hook_class": "lyric",
            "mode": "recall",
        },
    )

    assert profile.text_hook == "keep the line open"
    assert profile.title.split()[0] in {"Open", "Bright", "Fine", "Electric"}
    assert profile.title.split()[-1] in {"Lines", "Threads", "Wires", "Circuits"}


def test_settling_light_hook_prefers_softer_title_phrase() -> None:
    profile = build_hook_profile(
        family="ember",
        progression_profile="settling",
        cadence_state="wind_down",
        song_num=13,
        mood={"energy": 0.24, "valence": 0.52, "arousal": 0.21},
        repertoire_hint={
            "source_title": "Bright Machines",
            "hook_text": "hold the light",
            "hook_class": "lyric",
            "mode": "recall",
        },
    )

    assert profile.text_hook == "hold the light"
    assert profile.title in {"Pale Lamps", "Low Light", "Quiet Glass", "Soft Windows"}


def test_lift_line_hook_prefers_more_kinetic_title_phrase() -> None:
    profile = build_hook_profile(
        family="pulse",
        progression_profile="lift",
        cadence_state="occupied_day",
        song_num=21,
        mood={"energy": 0.68, "valence": 0.66, "arousal": 0.74},
        repertoire_hint={
            "source_title": "Quiet Rooms",
            "hook_text": "keep the line open",
            "hook_class": "rhythmic",
            "mode": "answer",
        },
    )

    assert profile.title in {"Electric Circuits", "Bright Wires", "Open Threads", "Moving Lines"}


def test_title_generation_avoids_exact_repertoire_title_repeat() -> None:
    profile = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=12,
        mood={"energy": 0.5, "valence": 0.62, "arousal": 0.48},
        repertoire_hint={
            "source_title": "Fine Lines",
            "hook_text": "keep the line open",
            "hook_class": "lyric",
            "mode": "recall",
        },
    )

    assert profile.text_hook == "keep the line open"
    assert profile.title != "Fine Lines"
    assert profile.title.split()[-1] in {"Lines", "Threads", "Wires", "Circuits"}


def test_light_titles_avoid_weak_glass_windows_pairing() -> None:
    profile = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=16,
        mood={"energy": 0.5, "valence": 0.62, "arousal": 0.48},
        repertoire_hint={
            "source_title": "Warm Figures",
            "hook_text": "hold the light",
            "hook_class": "lyric",
            "mode": "recall",
        },
    )

    assert profile.text_hook == "hold the light"
    assert profile.title != "Glass Windows"
    assert profile.title in {"Bright Glass", "Clear Windows", "Pale Lamps", "Low Light"}


def test_equally_valid_title_phrases_rotate_across_song_numbers() -> None:
    first = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=12,
        mood={"energy": 0.5, "valence": 0.62, "arousal": 0.48},
    )
    second = build_hook_profile(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=14,
        mood={"energy": 0.5, "valence": 0.62, "arousal": 0.48},
    )

    assert first.title != second.title
