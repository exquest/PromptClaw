"""Tests for triangulation — independence-of-angle scoring of verifier verdicts (P6)."""

from __future__ import annotations

import unittest

from promptclaw.coherence.triangulation import assess_triangulation


class TestAssessTriangulation(unittest.TestCase):
    def test_same_model_thrice_is_one_view(self):
        r = assess_triangulation([{"model": "claude", "verdict": "PASS"}] * 3)
        self.assertEqual(r.majority_verdict, "PASS")
        self.assertEqual(r.distinct_angles, 1)
        self.assertEqual(r.independent_support, 1)  # three PASSes, but one angle
        self.assertTrue(r.correlated)

    def test_three_distinct_models_are_independent(self):
        r = assess_triangulation([
            {"model": "claude", "verdict": "PASS"},
            {"model": "codex", "verdict": "PASS"},
            {"model": "gemini", "verdict": "PASS"},
        ])
        self.assertEqual(r.distinct_angles, 3)
        self.assertEqual(r.independent_support, 3)
        self.assertFalse(r.correlated)

    def test_majority_and_independent_support(self):
        r = assess_triangulation([
            {"model": "claude", "verdict": "PASS"},
            {"model": "codex", "verdict": "PASS"},
            {"model": "gemini", "verdict": "FAIL"},
        ])
        self.assertEqual(r.majority_verdict, "PASS")
        self.assertEqual(r.independent_support, 2)
        self.assertFalse(r.correlated)

    def test_verdicts_normalized_and_agent_fallback(self):
        r = assess_triangulation([
            {"agent": "a", "verdict": "pass"},
            {"agent": "b", "verdict": "Pass"},
        ])
        self.assertEqual(r.majority_verdict, "PASS")
        self.assertEqual(r.distinct_angles, 2)

    def test_empty(self):
        r = assess_triangulation([])
        self.assertEqual(r.total_votes, 0)
        self.assertEqual(r.distinct_angles, 0)


if __name__ == "__main__":
    unittest.main()
