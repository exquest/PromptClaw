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
from senseweave.music_tracker_runtime import schedule_song
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece
from senseweave.recursive_composer import compose_score_tree
from senseweave.tracker_compiler import compile_score_tree_to_tracker
from senseweave.usage_journal import (
    SampleUsageTracker,
    post_piece_hook,
    read_journal,
    record_scheduled_sample_event,
)


def _compose_short_piece():
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.52,
        narrative_pressure=0.64,
        occupancy_state="occupied_active",
        repertoire_entries=[object()] * 12,
        song_num=15,
        hour=17,
    )
    world = WorldModel(
        observer_description="bright room with taps and small motions near the desk",
        cadence_state="occupied_day",
        day_phase="day",
        time_of_day="evening",
        occupancy_state="occupied_active",
        attention_score=0.52,
        experimentation_bias=0.64,
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
        song_num=15,
        mood={"energy": 0.58, "valence": 0.6, "arousal": 0.54},
    )
    target_section = next(
        (
            name
            for name in ("Development", "Arrival", "Lift", "Theme")
            if any(section.scene_name == name for section in tree.sections)
        ),
        tree.sections[0].scene_name,
    )
    tree.arrangement_plan.setdefault("sample_gestures", {})[target_section] = {
        "source": "contact_mic",
        "source_kind": "field_recording",
        "mode": "grain_cloud",
        "voice": "sample_grain",
        "transforms": ["slice_rearrange", "granular_cloud", "reverse_accents"],
        "density": 0.72,
        "max_events": 6,
    }
    return tree, target_section


def test_short_composed_piece_writes_populated_usage_journal_entry(tmp_path: Path) -> None:
    tree, target_section = _compose_short_piece()
    report = evaluate_score_tree(tree)
    assert report.approved is True, f"gate failures: {report.failures}"

    compiled = compile_score_tree_to_tracker(
        tree,
        mood={"energy": 0.58, "valence": 0.6, "arousal": 0.54},
        family_name="ember",
        patch_name="house_procession",
        cadence_state="occupied_day",
        progression_profile="lift",
    )
    assert any(scene.name == target_section for scene in compiled.tracker_song.scenes)

    journal_path = tmp_path / "usage_journal.jsonl"
    tracker = SampleUsageTracker()
    tracker.start_piece(piece_id=tree.piece_id, timestamp="2026-04-25T19:45:00Z")
    emitted = []

    def _on_event(event) -> None:
        emitted.append(event)
        record_scheduled_sample_event(tracker, event)

    result = schedule_song(
        compiled.tracker_song,
        play_event=_on_event,
        sleep_fn=lambda _seconds: None,
        state_path=tmp_path / "tracker_state.json",
        time_fn=lambda: 4500.0,
    )

    assert result.completed is True
    sample_events = [event for event in emitted if event.role == "sample"]
    assert sample_events

    entry = post_piece_hook(
        tracker,
        arc_payoff_score=0.72,
        journal_path=journal_path,
        mode="evening_reflection",
        clicks=0,
    )

    assert entry.piece_id == tree.piece_id
    assert entry.mode == "evening_reflection"
    assert entry.arc_payoff.startswith("strong")
    assert entry.transformations == [
        "slice_rearrange",
        "granular_cloud",
        "reverse_accents",
    ]
    assert len(entry.samples_played) == len(sample_events)
    assert entry.samples_played[0].source == "contact_mic"
    assert entry.samples_played[0].source_kind == "field_recording"
    assert entry.samples_played[0].sample_id

    on_disk = read_journal(path=journal_path)
    assert len(on_disk) == 1
    assert on_disk[0].transformations == entry.transformations
    assert on_disk[0].samples_played
    assert on_disk[0].samples_played[0].source_kind == "field_recording"

    raw = json.loads(journal_path.read_text(encoding="utf-8").splitlines()[0])
    assert raw["piece_id"] == tree.piece_id
    assert raw["mode"] == "evening_reflection"
    assert raw["samples_used"]
    assert raw["samples_used"][0]["source_kind"] == "field_recording"
    assert raw["transformations"] == [
        "slice_rearrange",
        "granular_cloud",
        "reverse_accents",
    ]
    assert raw["arc_payoff"]
