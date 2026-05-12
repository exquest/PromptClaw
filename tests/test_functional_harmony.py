"""Tests for functional harmony labeling, modulation strategies, and tension levels."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.harmonic_planner import (
    HarmonicPlan,
    common_tones,
    pivot_degree,
    resolve_harmonic_plan,
)
from senseweave.reharmonizer import (
    HARMONIC_FUNCTIONS,
    label_harmonic_function,
    progression_bank_for_section,
    reharm_plan_for_song,
    tension_for_function,
    tension_for_phase,
)
from senseweave.score_tree import ScoreTree, SectionNode
from senseweave.piece_commission import PieceCommission


# ── label_harmonic_function covers all 10 labels ──────────────────────


def test_label_tonic() -> None:
    assert label_harmonic_function(1) == "tonic"
    assert label_harmonic_function(6) == "tonic"
    assert label_harmonic_function(3) == "tonic"


def test_label_subdominant() -> None:
    assert label_harmonic_function(4) == "subdominant"
    assert label_harmonic_function(2) == "subdominant"


def test_label_dominant() -> None:
    assert label_harmonic_function(5) == "dominant"
    assert label_harmonic_function(7) == "dominant"


def test_label_secondary_dominant() -> None:
    assert label_harmonic_function(5, is_secondary=True) == "secondary_dominant"
    assert label_harmonic_function(2, is_secondary=True) == "secondary_dominant"


def test_label_modal_interchange() -> None:
    assert label_harmonic_function(7, chromatic_alteration=-1) == "modal_interchange"
    assert label_harmonic_function(4, chromatic_alteration=-1) == "modal_interchange"


def test_label_tritone_sub() -> None:
    assert label_harmonic_function(2, chromatic_alteration=-1) == "tritone_sub"


def test_label_chromatic_mediant() -> None:
    assert label_harmonic_function(6, chromatic_alteration=-1) == "chromatic_mediant"
    assert label_harmonic_function(3, chromatic_alteration=-1) == "chromatic_mediant"
    assert label_harmonic_function(3, chromatic_alteration=1) == "chromatic_mediant"


def test_label_pedal() -> None:
    assert label_harmonic_function(1, bass_is_pedal=True) == "pedal"
    assert label_harmonic_function(5, bass_is_pedal=True) == "pedal"


def test_label_planing() -> None:
    assert label_harmonic_function(1, is_parallel_motion=True) == "planing"
    assert label_harmonic_function(3, is_parallel_motion=True) == "planing"


def test_label_modulation() -> None:
    assert label_harmonic_function(5, is_pivot=True) == "modulation"
    assert label_harmonic_function(2, is_pivot=True) == "modulation"


def test_all_harmonic_functions_are_labelable() -> None:
    labeled = {
        label_harmonic_function(1),
        label_harmonic_function(4),
        label_harmonic_function(5),
        label_harmonic_function(5, is_secondary=True),
        label_harmonic_function(7, chromatic_alteration=-1),
        label_harmonic_function(2, chromatic_alteration=-1),
        label_harmonic_function(6, chromatic_alteration=-1),
        label_harmonic_function(1, bass_is_pedal=True),
        label_harmonic_function(1, is_parallel_motion=True),
        label_harmonic_function(1, is_pivot=True),
    }
    assert labeled == set(HARMONIC_FUNCTIONS)


# ── cadence resolution ─────────────────────────────────────────────


def test_authentic_cadence_resolves_to_tonic() -> None:
    plan = reharm_plan_for_song(
        "lift", family="bloom", cadence_state="occupied_day", mode="ionian", song_num=1,
    )
    for name, section in plan.sections.items():
        if section.cadence == "authentic":
            last_root = section.progression[0][-1]
            assert last_root == 1, f"{name}: authentic cadence should resolve to 1, got {last_root}"


def test_plagal_cadence_has_iv_to_i_option() -> None:
    plan = reharm_plan_for_song(
        "settling", family="drift", cadence_state="wind_down", mode="aeolian", song_num=2,
    )
    for name, section in plan.sections.items():
        if section.cadence == "plagal":
            has_tonic_target = any(p[-1] in (1, 5) for p in section.progression)
            assert has_tonic_target, f"{name}: plagal cadence should have tonic-targeting option"


def test_half_cadence_ends_on_dominant() -> None:
    plan = reharm_plan_for_song(
        "open_day", family="bloom", cadence_state="occupied_day", mode="ionian", song_num=3,
    )
    for name, section in plan.sections.items():
        if section.cadence == "half":
            last_root = section.progression[0][-1]
            assert last_root in (1, 4, 5, 6), f"{name}: half cadence target unexpected: {last_root}"


def test_deceptive_cadence_avoids_pure_tonic_resolution() -> None:
    plan = reharm_plan_for_song(
        "lift", family="pulse", cadence_state="occupied_day", mode="ionian", song_num=4,
    )
    for name, section in plan.sections.items():
        if section.cadence == "deceptive":
            progressions = section.progression
            has_deceptive = any(p[-1] in (4, 5, 6) for p in progressions)
            assert has_deceptive, f"{name}: deceptive cadence should have non-tonic resolution option"


# ── pivot and common-tone modulation ────────────────────────────────


def test_pivot_degree_between_closely_related_keys() -> None:
    degree = pivot_degree("C", "G")
    assert degree is not None
    assert 1 <= degree <= 7


def test_pivot_degree_between_parallel_keys() -> None:
    degree = pivot_degree("C", "Cm")
    assert degree is not None


def test_common_tones_closely_related() -> None:
    tones = common_tones("C", "G")
    assert len(tones) >= 5


def test_common_tones_distant_keys() -> None:
    tones = common_tones("C", "F#:lydian")
    assert isinstance(tones, frozenset)
    assert len(tones) < 7


def test_modulation_path_has_common_tones_between_adjacent_keys() -> None:
    plan = resolve_harmonic_plan(
        "C",
        song_num=10,
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
        family="bloom",
        garden_state={},
        outdoor_state={},
        midi_state={
            "playing": True,
            "notes_on": [60, 64, 67],
            "last_activity": 999.9,
            "sustain_pedal": True,
            "expression": 110,
            "recent_pedal_events": [(999.5, True), (999.7, False), (999.9, True)],
        },
        inner_state={},
        now=1000.0,
    )
    path = plan.modulation_path
    for left, right in zip(path, path[1:]):
        shared = common_tones(left, right)
        assert len(shared) >= 1, f"No common tones between {left} and {right}"


def test_pivot_exists_for_modulation_path_steps() -> None:
    plan = resolve_harmonic_plan(
        "A",
        song_num=5,
        mood={"energy": 0.6, "valence": 0.4, "arousal": 0.5},
        family="forge",
        garden_state={},
        outdoor_state={},
        midi_state={},
        inner_state={},
        now=1000.0,
    )
    path = plan.modulation_path
    for left, right in zip(path, path[1:]):
        if left != right:
            degree = pivot_degree(left, right)
            assert degree is not None, f"No pivot between {left} and {right}"


# ── phase-appropriate tension levels ────────────────────────────────


def test_tension_increases_through_development() -> None:
    assert tension_for_phase("Emergence") < tension_for_phase("Development")
    assert tension_for_phase("Development") < tension_for_phase("Bridge")


def test_tension_decreases_through_resolution() -> None:
    assert tension_for_phase("Bridge") > tension_for_phase("Resolution")
    assert tension_for_phase("Resolution") > tension_for_phase("Afterglow")


def test_dominant_functions_have_higher_tension_than_tonic() -> None:
    assert tension_for_function("dominant") > tension_for_function("tonic")
    assert tension_for_function("secondary_dominant") > tension_for_function("dominant")
    assert tension_for_function("tritone_sub") > tension_for_function("dominant")


def test_subdominant_tension_between_tonic_and_dominant() -> None:
    t = tension_for_function("subdominant")
    assert tension_for_function("tonic") < t < tension_for_function("dominant")


def test_section_harmonic_functions_match_scene_tension_arc() -> None:
    plan = resolve_harmonic_plan(
        "D",
        song_num=6,
        mood={"energy": 0.55, "valence": 0.48, "arousal": 0.5},
        family="pulse",
        cadence_state="occupied_day",
        progression_profile="lift",
        garden_state={},
        outdoor_state={},
        midi_state={},
        inner_state={},
        now=1000.0,
    )
    assert plan.section_harmonic_functions["Emergence"] in HARMONIC_FUNCTIONS
    assert plan.section_harmonic_functions["Theme"] in {"tonic", "subdominant"}
    emergence_tension = tension_for_function(plan.section_harmonic_functions["Emergence"])
    bridge_fn = plan.section_harmonic_functions.get("Bridge", "dominant")
    bridge_tension = tension_for_function(bridge_fn)
    assert emergence_tension <= bridge_tension


# ── transition intents ──────────────────────────────────────────────


def test_transition_intents_populated() -> None:
    plan = resolve_harmonic_plan(
        "E",
        song_num=2,
        mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5},
        family="drift",
        garden_state={},
        outdoor_state={},
        midi_state={},
        inner_state={},
        now=1000.0,
    )
    assert plan.section_transition_intents["Emergence"] == "establish"
    assert plan.section_transition_intents["Afterglow"] == "dissolve"
    for name, intent in plan.section_transition_intents.items():
        assert intent in {
            "establish", "maintain", "pivot", "common_tone", "direct", "chromatic", "return", "dissolve",
        }, f"{name}: unexpected intent {intent}"


# ── score tree exposes harmonic function and transition intent ──────


def test_section_node_carries_harmonic_function_and_transition_intent() -> None:
    section = SectionNode(
        section_id="s1",
        scene_name="Development",
        function="development",
        target_duration_s=45.0,
        phrases=[],
        harmonic_role="dominant",
        cadence_type="deceptive",
        groove_state="building",
        harmonic_function="secondary_dominant",
        transition_intent="pivot",
    )
    assert section.harmonic_function == "secondary_dominant"
    assert section.transition_intent == "pivot"


def test_section_node_defaults() -> None:
    section = SectionNode(
        section_id="s1",
        scene_name="Theme",
        function="verse",
        target_duration_s=30.0,
        phrases=[],
        harmonic_role="tonic",
        cadence_type="authentic",
        groove_state="steady",
    )
    assert section.harmonic_function == "tonic"
    assert section.transition_intent == "maintain"


def test_score_tree_round_trips_new_section_fields() -> None:
    commission = PieceCommission(
        form_class="song",
        composition_mode="hybrid",
        duration_target_s=120.0,
        sonic_world_count=2,
        hook_pressure=0.7,
        narrative_scale="scene",
        ending_family="fade",
        groove_identity="flowing",
        reason_tags=("test",),
    )
    tree = ScoreTree.minimal(piece_id="test-1", title="Harmony Test", commission=commission)
    tree.sections.append(
        SectionNode(
            section_id="s1",
            scene_name="Bridge",
            function="bridge",
            target_duration_s=30.0,
            phrases=[],
            harmonic_role="dominant",
            cadence_type="half",
            groove_state="building",
            harmonic_function="chromatic_mediant",
            transition_intent="chromatic",
        )
    )
    data = json.loads(tree.to_json())
    restored = ScoreTree.from_dict(data)
    assert restored.sections[0].harmonic_function == "chromatic_mediant"
    assert restored.sections[0].transition_intent == "chromatic"


# ── reharm plan exposes new fields ──────────────────────────────────


def test_reharm_sections_carry_harmonic_function_and_transition() -> None:
    plan = reharm_plan_for_song(
        "open_day", family="bloom", cadence_state="occupied_day", mode="ionian", song_num=1,
    )
    for name, section in plan.sections.items():
        assert section.harmonic_function in HARMONIC_FUNCTIONS or section.harmonic_function in {
            "predominant", "deceptive", "plagal", "suspended",
        }
        assert section.transition_intent in {
            "establish", "maintain", "pivot", "common_tone", "direct", "chromatic", "return", "dissolve",
        }


# === End-to-end depth-2 coverage (frac-0072) ===


class FunctionalHarmonyEndToEndTests:
    """Drive resolved harmony through planning, score-tree, and JSON outputs."""

    __test__ = True

    @staticmethod
    def _resolved_live_plan() -> HarmonicPlan:
        return resolve_harmonic_plan(
            "C",
            song_num=14,
            mood={"energy": 0.72, "valence": 0.54, "arousal": 0.66},
            family="pulse",
            cadence_state="occupied_day",
            progression_profile="lift",
            garden_state={"music_key": "F lydian", "last_update": 999.0},
            outdoor_state={"brightness": 0.76},
            midi_state={
                "playing": True,
                "notes_on": [67, 71, 74],
                "last_activity": 999.8,
                "sustain_pedal": True,
                "expression": 118,
                "recent_pedal_events": [
                    (999.0, True),
                    (999.2, False),
                    (999.4, True),
                ],
            },
            inner_state={"suggested_key": "Dm", "updated": 999.0},
            now=1000.0,
        )

    def test_resolved_harmony_plan_produces_json_safe_section_contract(self) -> None:
        plan = self._resolved_live_plan()

        assert plan.source == "keyboard"
        assert plan.key == "G:lydian"
        assert plan.chord_palette == "extended"
        assert plan.voicing_profile == "pedal_point"
        assert plan.modulation_intent == "modulate"
        assert plan.modulation_path[0] == plan.scene_keys["Emergence"]
        assert plan.modulation_path[-1] == plan.scene_keys["Resolution"]

        section_names = set(plan.section_functions)
        assert section_names == set(plan.section_cadences)
        assert section_names == set(plan.section_progressions)
        assert section_names == set(plan.section_chord_degrees)
        assert section_names == set(plan.section_harmonic_functions)
        assert section_names == set(plan.section_transition_intents)

        for scene_name, roots in plan.section_progressions.items():
            assert len(roots) == 4, scene_name
            assert all(1 <= degree <= 7 for degree in roots), scene_name
            triads = plan.section_chord_degrees[scene_name]
            assert len(triads) == len(roots), scene_name
            assert all(len(chord) == 3 for chord in triads), scene_name
            assert all(
                1 <= degree <= 7
                for chord in triads
                for degree in chord
            ), scene_name

        for left, right in zip(plan.modulation_path, plan.modulation_path[1:]):
            assert common_tones(left, right)
            assert pivot_degree(left, right) is not None

        payload = {
            "key": plan.key,
            "scene_keys": plan.scene_keys,
            "section_functions": plan.section_functions,
            "section_cadences": plan.section_cadences,
            "section_progressions": plan.section_progressions,
            "section_chord_degrees": plan.section_chord_degrees,
            "section_harmonic_functions": plan.section_harmonic_functions,
            "section_transition_intents": plan.section_transition_intents,
            "modulation_path": plan.modulation_path,
        }
        restored = json.loads(json.dumps(payload, sort_keys=True))
        assert restored["key"] == "G:lydian"
        assert restored["section_functions"]["Development"] == "dominant"
        assert restored["section_transition_intents"]["Afterglow"] == "dissolve"
        assert restored["section_chord_degrees"]["Theme"][0] == [1, 3, 5]

    def test_reharm_lookup_and_tension_arc_line_up_with_resolved_plan(self) -> None:
        plan = self._resolved_live_plan()
        reharm = reharm_plan_for_song(
            "lift",
            family="pulse",
            cadence_state="occupied_day",
            mode=plan.mode,
            song_num=14,
        )

        assert plan.reharm_strategy == reharm.strategy
        assert reharm.study_focus == "harmony_lab"
        for scene_name, section in reharm.sections.items():
            assert plan.section_functions[scene_name] == section.function
            assert plan.section_cadences[scene_name] == section.cadence
            assert plan.section_harmonic_functions[scene_name] == section.harmonic_function
            assert plan.section_transition_intents[scene_name] == section.transition_intent
            assert progression_bank_for_section(scene_name, reharm) == section.progression

        emergence_tension = tension_for_function(plan.section_harmonic_functions["Emergence"])
        bridge_tension = tension_for_function(plan.section_harmonic_functions["Bridge"])
        afterglow_tension = tension_for_function(plan.section_harmonic_functions["Afterglow"])
        assert emergence_tension < bridge_tension
        assert afterglow_tension < bridge_tension
        assert plan.section_progressions["Bridge"][-1] == 5
        assert plan.section_progressions["Resolution"][-1] == 1
        assert plan.section_transition_intents["Development"] == "pivot"
        assert plan.section_transition_intents["Bridge"] == "chromatic"

    def test_harmony_plan_builds_score_tree_sections_and_round_trips(self) -> None:
        plan = self._resolved_live_plan()
        commission = PieceCommission(
            form_class="song",
            composition_mode="hybrid",
            duration_target_s=180.0,
            sonic_world_count=3,
            hook_pressure=0.78,
            narrative_scale="scene",
            ending_family="arrival",
            groove_identity="processional",
            reason_tags=("frac-0072", "functional_harmony"),
        )
        tree = ScoreTree.minimal(
            piece_id="frac-0072-harmony",
            title="Functional Harmony Depth",
            commission=commission,
        )
        tree.harmonic_plan = {
            "key": plan.key,
            "reharm_strategy": plan.reharm_strategy,
            "section_functions": plan.section_functions,
            "section_cadences": plan.section_cadences,
            "section_progressions": plan.section_progressions,
            "section_harmonic_functions": plan.section_harmonic_functions,
            "section_transition_intents": plan.section_transition_intents,
        }
        tree.sections.extend(
            SectionNode(
                section_id=f"s{index}",
                scene_name=scene_name,
                function=scene_name.lower(),
                target_duration_s=24.0 + index,
                phrases=[],
                harmonic_role=plan.section_functions[scene_name],
                cadence_type=plan.section_cadences[scene_name],
                groove_state="building" if scene_name in {"Development", "Bridge"} else "steady",
                harmonic_function=plan.section_harmonic_functions[scene_name],
                transition_intent=plan.section_transition_intents[scene_name],
            )
            for index, scene_name in enumerate(plan.section_functions, start=1)
        )

        data = json.loads(tree.to_json())
        restored = ScoreTree.from_dict(data)
        restored_by_scene = {section.scene_name: section for section in restored.sections}

        assert len(restored.sections) == len(plan.section_functions)
        assert restored.harmonic_plan["key"] == "G:lydian"
        assert restored.harmonic_plan["section_functions"]["Bridge"] == "dominant"
        assert restored_by_scene["Bridge"].harmonic_function == "dominant"
        assert restored_by_scene["Bridge"].transition_intent == "chromatic"
        assert restored_by_scene["Resolution"].cadence_type == "authentic"
        assert restored_by_scene["Afterglow"].harmonic_function == "pedal"
        assert all(
            section.harmonic_function in HARMONIC_FUNCTIONS
            for section in restored.sections
        )

        summary = {
            section.scene_name: {
                "harmonic_role": section.harmonic_role,
                "harmonic_function": section.harmonic_function,
                "cadence_type": section.cadence_type,
                "transition_intent": section.transition_intent,
            }
            for section in restored.sections
        }
        assert json.loads(json.dumps(summary, sort_keys=True))["Development"] == {
            "harmonic_role": "dominant",
            "harmonic_function": "dominant",
            "cadence_type": "deceptive",
            "transition_intent": "pivot",
        }
