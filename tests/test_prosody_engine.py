"""Tests for prosody_engine.py -- short musical language cues."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.prosody_engine import compose_scene_caption, compose_song_title


def test_compose_song_title_is_short_and_nonempty() -> None:
    title = compose_song_title(
        family="ember",
        progression_profile="open_day",
        cadence_state="occupied_day",
        song_num=7,
        practice_block="",
    )

    assert title
    assert len(title) <= 40


def test_compose_scene_caption_reflects_scene_or_hook() -> None:
    caption = compose_scene_caption(
        title="Quiet Machines",
        scene_name="Theme",
        text_hook="hold the light",
        cadence_state="occupied_day",
        section_function="tonic",
        cadence_type="authentic",
        practice_block="",
    )

    assert caption
    assert len(caption) <= 48
    assert "light" in caption.lower() or "theme" in caption.lower()


def test_compose_scene_caption_varies_same_hook_by_scene_role() -> None:
    theme = compose_scene_caption(
        title="Glass Machines",
        scene_name="Theme",
        text_hook="keep the line open",
        cadence_state="occupied_day",
        section_function="tonic",
        cadence_type="authentic",
        practice_block="",
    )
    recap = compose_scene_caption(
        title="Glass Machines",
        scene_name="Recap",
        text_hook="keep the line open",
        cadence_state="occupied_day",
        section_function="return",
        cadence_type="authentic",
        practice_block="",
    )
    afterglow = compose_scene_caption(
        title="Glass Machines",
        scene_name="Afterglow",
        text_hook="keep the line open",
        cadence_state="occupied_day",
        section_function="suspended",
        cadence_type="authentic",
        practice_block="",
    )

    assert theme == "keep the line open"
    assert recap == "the line stays open"
    assert afterglow == "line at rest"


def test_compose_scene_caption_falls_back_cleanly_for_unknown_hooks() -> None:
    recap = compose_scene_caption(
        title="Quiet Machines",
        scene_name="Recap",
        text_hook="carry the lantern",
        cadence_state="occupied_day",
        section_function="return",
        cadence_type="deceptive",
        practice_block="",
    )
    afterglow = compose_scene_caption(
        title="Quiet Machines",
        scene_name="Afterglow",
        text_hook="carry the lantern",
        cadence_state="occupied_day",
        section_function="suspended",
        cadence_type="deceptive",
        practice_block="",
    )

    assert recap == "Recap: carry the lantern"
    assert afterglow == "Afterglow: suspended"


def test_compose_scene_caption_uses_cadence_type_for_afterglow() -> None:
    dominant = compose_scene_caption(
        title="Glass Machines",
        scene_name="Afterglow",
        text_hook="keep the line open",
        cadence_state="occupied_day",
        section_function="suspended",
        cadence_type="half",
        practice_block="",
    )
    plagal = compose_scene_caption(
        title="Glass Machines",
        scene_name="Afterglow",
        text_hook="keep the line open",
        cadence_state="occupied_day",
        section_function="suspended",
        cadence_type="plagal",
        practice_block="",
    )

    assert dominant == "line still reaching"
    assert plagal == "line settling open"


def test_compose_scene_caption_uses_cadence_type_for_resolution() -> None:
    authentic = compose_scene_caption(
        title="Open Machines",
        scene_name="Resolution",
        text_hook="keep the room open",
        cadence_state="occupied_day",
        section_function="tonic",
        cadence_type="authentic",
        practice_block="",
    )
    deceptive = compose_scene_caption(
        title="Open Machines",
        scene_name="Resolution",
        text_hook="keep the room open",
        cadence_state="occupied_day",
        section_function="tonic",
        cadence_type="deceptive",
        practice_block="",
    )

    assert authentic == "room at rest"
    assert deceptive == "room turned aside"


def test_compose_scene_caption_reacts_to_sparse_orchestration() -> None:
    sparse = compose_scene_caption(
        title="Glass Machines",
        scene_name="Theme",
        text_hook="keep the line open",
        cadence_state="occupied_day",
        section_function="tonic",
        cadence_type="authentic",
        patch_name="house_monastery",
        lane_count=2,
        practice_block="",
    )

    assert sparse == "line open"


def test_compose_scene_caption_reacts_to_dense_orchestration() -> None:
    dense = compose_scene_caption(
        title="Open Rooms",
        scene_name="Theme",
        text_hook="keep the room open",
        cadence_state="occupied_day",
        section_function="tonic",
        cadence_type="authentic",
        patch_name="house_workshop",
        lane_count=4,
        practice_block="",
    )

    assert dense == "keep the whole room open"
