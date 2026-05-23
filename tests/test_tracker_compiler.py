from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from cypherclaw import midi_vocabulary_store as store
from cypherclaw.composer_vocabulary_bridge import scene_vocabulary_log_suffix
from inner_life.world_model import WorldModel
from senseweave.form_grammar import plan_form
from senseweave.music_tracker_runtime import build_scene_events
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece
from senseweave.recursive_composer import compose_score_tree
from senseweave.score_tree import (
    PRODUCTION_COURSE_KEYS,
    MeterSceneValue,
    MeterTrajectory,
    PhraseNode,
    SectionNode,
)
from senseweave.tracker_compiler import (
    _transition_profile_for_section,
    compile_score_tree_to_tracker,
    estimate_tracker_song_duration_s,
)


def test_tracker_compiler_preserves_structure_and_targets_duration() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.41,
        song_num=9,
        hour=16,
    )
    world = WorldModel(
        observer_description="open room with bright windows",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="day",
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=9,
        mood={"energy": 0.52, "valence": 0.54, "arousal": 0.41},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.52, "valence": 0.54, "arousal": 0.41},
        family_name="ember",
        patch_name="house_chamber",
        cadence_state="occupied_day",
    )

    assert len(compiled.tracker_song.scenes) == len(tree.sections)
    assert compiled.source_score.metadata["song_title"] == tree.title
    assert json.loads(compiled.source_score.metadata["section_functions"]) == {
        section.scene_name: section.function for section in tree.sections
    }
    section_cadences = {
        section.scene_name: section.cadence_type for section in tree.sections
    }
    assert json.loads(compiled.source_score.metadata["section_cadences"]) == section_cadences
    estimated = estimate_tracker_song_duration_s(compiled.tracker_song)
    assert estimated >= commission.duration_target_s * 0.6
    assert estimated <= commission.duration_target_s * 1.4
    assert any(scene.metadata.get("section_function") for scene in compiled.tracker_song.scenes)
    assert all(
        scene.metadata.get("cadence_type") == section_cadences[scene.name]
        for scene in compiled.tracker_song.scenes
    )
    feature_steps = [
        step
        for scene in compiled.tracker_song.scenes
        for lane in scene.pattern.lanes
        for step in lane.steps
        if lane.role == "melody" and "harmonic_charge" in step.metadata
    ]
    assert feature_steps
    feature_metadata = feature_steps[0].metadata
    assert 0.0 <= float(feature_metadata["harmonic_charge"]) <= 1.0
    assert 0.0 <= float(feature_metadata["melodic_charge"]) <= 1.0
    assert 0.0 <= float(feature_metadata["metric_weight"]) <= 1.0
    assert feature_metadata["is_cadential"] in {"true", "false"}
    assert "contour_apex" in feature_metadata


def test_tracker_compiler_fills_long_sections_with_repeated_motion_not_drones() -> None:
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
    world = WorldModel(
        observer_description="empty workshop room",
        cadence_state="away_practice",
        day_phase="day",
        time_of_day="day",
        occupancy_state="likely_away",
        attention_score=0.4,
        experimentation_bias=0.85,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="forge",
        cadence_state="away_practice",
        progression_profile="experiment",
    )
    form = plan_form(commission=commission, brief=brief, family="forge")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="forge",
        cadence_state="away_practice",
        progression_profile="experiment",
        song_num=1,
        mood={"energy": 0.27, "valence": 0.35, "arousal": 0.35},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.27, "valence": 0.35, "arousal": 0.35},
        family_name="forge",
        patch_name="house_workshop",
        cadence_state="away_practice",
        progression_profile="experiment",
    )

    emergence = compiled.tracker_song.scenes[0]
    events = build_scene_events(emergence)

    assert int(emergence.metadata["repeat_count"]) > 1
    assert any(event.role == "bass" for event in events)
    assert len(events) >= 14
    assert max(event.duration_seconds for event in events) < 8.0


