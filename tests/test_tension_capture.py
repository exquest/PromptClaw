"""Tests for ```tension parsing and engine auto-capture / injection / digest wiring (P1)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.tension_capture import parse_tension_blocks


class TestParseTensionBlocks(unittest.TestCase):
    def test_no_fence_returns_empty(self):
        self.assertEqual(parse_tension_blocks("just prose, tension: nope"), [])

    def test_ignores_decision_fence(self):
        self.assertEqual(parse_tension_blocks("```decision\ntitle: X\n```"), [])

    def test_full_block(self):
        text = (
            "```tension\n"
            "statement: Simplicity vs. horizontal scale\n"
            "state: open — leaning simple for now\n"
            "resolves: a load test exceeding 20 concurrent users\n"
            "between: dec-001, T-042\n"
            "```"
        )
        b = parse_tension_blocks(text)[0]
        self.assertEqual(b["statement"], "Simplicity vs. horizontal scale")
        self.assertEqual(b["dialectic_state"], "open — leaning simple for now")
        self.assertEqual(b["resolution_criterion"], "a load test exceeding 20 concurrent users")
        self.assertEqual(b["between"], ["dec-001", "T-042"])

    def test_statement_required(self):
        self.assertEqual(parse_tension_blocks("```tension\nstate: open\n```"), [])

    def test_key_aliases(self):
        b = parse_tension_blocks(
            "```tension\ntension: A vs B\ndialectic: stuck\nresolution: more data\n```"
        )[0]
        self.assertEqual(b["statement"], "A vs B")
        self.assertEqual(b["dialectic_state"], "stuck")
        self.assertEqual(b["resolution_criterion"], "more data")


class TestEngineTensionWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-teng-"))
        from promptclaw.coherence.engine import CoherenceEngine
        from promptclaw.coherence.models import CoherenceConfig
        self.engine = CoherenceEngine(CoherenceConfig(), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_post_lead_captures_tension(self):
        out = "```tension\nstatement: Latency vs. cost\nstate: open\nresolves: a budget decision\n```"
        self.engine.post_lead("r1", "claude", out)
        self.assertEqual([t.statement for t in self.engine.tension_store.list_open()], ["Latency vs. cost"])

    def test_tension_dedup_normalized(self):
        self.engine.post_lead("r1", "claude", "```tension\nstatement: A vs B\n```")
        self.engine.post_lead("r1", "claude", "```tension\nstatement:  a   vs b \n```")
        self.assertEqual(len(self.engine.tension_store.list_open()), 1)

    def test_open_tension_injected_into_pre_lead(self):
        self.engine.record_tension("Simplicity vs. scale", dialectic_state="open")
        v = self.engine.pre_lead("r1", "claude", "build the thing")
        self.assertIn("Active Tensions (HOLD", v.injected_context)
        self.assertIn("Simplicity vs. scale", v.injected_context)

    def test_resolved_tension_not_injected(self):
        t = self.engine.record_tension("Temp tension", dialectic_state="open")
        self.engine.resolve_tension(t.tension_id, resolved_by="dec-1")
        v = self.engine.pre_lead("r1", "claude", "build")
        self.assertNotIn("Temp tension", v.injected_context)

    def test_dissolve_tension_removes_it(self):
        t = self.engine.record_tension("Illusory tension")
        self.engine.dissolve_tension(t.tension_id)
        self.assertEqual(self.engine.tension_store.list_open(), [])

    def test_digest_shows_open_tensions(self):
        self.engine.record_tension("Held thing", dialectic_state="open")
        self.engine.emit("r1", "coherence.finalize", phase="complete")
        text = self.engine.build_reentry_digest_text(run_id="r1")
        self.assertIn("Held tensions", text)
        self.assertIn("Held thing", text)

    def test_decisions_still_injected_alongside_tensions(self):
        # Guards the pre_* hook refactor: decisions must still be injected.
        self.engine.record_decision(title="Use Redis", context="c",
                                    decision_text="Redis cache", rationale="fast")
        v = self.engine.pre_lead("r1", "claude", "set up the Redis cache")
        self.assertIn("Active Decisions (DO NOT VIOLATE)", v.injected_context)


if __name__ == "__main__":
    unittest.main()
