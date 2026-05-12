"""End-to-end offline musical lifecycle and marathon proxy tests."""
from __future__ import annotations

import math
import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from audio_analysis import classify_audio_content, detect_amplitude
from inner_life.world_model import WorldModel
from senseweave.composition_gate import evaluate_score_tree
from senseweave.form_grammar import plan_form
from senseweave.music_tracker_runtime import build_scene_events, schedule_song
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece
from senseweave.recursive_composer import compose_score_tree
from senseweave.repertoire_memory import RepertoireMemory
from senseweave.score_tree import ScoreTree
from senseweave.tracker_compiler import compile_score_tree_to_tracker


def _compose_piece(
    *,
    family: str,
    cadence_state: str,
    progression_profile: str,
    song_num: int,
    duration_target_s: float,
    form_class: str,
    composition_mode: str,
    mood: dict[str, float],
    narrative_pressure: float,
) -> ScoreTree:
    commission = commission_piece(
        cadence_state=cadence_state,
        day_phase="day",
        weekly_phase="midweek",
        attention_score=mood.get("energy", 0.5),
        narrative_pressure=narrative_pressure,
        occupancy_state="likely_away" if cadence_state == "away_practice" else "occupied_active",
        repertoire_entries=[object()] * 20 if form_class == "extended" else (),
        song_num=song_num,
        hour=16,
    )
    commission = replace(
        commission,
        form_class=form_class,
        duration_target_s=duration_target_s,
        composition_mode=composition_mode,
        narrative_scale="journey" if duration_target_s >= 300.0 else "single_image",
        sonic_world_count=2 if form_class in {"extended", "suite"} else 1,
        ending_family="reprise_coda" if form_class == "extended" else "afterglow",
    )
    world = WorldModel(
        observer_description="room with enough motion to justify a complete offline piece",
        cadence_state=cadence_state,
        day_phase="day",
        time_of_day="day",
        occupancy_state="likely_away" if cadence_state == "away_practice" else "occupied_active",
        attention_score=mood.get("energy", 0.5),
        experimentation_bias=narrative_pressure,
    )
    brief = build_piece_brief(
        world=world,
        commission=commission,
        family=family,
        cadence_state=cadence_state,
        progression_profile=progression_profile,
    )
    form = plan_form(commission=commission, brief=brief, family=family)
    return compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family=family,
        cadence_state=cadence_state,
        progression_profile=progression_profile,
        song_num=song_num,
        mood=mood,
    )


def _assert_non_flat_automation(tracker_song: object) -> None:
    for scene in tracker_song.scenes:
        assert scene.pattern.automation, f"{scene.name} has no automation lanes"
        assert any(
            len({value for _row, value in lane.points}) > 1
            for lane in scene.pattern.automation
        ), f"{scene.name} automation is flat"


def _assert_no_single_note_drone_sections(tracker_song: object) -> list[object]:
    all_events: list[object] = []
    for scene in tracker_song.scenes:
        events = build_scene_events(scene, song_title=tracker_song.title)
        pitched = [event for event in events if event.role != "sample"]
        assert pitched, f"{scene.name} emitted no pitched events"
        assert len({round(event.frequency_hz, 2) for event in pitched}) > 1, (
            f"{scene.name} collapsed to one pitch"
        )
        assert max(event.duration_seconds for event in pitched) < 8.0, (
            f"{scene.name} contains a long drone event"
        )
        all_events.extend(events)
    return all_events