def test_tracker_compiler_writes_distinct_section_melodies() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.52,
        narrative_pressure=0.62,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 12,
        song_num=5,
        hour=15,
    )
    world = WorldModel(
        observer_description="bright room with movement near the desk",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="day",
        occupancy_state="occupied_active",
        attention_score=0.52,
        experimentation_bias=0.62,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="bloom",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="bloom")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="bloom",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=5,
        mood={"energy": 0.52, "valence": 0.64, "arousal": 0.48},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.52, "valence": 0.64, "arousal": 0.48},
        family_name="bloom",
        patch_name="house_garden",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    scenes = {scene.name: scene for scene in compiled.tracker_song.scenes}
    theme = scenes["Theme"]
    development = scenes["Development"]
    recap = scenes["Recap"]

    def melody_signature(scene):
        lane = next(lane for lane in scene.pattern.lanes if lane.role == "melody")
        return tuple((step.scale_degree, step.length_rows, step.accent) for step in lane.steps[:8])

    assert melody_signature(development) != melody_signature(theme)
    assert melody_signature(recap) != melody_signature(theme)


def test_tracker_compiler_varies_repeat_cycles_inside_long_sections() -> None:
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
    world = WorldModel(
        observer_description="empty workshop room",
        cadence_state="away_practice",
        day_phase="day",
        time_of_day="day",
        occupancy_state="likely_away",
        attention_score=0.4,
        experimentation_bias=0.85,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="forge",
        cadence_state="away_practice",
        progression_profile="experiment",
    )
    form = plan_form(commission=commission, brief=brief, family="forge")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="forge",
        cadence_state="away_practice",
        progression_profile="experiment",
        song_num=1,
        mood={"energy": 0.27, "valence": 0.35, "arousal": 0.35},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.27, "valence": 0.35, "arousal": 0.35},
        family_name="forge",
        patch_name="house_workshop",
        cadence_state="away_practice",
        progression_profile="experiment",
    )

    emergence = compiled.tracker_song.scenes[0]
    melody = next(lane for lane in emergence.pattern.lanes if lane.role == "melody")
    cycles: dict[str, list[int]] = {}
    for step in melody.steps:
        cycle = step.metadata.get("repeat_cycle", "0")
        cycles.setdefault(cycle, []).append(step.scale_degree)

    signatures = {tuple(values[:6]) for key, values in cycles.items() if key in {"0", "1", "2"}}
    assert len(signatures) >= 2


def test_tracker_compiler_builds_internal_phrase_families_inside_development() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.55,
        narrative_pressure=0.72,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 22,
        song_num=6,
        hour=18,
    )
    world = WorldModel(
        observer_description="active studio room with light moving across the desk",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.55,
        experimentation_bias=0.72,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=6,
        mood={"energy": 0.61, "valence": 0.58, "arousal": 0.56},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.61, "valence": 0.58, "arousal": 0.56},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    development = next(scene for scene in compiled.tracker_song.scenes if scene.name == "Development")
    melody = next(lane for lane in development.pattern.lanes if lane.role == "melody")
    families: dict[str, list[int]] = {}
    for step in melody.steps:
        family = step.metadata.get("internal_phrase_family")
        if family is not None and step.metadata.get("repeat_cycle", "0") == "0":
            families.setdefault(family, []).append(step.scale_degree)

    assert set(families) >= {"A", "A_prime", "B"}
    signatures = {family: tuple(values[:6]) for family, values in families.items()}
    assert signatures["A"] != signatures["A_prime"]
    assert signatures["A"] != signatures["B"]


def test_tracker_compiler_coordinates_internal_phrase_families_across_roles() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.58,
        narrative_pressure=0.76,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 24,
        song_num=7,
        hour=19,
    )
    world = WorldModel(
        observer_description="room active at dusk with repeating light and movement",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.58,
        experimentation_bias=0.76,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=7,
        mood={"energy": 0.63, "valence": 0.58, "arousal": 0.59},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.63, "valence": 0.58, "arousal": 0.59},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    development = next(scene for scene in compiled.tracker_song.scenes if scene.name == "Development")
    lanes = {lane.role: lane for lane in development.pattern.lanes}
    assert {"melody", "bass", "counter", "color"} <= set(lanes)

    expected_families = {"A", "A_prime", "B"}
    for role in ("melody", "bass", "counter", "color"):
        families = {
            step.metadata.get("internal_phrase_family")
            for step in lanes[role].steps
        }
        assert families >= expected_families

    for family in expected_families:
        role_roots: dict[str, int] = {}
        for role, lane in lanes.items():
            step = next(
                step
                for step in lane.steps
                if step.metadata.get("internal_phrase_family") == family
            )
            role_roots[role] = int(step.metadata["internal_family_root_degree"])

        root = next(iter(role_roots.values()))
        assert role_roots == {role: root for role in role_roots}

        bass_step = next(
            step
            for step in lanes["bass"].steps
            if step.metadata.get("internal_phrase_family") == family
        )
        assert bass_step.scale_degree == root


