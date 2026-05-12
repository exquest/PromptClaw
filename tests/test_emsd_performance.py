"""Tests for EMSD-informed playback shaping."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.emsd_performance import render_adjustments_for_event
from senseweave.emsd_runtime import build_live_emsd_context


def test_divination_environment_softens_and_widens_color_material() -> None:
    context = build_live_emsd_context(
        cadence_state="wind_down",
        occupancy_state="occupied_quiet",
        family_name="drift",
        progression_profile="settling",
        patch_name="house_monastery",
        song_num=3,
        theramini_present=False,
        repertoire_songs=[],
        now_seconds=2 * 60,
    )

    adjustment = render_adjustments_for_event(
        role="color",
        voice_name="breath",
        frequency_hz=1400.0,
        context=context,
        theramini_active=False,
    )

    assert adjustment.amp_multiplier < 1.0
    assert adjustment.release_multiplier > 1.0
    assert adjustment.brightness_multiplier < 1.0
    assert adjustment.verb_add > 0.0
    assert adjustment.sample_capture_path.endswith("room_capture.wav")


def test_conversation_with_theramini_ducks_frontline_material() -> None:
    context = build_live_emsd_context(
        cadence_state="occupied_day",
        occupancy_state="occupied_active",
        family_name="bloom",
        progression_profile="lift",
        patch_name="house_garden",
        song_num=11,
        theramini_present=True,
        repertoire_songs=[],
        attention_score=0.8,
        now_seconds=13 * 60,
    )

    without_duck = render_adjustments_for_event(
        role="melody",
        voice_name="pluck",
        frequency_hz=660.0,
        context=context,
        theramini_active=False,
    )
    with_duck = render_adjustments_for_event(
        role="melody",
        voice_name="pluck",
        frequency_hz=660.0,
        context=context,
        theramini_active=True,
    )

    assert with_duck.amp_multiplier < without_duck.amp_multiplier
    assert with_duck.dly_add >= without_duck.dly_add
    assert with_duck.saturation_add >= without_duck.saturation_add


def test_conversation_dsp_blocks_add_delay_and_detune_to_counter_lines() -> None:
    context = build_live_emsd_context(
        cadence_state="occupied_day",
        occupancy_state="occupied_active",
        family_name="bloom",
        progression_profile="open_day",
        patch_name="house_garden",
        song_num=7,
        theramini_present=True,
        repertoire_songs=[],
        attention_score=0.9,
        now_seconds=14 * 60,
    )

    adjustment = render_adjustments_for_event(
        role="counter",
        voice_name="choir",
        frequency_hz=880.0,
        context=context,
        theramini_active=False,
    )

    assert "parallel_delay" in adjustment.dsp_blocks
    assert adjustment.dly_add > 0.0
    assert adjustment.detune_add > 0.0


def test_away_practice_mix_does_not_hard_clamp_frontline_roles() -> None:
    context = build_live_emsd_context(
        cadence_state="away_practice",
        occupancy_state="likely_away",
        family_name="forge",
        progression_profile="experiment",
        patch_name="house_workshop",
        song_num=1,
        theramini_present=False,
        repertoire_songs=[],
        base_density_bias=0.02,
        attention_score=0.4,
        now_seconds=1776295532.5143123,
    )

    bass = render_adjustments_for_event(
        role="bass",
        voice_name="bowed",
        frequency_hz=110.0,
        context=context,
        theramini_active=False,
    )
    melody = render_adjustments_for_event(
        role="melody",
        voice_name="pluck",
        frequency_hz=440.0,
        context=context,
        theramini_active=False,
    )
    color = render_adjustments_for_event(
        role="color",
        voice_name="breath",
        frequency_hz=880.0,
        context=context,
        theramini_active=False,
    )

    assert bass.amp_multiplier < 1.2
    assert melody.amp_multiplier < 1.2
    assert color.amp_multiplier >= 0.8
