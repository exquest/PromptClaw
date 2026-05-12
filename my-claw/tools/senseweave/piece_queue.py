"""Small persistent queue of precomposed score trees."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .score_tree import ScoreTree


@dataclass(frozen=True)
class QueuedPiece:
    context_key: str
    created_at: float
    score_tree: ScoreTree


class PieceQueue:
    def __init__(
        self,
        path: str | Path = "/home/user/cypherclaw-data/state/piece_queue.json",
        active_path: str | Path = "/tmp/current_score_tree.json",
    ):
        self.path = Path(path)
        self.active_path = Path(active_path)

    def _load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            pass
        return {"pieces": []}

    def _save(self, data: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            os.replace(str(tmp), str(self.path))
        except OSError:
            pass

    def _write_active_path(self, score_tree: ScoreTree) -> None:
        try:
            self.active_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.active_path.with_name(f"{self.active_path.name}.tmp")
            tmp.write_text(json.dumps(score_tree.to_dict(), indent=2))
            os.replace(str(tmp), str(self.active_path))
        except OSError:
            pass

    def set_active(self, score_tree: ScoreTree | None) -> None:
        data = self._load()
        if score_tree is None:
            data.pop("active_score_tree", None)
            try:
                self.active_path.unlink(missing_ok=True)
            except OSError:
                pass
        else:
            data["active_score_tree"] = score_tree.to_dict()
            self._write_active_path(score_tree)
        self._save(data)

    def get_active(self) -> ScoreTree | None:
        data = self._load()
        active = data.get("active_score_tree")
        if not active:
            try:
                if self.active_path.exists():
                    active = json.loads(self.active_path.read_text())
            except (OSError, json.JSONDecodeError):
                active = None
        if not active:
            return None
        return ScoreTree.from_dict(dict(active))

    def enqueue(self, score_tree: ScoreTree, *, context_key: str) -> None:
        data = self._load()
        pieces = list(data.get("pieces", []))
        pieces.append(
            {
                "context_key": context_key,
                "created_at": time.time(),
                "score_tree": score_tree.to_dict(),
            }
        )
        data["pieces"] = pieces[-8:]
        self._save(data)

    def has_context_key(self, *, context_key: str) -> bool:
        data = self._load()
        pieces = list(data.get("pieces", []))
        return any(item.get("context_key") == context_key for item in pieces)

    def dequeue_matching(self, *, context_key: str) -> ScoreTree | None:
        data = self._load()
        pieces = list(data.get("pieces", []))
        selected_index: int | None = None
        for index, item in enumerate(pieces):
            if item.get("context_key") == context_key:
                selected_index = index
                break
        if selected_index is None and pieces:
            selected_index = 0
        if selected_index is None:
            return None
        selected = pieces.pop(selected_index)
        data["pieces"] = pieces
        self._save(data)
        return ScoreTree.from_dict(dict(selected.get("score_tree", {})))
