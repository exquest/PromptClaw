"""Decision store — persists architectural decisions (ADRs) for prompt injection."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Decision:
    """An architectural decision record (ADR)."""

    decision_id: str  # UUID
    created_at: str  # ISO timestamp
    title: str  # e.g., "Use Redis vector sets instead of ChromaDB"
    context: str  # Why this was decided
    decision_text: str  # What was decided
    rationale: str  # The reasoning
    status: str  # "active", "superseded", "deprecated"
    superseded_by: str | None = None  # decision_id of superseding decision
    tags: list[str] = field(default_factory=list)  # e.g., ["database", "storage"]
    file_paths: list[str] = field(default_factory=list)  # Code paths this decision affects


class SqliteDecisionStore:
    """SQLite-backed decision store using stdlib sqlite3."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS decisions (
        decision_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        title TEXT NOT NULL,
        context TEXT NOT NULL DEFAULT '',
        decision_text TEXT NOT NULL DEFAULT '',
        rationale TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        superseded_by TEXT,
        tags TEXT NOT NULL DEFAULT '[]',
        file_paths TEXT NOT NULL DEFAULT '[]'
    );
    CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
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
        """Create the decisions table if it does not exist."""
        conn = self._get_conn()
        conn.executescript(self._SCHEMA)
        conn.commit()

    def record(self, decision: Decision) -> None:
        """Insert a new decision into the store."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO decisions "
            "(decision_id, created_at, title, context, decision_text, rationale, "
            "status, superseded_by, tags, file_paths) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                decision.decision_id,
                decision.created_at,
                decision.title,
                decision.context,
                decision.decision_text,
                decision.rationale,
                decision.status,
                decision.superseded_by,
                json.dumps(decision.tags),
                json.dumps(decision.file_paths),
            ),
        )
        conn.commit()

    def get(self, decision_id: str) -> Decision | None:
        """Fetch a decision by ID, or None if not found."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_decision(row)

    def query_relevant(
        self,
        task_text: str,
        file_paths: list[str] | None = None,
        limit: int = 5,
    ) -> list[Decision]:
        """Find relevant active decisions by keyword matching and file path overlap.

        Searches title, context, and decision_text for words from task_text.
        Also matches decisions whose file_paths overlap with the given file_paths.
        Only returns active decisions.
        """
        conn = self._get_conn()

        # Get all active decisions and score them in Python for flexibility
        rows = conn.execute(
            "SELECT * FROM decisions WHERE status = 'active'"
        ).fetchall()

        if not rows:
            return []

        # Tokenize task text into lowercase keywords (skip very short words)
        keywords = {
            w.lower()
            for w in task_text.replace(",", " ").replace(".", " ").replace(":", " ").split()
            if len(w) >= 3
        }

        scored: list[tuple[float, Decision]] = []
        for row in rows:
            decision = self._row_to_decision(row)
            score = 0.0

            # Keyword matching against title, context, decision_text
            searchable = f"{decision.title} {decision.context} {decision.decision_text}".lower()
            for kw in keywords:
                if kw in searchable:
                    score += 1.0

            # File path overlap bonus
            if file_paths:
                decision_paths_set = set(decision.file_paths)
                overlap = decision_paths_set & set(file_paths)
                score += len(overlap) * 2.0  # Weight file path matches higher

            if score > 0:
                scored.append((score, decision))

        # Sort by score descending, return top N
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:limit]]

    def update_status(
        self,
        decision_id: str,
        status: str,
        superseded_by: str | None = None,
    ) -> None:
        """Change the status of a decision (immutable content, mutable status)."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE decisions SET status = ?, superseded_by = ? WHERE decision_id = ?",
            (status, superseded_by, decision_id),
        )
        conn.commit()

    def list_active(self) -> list[Decision]:
        """Return all decisions with status 'active'."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM decisions WHERE status = 'active' ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_decision(row) for row in rows]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_decision(row: sqlite3.Row) -> Decision:
        tags = row["tags"]
        if isinstance(tags, str):
            tags = json.loads(tags)
        file_paths = row["file_paths"]
        if isinstance(file_paths, str):
            file_paths = json.loads(file_paths)
        return Decision(
            decision_id=row["decision_id"],
            created_at=row["created_at"],
            title=row["title"],
            context=row["context"],
            decision_text=row["decision_text"],
            rationale=row["rationale"],
            status=row["status"],
            superseded_by=row["superseded_by"],
            tags=tags,
            file_paths=file_paths,
        )
