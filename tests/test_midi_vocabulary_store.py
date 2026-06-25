"""Tests for the SQLite vocabulary store (T-015)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cypherclaw import midi_vocabulary_store as store


def test_connect_enables_wal_journal_mode(tmp_path: Path) -> None:
    # WAL avoids an fsync per row-commit (insert_fragment commits per row), so
    # a large MIDI import does not saturate disk I/O on the live audio box.
    db_path = tmp_path / "midi_vocabulary.sqlite"
    conn = store.connect(db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"


def test_apply_migrations_creates_fragments_table(tmp_path: Path) -> None:
    db_path = tmp_path / "midi_vocabulary.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        store.apply_migrations(conn)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(fragments)").fetchall()
        }
    finally:
        conn.close()

    expected = {
        "id",
        "source_file",
        "kind",
        "interval_pattern_json",
        "duration_pattern_json",
        "source_key",
        "source_tempo",
        "harmonic_context_json",
    }
    assert expected.issubset(columns)


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "midi_vocabulary.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        store.apply_migrations(conn)
        store.apply_migrations(conn)
        versions = [
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
    finally:
        conn.close()
    assert versions == [store.SCHEMA_VERSION]


def test_insert_and_query_fragment_round_trips(tmp_path: Path) -> None:
    db_path = tmp_path / "midi_vocabulary.sqlite"
    conn = store.connect(db_path)
    try:
        rowid = store.insert_fragment(
            conn,
            source_file="sample.mid",
            kind="melodic_motif",
            interval_pattern=[2, 2, 3],
            duration_pattern=[1.0, 1.0, 2.0],
            source_key="C major",
            source_tempo=120.0,
            harmonic_context={"pitch_classes": [0, 2, 4, 7]},
        )
        assert rowid > 0

        rows = store.query_fragments(conn, kind="melodic_motif")
    finally:
        conn.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["source_file"] == "sample.mid"
    assert row["kind"] == "melodic_motif"
    assert json.loads(row["interval_pattern_json"]) == [2, 2, 3]
    assert json.loads(row["duration_pattern_json"]) == [1.0, 1.0, 2.0]
    assert row["source_key"] == "C major"
    assert row["source_tempo"] == 120.0
    assert json.loads(row["harmonic_context_json"]) == {
        "pitch_classes": [0, 2, 4, 7]
    }


def test_ingest_extracted_fragments_writes_each_kind(tmp_path: Path) -> None:
    fragments = {
        "melodic_motifs": [
            {
                "interval_pattern": [2, 2, 3],
                "duration_ratios": [1.0, 1.0, 2.0],
                "pitch_classes": [0, 2, 4, 7],
                "contour": ["up", "up", "up"],
            }
        ],
        "rhythm_cells": [
            {
                "duration_ratios": [1.0, 1.0, 2.0],
                "onset_delta_ratios": [1.0, 1.0],
            }
        ],
        "chord_progressions": [
            {
                "symbols": ["C", "F", "G", "C"],
                "roots": ["C", "F", "G", "C"],
                "qualities": ["major", "major", "major", "major"],
            }
        ],
        "groove_patterns": [
            {
                "drum_roles": ["kick", "hihat", "snare", "hihat"],
                "pattern": "kick-hihat-snare-hihat",
                "beat_positions": [0.0, 0.5, 1.0, 1.5],
                "bar_positions": [0.0, 0.5, 1.0, 1.5],
            }
        ],
    }

    db_path = tmp_path / "midi_vocabulary.sqlite"
    conn = store.connect(db_path)
    try:
        rowids = store.ingest_extracted_fragments(
            conn,
            source_file="seed.mid",
            fragments=fragments,
            source_key="C major",
            source_tempo=120.0,
        )
        kinds = [
            row["kind"]
            for row in store.query_fragments(conn, source_file="seed.mid")
        ]
    finally:
        conn.close()

    assert len(rowids) == 4
    assert set(kinds) == {
        "melodic_motif",
        "rhythm_cell",
        "chord_progression",
        "groove_pattern",
    }


def test_sample_query_returns_expected_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "midi_vocabulary.sqlite"
    conn = store.connect(db_path)
    try:
        store.insert_fragment(
            conn,
            source_file="a.mid",
            kind="melodic_motif",
            interval_pattern=[2, 2],
            duration_pattern=[1.0, 1.0],
            source_key="C major",
            source_tempo=120.0,
        )
        store.insert_fragment(
            conn,
            source_file="a.mid",
            kind="rhythm_cell",
            interval_pattern=[1, 1],
            duration_pattern=[1.0, 1.0],
            source_key="C major",
            source_tempo=120.0,
        )
        store.insert_fragment(
            conn,
            source_file="b.mid",
            kind="melodic_motif",
            interval_pattern=[5, -2],
            duration_pattern=[2.0, 1.0],
            source_key="A minor",
            source_tempo=90.0,
        )

        motifs = store.query_fragments(conn, kind="melodic_motif")
        a_rows = store.query_fragments(conn, source_file="a.mid")
        capped = store.query_fragments(conn, kind="melodic_motif", limit=1)
    finally:
        conn.close()

    assert [row["source_file"] for row in motifs] == ["a.mid", "b.mid"]
    assert [row["kind"] for row in a_rows] == ["melodic_motif", "rhythm_cell"]
    # A positive limit caps the fetch (lowest id first) so the composer's read
    # path never materializes an entire kind.
    assert [row["source_file"] for row in capped] == ["a.mid"]