def test_tracker_compiler_authors_section_tails_toward_next_section() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.6,
        narrative_pressure=0.78,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 26,
        song_num=8,
        hour=20,
    )
    world = WorldModel(
        observer_description="active room moving toward evening focus",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.6,
        experimentation_bias=0.78,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=8,
        mood={"energy": 0.66, "valence": 0.58, "arousal": 0.61},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.66, "valence": 0.58, "arousal": 0.61},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    scenes = compiled.tracker_song.scenes
    scene_by_name = {scene.name: scene for scene in scenes}
    first_transition = next((scene for scene in scenes[:-1] if any(lane.role == "bass" for lane in scene.pattern.lanes)), None)
    assert first_transition is not None
    next_scene = scenes[scenes.index(first_transition) + 1]
    bass_lane = next(lane for lane in first_transition.pattern.lanes if lane.role == "bass")
    final_bass_step = max(bass_lane.steps, key=lambda step: (step.row, step.length_rows))

    assert first_transition.metadata["transition_target_scene"] == next_scene.name
    assert first_transition.metadata["transition_target_function"] == scene_by_name[next_scene.name].metadata["section_function"]
    assert final_bass_step.metadata["transition_role"] == "preparation"
    assert final_bass_step.metadata["transition_target_scene"] == next_scene.name
    assert final_bass_step.scale_degree == int(final_bass_step.metadata["transition_target_root_degree"])

    for current, target in zip(scenes, scenes[1:]):
        bass = next((lane for lane in current.pattern.lanes if lane.role == "bass" and lane.steps), None)
        if bass is None:
            continue
        final_step = max(bass.steps, key=lambda step: (step.row, step.length_rows))
        assert current.metadata["transition_target_scene"] == target.name
        assert final_step.metadata["transition_role"] == "preparation"
        assert final_step.metadata["transition_target_scene"] == target.name


def test_transition_planner_emits_valid_phase_transition_metadata() -> None:
    def section(
        name: str,
        function: str,
        *,
        harmonic_role: str,
        cadence_type: str,
        groove_state: str,
        transform_strength: str,
        motif_refs: tuple[str, ...],
    ) -> SectionNode:
        return SectionNode(
            section_id=name.lower(),
            scene_name=name,
            function=function,
            target_duration_s=24.0,
            phrases=[
                PhraseNode(
                    phrase_id=f"{name.lower()}-phrase",
                    function=function,
                    motif_refs=motif_refs,
                    target_duration_s=12.0,
                    transform_ops=(),
                )
            ],
            harmonic_role=harmonic_role,
            cadence_type=cadence_type,
            groove_state=groove_state,
            transform_strength=transform_strength,
        )

    score_tree = SimpleNamespace(
        arrangement_plan={},
        sections=[
            section(
                "Theme",
                "statement",
                harmonic_role="tonic",
                cadence_type="authentic",
                groove_state="pulse",
                transform_strength="none",
                motif_refs=("m1",),
            ),
            section(
                "Arrival",
                "arrival",
                harmonic_role="dominant",
                cadence_type="half",
                groove_state="lift",
                transform_strength="bright",
                motif_refs=("m1",),
            ),
            section(
                "Turn",
                "turn",
                harmonic_role="borrowed",
                cadence_type="deceptive",
                groove_state="half_time",
                transform_strength="shadow",
                motif_refs=("m2",),
            ),
        ],
    )
    supported_techniques = {
        "pivot_event",
        "breath_silence",
        "metric_modulation",
        "timbral_morph",
        "harmonic_pivot_chord",
        "common_tone_bridge",
    }

    profiles = [
        _transition_profile_for_section(score_tree, index)
        for index in range(len(score_tree.sections) - 1)
    ]
    emitted_techniques = {
        technique
        for profile in profiles
        for technique in json.loads(profile["transition_techniques"])
    }

    assert supported_techniques <= emitted_techniques
    for profile in profiles:
        techniques = json.loads(profile["transition_techniques"])
        continuity = json.loads(profile["transition_continuity_elements"])
        assert profile["transition_technique"] in techniques
        assert set(techniques) <= supported_techniques
        assert profile["transition_hard_cut"] == "false"
        assert continuity
        assert profile["transition_common_tone_degree"].isdigit()
        assert profile["transition_pivot_chord_degree"].isdigit()


