"""Tests for the foundation/formula rule tier (P5).

tier is orthogonal to severity: severity governs *when a match blocks*, tier governs *whether
the rule is entrenched* (foundation = fixed, recut-don't-grandfather; formula = adjustable).
See docs/Shadowland2/promptclaw-integration-proposal.md (P5).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.constitution import Constitution
from promptclaw.coherence.models import EnforcementMode
from promptclaw.coherence.prompt_injection import format_constitutional_context


class TestRuleTier(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-tier-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _constitution(self, rules) -> Constitution:
        path = self.tmp / "c.json"
        path.write_text(json.dumps({"rules": rules}))
        return Constitution(path)

    def test_tier_defaults_to_formula(self):
        c = self._constitution([{"id": "R1", "severity": "soft", "description": "d", "keywords": ["x"]}])
        self.assertEqual(c.rules[0].tier, "formula")

    def test_tier_loaded_and_accessors(self):
        c = self._constitution([
            {"id": "F1", "severity": "hard", "tier": "foundation", "description": "d"},
            {"id": "M1", "severity": "soft", "tier": "formula", "description": "d"},
        ])
        self.assertEqual([r.rule_id for r in c.foundation_rules()], ["F1"])
        self.assertEqual([r.rule_id for r in c.formula_rules()], ["M1"])

    def test_format_shows_tier_and_severity(self):
        c = self._constitution([{"id": "F1", "severity": "hard", "tier": "foundation", "description": "d"}])
        out = format_constitutional_context(c.rules, EnforcementMode.MONITOR)
        self.assertIn("FOUNDATION", out)
        self.assertIn("HARD", out)


if __name__ == "__main__":
    unittest.main()
