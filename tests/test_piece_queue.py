from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.piece_commission import commission_piece
from senseweave.piece_queue import PieceQueue
from senseweave.score_tree import ScoreTree


def _fake_tree(piece_id: str) -> ScoreTree:
    commission = commission_piece(
        cadence_state="occupied_day",
        day_phase="day",
        weekly_phase="midweek",
        attention_score=0.4,
        song_num=1,
        hour=14,
    )
    return ScoreTree.minimal(
        piece_id=piece_id,
        title=f"Piece {piece_id}",
        commission=commission,
    )


def test_piece_queue_round_trips_ready_piece(tmp_path: Path) -> None:
    queue = PieceQueue(path=tmp_path / "piece_queue.json")
    tree = _fake_tree("piece-1")

    queue.enqueue(tree, context_key="occupied_day:ember")
    recovered = queue.dequeue_matching(context_key="occupied_day:ember")

    assert recovered is not None
    assert recovered.piece_id == "piece-1"
    assert queue.dequeue_matching(context_key="occupied_day:ember") is None


def test_piece_queue_persists_active_score_tree(tmp_path: Path) -> None:
    path = tmp_path / "piece_queue.json"
    active_path = tmp_path / "current_score_tree.json"
    queue = PieceQueue(path=str(path), active_path=str(active_path))
    tree = _fake_tree("piece-1")

    queue.set_active(tree)
    assert active_path.exists()
    assert json.loads(active_path.read_text())["piece_id"] == "piece-1"

    # The active state path is sufficient for restart recovery even if the
    # queue ledger is unavailable.
    active_only_queue = PieceQueue(path=str(tmp_path / "missing_queue.json"), active_path=str(active_path))
    active_only = active_only_queue.get_active()
    assert active_only is not None
    assert active_only.piece_id == "piece-1"

    # Restart
    queue_restarted = PieceQueue(path=str(path), active_path=str(active_path))
    active = queue_restarted.get_active()
    assert active is not None
    assert active.piece_id == "piece-1"

    # Clear active
    queue_restarted.set_active(None)
    assert queue_restarted.get_active() is None
    assert not active_path.exists()