def test_tracker_compiler_stages_support_lane_entrances_inside_long_development() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.62,
        narrative_pressure=0.82,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 30,
        song_num=9,
        hour=21,
    )
    world = WorldModel(
        observer_description="room active with a long evening build",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.62,
        experimentation_bias=0.82,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=9,
        mood={"energy": 0.68, "valence": 0.6, "arousal": 0.64},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.68, "valence": 0.6, "arousal": 0.64},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    development = next(scene for scene in compiled.tracker_song.scenes if scene.name == "Development")
    assert int(development.metadata["repeat_count"]) >= 3
    lanes = {lane.role: lane for lane in development.pattern.lanes}
    bass_first_row = min(step.row for step in lanes["bass"].steps)
    melody_first_row = min(step.row for step in lanes["melody"].steps)
    counter_first_row = min(step.row for step in lanes["counter"].steps)
    color_first_row = min(step.row for step in lanes["color"].steps)

    assert bass_first_row == 0
    # Melody may start a small number of rows late due to default polyrhythmic-cross
    # lane phase offsets (DEFAULT_LANE_PHASE_OFFSETS in music_tracker.py).
    assert 0 <= melody_first_row <= 4
    assert counter_first_row > bass_first_row
    assert color_first_row > melody_first_row
    assert int(lanes["counter"].metadata["entry_cycle"]) >= 1
    assert int(lanes["color"].metadata["entry_cycle"]) >= 1


def test_tracker_compiler_develops_motifs_by_section_function() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.64,
        narrative_pressure=0.84,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 32,
        song_num=10,
        hour=19,
    )
    world = WorldModel(
        observer_description="room in an active evening arc",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.64,
        experimentation_bias=0.84,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=10,
        mood={"energy": 0.69, "valence": 0.6, "arousal": 0.65},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.69, "valence": 0.6, "arousal": 0.65},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    scenes = {scene.name: scene for scene in compiled.tracker_song.scenes}
    theme = scenes["Theme"]
    development = scenes["Development"]
    bridge = scenes["Bridge"]
    recap = scenes["Recap"]

    assert theme.metadata["motif_development"] == "statement"
    assert development.metadata["motif_development"] == "sequence_fragment"
    assert bridge.metadata["motif_development"] == "contrast_inversion"
    assert recap.metadata["motif_development"] == "recall_answer"

    def first_melody_degrees(scene):
        lane = next(lane for lane in scene.pattern.lanes if lane.role == "melody")
        return tuple(step.scale_degree for step in lane.steps[:8])

    assert first_melody_degrees(theme) != first_melody_degrees(development)
    assert first_melody_degrees(theme) != first_melody_degrees(bridge)
    assert set(first_melody_degrees(theme)) & set(first_melody_degrees(recap))


