"""Tests for the SHARED SHADOW handoff record (P4).

A compact, inspectable record of the current agreement, carried on the lead->verify handoff.
Two integrity rules: absence is always visible (never a silent omission), and Material unknowns
must not be empty when unresolved items (open tensions) exist.
See docs/Shadowland2/promptclaw-integration-proposal.md (P4).
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.shared_shadow import (
    SharedShadow,
    render_shared_shadow,
    validate_shared_shadow,
)


class TestRenderSharedShadow(unittest.TestCase):
    def test_renders_all_sections(self):
        s = SharedShadow(
            purpose="Build the asset-bus producer",
            deliverable="run_asset_bus_producer loop",
            constraints=["no new external deps"],
            decisions=["Use Redis for the cache"],
            material_unknowns=["Simplicity vs. scale"],
            current_phase="verify",
            next_move="codex verifies claude's output",
            success_criteria=["all ACs pass"],
        )
        out = render_shared_shadow(s)
        self.assertIn("# Shared Shadow", out)
        for needle in ("Build the asset-bus producer", "no new external deps",
                       "Use Redis for the cache", "Simplicity vs. scale",
                       "verify", "all ACs pass"):
            self.assertIn(needle, out)

    def test_absence_is_visible_not_silent(self):
        # Empty fields must still render a line, so a gap is a conscious claim, not an omission.
        out = render_shared_shadow(SharedShadow(purpose="x"))
        self.assertIn("Material unknowns", out)
        self.assertIn("none stated", out.lower())


class TestValidateSharedShadow(unittest.TestCase):
    def test_empty_material_unknowns_with_open_items_flagged(self):
        s = SharedShadow(purpose="x", material_unknowns=[])
        issues = validate_shared_shadow(s, open_item_count=2)
        self.assertTrue(any("unknown" in i.lower() for i in issues))

    def test_material_unknowns_present_no_issue(self):
        s = SharedShadow(purpose="x", material_unknowns=["a held tension"])
        issues = validate_shared_shadow(s, open_item_count=2)
        self.assertFalse(any("unknown" in i.lower() for i in issues))

    def test_empty_material_unknowns_no_open_items_ok(self):
        s = SharedShadow(purpose="x", material_unknowns=[])
        self.assertEqual(validate_shared_shadow(s, open_item_count=0), [])

    def test_missing_purpose_flagged(self):
        issues = validate_shared_shadow(SharedShadow(purpose=""), open_item_count=0)
        self.assertTrue(any("purpose" in i.lower() for i in issues))


class TestEngineSharedShadow(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-ss-"))
        from promptclaw.coherence.engine import CoherenceEngine
        from promptclaw.coherence.models import CoherenceConfig
        self.engine = CoherenceEngine(CoherenceConfig(), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_pulls_decisions_constraints_and_tensions(self):
        self.engine.record_decision(
            title="Use Redis", context="c", decision_text="Redis cache",
            rationale="fast", constrains=["TTL on every key"],
        )
        self.engine.record_tension("Simplicity vs. scale", dialectic_state="open")
        s = self.engine.build_shared_shadow(purpose="Build cache", current_phase="verify")
        self.assertIn("Use Redis", s.decisions)
        self.assertIn("TTL on every key", s.constraints)
        # open tensions become material unknowns -> the integrity rule holds by construction
        self.assertIn("Simplicity vs. scale", s.material_unknowns)

    def test_handoff_string_includes_open_tension_as_unknown(self):
        self.engine.record_tension("Latency vs. cost", dialectic_state="open")
        out = self.engine.shared_shadow_handoff(purpose="Build cache", current_phase="verify")
        self.assertIn("# Shared Shadow", out)
        self.assertIn("Material unknowns", out)
        self.assertIn("Latency vs. cost", out)


class TestVerifyPromptShadowInjection(unittest.TestCase):
    """Phase 1b: the SHARED SHADOW handoff must reach the verify prompt, not just disk."""

    def _decision(self):
        from promptclaw.models import RouteDecision
        return RouteDecision(
            ambiguous=False, clarification_question="", lead_agent="claude",
            verifier_agent="codex", reason="r", subtask_brief="b", task_type="coding",
        )

    def test_build_verify_prompt_includes_shared_shadow(self):
        from promptclaw.prompt_builder import build_verify_prompt
        out = build_verify_prompt(
            agent_instruction="V", task_text="T", decision=self._decision(),
            lead_output="L", memory_text="",
            shared_shadow="# Shared Shadow\n**Purpose:** build the widget",
        )
        self.assertIn("Shared Shadow (lead", out)
        self.assertIn("build the widget", out)

    def test_build_verify_prompt_omits_shadow_when_empty(self):
        from promptclaw.prompt_builder import build_verify_prompt
        out = build_verify_prompt(
            agent_instruction="V", task_text="T", decision=self._decision(),
            lead_output="L", memory_text="",
        )
        self.assertNotIn("Shared Shadow (lead", out)


if __name__ == "__main__":
    unittest.main()
