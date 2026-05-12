from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from inner_life.world_model import WorldModel
from senseweave.composition_gate import evaluate_score_tree
from senseweave.form_grammar import plan_form
from senseweave.piece_brief import build_piece_brief
from senseweave.piece_commission import commission_piece
from senseweave.piece_queue import PieceQueue
from senseweave.recursive_composer import compose_score_tree
from senseweave.tracker_compiler import compile_score_tree_to_tracker


def test_score_tree_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    commission = commission_piece(
        cadence_state="wind_down",
        day_phase="late_evening",
        weekly_phase="weekend",
        attention_score=0.22,
        narrative_pressure=0.8,
        song_num=21,
        hour=22,
    )
    brief = build_piece_brief(
        world=WorldModel(
            observer_description="dark room and one lamp near the hallway",
            cadence_state="wind_down",
            day_phase="late_evening",
            time_of_day="night",
            occupancy_state="occupied_quiet",
            attention_score=0.22,
        ),
        commission=commission,
        family="nocturne",
        cadence_state="wind_down",
        progression_profile="settling",
    )
    form = plan_form(commission=commission, brief=brief, family="nocturne")
    tree = compose_score_tree(
        commission=commission,
        brief=brief,
        form=form,
        family="nocturne",
        cadence_state="wind_down",
        progression_profile="settling",
        song_num=21,
        mood={"energy": 0.18, "valence": 0.34, "arousal": 0.2},
    )
    assert evaluate_score_tree(tree).approved is True

    queue = PieceQueue(path=tmp_path / "piece_queue.json")
    queue.enqueue(tree, context_key="wind_down:nocturne")
    active = queue.dequeue_matching(context_key="wind_down:nocturne")
    assert active is not None

    compiled = compile_score_tree_to_tracker(
        active,
        mood={"energy": 0.18, "valence": 0.34, "arousal": 0.2},
        family_name="nocturne",
        patch_name="house_monastery",
        cadence_state="wind_down",
    )
    assert compiled.tracker_song.scenes
    assert compiled.tracker_song.metadata["song_title"] == active.title
