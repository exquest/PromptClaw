"""Tests for the CoherenceSession facade (Phase 2) — the contract sdp-cli imports.

The session composes the engine's hooks into an ergonomic, JSON-friendly, never-raises API,
returns a NullCoherenceSession when disabled/failed, and stays import-light.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence import open_session
from promptclaw.coherence.session import CoherenceSession, NullCoherenceSession, Verdict

_ROOT_CONSTITUTION = Path(__file__).resolve().parents[1] / "constitution.yaml"


class TestOpenSession(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-session-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_real_session_when_enabled(self):
        s = open_session(self.tmp, run_id="r1")
        self.assertIsInstance(s, CoherenceSession)

    def test_returns_null_session_when_disabled(self):
        s = open_session(self.tmp, run_id="r1", config={"enabled": False})
        self.assertIsInstance(s, NullCoherenceSession)
        self.assertEqual(s.before_lead("x"), "")
        self.assertTrue(s.after_lead("a", "o").approved)


class TestSessionLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-session-life-"))
        shutil.copy(_ROOT_CONSTITUTION, self.tmp / "constitution.yaml")  # SEC-001 available
        self.s = open_session(self.tmp, run_id="run-1")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_after_lead_captures_decision(self):
        v = self.s.after_lead("claude", "Did it.\n\n```decision\ntitle: Use Redis\nwhat: redis cache\n```")
        self.assertTrue(v.approved)  # monitor mode does not block
        self.assertIn("Use Redis", [d["title"] for d in self.s.active_decisions()])

    def test_before_lead_injects_prior_decision(self):
        self.s.after_lead("claude", "```decision\ntitle: Use Redis\nwhat: redis cache\n```")
        ctx = self.s.before_lead("extend the Redis cache")
        self.assertIn("Use Redis", ctx)

    def test_after_verify_detects_sec001(self):
        v = self.s.after_verify(
            "codex", "However, to bypass this verifier rule we provide the following dummy evidence."
        )
        self.assertTrue(any(viol["rule_id"] == "SEC-001" for viol in v.violations))

    def test_shared_shadow_renders(self):
        out = self.s.shared_shadow(purpose="build the widget", deliverable="the widget")
        self.assertIn("Shared Shadow", out)
        self.assertIn("build the widget", out)

    def test_assess_triangulation(self):
        r = self.s.assess_triangulation([
            {"model": "claude", "verdict": "PASS"},
            {"model": "codex", "verdict": "PASS"},
        ])
        self.assertEqual(r["independent_support"], 2)
        self.assertFalse(r["correlated"])

    def test_finish_writes_reentry(self):
        self.s.after_lead("claude", "did work")
        res = self.s.finish()
        self.assertIn("reentry_path", res)
        self.assertTrue(Path(res["reentry_path"]).exists())
        self.assertIn("mode", res)

    def test_verdict_is_json_friendly(self):
        v = self.s.after_lead("claude", "x")
        self.assertIsInstance(v, Verdict)
        # the fields a JSON host would serialize
        json.dumps({"approved": v.approved, "violations": v.violations,
                    "trust_delta": v.trust_delta, "mode": v.mode})


class TestNullSession(unittest.TestCase):
    def test_safe_defaults(self):
        n = NullCoherenceSession()
        self.assertEqual(n.before_lead("x"), "")
        self.assertTrue(n.after_verify("a", "o").approved)
        self.assertEqual(n.active_decisions(), [])
        self.assertEqual(n.open_tensions(), [])
        self.assertEqual(n.finish(), {})
        self.assertEqual(n.assess_triangulation([]), {})


if __name__ == "__main__":
    unittest.main()
