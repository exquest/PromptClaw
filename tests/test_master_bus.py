"""Tests for EMSD master-bus scene control."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.emsd_runtime import build_live_emsd_context
from senseweave.master_bus import (
    DEFAULT_MASTER_BUS_VALUES,
    MASTER_NODE_ID,
    master_bus_n_set_args,
    master_bus_s_new_args,
    master_bus_values_for_scene,
)
from senseweave.music_tracker import build_korsakov_tracker_song
from senseweave.generative_scores import Note, Phrase, Score


def _scene_score() -> Score:
    return Score(
        phrases=[
            Phrase(notes=[Note(1, 1.0, True), Note(3, 1.0, False)], voice="pluck", dynamic="mf", role="melody"),
            Phrase(notes=[Note(1, 1.0, True), Note(5, 1.0, False)], voice="gong", dynamic="mp", role="bass"),
        ],
        key="C",
        tempo_bpm=96.0,
        mood="calm",
        created_at=0.0,
        metadata={"patch_name": "house_garden", "cadence_state": "occupied_day", "progression_profile": "open_day"},
    )


def test_master_bus_values_consume_mix_and_scene_automation() -> None:
    context = build_live_emsd_context(
        cadence_state="occupied_day",
        occupancy_state="occupied_active",
        family_name="bloom",
        progression_profile="open_day",
        patch_name="house_garden",
        song_num=5,
        theramini_present=True,
        repertoire_songs=[],
        attention_score=0.8,
        now_seconds=13 * 60,
    )
    scene = build_korsakov_tracker_song(_scene_score()).scenes[2]

    values = master_bus_values_for_scene(scene, context=context, theramini_active=True)
    args = master_bus_n_set_args(scene, context=context, theramini_active=True)

    assert args[0] == MASTER_NODE_ID
    assert "amp" in args
    assert "reverb" in args
    assert values["amp"] > 0.0
    assert values["drive"] > 0.0
    assert values["room"] >= values["reverb"]


def test_master_bus_values_can_follow_runtime_automation_overrides() -> None:
    scene = build_korsakov_tracker_song(_scene_score()).scenes[2]

    default_values = master_bus_values_for_scene(scene, context=None)
    faded_values = master_bus_values_for_scene(
        scene,
        context=None,
        automation_values={"density": 0.2, "master_amp": 0.24, "reverb_send": 0.36},
    )

    assert faded_values["amp"] < default_values["amp"]
    assert faded_values["reverb"] > default_values["reverb"]


def test_sampler_amp_tracks_master_amp_not_density() -> None:
    scene = build_korsakov_tracker_song(_scene_score()).scenes[2]
    context = build_live_emsd_context(
        cadence_state="occupied_day",
        occupancy_state="occupied_active",
        family_name="bloom",
        progression_profile="open_day",
        patch_name="house_garden",
        song_num=5,
        theramini_present=True,
        repertoire_songs=[],
        attention_score=0.8,
        now_seconds=13 * 60,
    )

    for runtime_context in (None, context):
        sparse = master_bus_values_for_scene(
            scene,
            context=runtime_context,
            automation_values={"density": 0.12, "master_amp": 0.24},
        )
        dense = master_bus_values_for_scene(
            scene,
            context=runtime_context,
            automation_values={"density": 0.9, "master_amp": 0.24},
        )
        hot = master_bus_values_for_scene(
            scene,
            context=runtime_context,
            automation_values={"density": 0.12, "master_amp": 1.4},
        )
        quiet = master_bus_values_for_scene(
            scene,
            context=runtime_context,
            automation_values={"density": 0.9, "master_amp": 0.0},
        )

        assert sparse["sampler_amp"] == dense["sampler_amp"] == 0.24
        assert hot["sampler_amp"] == 1.0
        assert quiet["sampler_amp"] == 0.05


def test_master_bus_seed_args_target_master_node() -> None:
    args = master_bus_s_new_args()

    assert args[:4] == ["sw_master_smooth", MASTER_NODE_ID, 1, 0]
    assert args[4::2] == [
        "drive",
        "warmth",
        "reverb",
        "room",
        "amp",
        "sampler_amp",
        "sampler_bypass_comp",
    ]
    assert args[5::2] == [
        DEFAULT_MASTER_BUS_VALUES["drive"],
        DEFAULT_MASTER_BUS_VALUES["warmth"],
        DEFAULT_MASTER_BUS_VALUES["reverb"],
        DEFAULT_MASTER_BUS_VALUES["room"],
        DEFAULT_MASTER_BUS_VALUES["amp"],
        DEFAULT_MASTER_BUS_VALUES["sampler_amp"],
        DEFAULT_MASTER_BUS_VALUES["sampler_bypass_comp"],
    ]


def test_sampler_bypass_comp_defaults_to_bypass_and_follows_automation() -> None:
    scene = build_korsakov_tracker_song(_scene_score()).scenes[2]
    context = build_live_emsd_context(
        cadence_state="occupied_day",
        occupancy_state="occupied_active",
        family_name="bloom",
        progression_profile="open_day",
        patch_name="house_garden",
        song_num=5,
        theramini_present=True,
        repertoire_songs=[],
        attention_score=0.8,
        now_seconds=13 * 60,
    )

    for runtime_context in (None, context):
        default_values = master_bus_values_for_scene(scene, context=runtime_context)
        overridden = master_bus_values_for_scene(
            scene,
            context=runtime_context,
            automation_values={"sampler_bypass_comp": 0.0},
        )

        assert default_values["sampler_bypass_comp"] == 1.0
        assert overridden["sampler_bypass_comp"] == 0.0


def test_master_bus_n_set_args_target_master_node_and_preserve_param_order() -> None:
    scene = build_korsakov_tracker_song(_scene_score()).scenes[2]
    values = master_bus_values_for_scene(scene, context=None)
    args = master_bus_n_set_args(scene, context=None)

    assert args[0] == MASTER_NODE_ID
    assert args[1::2] == [
        "amp",
        "sampler_amp",
        "sampler_bypass_comp",
        "drive",
        "warmth",
        "reverb",
        "room",
    ]
    assert args[2::2] == [
        values["amp"],
        values["sampler_amp"],
        values["sampler_bypass_comp"],
        values["drive"],
        values["warmth"],
        values["reverb"],
        values["room"],
    ]
