"""End-to-end production-course integration tests (T-012).

Compose, gate, compile, schedule, and inspect a 5-minute proxy arc
using production-course metadata — no live hardware, mocked inputs.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from inner_life.world_model import WorldModel
from senseweave.composition_gate import evaluate_score_tree
from senseweave.form_grammar import plan_form
from senseweave.music_tracker_runtime import build_scene_events
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece
from senseweave.piece_queue import PieceQueue
from senseweave.recursive_composer import compose_score_tree
from senseweave.repertoire_memory import RepertoireMemory
from senseweave.score_tree import PRODUCTION_COURSE_KEYS
from senseweave.tracker_compiler import (
    compile_score_tree_to_tracker,
    estimate_tracker_song_duration_s,
)


def _compose_5min_proxy_arc():
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
    return tree


def _compile_tree(tree):
    return compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.74, "valence": 0.62, "arousal": 0.72},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )


def test_proxy_arc_composes_gates_compiles_schedules_and_inspects() -> None:
    tree = _compose_5min_proxy_arc()
    report = evaluate_score_tree(tree)
    assert report.approved is True, f"gate failures: {report.failures}"

    compiled = _compile_tree(tree)
    assert compiled.tracker_song.scenes
    estimated = estimate_tracker_song_duration_s(compiled.tracker_song)
    assert estimated > 0


def test_proxy_arc_non_silent_output() -> None:
    tree = _compose_5min_proxy_arc()
    compiled = _compile_tree(tree)

    for scene in compiled.tracker_song.scenes:
        events = build_scene_events(scene)
        assert len(events) >= 2, f"scene {scene.name} has fewer than 2 events"


def test_proxy_arc_no_single_note_long_sections() -> None:
    tree = _compose_5min_proxy_arc()
    compiled = _compile_tree(tree)

    for scene in compiled.tracker_song.scenes:
        melody = next(
            (lane for lane in scene.pattern.lanes if lane.role == "melody"),
            None,
        )
        if melody is None:
            continue
        assert len(melody.steps) >= 2, (
            f"scene {scene.name} melody has only {len(melody.steps)} step(s)"
        )
        max_duration = max(step.length_rows for step in melody.steps)
        total_rows = scene.pattern.rows
        assert max_duration < total_rows * 0.8, (
            f"scene {scene.name} has a single note spanning {max_duration}/{total_rows} rows"
        )


def test_proxy_arc_phase_contour() -> None:
    tree = _compose_5min_proxy_arc()
    contour = json.loads(tree.metadata["arc_phase_contour"])

    assert len(contour) == len(tree.sections)
    unique_phases = list(dict.fromkeys(contour))
    assert unique_phases == [
        "Divination",
        "Emergence",
        "Conversation",
        "Convergence",
        "Crystallization",
    ]


def test_proxy_arc_transition_continuity() -> None:
    tree = _compose_5min_proxy_arc()

    for section in tree.sections:
        tt = section.production_course.get("transition_type", "")
        assert tt, f"section {section.scene_name} missing transition_type"

    last = tree.sections[-1]
    assert last.production_course["transition_type"] == "terminal"

    for section in tree.sections[:-1]:
        assert section.production_course["transition_type"] in {
            "seamless",
            "modulation",
            "breath",
            "crossfade",
        }, f"section {section.scene_name} has unexpected transition_type: {section.production_course['transition_type']}"

    compiled = _compile_tree(tree)
    for scene in compiled.tracker_song.scenes[:-1]:
        continuity_raw = scene.metadata.get("transition_continuity_elements")
        hard_cut = scene.metadata.get("transition_hard_cut")
        assert hard_cut == "true" or (
            continuity_raw and json.loads(continuity_raw)
        ), f"scene {scene.name} has no transition continuity"


def test_proxy_arc_mix_role_allocation() -> None:
    tree = _compose_5min_proxy_arc()
    compiled = _compile_tree(tree)

    for section in tree.sections:
        mix_role = section.production_course.get("mix_role")
        assert mix_role, f"section {section.scene_name} missing mix_role"

    for scene in compiled.tracker_song.scenes:
        meta_role = scene.metadata.get("production_mix_role")
        assert meta_role, f"scene {scene.name} missing production_mix_role in compiled metadata"

    roles_seen = {
        section.production_course["mix_role"] for section in tree.sections
    }
    assert len(roles_seen) >= 2, "expected at least 2 distinct mix roles across sections"


def test_proxy_arc_production_course_all_keys_populated() -> None:
    tree = _compose_5min_proxy_arc()

    for section in tree.sections:
        for key in PRODUCTION_COURSE_KEYS:
            assert key in section.production_course, (
                f"section {section.scene_name} missing production_course key: {key}"
            )
            assert section.production_course[key], (
                f"section {section.scene_name} has empty production_course[{key}]"
            )


def test_proxy_arc_production_course_survives_compile_to_scene_metadata() -> None:
    tree = _compose_5min_proxy_arc()
    compiled = _compile_tree(tree)

    scene_by_name = {scene.name: scene for scene in compiled.tracker_song.scenes}
    for section in tree.sections:
        scene = scene_by_name[section.scene_name]
        for key in PRODUCTION_COURSE_KEYS:
            meta_key = f"production_{key}"
            assert meta_key in scene.metadata, (
                f"scene {scene.name} missing {meta_key}"
            )
            assert scene.metadata[meta_key] == section.production_course[key]


def test_proxy_arc_repertoire_storage(tmp_path: Path) -> None:
    tree = _compose_5min_proxy_arc()
    compiled = _compile_tree(tree)

    repo = RepertoireMemory(path=str(tmp_path / "repertoire.json"))
    repo.store_song(
        title=tree.title,
        family="ember",
        progression_profile="lift",
        cadence_state="occupied_day",
        key=compiled.source_score.key,
        hook_text=tree.primary_hook_text,
        hook_class=tree.motifs[0].hook_class if tree.motifs else "",
        practice_block="proxy_arc_test",
        ear_metrics={"hook_clarity": 0.88, "cadence_strength": 0.91},
        form_class=tree.commission.form_class,
        ending_family=tree.ending_family,
        score_tree=tree,
    )

    songs = repo.all_songs()
    assert len(songs) == 1
    stored = songs[0]
    assert stored["title"] == tree.title
    assert stored["family"] == "ember"
    assert "score_tree_summary" in stored
    assert stored["score_tree_summary"]["piece_id"] == tree.piece_id
    assert stored["score_tree_summary"]["section_functions"]

    hint = repo.recall_hint(family="ember", cadence_state="occupied_day")
    assert hint is not None
    assert hint["title"] == tree.title


def test_proxy_arc_piece_queue_round_trip(tmp_path: Path) -> None:
    tree = _compose_5min_proxy_arc()
    report = evaluate_score_tree(tree)
    assert report.approved is True

    queue = PieceQueue(path=tmp_path / "queue.json")
    queue.enqueue(tree, context_key="occupied_day:ember")
    restored = queue.dequeue_matching(context_key="occupied_day:ember")
    assert restored is not None
    assert restored.title == tree.title
    assert len(restored.sections) == len(tree.sections)
    for orig, rest in zip(tree.sections, restored.sections):
        assert rest.production_course == orig.production_course