def test_tracker_compiler_applies_section_local_progressions_to_bass() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.66,
        narrative_pressure=0.86,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 34,
        song_num=11,
        hour=20,
    )
    world = WorldModel(
        observer_description="room active with harmonic motion",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.66,
        experimentation_bias=0.86,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=11,
        mood={"energy": 0.7, "valence": 0.61, "arousal": 0.66},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.7, "valence": 0.61, "arousal": 0.66},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    development = next(scene for scene in compiled.tracker_song.scenes if scene.name == "Development")
    progression = [int(value) for value in json.loads(development.metadata["section_progression"])]
    bass = next(lane for lane in development.pattern.lanes if lane.role == "bass")
    first_cycle_roots = [
        step
        for step in bass.steps
        if step.metadata.get("repeat_cycle", "0") == "0"
        and step.metadata.get("section_progression_role") == "root"
    ]

    assert len(progression) >= 4
    assert [step.scale_degree for step in first_cycle_roots[: len(progression)]] == progression
    assert [int(step.metadata["section_progression_root"]) for step in first_cycle_roots[: len(progression)]] == progression


def test_tracker_compiler_develops_rhythm_by_section_function() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.67,
        narrative_pressure=0.88,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 36,
        song_num=12,
        hour=21,
    )
    world = WorldModel(
        observer_description="room active with rhythmic pressure",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.67,
        experimentation_bias=0.88,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=12,
        mood={"energy": 0.72, "valence": 0.62, "arousal": 0.69},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.72, "valence": 0.62, "arousal": 0.69},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    scenes = {scene.name: scene for scene in compiled.tracker_song.scenes}
    assert scenes["Theme"].metadata["rhythm_development"] == "steady_statement"
    assert scenes["Development"].metadata["rhythm_development"] == "syncopated_fragment"
    assert scenes["Bridge"].metadata["rhythm_development"] == "half_time_displacement"
    assert scenes["Recap"].metadata["rhythm_development"] == "recall_groove"

    def melody_lengths(scene):
        lane = next(lane for lane in scene.pattern.lanes if lane.role == "melody")
        return tuple(step.length_rows for step in lane.steps[:8])

    assert melody_lengths(scenes["Theme"]) != melody_lengths(scenes["Development"])
    assert melody_lengths(scenes["Theme"]) != melody_lengths(scenes["Bridge"])
    first_development = next(lane for lane in scenes["Development"].pattern.lanes if lane.role == "melody").steps[0]
    first_recap = next(lane for lane in scenes["Recap"].pattern.lanes if lane.role == "melody").steps[0]
    assert first_development.metadata["rhythm_development"] == "syncopated_fragment"
    assert first_recap.metadata["rhythm_development"] == "recall_groove"


def test_tracker_compiler_syncopates_development_onsets() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.69,
        narrative_pressure=0.9,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 38,
        song_num=13,
        hour=22,
    )
    world = WorldModel(
        observer_description="room active with offbeat movement",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.69,
        experimentation_bias=0.9,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=13,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
    )

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    development = next(scene for scene in compiled.tracker_song.scenes if scene.name == "Development")
    melody = next(lane for lane in development.pattern.lanes if lane.role == "melody")
    first_cycle_rows = [
        step.row
        for step in melody.steps
        if step.metadata.get("repeat_cycle", "0") == "0"
    ]

    # First cycle's melody rows may start slightly late due to default lane phase
    # offsets (polyrhythmic-cross feel). Pre-offset assertion was == 0.
    assert min(first_cycle_rows) <= 4
    assert any(row % development.rows_per_beat not in {0} for row in first_cycle_rows[1:8])
    assert melody.metadata["rhythm_development"] == "syncopated_fragment"


def test_score_tree_arrangement_plan_requests_sample_gesture_voice() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.6,
        narrative_pressure=0.8,
        occupancy_state="occupied_active",
        song_num=14,
        hour=20,
    )
    world = WorldModel(
        observer_description="room with quick contact-mic taps",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.6,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=14,
        mood={"energy": 0.64, "valence": 0.58, "arousal": 0.68},
    )
    tree.arrangement_plan["sample_gestures"] = {
        "Development": {
            "source": "contact_mic",
            "mode": "grain_cloud",
            "voice": "sample_grain",
            "transforms": ["slice_rearrange", "granular_cloud", "reverse_accents"],
            "density": 0.44,
            "max_events": 6,
        }
    }

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.64, "valence": 0.58, "arousal": 0.68},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    development = next(scene for scene in compiled.tracker_song.scenes if scene.name == "Development")
    sample_lane = next(lane for lane in development.pattern.lanes if lane.role == "sample")

    assert sample_lane.voice == "sample_grain"
    assert sample_lane.metadata["sample_gesture_source"] == "contact_mic"
    assert development.metadata["sample_gesture_mode"] == "grain_cloud"
    assert len(sample_lane.steps) <= 6


