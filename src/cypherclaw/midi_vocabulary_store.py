"""SQLite store for MIDI vocabulary fragments.

Schema migration is idempotent and applied on every :func:`connect`. Rows hold
the per-fragment data described in the CypherClaw v2 PRD §Feature 2 — one row
per extracted melodic motif, rhythm cell, chord progression, or groove pattern.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

DEFAULT_DB_FILENAME = "midi_vocabulary.sqlite"
SCHEMA_VERSION = 1

FRAGMENT_KINDS: tuple[str, ...] = (
    "melodic_motif",
    "rhythm_cell",
    "chord_progression",
    "groove_pattern",
)

_MIGRATION_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fragments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file TEXT NOT NULL,
        kind TEXT NOT NULL,
        interval_pattern_json TEXT,
        duration_pattern_json TEXT,
        source_key TEXT,
        source_tempo REAL,
        harmonic_context_json TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_fragments_kind ON fragments(kind)",
    "CREATE INDEX IF NOT EXISTS idx_fragments_source_file "
    "ON fragments(source_file)",
)


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open and migrate the vocabulary database at ``db_path``."""

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # WAL + synchronous=NORMAL: insert_fragment commits per row, so a single
    # MIDI import is tens of thousands of commits. Under the default rollback
    # journal + synchronous=FULL each commit fsyncs, saturating disk I/O for
    # minutes (which can starve the live audio engine). WAL appends without a
    # per-commit fsync and lets the composer read while the daemon writes.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    apply_migrations(conn)
    return conn


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending schema migrations. Returns the current schema version."""

    with conn:
        for statement in _MIGRATION_STATEMENTS:
            conn.execute(statement)
        current_row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()
        current = int(current_row[0]) if current_row is not None else 0
        if current < SCHEMA_VERSION:
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
    return SCHEMA_VERSION


def insert_fragment(
    conn: sqlite3.Connection,
    *,
    source_file: str,
    kind: str,
    interval_pattern: Any = None,
    duration_pattern: Any = None,
    source_key: str | None = None,
    source_tempo: float | None = None,
    harmonic_context: Any = None,
) -> int:
    """Insert one fragment row, returning its rowid."""

    if kind not in FRAGMENT_KINDS:
        raise ValueError(
            f"unknown fragment kind: {kind!r} (expected one of {FRAGMENT_KINDS})"
        )

    cur = conn.execute(
        """
        INSERT INTO fragments (
            source_file, kind,
            interval_pattern_json, duration_pattern_json,
            source_key, source_tempo, harmonic_context_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_file,
            kind,
            _to_json(interval_pattern),
            _to_json(duration_pattern),
            source_key,
            source_tempo,
            _to_json(harmonic_context),
        ),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def ingest_extracted_fragments(
    conn: sqlite3.Connection,
    *,
    source_file: str,
    fragments: Mapping[str, Iterable[Mapping[str, Any]]],
    source_key: str | None = None,
    source_tempo: float | None = None,
) -> list[int]:
    """Insert every fragment from an ``extract_midi_fragments`` payload."""

    rowids: list[int] = []
    for motif in fragments.get("melodic_motifs") or ():
        rowids.append(
            insert_fragment(
                conn,
                source_file=source_file,
                kind="melodic_motif",
                interval_pattern=motif.get("interval_pattern"),
                duration_pattern=motif.get("duration_ratios"),
                source_key=source_key,
                source_tempo=source_tempo,
                harmonic_context={
                    "pitch_classes": motif.get("pitch_classes"),
                    "contour": motif.get("contour"),
                },
            )
        )
    for cell in fragments.get("rhythm_cells") or ():
        rowids.append(
            insert_fragment(
                conn,
                source_file=source_file,
                kind="rhythm_cell",
                interval_pattern=cell.get("onset_delta_ratios"),
                duration_pattern=cell.get("duration_ratios"),
                source_key=source_key,
                source_tempo=source_tempo,
            )
        )
    for progression in fragments.get("chord_progressions") or ():
        rowids.append(
            insert_fragment(
                conn,
                source_file=source_file,
                kind="chord_progression",
                source_key=source_key,
                source_tempo=source_tempo,
                harmonic_context={
                    "symbols": progression.get("symbols"),
                    "roots": progression.get("roots"),
                    "qualities": progression.get("qualities"),
                },
            )
        )
    for groove in fragments.get("groove_patterns") or ():
        rowids.append(
            insert_fragment(
                conn,
                source_file=source_file,
                kind="groove_pattern",
                interval_pattern=groove.get("beat_positions"),
                duration_pattern=groove.get("bar_positions"),
                source_key=source_key,
                source_tempo=source_tempo,
                harmonic_context={
                    "drum_roles": groove.get("drum_roles"),
                    "pattern": groove.get("pattern"),
                },
            )
        )
    return rowids


def query_fragments(
    conn: sqlite3.Connection,
    *,
    kind: str | None = None,
    source_file: str | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Return fragment rows, optionally filtered by kind or source file.

    When ``limit`` is a positive integer, at most that many rows are returned
    (lowest ``id`` first). A single MIDI import can yield tens of thousands of
    motif rows, so the live composer's read path must cap the fetch rather than
    materialize an entire kind on every score-tree build.
    """

    sql = "SELECT * FROM fragments"
    clauses: list[str] = []
    params: list[object] = []
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if source_file is not None:
        clauses.append("source_file = ?")
        params.append(source_file)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id"
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(int(limit))
    return list(conn.execute(sql, params).fetchall())


def _to_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)
