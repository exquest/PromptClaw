"""Tests for live EMSD runtime wiring."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.emsd_runtime import build_live_emsd_context, composer_emsd_extras


def test_build_live_emsd_context_tracks_arc_phase_and_density_bias() -> None:
    context = build_live_emsd_context(
        cadence_state="occupied_day",
        occupancy_state="occupied_quiet",
        family_name="bloom",
        progression_profile="open_day",
        patch_name="house_garden",
        song_num=7,
        theramini_present=True,
        repertoire_songs=[
            {
                "title": "Quiet Rooms",
                "family": "bloom",
                "patch_name": "house_garden",
                "hook_text": "keep the room open",
            }
        ],
        base_density_bias=0.04,
        attention_score=0.72,
        now_seconds=13 * 60,
    )

    assert context.arc.phase.name == "Conversation"
    assert context.phase_plan.phase_name == "Conversation"
    assert context.phase_plan.family_name == "bloom"
    assert context.phase_plan.patch_name == "house_garden"
    assert context.density_bias > 0.04
    assert "room" in context.identity.statement.lower()


def test_composer_emsd_extras_exposes_arc_mix_sample_and_identity_fields() -> None:
    context = build_live_emsd_context(
        cadence_state="wind_down",
        occupancy_state="occupied_quiet",
        family_name="drift",
        progression_profile="settling",
        patch_name="house_monastery",
        song_num=12,
        theramini_present=False,
        repertoire_songs=[],
        base_density_bias=0.0,
        attention_score=0.1,
        now_seconds=2 * 60,
    )

    extras = composer_emsd_extras(context)

    assert extras["arc_phase"] == "Divination"
    assert extras["mix_target_lufs"] <= -20.0
    assert extras["sample_source"] == "room_mic"
    assert extras["sample_capture_path"].endswith("room_capture.wav")
    assert extras["sample_refresh_seconds"] == 45
    assert "presence" in extras["sample_roles"]
    assert extras["dsp_source_focus"] == "room_mic"
    assert isinstance(extras["glyph_visual_bias"], dict)
    assert extras["artistic_identity"]
    assert extras["artistic_families"]
    assert extras["artistic_patches"]
    assert extras["artistic_images"]
    assert extras["emsd_density_bias"] == context.density_bias


def test_composer_emsd_extras_exposes_dynamics_and_sidechain_metadata() -> None:
    context = build_live_emsd_context(
        cadence_state="occupied_day",
        occupancy_state="occupied_quiet",
        family_name="bloom",
        progression_profile="open_day",
        patch_name="house_garden",
        song_num=5,
        theramini_present=True,
        repertoire_songs=[],
        now_seconds=13 * 60,
    )

    extras = composer_emsd_extras(context)

    # Dynamics metadata should be present because capstone_engine passes phase_name
    assert extras["mix_dynamic_range_db"] is not None
    assert extras["mix_comp_ratio_phase"] is not None
    assert extras["mix_comp_attack_ms"] is not None
    assert extras["mix_comp_release_ms"] is not None
    assert extras["mix_transient_policy"] in ("preserve", "soften", "shape")
    assert extras["mix_role_frequency_lanes"]["bass"] == ["sub", "bass"]
    assert "air" in extras["mix_role_frequency_lanes"]["texture"]
    production_metadata = extras["mix_production_metadata"]
    for role in ("bass", "pad", "lead", "texture", "noise", "sample", "theramini"):
        assert production_metadata[role]["hpf_hz"] > 0.0
        assert production_metadata[role]["lpf_hz"] > production_metadata[role]["hpf_hz"]
        assert production_metadata[role]["eq_intent"]
    assert isinstance(extras["mix_deference_rules"], list)
    assert len(extras["mix_deference_rules"]) >= 2

    # At least one theramini deference rule and one environmental
    sources = {r["source"] for r in extras["mix_deference_rules"]}
    assert "theramini" in sources
    assert "environmental" in sources

    # Every rule dict has expected keys
    for rule in extras["mix_deference_rules"]:
        assert "source" in rule
        assert "trigger" in rule
        assert "action" in rule
        assert "duck_db" in rule
        assert "priority" in rule
