"""Tests for the EMSD capstone cycle planner."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.capstone_engine import build_capstone_cycle


def test_capstone_cycle_builds_five_linked_phases() -> None:
    plan = build_capstone_cycle(
        cadence_state="occupied_day",
        occupancy_state="occupied_active",
        theramini_present=True,
        repertoire_songs=[{"family": "bloom", "patch_name": "house_garden", "title": "Quiet Rooms", "hook_text": "keep the room open"}],
    )

    assert [phase.phase_name for phase in plan.phases] == [
        "Divination",
        "Emergence",
        "Conversation",
        "Convergence",
        "Crystallization",
    ]
    assert plan.phases[0].sampling.source.name == "room_mic"
    assert plan.phases[2].arc.density_target > plan.phases[0].arc.density_target
    assert plan.marathon_distinctness_axes
    assert plan.identity.statement


def test_capstone_cycle_prefers_room_mic_in_late_phases_for_lived_in_states() -> None:
    plan = build_capstone_cycle(
        cadence_state="occupied_day",
        occupancy_state="occupied_quiet",
        theramini_present=False,
        repertoire_songs=[],
    )

    assert plan.phases[3].sampling.source.name == "room_mic"
    assert plan.phases[4].sampling.source.name == "room_mic"


def test_capstone_cycle_keeps_self_bus_for_away_practice_late_phases() -> None:
    plan = build_capstone_cycle(
        cadence_state="away_practice",
        occupancy_state="likely_away",
        theramini_present=False,
        repertoire_songs=[],
    )

    assert plan.phases[3].sampling.source.name == "self_bus"
    assert plan.phases[4].sampling.source.name == "self_bus"


class TestCapstoneCycleEndToEnd:
    """End-to-end checks for the public capstone-cycle planner."""

    def test_all_phases_expose_linked_capstone_contracts(self) -> None:
        plan = build_capstone_cycle(
            cadence_state="occupied_day",
            occupancy_state="occupied_active",
            theramini_present=True,
            repertoire_songs=[
                {
                    "family": "bloom",
                    "patch_name": "house_garden",
                    "title": "Quiet Rooms",
                    "hook_text": "keep the room open",
                }
            ],
        )
        expected = {
            "Divination": ("drift", "house_monastery", "room_mic"),
            "Emergence": ("ember", "house_chamber", "room_mic"),
            "Conversation": ("bloom", "house_garden", "theramini_in"),
            "Convergence": ("pulse", "house_procession", "room_mic"),
            "Crystallization": ("nocturne", "house_monastery", "room_mic"),
        }

        observed_names: list[str] = []
        for phase in plan.phases:
            family_name, patch_name, source_name = expected[phase.phase_name]
            observed_names.append(phase.phase_name)
            assert phase.family_name == family_name
            assert phase.patch_name == patch_name
            assert phase.arc.phase.name == phase.phase_name
            assert phase.palette.patch_name == patch_name
            assert phase.palette.primary_voices
            assert phase.mix.cadence_state == "occupied_day"
            assert phase.mix.patch_name == patch_name
            assert phase.mix.dynamics is not None
            assert phase.mix.spatial is not None
            assert phase.mix.mastering is not None
            assert phase.sampling.source.name == source_name
            assert phase.sampling.cadence_state == "occupied_day"
            assert phase.dsp.phase_name == phase.phase_name
            assert phase.dsp.blocks
        assert observed_names == list(expected)

    def test_phase_order_density_and_distinctness_form_complete_cycle(self) -> None:
        plan = build_capstone_cycle(
            cadence_state="occupied_day",
            occupancy_state="occupied_quiet",
            theramini_present=False,
            repertoire_songs=[],
        )
        phase_names = [phase.phase_name for phase in plan.phases]
        densities = {phase.phase_name: phase.arc.density_target for phase in plan.phases}
        starts = [phase.arc.phase.start_minute for phase in plan.phases]
        ends = [phase.arc.phase.end_minute for phase in plan.phases]

        for earlier_end, later_start in zip(ends, starts[1:]):
            assert earlier_end <= later_start
        assert phase_names == [
            "Divination",
            "Emergence",
            "Conversation",
            "Convergence",
            "Crystallization",
        ]
        assert densities["Conversation"] == max(densities.values())
        assert densities["Divination"] < densities["Emergence"]
        assert densities["Crystallization"] < densities["Convergence"]
        assert set(plan.marathon_distinctness_axes) == {
            "family",
            "patch",
            "sampling",
            "dsp",
            "mix",
        }
        assert len({phase.family_name for phase in plan.phases}) == 5
        assert len({phase.patch_name for phase in plan.phases}) >= 4

    def test_occupied_theramini_path_activates_dialogue_phase(self) -> None:
        plan = build_capstone_cycle(
            cadence_state="occupied_day",
            occupancy_state="occupied_active",
            theramini_present=True,
            repertoire_songs=[],
        )
        phase_by_name = {phase.phase_name: phase for phase in plan.phases}
        dialogue = phase_by_name["Conversation"]
        return_phase = phase_by_name["Convergence"]

        assert dialogue.sampling.source.name == "theramini_in"
        assert dialogue.dsp.source_focus == "theramini_in"
        assert "parallel_delay" in dialogue.dsp.blocks
        assert dialogue.arc.density_target > phase_by_name["Divination"].arc.density_target
        for phase in plan.phases:
            if phase.phase_name in {"Conversation", "Convergence"}:
                assert phase.mix.theramini_duck_db > 0.0
            else:
                assert phase.mix.theramini_duck_db == 0.0
        assert return_phase.sampling.source.name == "room_mic"
        assert return_phase.dsp.source_focus == "room_mic"

    def test_away_practice_retargets_late_sample_and_dsp_paths(self) -> None:
        plan = build_capstone_cycle(
            cadence_state="away_practice",
            occupancy_state="likely_away",
            theramini_present=False,
            repertoire_songs=[],
        )
        late_names = {"Convergence", "Crystallization"}

        for phase in plan.phases:
            assert "granular_cloud" in phase.sampling.transforms
            assert "reverse_accents" in phase.sampling.transforms
            assert phase.mix.target_lufs == -15.0
            assert phase.mix.theramini_duck_db == 0.0
            if phase.phase_name in late_names:
                assert phase.sampling.source.name == "self_bus"
                assert phase.dsp.source_focus == "self_bus"
            else:
                assert phase.sampling.source.name in {"room_mic", "theramini_in"}
        conversation = next(phase for phase in plan.phases if phase.phase_name == "Conversation")
        assert "diffuse_feedback" in conversation.dsp.blocks

    def test_quiet_cadences_reduce_density_and_mix_loudness(self) -> None:
        occupied = build_capstone_cycle(
            cadence_state="occupied_day",
            occupancy_state="occupied_quiet",
            theramini_present=False,
            repertoire_songs=[],
        )

        for cadence_state in ("sleep", "wind_down"):
            quiet = build_capstone_cycle(
                cadence_state=cadence_state,
                occupancy_state="likely_away",
                theramini_present=False,
                repertoire_songs=[],
            )
            for quiet_phase, occupied_phase in zip(quiet.phases, occupied.phases):
                assert quiet_phase.phase_name == occupied_phase.phase_name
                assert quiet_phase.arc.density_target < occupied_phase.arc.density_target
                assert quiet_phase.mix.target_lufs < occupied_phase.mix.target_lufs
                assert quiet_phase.mix.dynamics is not None
                assert occupied_phase.mix.dynamics is not None
                assert (
                    quiet_phase.mix.dynamics.dynamic_range_db
                    >= occupied_phase.mix.dynamics.dynamic_range_db
                )
                assert quiet_phase.sampling.density < occupied_phase.sampling.density

    def test_repertoire_identity_summarizes_families_patches_and_images(self) -> None:
        repertoire_songs = [
            {
                "family": "drift",
                "patch_name": "house_monastery",
                "title": "Thread Room",
                "hook_text": "hold the line through the threshold",
            },
            {
                "family": "drift",
                "patch_name": "house_monastery",
                "title": "Wire Lamp",
                "hook_text": "follow the light line",
            },
            {
                "family": "bloom",
                "patch_name": "house_garden",
                "title": "Garden Signal",
                "hook_text": "keep the room open",
            },
        ]

        plan = build_capstone_cycle(
            cadence_state="occupied_day",
            occupancy_state="occupied_active",
            theramini_present=True,
            repertoire_songs=repertoire_songs,
        )

        assert plan.identity.signature_families == ("drift", "bloom")
        assert plan.identity.signature_patches == ("house_monastery", "house_garden")
        assert plan.identity.signature_images[0] == "room"
        for token in ("drift", "house_monastery", "room"):
            assert token in plan.identity.statement

    def test_cycle_outputs_json_safe_diagnostics(self) -> None:
        plan = build_capstone_cycle(
            cadence_state="occupied_day",
            occupancy_state="occupied_active",
            theramini_present=True,
            repertoire_songs=[
                {
                    "family": "bloom",
                    "patch_name": "house_garden",
                    "title": "Quiet Rooms",
                    "hook_text": "keep the room open",
                }
            ],
        )
        payload: list[dict[str, object]] = []
        for phase in plan.phases:
            assert phase.mix.mastering is not None
            payload.append(
                {
                    "phase": phase.phase_name,
                    "family": phase.family_name,
                    "patch": phase.patch_name,
                    "arc": {
                        "density": phase.arc.density_target,
                        "mutation": phase.arc.mutation_rate,
                        "max_roles": phase.arc.max_active_roles,
                    },
                    "palette": {
                        "primary": list(phase.palette.primary_voices),
                        "secondary": list(phase.palette.secondary_voices),
                        "focus": phase.palette.study_focus,
                    },
                    "mix": {
                        "target_lufs": phase.mix.target_lufs,
                        "duck_db": phase.mix.theramini_duck_db,
                        "true_peak": list(phase.mix.mastering.true_peak_range_dbtp),
                    },
                    "sampling": {
                        "source": phase.sampling.source.name,
                        "path": phase.sampling.source.capture_path,
                        "transforms": list(phase.sampling.transforms),
                        "density": phase.sampling.density,
                    },
                    "dsp": {
                        "focus": phase.dsp.source_focus,
                        "blocks": list(phase.dsp.blocks),
                        "visual_bias": dict(phase.dsp.visual_bias),
                    },
                }
            )
        diagnostics = {"identity": plan.identity.statement, "phases": payload}
        decoded = json.loads(json.dumps(diagnostics, sort_keys=True))
        assert decoded["identity"] == plan.identity.statement
        assert len(decoded["phases"]) == 5
        assert decoded["phases"][2]["sampling"]["source"] == "theramini_in"
        assert decoded["phases"][2]["mix"]["duck_db"] > 0.0

    def test_cycle_modes_preserve_phase_count_and_valid_ranges(self) -> None:
        scenarios = [
            ("occupied_day", "occupied_active", True),
            ("away_practice", "likely_away", False),
            ("sleep", "likely_away", False),
            ("wind_down", "occupied_quiet", False),
        ]

        for cadence_state, occupancy_state, theramini_present in scenarios:
            plan = build_capstone_cycle(
                cadence_state=cadence_state,
                occupancy_state=occupancy_state,
                theramini_present=theramini_present,
                repertoire_songs=[],
            )
            assert len(plan.phases) == 5
            assert plan.identity.statement
            for phase in plan.phases:
                assert 0.0 < phase.arc.density_target <= 1.0
                assert 0.0 < phase.arc.mutation_rate <= 1.0
                assert 1 <= phase.arc.max_active_roles <= 4
                assert phase.sampling.source.capture_path.endswith(".wav")
                assert 0.04 <= phase.sampling.density <= 0.95
                assert phase.sampling.buffer_seconds > 0.0
                assert phase.mix.peak_ceiling_dbtp <= -1.0
                assert {target.role for target in phase.mix.voice_targets} == {
                    "bass",
                    "melody",
                    "counter",
                    "color",
                }
                assert 0.0 <= phase.dsp.visual_bias["density"] <= 1.0
                assert 0.0 <= phase.dsp.visual_bias["motion"] <= 1.0
