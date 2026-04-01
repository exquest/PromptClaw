"""Regression tests for observatory disk authority and WAL behavior."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

from observatory import Observatory


AUTHORITY_PATH = "/home/user/cypherclaw/.promptclaw/observatory.db"


def test_observatory_authority_path_constant() -> None:
    assert Observatory.AUTHORITY_PATH == AUTHORITY_PATH


def test_observatory_default_path_resolves_to_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_db = tmp_path / "observatory.db"
    monkeypatch.setattr(Observatory, "AUTHORITY_PATH", str(fake_db))

    obs = Observatory()

    assert obs.db_path == str(fake_db)
    obs.close()


def test_observatory_wal_mode(tmp_path: Path) -> None:
    obs = Observatory(str(tmp_path / "observatory.db"))

    mode = obs._conn.execute("PRAGMA journal_mode").fetchone()[0]
    sync = obs._conn.execute("PRAGMA synchronous").fetchone()[0]

    assert mode == "wal"
    assert sync == 1
    obs.close()


def test_observatory_close_checkpoints_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "observatory.db"
    obs = Observatory(str(db_path))
    obs.record("test_event", {"key": "value"})

    obs.close()

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()

    assert count >= 1


def test_observatory_preserves_existing_data(tmp_path: Path) -> None:
    db_path = tmp_path / "observatory.db"
    obs = Observatory(str(db_path))
    obs.record_task_result("claude", "T-001", True, 1_000, 500, True)
    obs.record_task_result("codex", "T-002", False, 2_000, 1_000, False)
    obs.record("healing", {"fix": "something"})
    obs.close()

    conn = sqlite3.connect(db_path)
    task_count = conn.execute("SELECT COUNT(*) FROM task_results").fetchone()[0]
    event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()

    assert task_count == 2
    assert event_count >= 1

    reopened = Observatory(str(db_path))
    task_count_after = reopened._conn.execute("SELECT COUNT(*) FROM task_results").fetchone()[0]
    event_count_after = reopened._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    reopened.close()

    assert task_count_after == task_count
    assert event_count_after == event_count
