"""Tests for the coherence decision store."""

import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.decision_store import Decision, SqliteDecisionStore


def _make_decision(**overrides) -> Decision:
    """Helper to create a Decision with sensible defaults."""
    defaults = dict(
        decision_id="dec-001",
        created_at="2026-03-01T00:00:00Z",
        title="Use Redis for caching",
        context="We need a fast in-memory cache layer.",
        decision_text="Use Redis as the primary caching backend.",
        rationale="Redis provides sub-millisecond latency and built-in TTL support.",
        status="active",
        superseded_by=None,
        tags=["database", "caching"],
        file_paths=["src/cache.py", "src/config.py"],
    )
    defaults.update(overrides)
    return Decision(**defaults)


class TestSqliteDecisionStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-decision-"))
        self.db_path = self.temp_dir / "decisions.db"
        self.store = SqliteDecisionStore(self.db_path)
        self.store.migrate()

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir)

    # --- Basic roundtrip ---

    def test_record_and_get_roundtrip(self):
        dec = _make_decision()
        self.store.record(dec)
        fetched = self.store.get("dec-001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.decision_id, "dec-001")
        self.assertEqual(fetched.title, "Use Redis for caching")
        self.assertEqual(fetched.context, "We need a fast in-memory cache layer.")
        self.assertEqual(fetched.decision_text, "Use Redis as the primary caching backend.")
        self.assertEqual(fetched.rationale, "Redis provides sub-millisecond latency and built-in TTL support.")
        self.assertEqual(fetched.status, "active")
        self.assertIsNone(fetched.superseded_by)
        self.assertEqual(fetched.tags, ["database", "caching"])
        self.assertEqual(fetched.file_paths, ["src/cache.py", "src/config.py"])

    def test_get_nonexistent_returns_none(self):
        self.assertIsNone(self.store.get("does-not-exist"))

    # --- query_relevant: keyword matching ---

    def test_query_relevant_matches_keywords_in_task_text(self):
        self.store.record(_make_decision(decision_id="dec-redis", title="Use Redis for caching"))
        self.store.record(_make_decision(
            decision_id="dec-pg",
            title="Use PostgreSQL for persistence",
            context="We need durable relational storage.",
            decision_text="Use PostgreSQL as the primary database.",
            rationale="Mature, widely supported, good for relational data.",
            tags=["database", "persistence"],
            file_paths=["src/db.py"],
        ))
        results = self.store.query_relevant("Set up Redis caching for the API")
        self.assertTrue(len(results) >= 1)
        ids = [d.decision_id for d in results]
        self.assertIn("dec-redis", ids)

    # --- query_relevant: file path matching ---

    def test_query_relevant_matches_file_paths(self):
        self.store.record(_make_decision(
            decision_id="dec-cache",
            title="Cache layer architecture",
            file_paths=["src/cache.py"],
        ))
        self.store.record(_make_decision(
            decision_id="dec-auth",
            title="Authentication flow",
            context="Auth decisions",
            decision_text="Use OAuth2",
            file_paths=["src/auth.py"],
        ))
        results = self.store.query_relevant(
            "Update the cache module",
            file_paths=["src/cache.py"],
        )
        ids = [d.decision_id for d in results]
        self.assertIn("dec-cache", ids)

    # --- query_relevant: only active ---

    def test_query_relevant_excludes_non_active(self):
        self.store.record(_make_decision(decision_id="dec-active", status="active"))
        self.store.record(_make_decision(
            decision_id="dec-superseded",
            title="Old Redis config",
            status="superseded",
        ))
        self.store.record(_make_decision(
            decision_id="dec-deprecated",
            title="Deprecated Redis approach",
            status="deprecated",
        ))
        results = self.store.query_relevant("Redis caching")
        ids = [d.decision_id for d in results]
        self.assertIn("dec-active", ids)
        self.assertNotIn("dec-superseded", ids)
        self.assertNotIn("dec-deprecated", ids)

    # --- update_status ---

    def test_update_status_changes_status(self):
        self.store.record(_make_decision(decision_id="dec-001"))
        self.store.update_status("dec-001", "deprecated")
        fetched = self.store.get("dec-001")
        self.assertEqual(fetched.status, "deprecated")

    def test_update_status_with_superseded_by(self):
        self.store.record(_make_decision(decision_id="dec-old"))
        self.store.record(_make_decision(decision_id="dec-new", title="New Redis approach"))
        self.store.update_status("dec-old", "superseded", superseded_by="dec-new")
        fetched = self.store.get("dec-old")
        self.assertEqual(fetched.status, "superseded")
        self.assertEqual(fetched.superseded_by, "dec-new")

    # --- list_active ---

    def test_list_active_returns_only_active(self):
        self.store.record(_make_decision(decision_id="dec-1", status="active"))
        self.store.record(_make_decision(decision_id="dec-2", status="superseded"))
        self.store.record(_make_decision(decision_id="dec-3", status="active"))
        active = self.store.list_active()
        ids = [d.decision_id for d in active]
        self.assertIn("dec-1", ids)
        self.assertIn("dec-3", ids)
        self.assertNotIn("dec-2", ids)
        self.assertEqual(len(active), 2)

    # --- Empty store ---

    def test_empty_store_returns_empty_results(self):
        self.assertEqual(self.store.list_active(), [])
        self.assertEqual(self.store.query_relevant("anything"), [])
        self.assertIsNone(self.store.get("nonexistent"))

    # --- unlocks / constrains fields (P2) ---

    def test_record_and_get_preserves_unlocks_and_constrains(self):
        dec = _make_decision(
            decision_id="dec-uc",
            unlocks=["feature X", "feature Y"],
            constrains=["no global state"],
        )
        self.store.record(dec)
        fetched = self.store.get("dec-uc")
        self.assertEqual(fetched.unlocks, ["feature X", "feature Y"])
        self.assertEqual(fetched.constrains, ["no global state"])

    def test_unlocks_constrains_default_empty(self):
        dec = _make_decision(decision_id="dec-default")
        self.store.record(dec)
        fetched = self.store.get("dec-default")
        self.assertEqual(fetched.unlocks, [])
        self.assertEqual(fetched.constrains, [])

    def test_migrate_adds_columns_to_legacy_db(self):
        # A DB created before unlocks/constrains existed must gain the columns on migrate().
        import sqlite3

        legacy_path = self.temp_dir / "legacy.db"
        conn = sqlite3.connect(str(legacy_path))
        conn.executescript(
            "CREATE TABLE decisions ("
            "decision_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL,"
            "context TEXT NOT NULL DEFAULT '', decision_text TEXT NOT NULL DEFAULT '',"
            "rationale TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',"
            "superseded_by TEXT, tags TEXT NOT NULL DEFAULT '[]', "
            "file_paths TEXT NOT NULL DEFAULT '[]');"
        )
        conn.execute(
            "INSERT INTO decisions (decision_id, created_at, title) "
            "VALUES ('leg-1','2026-01-01T00:00:00Z','Legacy')"
        )
        conn.commit()
        conn.close()

        store = SqliteDecisionStore(legacy_path)
        store.migrate()  # must ALTER TABLE to add the new columns
        try:
            fetched = store.get("leg-1")
            self.assertEqual(fetched.unlocks, [])
            self.assertEqual(fetched.constrains, [])
            store.record(_make_decision(decision_id="leg-2", unlocks=["a"], constrains=["b"]))
            self.assertEqual(store.get("leg-2").unlocks, ["a"])
            self.assertEqual(store.get("leg-2").constrains, ["b"])
        finally:
            store.close()

    def test_migrate_partial_legacy_db_adds_only_missing_column(self):
        # A DB where one of the two new columns already exists must gain only the other,
        # without error.
        import sqlite3

        partial_path = self.temp_dir / "partial.db"
        conn = sqlite3.connect(str(partial_path))
        conn.executescript(
            "CREATE TABLE decisions ("
            "decision_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL,"
            "context TEXT NOT NULL DEFAULT '', decision_text TEXT NOT NULL DEFAULT '',"
            "rationale TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',"
            "superseded_by TEXT, tags TEXT NOT NULL DEFAULT '[]', "
            "file_paths TEXT NOT NULL DEFAULT '[]', "
            "unlocks TEXT NOT NULL DEFAULT '[]');"  # has unlocks, missing constrains
        )
        conn.commit()
        conn.close()

        store = SqliteDecisionStore(partial_path)
        store.migrate()  # should add only 'constrains'
        try:
            store.record(_make_decision(decision_id="p-1", unlocks=["u"], constrains=["c"]))
            fetched = store.get("p-1")
            self.assertEqual(fetched.unlocks, ["u"])
            self.assertEqual(fetched.constrains, ["c"])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
