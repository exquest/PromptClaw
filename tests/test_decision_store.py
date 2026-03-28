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


if __name__ == "__main__":
    unittest.main()
