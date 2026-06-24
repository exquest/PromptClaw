"""Tests for the held-tension store (P1) and its prompt-injection rendering.

A Tension is a contradiction that is deliberately HELD (surfaced, tracked) rather than
force-resolved — the coherence engine's first "hold, don't fix" primitive.
See docs/Shadowland2/promptclaw-integration-proposal.md (P1).
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.prompt_injection import format_tension_context
from promptclaw.coherence.tension_store import SqliteTensionStore, Tension


def _t(**overrides) -> Tension:
    defaults = dict(
        tension_id="t-1",
        created_at="2026-06-24T00:00:00Z",
        statement="Simplicity vs. horizontal scale",
        dialectic_state="open — leaning simplicity for <20 concurrent",
        resolution_criterion="a load test exceeding 20 concurrent users",
        between=["dec-001", "T-042"],
        status="open",
        resolved_by=None,
    )
    defaults.update(overrides)
    return Tension(**defaults)


class TestSqliteTensionStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-tension-"))
        self.store = SqliteTensionStore(self.tmp / "t.db")
        self.store.migrate()

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_record_get_roundtrip(self):
        self.store.record(_t())
        f = self.store.get("t-1")
        self.assertIsNotNone(f)
        self.assertEqual(f.statement, "Simplicity vs. horizontal scale")
        self.assertEqual(f.between, ["dec-001", "T-042"])
        self.assertEqual(f.dialectic_state, "open — leaning simplicity for <20 concurrent")
        self.assertEqual(f.resolution_criterion, "a load test exceeding 20 concurrent users")
        self.assertEqual(f.status, "open")

    def test_list_open_excludes_resolved_and_dissolved(self):
        self.store.record(_t(tension_id="t-open", status="open"))
        self.store.record(_t(tension_id="t-res", status="resolved"))
        self.store.record(_t(tension_id="t-dis", status="dissolved"))
        ids = [t.tension_id for t in self.store.list_open()]
        self.assertEqual(ids, ["t-open"])

    def test_list_open_newest_first(self):
        self.store.record(_t(tension_id="t-old", created_at="2026-06-20T00:00:00Z"))
        self.store.record(_t(tension_id="t-new", created_at="2026-06-23T00:00:00Z"))
        ids = [t.tension_id for t in self.store.list_open()]
        self.assertLess(ids.index("t-new"), ids.index("t-old"))

    def test_update_status_resolve_removes_from_open(self):
        self.store.record(_t(tension_id="t-1"))
        self.store.update_status("t-1", "resolved", resolved_by="dec-009")
        f = self.store.get("t-1")
        self.assertEqual(f.status, "resolved")
        self.assertEqual(f.resolved_by, "dec-009")
        self.assertEqual(self.store.list_open(), [])

    def test_query_relevant_matches_statement(self):
        self.store.record(_t(tension_id="t-cache", statement="Redis cache TTL vs. memory pressure"))
        self.store.record(_t(tension_id="t-auth", statement="OAuth tokens vs. session cookies"))
        res = self.store.query_relevant("how should the cache handle memory")
        self.assertIn("t-cache", [t.tension_id for t in res])

    def test_empty_store(self):
        self.assertEqual(self.store.list_open(), [])
        self.assertIsNone(self.store.get("nope"))


class TestFormatTensionContext(unittest.TestCase):
    def test_empty_returns_empty_string(self):
        self.assertEqual(format_tension_context([]), "")

    def test_renders_hold_header_and_fields(self):
        out = format_tension_context([_t()])
        self.assertIn("Active Tensions (HOLD", out)
        self.assertIn("do not silently collapse", out.lower())
        self.assertIn("Simplicity vs. horizontal scale", out)
        self.assertIn("a load test exceeding 20 concurrent users", out)
        self.assertIn("dec-001", out)


if __name__ == "__main__":
    unittest.main()