def test_tracker_compiler_executes_proxy_arc_production_targets() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="weekend",
        attention_score=0.72,
        narrative_pressure=0.96,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 80,
        song_num=30,
        hour=22,
        elapsed_minutes=0.0,
        cycle_minutes=5.0,
    )
    world = WorldModel(
        observer_description="active room with a full installation arc",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.72,
        experimentation_bias=0.96,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=30,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
    )

    production_arc = tree.arrangement_plan["production_arc"]
    contour = json.loads(tree.metadata["arc_phase_contour"])
    assert list(dict.fromkeys(contour)) == [
        "Divination",
        "Emergence",
        "Conversation",
        "Convergence",
        "Crystallization",
    ]
    assert set(production_arc) == {section.scene_name for section in tree.sections}

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    scene_by_name = {scene.name: scene for scene in compiled.tracker_song.scenes}
    for section in tree.sections:
        expected = production_arc[section.scene_name]
        scene = scene_by_name[section.scene_name]
        automation = {lane.name: lane.default for lane in scene.pattern.automation}

        assert scene.metadata["arc_phase"] == expected["arc_phase"]
        assert scene.metadata["arc_dynamic"] == expected["arc_dynamic"]
        assert scene.metadata["arc_harmonic"] == expected["arc_harmonic"]
        assert scene.metadata["arc_rhythm"] == expected["arc_rhythm"]
        assert scene.metadata["arc_timbre"] == expected["arc_timbre"]
        assert scene.metadata["arc_spatial"] == expected["arc_spatial"]
        assert scene.metadata["arc_synthesis"] == expected["arc_synthesis"]
        assert automation["compression"] == float(expected["arc_compression"])
        assert automation["senseweave"] == float(expected["arc_senseweave"])

    for current, target in zip(compiled.tracker_song.scenes, compiled.tracker_song.scenes[1:]):
        if current.metadata["arc_phase"] == target.metadata["arc_phase"]:
            continue
        assert current.metadata["transition_hard_cut"] == "true" or json.loads(
            current.metadata["transition_continuity_elements"]
        )


def test_tracker_compiler_carries_meter_trajectory_scene_metadata() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="weekend",
        attention_score=0.72,
        narrative_pressure=0.96,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 80,
        song_num=30,
        hour=22,
        elapsed_minutes=0.0,
        cycle_minutes=5.0,
    )
    world = WorldModel(
        observer_description="active room with a full installation arc",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.72,
        experimentation_bias=0.96,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=30,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
    )
    trajectory = MeterTrajectory(
        trajectory_id="meter-arc-compiler",
        arc_plan="ascending_complexity",
        arc_phase="Convergence",
        scene_values=tuple(
            MeterSceneValue(
                scene_name=section.scene_name,
                meter=("4/4", "15/16", "7/8")[index % 3],
                subdivision="dotted" if index % 3 == 1 else "straight",
                groove_timing="metric_modulation" if index % 3 else "grid",
                metric_modulation="5:4" if index % 3 == 1 else "",
            )
            for index, section in enumerate(tree.sections)
        ),
        rationale="compiler metadata propagation fixture",
    )
    tree.meter_trajectory = trajectory
    for section in tree.sections:
        section.scene_metadata.update(trajectory.metadata_for_scene(section.scene_name))

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    scene_by_name = {scene.name: scene for scene in compiled.tracker_song.scenes}
    for section in tree.sections:
        scene = scene_by_name[section.scene_name]
        assert scene.metadata["meter_trajectory_id"] == "meter-arc-compiler"
        assert scene.metadata["meter_trajectory_arc_plan"] == "ascending_complexity"
        assert scene.metadata["meter_trajectory_scene"] == section.scene_name
        assert scene.metadata["meter_trajectory_meter"] == section.scene_metadata["meter_trajectory_meter"]
        assert json.loads(scene.metadata["meter_trajectory_path"])
        entry = json.loads(scene.metadata["meter_trajectory_entry"])
        assert entry["scene_name"] == section.scene_name
        assert entry["meter"] == section.scene_metadata["meter_trajectory_meter"]