def _render_preview_samples(events: list[object], sample_rate: int = 8000) -> list[int]:
    samples: list[int] = []
    for event in events[:96]:
        frequency = max(80.0, min(2000.0, event.frequency_hz))
        duration_s = min(0.06, max(0.025, event.duration_seconds))
        event_samples = max(1, int(sample_rate * duration_s))
        fade_samples = max(1, event_samples // 8)
        amplitude = min(0.85, max(0.05, event.amplitude * 3.0))
        for index in range(event_samples):
            fade_in = min(1.0, index / fade_samples)
            fade_out = min(1.0, (event_samples - index) / fade_samples)
            envelope = min(fade_in, fade_out)
            samples.append(
                int(
                    32767
                    * amplitude
                    * envelope
                    * math.sin(2.0 * math.pi * frequency * index / sample_rate)
                )
            )
        samples.extend([0] * max(1, sample_rate // 200))
    return samples


def _ear_metrics_for_events(events: list[object], samples: list[int]) -> dict[str, float]:
    rms, peak = detect_amplitude(samples)
    pitched = [event.frequency_hz for event in events if event.role != "sample"]
    if pitched:
        pitch_range = 12.0 * math.log2(max(pitched) / min(pitched))
        interval_variety = min(1.0, len({round(freq, 1) for freq in pitched}) / 18.0)
        centroid = sum(pitched) / len(pitched)
    else:
        pitch_range = 0.0
        interval_variety = 0.0
        centroid = 0.0
    return {
        "rms": round(rms, 4),
        "peak": round(peak, 4),
        "interval_variety": round(interval_variety, 3),
        "pitch_range_semitones": round(pitch_range, 3),
        "onset_density": round(min(3.0, len(events) / 90.0), 3),
        "repetition_score": 0.35,
        "spectral_centroid_hz": round(centroid, 3),
        "spectral_flatness": 0.22,
        "roughness": 0.1,
        "hook_clarity": 0.86 if peak > 0.0 else 0.0,
        "cadence_strength": 0.82 if pitch_range > 0.0 else 0.0,
        "development_score": min(1.0, round(interval_variety + 0.25, 3)),
    }


def test_offline_piece_lifecycle_runs_five_minute_marathon_proxy(tmp_path: Path) -> None:
    mood = {"energy": 0.46, "valence": 0.42, "arousal": 0.55}
    tree = _compose_piece(
        family="forge",
        cadence_state="away_practice",
        progression_profile="experiment",
        song_num=12,
        duration_target_s=300.0,
        form_class="extended",
        composition_mode="hybrid",
        mood=mood,
        narrative_pressure=0.55,
    )

    report = evaluate_score_tree(tree)
    assert report.approved is True
    assert tree.planned_duration_s == 300.0

    compiled = compile_score_tree_to_tracker(
        tree,
        mood=mood,
        family_name="forge",
        patch_name="house_workshop",
        cadence_state="away_practice",
        progression_profile="experiment",
    )
    assert 270.0 <= compiled.estimated_duration_s <= 330.0
    _assert_non_flat_automation(compiled.tracker_song)
    planned_events = _assert_no_single_note_drone_sections(compiled.tracker_song)

    played = []
    slept = []
    result = schedule_song(
        compiled.tracker_song,
        play_event=played.append,
        sleep_fn=slept.append,
        state_path=tmp_path / "tracker_state.json",
        time_fn=lambda: 3000.0,
    )

    assert result.completed is True
    assert result.events_emitted == len(played)
    assert result.events_emitted > 0
    assert max(event.amplitude for event in played) > 0.0
    assert 270.0 <= sum(slept) <= 330.0

    samples = _render_preview_samples(planned_events)
    rms, peak = detect_amplitude(samples)
    classification = classify_audio_content(samples, 8000)
    assert rms > 0.003
    assert peak > 0.0
    assert classification["type"] != "silence"

    memory = RepertoireMemory(path=str(tmp_path / "repertoire_memory.json"))
    memory.store_song(
        title=tree.title,
        family="forge",
        progression_profile="experiment",
        cadence_state="away_practice",
        key=compiled.source_score.key,
        hook_text=tree.primary_hook_text,
        hook_class=tree.motifs[0].hook_class,
        practice_block="T-011 offline proxy",
        patch_name="house_workshop",
        ear_metrics=_ear_metrics_for_events(planned_events, samples),
        form_class=tree.commission.form_class,
        composition_mode=tree.commission.composition_mode,
        ending_family=tree.ending_family,
        score_tree=tree,
    )

    songs = memory.all_songs()
    assert len(songs) == 1
    stored = songs[0]
    assert stored["title"] == tree.title
    assert stored["ear_metrics"]["peak"] > 0.0
    assert stored["score_tree_summary"]["piece_id"] == tree.piece_id
    assert stored["score_tree_summary"]["duration_s"] == tree.planned_duration_s
    assert stored["score_tree_summary"]["section_functions"]

    hint = memory.recall_hint(family="forge", cadence_state="away_practice")
    assert hint is not None
    assert hint["title"] == tree.title
    assert hint["score_tree_summary"]["piece_id"] == tree.piece_id


def test_multi_piece_queue_run_schedules_each_piece_without_hardware(tmp_path: Path) -> None:
    specs = (
        {
            "family": "ember",
            "cadence_state": "occupied_day",
            "progression_profile": "lift",
            "song_num": 21,
            "patch_name": "house_chamber",
        },
        {
            "family": "drift",
            "cadence_state": "wind_down",
            "progression_profile": "settling",
            "song_num": 22,
            "patch_name": "house_monastery",
        },
    )
    mood = {"energy": 0.45, "valence": 0.5, "arousal": 0.4}
    queued_trees = [
        _compose_piece(
            family=spec["family"],
            cadence_state=spec["cadence_state"],
            progression_profile=spec["progression_profile"],
            song_num=spec["song_num"],
            duration_target_s=45.0,
            form_class="micro",
            composition_mode="hook_led",
            mood=mood,
            narrative_pressure=0.1,
        )
        for spec in specs
    ]

    emitted_by_piece: dict[str, int] = {}
    for spec, tree in zip(specs, queued_trees):
        assert evaluate_score_tree(tree).approved is True
        compiled = compile_score_tree_to_tracker(
            tree,
            mood=mood,
            family_name=spec["family"],
            patch_name=spec["patch_name"],
            cadence_state=spec["cadence_state"],
            progression_profile=spec["progression_profile"],
        )
        _assert_non_flat_automation(compiled.tracker_song)
        _assert_no_single_note_drone_sections(compiled.tracker_song)

        piece_events = []
        result = schedule_song(
            compiled.tracker_song,
            play_event=piece_events.append,
            sleep_fn=lambda _seconds: None,
            state_path=tmp_path / f"tracker_state_{tree.piece_id}.json",
            time_fn=lambda: 4000.0,
        )
        assert result.completed is True
        assert result.events_emitted == len(piece_events)
        assert piece_events
        emitted_by_piece[tree.piece_id] = len(piece_events)

    assert len(emitted_by_piece) == 2
    assert all(count > 0 for count in emitted_by_piece.values())
