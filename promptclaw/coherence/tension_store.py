"""Tension store — persists *held* contradictions that are surfaced, not force-resolved.

The decision store records what was settled; the tension store records what is deliberately
left open. A Tension is a legitimate contradiction (Shadowland's "chord" — two true things in
tension) tracked with its dialectic state and what would resolve it, and surfaced to agents as
"HOLD — do not silently collapse" rather than treated as a violation to block.
See docs/Shadowland2/promptclaw-integration-proposal.md (P1).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return json.loads(value)
    return value or []


@dataclass
class Tension:
    """A deliberately-held contradiction."""

    tension_id: str  # UUID
    created_at: str  # ISO timestamp
    statement: str  # the contradiction, stated plainly
    dialectic_state: str = ""  # current state of the argument
    resolution_criterion: str = ""  # what would sharpen or resolve it
    between: list[str] = field(default_factory=list)  # decision_ids / task_ids / refs in tension
    status: str = "open"  # "open" | "resolved" | "dissolved"
    resolved_by: str | None = None  # decision_id / note that closed it


class SqliteTensionStore:
    """SQLite-backed tension store using stdlib sqlite3 (mirrors SqliteDecisionStore)."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS tensions (
        tension_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        statement TEXT NOT NULL,
        dialectic_state TEXT NOT NULL DEFAULT '',
        resolution_criterion TEXT NOT NULL DEFAULT '',
        between_refs TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'open',
        resolved_by TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_tensions_status ON tensions(status);
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=30)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def migrate(self) -> None:
        conn = self._get_conn()
        conn.executescript(self._SCHEMA)
        conn.commit()

    def record(self, tension: Tension) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO tensions "
            "(tension_id, created_at, statement, dialectic_state, resolution_criterion, "
            "between_refs, status, resolved_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tension.tension_id,
                tension.created_at,
                tension.statement,
                tension.dialectic_state,
                tension.resolution_criterion,
                json.dumps(tension.between),
                tension.status,
                tension.resolved_by,
            ),
        )
        conn.commit()

    def get(self, tension_id: str) -> Tension | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM tensions WHERE tension_id = ?", (tension_id,)
        ).fetchone()
        return self._row_to_tension(row) if row else None

    def list_open(self, limit: int | None = None) -> list[Tension]:
        """Return open tensions, newest first."""
        conn = self._get_conn()
        sql = "SELECT * FROM tensions WHERE status = 'open' ORDER BY created_at DESC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return [self._row_to_tension(r) for r in conn.execute(sql).fetchall()]

    def query_relevant(self, task_text: str, limit: int = 5) -> list[Tension]:
        """Find open tensions whose statement keyword-overlaps the task text."""
        keywords = {
            w.lower()
            for w in task_text.replace(",", " ").replace(".", " ").replace(":", " ").split()
            if len(w) >= 3
        }
        scored: list[tuple[float, Tension]] = []
        for t in self.list_open():
            searchable = f"{t.statement} {t.dialectic_state}".lower()
            score = sum(1.0 for kw in keywords if kw in searchable)
            if score > 0:
                scored.append((score, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:limit]]

    def update_status(
        self, tension_id: str, status: str, resolved_by: str | None = None
    ) -> None:
        """Change a tension's status (open -> resolved | dissolved). Content stays immutable."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE tensions SET status = ?, resolved_by = ? WHERE tension_id = ?",
            (status, resolved_by, tension_id),
        )
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_tension(row: sqlite3.Row) -> Tension:
        return Tension(
            tension_id=row["tension_id"],
            created_at=row["created_at"],
            statement=row["statement"],
            dialectic_state=row["dialectic_state"],
            resolution_criterion=row["resolution_criterion"],
            between=_json_list(row["between_refs"]),
            status=row["status"],
            resolved_by=row["resolved_by"],
        )