def test_production_course_metadata_survives_compose_compile_schedule() -> None:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="weekend",
        attention_score=0.72,
        narrative_pressure=0.96,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 80,
        song_num=30,
        hour=22,
        elapsed_minutes=0.0,
        cycle_minutes=5.0,
    )
    world = WorldModel(
        observer_description="active room with a full installation arc",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.72,
        experimentation_bias=0.96,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=30,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
    )

    for section in tree.sections:
        assert section.production_course, f"{section.scene_name} missing production_course"
        for key in PRODUCTION_COURSE_KEYS:
            assert key in section.production_course, f"{section.scene_name} missing {key}"
            assert section.production_course[key], f"{section.scene_name} empty {key}"

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    courses = json.loads(compiled.source_score.metadata["section_production_courses"])
    assert set(courses) == {section.scene_name for section in tree.sections}

    scene_by_name = {scene.name: scene for scene in compiled.tracker_song.scenes}
    for section in tree.sections:
        scene = scene_by_name[section.scene_name]
        for key in PRODUCTION_COURSE_KEYS:
            meta_key = f"production_{key}"
            assert meta_key in scene.metadata, f"{scene.name} missing {meta_key}"
            assert scene.metadata[meta_key] == section.production_course[key]

    last_scene = compiled.tracker_song.scenes[-1]
    assert last_scene.metadata["production_transition_type"] == "terminal"

    non_terminal = [
        scene for scene in compiled.tracker_song.scenes
        if scene.metadata["production_transition_type"] != "terminal"
    ]
    assert non_terminal
    for scene in non_terminal:
        assert scene.metadata["production_transition_type"] in {
            "seamless", "modulation", "breath", "crossfade",
        }


def _vocabulary_tree(tmp_path: Path) -> tuple[object, int]:
    db_path = tmp_path / "midi_vocabulary.sqlite"
    conn = store.connect(db_path)
    try:
        fragment_id = store.insert_fragment(
            conn,
            source_file="seed.mid",
            kind="melodic_motif",
            interval_pattern=[2, 2, 3],
            duration_pattern=[1.0, 0.5, 0.5, 2.0],
            source_key="C major",
            source_tempo=120.0,
            harmonic_context={"pitch_classes": [0, 2, 4, 7]},
        )
    finally:
        conn.close()

    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="weekend",
        attention_score=0.72,
        narrative_pressure=0.96,
        occupancy_state="occupied_active",
        song_num=31,
        hour=17,
    )
    world = WorldModel(
        observer_description="active room with a fragment vocabulary",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.72,
        experimentation_bias=0.96,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    form = plan_form(commission=commission, brief=brief, family="ember")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="ember",
        cadence_state="occupied_day",
        progression_profile="lift",
        song_num=31,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
        composition_seed="t-016-compiler",
        vocabulary_db_path=db_path,
        vocabulary_curiosity=1.0,
    )
    return tree, fragment_id


def test_compiled_scene_carries_vocabulary_fragment_citation(tmp_path: Path) -> None:
    tree, fragment_id = _vocabulary_tree(tmp_path)

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )

    scene = compiled.tracker_song.scenes[0]
    assert scene.metadata["vocabulary_fragment_id"] == str(fragment_id)
    assert scene.metadata["vocabulary_fragment_kind"] == "melodic_motif"
    assert scene.metadata["vocabulary_fragment_source"] == "seed.mid"
    assert f"vocabulary_fragment_id={fragment_id}" in scene_vocabulary_log_suffix(scene.metadata)

    melody_lane = next(lane for lane in scene.pattern.lanes if lane.role == "melody")
    assert melody_lane.metadata["vocabulary_fragment_id"] == str(fragment_id)
    assert melody_lane.metadata["vocabulary_transform"] == "degree_seed"
    assert any(
        step.metadata.get("vocabulary_fragment_id") == str(fragment_id)
        for step in melody_lane.steps
    )
