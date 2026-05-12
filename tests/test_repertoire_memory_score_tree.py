from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.piece_commission import commission_piece
from senseweave.repertoire_memory import RepertoireMemory
from senseweave.score_tree import ScoreTree


def test_repertoire_memory_stores_score_tree_summary(tmp_path: Path) -> None:
    memory = RepertoireMemory(path=str(tmp_path / "repertoire_memory.json"))
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.55,
        song_num=12,
        hour=15,
    )
    tree = ScoreTree.minimal(piece_id="piece-12", title="Open Rooms", commission=commission)

    memory.store_song(
        title="Open Rooms",
        family="ember",
        progression_profile="lift",
        cadence_state="occupied_day",
        key="C",
        hook_text="keep the room open",
        hook_class="lyric",
        practice_block="",
        patch_name="house_chamber",
        ear_metrics={"hook_clarity": 0.9, "cadence_strength": 0.84},
        form_class=commission.form_class,
        composition_mode=commission.composition_mode,
        ending_family=commission.ending_family,
        score_tree=tree,
    )

    songs = memory.all_songs()
    assert len(songs) == 1
    summary = songs[0].get("score_tree_summary", {})
    assert summary.get("piece_id") == "piece-12"
    assert summary.get("form_class") == commission.form_class
    assert summary.get("composition_mode") == commission.composition_mode

