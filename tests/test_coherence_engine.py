"""Tests for the coherence engine facade."""

import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.engine import CoherenceEngine, NullCoherenceEngine
from promptclaw.coherence.models import CoherenceConfig, EnforcementMode


class TestCoherenceEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-coherence-"))
        (self.temp_dir / ".promptclaw").mkdir()
        self.config = CoherenceConfig()
        self.engine = CoherenceEngine(self.config, self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_init_creates_sqlite_db(self):
        db_path = self.temp_dir / ".promptclaw" / "coherence.db"
        self.assertTrue(db_path.exists())

    def test_emit_persists_event(self):
        event = self.engine.emit("run-1", "test_event", "hello")
        self.assertEqual(event.run_id, "run-1")
        self.assertEqual(event.event_type, "test_event")
        events = self.engine.replay("run-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["message"], "hello")

    def test_emit_increments_sequence(self):
        self.engine.emit("run-1", "event_a")
        self.engine.emit("run-1", "event_b")
        self.engine.emit("run-1", "event_c")
        events = self.engine.replay("run-1")
        self.assertEqual([e.sequence_number for e in events], [0, 1, 2])

    def test_pre_routing_returns_approved(self):
        verdict = self.engine.pre_routing("run-1", "task text", "memory")
        self.assertTrue(verdict.approved)
        self.assertEqual(verdict.mode, EnforcementMode.MONITOR)
        self.assertEqual(len(verdict.violations), 0)

    def test_post_routing_returns_approved(self):
        verdict = self.engine.post_routing("run-1", {"lead_agent": "claude"})
        self.assertTrue(verdict.approved)

    def test_pre_lead_returns_approved(self):
        verdict = self.engine.pre_lead("run-1", "claude", "task text")
        self.assertTrue(verdict.approved)

    def test_post_lead_returns_approved(self):
        verdict = self.engine.post_lead("run-1", "claude", "output text")
        self.assertTrue(verdict.approved)

    def test_pre_verify_returns_approved(self):
        verdict = self.engine.pre_verify("run-1", "codex", "lead output")
        self.assertTrue(verdict.approved)

    def test_post_verify_returns_approved(self):
        verdict = self.engine.post_verify("run-1", "codex", "PASS")
        self.assertTrue(verdict.approved)

    def test_finalize_returns_approved(self):
        verdict = self.engine.finalize("run-1")
        self.assertTrue(verdict.approved)

    def test_hooks_emit_events(self):
        self.engine.pre_routing("run-1", "task", "memory")
        self.engine.post_routing("run-1", {})
        self.engine.pre_lead("run-1", "claude", "task")
        self.engine.post_lead("run-1", "claude", "output")
        self.engine.pre_verify("run-1", "codex", "lead output")
        self.engine.post_verify("run-1", "codex", "PASS")
        self.engine.finalize("run-1")
        events = self.engine.replay("run-1")
        self.assertEqual(len(events), 7)
        types = [e.event_type for e in events]
        self.assertIn("coherence.pre_routing", types)
        self.assertIn("coherence.finalize", types)


class TestNullCoherenceEngine(unittest.TestCase):
    def test_all_hooks_return_approved(self):
        engine = NullCoherenceEngine()
        self.assertTrue(engine.pre_routing("run-1", "t", "m").approved)
        self.assertTrue(engine.post_routing("run-1", {}).approved)
        self.assertTrue(engine.pre_lead("run-1", "a", "t").approved)
        self.assertTrue(engine.post_lead("run-1", "a", "o").approved)
        self.assertTrue(engine.pre_verify("run-1", "a", "o").approved)
        self.assertTrue(engine.post_verify("run-1", "a", "P").approved)
        self.assertTrue(engine.finalize("run-1").approved)

    def test_emit_is_noop(self):
        engine = NullCoherenceEngine()
        engine.emit("run-1", "test")  # Should not raise

    def test_replay_returns_empty(self):
        engine = NullCoherenceEngine()
        self.assertEqual(engine.replay("run-1"), [])


if __name__ == "__main__":
    unittest.main()
