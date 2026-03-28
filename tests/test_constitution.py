"""Tests for constitutional rule enforcement."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.constitution import Constitution, Rule
from promptclaw.coherence.models import EnforcementMode, Violation, ViolationSeverity


def _write_json_constitution(dir_path: Path, rules: list[dict]) -> Path:
    """Helper: write a JSON constitution file and return its path."""
    path = dir_path / "constitution.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"rules": rules}, f)
    return path


class TestConstitutionLoading(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-const-"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_load_rules_from_json(self):
        path = _write_json_constitution(self.temp_dir, [
            {
                "id": "no-secrets",
                "severity": "hard",
                "description": "Never include API keys or secrets",
                "pattern": r"(api[_-]?key|secret|password|token)\s*[:=]\s*\S+",
                "message": "Output contains what appears to be a secret",
            },
            {
                "id": "be-polite",
                "severity": "soft",
                "description": "Responses should be polite",
                "keywords": ["rude", "offensive"],
                "message": "Response may contain impolite language",
            },
        ])
        c = Constitution(path)
        self.assertEqual(len(c.rules), 2)
        self.assertEqual(c.rules[0].rule_id, "no-secrets")
        self.assertEqual(c.rules[0].severity, ViolationSeverity.HARD)
        self.assertEqual(c.rules[1].rule_id, "be-polite")
        self.assertEqual(c.rules[1].severity, ViolationSeverity.SOFT)

    def test_missing_file_initializes_empty(self):
        c = Constitution(self.temp_dir / "nonexistent.json")
        self.assertEqual(c.rules, [])

    def test_none_path_initializes_empty(self):
        c = Constitution(None)
        self.assertEqual(c.rules, [])

    def test_empty_constitution_returns_no_violations(self):
        c = Constitution(None)
        violations = c.evaluate("some text here")
        self.assertEqual(violations, [])


class TestConstitutionEvaluate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-const-"))
        path = _write_json_constitution(self.temp_dir, [
            {
                "id": "no-secrets",
                "severity": "hard",
                "description": "Never include API keys or secrets",
                "pattern": r"(api[_-]?key|secret|password|token)\s*[:=]\s*\S+",
                "message": "Output contains what appears to be a secret",
            },
            {
                "id": "no-profanity",
                "severity": "soft",
                "description": "No profanity allowed",
                "keywords": ["badword", "curseword"],
                "message": "Contains profanity",
            },
            {
                "id": "lead-only-rule",
                "severity": "soft",
                "description": "Only applies to lead phase",
                "keywords": ["restricted"],
                "applies_to": ["lead"],
                "message": "Restricted content in lead phase",
            },
            {
                "id": "claude-only-rule",
                "severity": "soft",
                "description": "Only applies to claude agent",
                "keywords": ["agentspecific"],
                "applies_to_agents": ["claude"],
                "message": "Agent-specific violation",
            },
        ])
        self.constitution = Constitution(path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_regex_pattern_match(self):
        violations = self.constitution.evaluate("Here is api_key = sk-12345abc")
        rule_ids = [v.rule_id for v in violations]
        self.assertIn("no-secrets", rule_ids)

    def test_regex_no_match(self):
        violations = self.constitution.evaluate("This text has no secrets at all.")
        rule_ids = [v.rule_id for v in violations]
        self.assertNotIn("no-secrets", rule_ids)

    def test_keyword_match(self):
        violations = self.constitution.evaluate("This contains a badword in it")
        rule_ids = [v.rule_id for v in violations]
        self.assertIn("no-profanity", rule_ids)

    def test_keyword_case_insensitive(self):
        violations = self.constitution.evaluate("This contains BADWORD uppercase")
        rule_ids = [v.rule_id for v in violations]
        self.assertIn("no-profanity", rule_ids)

    def test_phase_filtering_applies(self):
        # "lead-only-rule" should fire during "lead" phase
        violations = self.constitution.evaluate("restricted content", phase="lead")
        rule_ids = [v.rule_id for v in violations]
        self.assertIn("lead-only-rule", rule_ids)

    def test_phase_filtering_excludes(self):
        # "lead-only-rule" should NOT fire during "routing" phase
        violations = self.constitution.evaluate("restricted content", phase="routing")
        rule_ids = [v.rule_id for v in violations]
        self.assertNotIn("lead-only-rule", rule_ids)

    def test_agent_filtering_applies(self):
        # "claude-only-rule" should fire for "claude" agent
        violations = self.constitution.evaluate("agentspecific text", agent="claude")
        rule_ids = [v.rule_id for v in violations]
        self.assertIn("claude-only-rule", rule_ids)

    def test_agent_filtering_excludes(self):
        # "claude-only-rule" should NOT fire for "gpt" agent
        violations = self.constitution.evaluate("agentspecific text", agent="gpt")
        rule_ids = [v.rule_id for v in violations]
        self.assertNotIn("claude-only-rule", rule_ids)

    def test_no_phase_means_all_phases(self):
        # Rules without phase restriction should fire regardless of phase
        violations = self.constitution.evaluate("api_key = mysecret123", phase="routing")
        rule_ids = [v.rule_id for v in violations]
        self.assertIn("no-secrets", rule_ids)

    def test_violation_has_correct_fields(self):
        violations = self.constitution.evaluate("api_key = mysecret123")
        secret_violations = [v for v in violations if v.rule_id == "no-secrets"]
        self.assertEqual(len(secret_violations), 1)
        v = secret_violations[0]
        self.assertEqual(v.severity, ViolationSeverity.HARD)
        self.assertEqual(v.message, "Output contains what appears to be a secret")


class TestConstitutionHelpers(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-const-"))
        path = _write_json_constitution(self.temp_dir, [
            {
                "id": "hard-rule",
                "severity": "hard",
                "description": "A hard rule",
                "keywords": ["hardtrigger"],
                "applies_to": ["lead", "verify"],
            },
            {
                "id": "soft-rule",
                "severity": "soft",
                "description": "A soft rule",
                "keywords": ["softtrigger"],
                "applies_to": ["routing"],
            },
        ])
        self.constitution = Constitution(path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_hard_rules(self):
        hard = self.constitution.hard_rules()
        self.assertEqual(len(hard), 1)
        self.assertEqual(hard[0].rule_id, "hard-rule")

    def test_soft_rules(self):
        soft = self.constitution.soft_rules()
        self.assertEqual(len(soft), 1)
        self.assertEqual(soft[0].rule_id, "soft-rule")

    def test_rules_for_phase(self):
        lead_rules = self.constitution.rules_for_phase("lead")
        rule_ids = [r.rule_id for r in lead_rules]
        self.assertIn("hard-rule", rule_ids)
        self.assertNotIn("soft-rule", rule_ids)

        routing_rules = self.constitution.rules_for_phase("routing")
        rule_ids = [r.rule_id for r in routing_rules]
        self.assertIn("soft-rule", rule_ids)
        self.assertNotIn("hard-rule", rule_ids)


class TestShouldBlock(unittest.TestCase):
    def setUp(self):
        self.constitution = Constitution(None)
        self.hard_violation = Violation(
            rule_id="hard-rule",
            severity=ViolationSeverity.HARD,
            message="Hard violation",
        )
        self.soft_violation = Violation(
            rule_id="soft-rule",
            severity=ViolationSeverity.SOFT,
            message="Soft violation",
        )

    def test_monitor_never_blocks(self):
        self.assertFalse(
            self.constitution.should_block([self.hard_violation], EnforcementMode.MONITOR)
        )
        self.assertFalse(
            self.constitution.should_block([self.soft_violation], EnforcementMode.MONITOR)
        )
        self.assertFalse(
            self.constitution.should_block(
                [self.hard_violation, self.soft_violation], EnforcementMode.MONITOR
            )
        )

    def test_soft_mode_blocks_on_hard_violation(self):
        self.assertTrue(
            self.constitution.should_block([self.hard_violation], EnforcementMode.SOFT)
        )

    def test_soft_mode_does_not_block_on_soft_violation(self):
        self.assertFalse(
            self.constitution.should_block([self.soft_violation], EnforcementMode.SOFT)
        )

    def test_soft_mode_blocks_when_mixed_violations(self):
        self.assertTrue(
            self.constitution.should_block(
                [self.soft_violation, self.hard_violation], EnforcementMode.SOFT
            )
        )

    def test_full_mode_blocks_on_any_violation(self):
        self.assertTrue(
            self.constitution.should_block([self.soft_violation], EnforcementMode.FULL)
        )
        self.assertTrue(
            self.constitution.should_block([self.hard_violation], EnforcementMode.FULL)
        )

    def test_no_violations_never_blocks(self):
        self.assertFalse(
            self.constitution.should_block([], EnforcementMode.FULL)
        )
        self.assertFalse(
            self.constitution.should_block([], EnforcementMode.SOFT)
        )
        self.assertFalse(
            self.constitution.should_block([], EnforcementMode.MONITOR)
        )


if __name__ == "__main__":
    unittest.main()
