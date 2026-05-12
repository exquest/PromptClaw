"""Tests for constitutional rule enforcement."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.constitution import Constitution
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


class ConstitutionEndToEndTests(unittest.TestCase):
    """End-to-end depth-2 coverage for the constitutional rule pipeline."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-const-e2e-"))
        self.addCleanup(shutil.rmtree, self.temp_dir)
        self.rule_definitions: list[dict] = [
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
                "id": "be-polite",
                "severity": "soft",
                "description": "Responses should remain polite",
                "keywords": ["rude", "offensive"],
            },
            {
                "id": "lead-only-rule",
                "severity": "hard",
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
            {
                "id": "lead-claude-only-rule",
                "severity": "hard",
                "description": "Compound phase + agent gating",
                "keywords": ["compound"],
                "applies_to": ["lead"],
                "applies_to_agents": ["claude"],
                "message": "Compound violation",
            },
            {
                "id": "combo-pattern-and-keywords",
                "severity": "soft",
                "description": "Either regex or keyword path may match",
                "pattern": r"\bdrop\s+table\b",
                "keywords": ["bobby tables"],
                "message": "SQL-style risk content",
            },
        ]
        self.constitution_path = _write_json_constitution(
            self.temp_dir, self.rule_definitions
        )
        self.constitution = Constitution(self.constitution_path)

    def _rule_ids(self, violations: list[Violation]) -> list[str]:
        ids: list[str] = []
        for violation in violations:
            ids.append(violation.rule_id)
        return ids

    def test_json_load_preserves_rule_count_and_field_mapping(self) -> None:
        loaded = self.constitution.rules
        self.assertEqual(len(loaded), len(self.rule_definitions))
        loaded_ids = [r.rule_id for r in loaded]
        for definition in self.rule_definitions:
            self.assertIn(definition["id"], loaded_ids)
        secret_rule = next(r for r in loaded if r.rule_id == "no-secrets")
        self.assertEqual(secret_rule.severity, ViolationSeverity.HARD)
        self.assertEqual(secret_rule.message, "Output contains what appears to be a secret")

    def test_missing_file_path_yields_empty_rules_without_error(self) -> None:
        ghost_path = self.temp_dir / "does-not-exist.json"
        self.assertFalse(ghost_path.exists())
        constitution = Constitution(ghost_path)
        self.assertEqual(constitution.rules, [])
        violations = constitution.evaluate("api_key = sk-shouldnotmatch")
        self.assertEqual(violations, [])

    def test_none_path_yields_empty_rules_without_error(self) -> None:
        constitution = Constitution(None)
        self.assertEqual(constitution.rules, [])
        violations = constitution.evaluate("api_key = sk-shouldnotmatch")
        self.assertEqual(violations, [])
        for mode in (EnforcementMode.MONITOR, EnforcementMode.SOFT, EnforcementMode.FULL):
            self.assertFalse(constitution.should_block(violations, mode))

    def test_malformed_json_falls_back_to_empty_rules(self) -> None:
        broken_path = self.temp_dir / "broken.json"
        broken_path.write_text("{ this is not valid json", encoding="utf-8")
        constitution = Constitution(broken_path)
        self.assertEqual(constitution.rules, [])
        violations = constitution.evaluate("api_key = sk-shouldnotmatch")
        self.assertEqual(violations, [])

    def test_unknown_extension_falls_back_to_json_parse(self) -> None:
        weird_path = self.temp_dir / "rules.txt"
        payload = {"rules": [{"id": "weird", "severity": "soft", "keywords": ["weird"]}]}
        weird_path.write_text(json.dumps(payload), encoding="utf-8")
        constitution = Constitution(weird_path)
        self.assertEqual(len(constitution.rules), 1)
        self.assertEqual(constitution.rules[0].rule_id, "weird")
        violations = constitution.evaluate("this text is weird")
        self.assertIn("weird", self._rule_ids(violations))

    def test_regex_pattern_matches_secret_payload_end_to_end(self) -> None:
        text = "Here is api_key = sk-12345abc embedded in a message"
        violations = self.constitution.evaluate(text)
        rule_ids = self._rule_ids(violations)
        self.assertIn("no-secrets", rule_ids)
        secret_violations = [v for v in violations if v.rule_id == "no-secrets"]
        self.assertEqual(len(secret_violations), 1)
        self.assertEqual(secret_violations[0].severity, ViolationSeverity.HARD)

    def test_regex_no_match_returns_no_violation_for_clean_payload(self) -> None:
        text = "This text has nothing sensitive in it whatsoever."
        violations = self.constitution.evaluate(text)
        rule_ids = self._rule_ids(violations)
        self.assertNotIn("no-secrets", rule_ids)
        self.assertNotIn("no-profanity", rule_ids)
        self.assertNotIn("be-polite", rule_ids)

    def test_keyword_match_case_insensitive_end_to_end(self) -> None:
        violations = self.constitution.evaluate("This contains BADWORD uppercase")
        rule_ids = self._rule_ids(violations)
        self.assertIn("no-profanity", rule_ids)
        profanity = [v for v in violations if v.rule_id == "no-profanity"]
        self.assertEqual(profanity[0].severity, ViolationSeverity.SOFT)
        self.assertEqual(profanity[0].message, "Contains profanity")

    def test_keyword_substring_match_within_larger_text(self) -> None:
        text = "while reviewing curseword-laden output we want a flag"
        violations = self.constitution.evaluate(text)
        rule_ids = self._rule_ids(violations)
        self.assertIn("no-profanity", rule_ids)
        for unrelated in ("be-polite", "no-secrets", "claude-only-rule"):
            self.assertNotIn(unrelated, rule_ids)

    def test_combined_pattern_and_keywords_each_match_independently(self) -> None:
        pattern_violations = self.constitution.evaluate("about to DROP TABLE users now")
        keyword_violations = self.constitution.evaluate("watch out for bobby tables jokes")
        self.assertIn("combo-pattern-and-keywords", self._rule_ids(pattern_violations))
        self.assertIn("combo-pattern-and-keywords", self._rule_ids(keyword_violations))
        for violations in (pattern_violations, keyword_violations):
            self.assertEqual(
                len([v for v in violations if v.rule_id == "combo-pattern-and-keywords"]),
                1,
            )

    def test_phase_filter_active_includes_only_phase_specific_rule(self) -> None:
        violations = self.constitution.evaluate("restricted content here", phase="lead")
        rule_ids = self._rule_ids(violations)
        self.assertIn("lead-only-rule", rule_ids)
        lead_only = [v for v in violations if v.rule_id == "lead-only-rule"]
        self.assertEqual(lead_only[0].severity, ViolationSeverity.HARD)

    def test_phase_filter_inactive_excludes_phase_specific_rule(self) -> None:
        violations = self.constitution.evaluate("restricted content here", phase="routing")
        rule_ids = self._rule_ids(violations)
        self.assertNotIn("lead-only-rule", rule_ids)
        for unrelated in ("no-secrets", "no-profanity"):
            self.assertNotIn(unrelated, rule_ids)

    def test_agent_filter_active_includes_only_agent_specific_rule(self) -> None:
        violations = self.constitution.evaluate("agentspecific text", agent="claude")
        rule_ids = self._rule_ids(violations)
        self.assertIn("claude-only-rule", rule_ids)
        claude_only = [v for v in violations if v.rule_id == "claude-only-rule"]
        self.assertEqual(claude_only[0].severity, ViolationSeverity.SOFT)

    def test_agent_filter_inactive_excludes_agent_specific_rule(self) -> None:
        violations = self.constitution.evaluate("agentspecific text", agent="gpt")
        rule_ids = self._rule_ids(violations)
        self.assertNotIn("claude-only-rule", rule_ids)
        for other in ("lead-claude-only-rule", "no-secrets"):
            self.assertNotIn(other, rule_ids)

    def test_phase_agnostic_rule_fires_under_every_phase_argument(self) -> None:
        for phase in ("", "lead", "verify", "routing", "scan"):
            violations = self.constitution.evaluate("api_key = sk-anywhere", phase=phase)
            rule_ids = self._rule_ids(violations)
            self.assertIn("no-secrets", rule_ids)

    def test_compound_phase_and_agent_filter_must_match_both_axes(self) -> None:
        match = self.constitution.evaluate("compound content", phase="lead", agent="claude")
        wrong_phase = self.constitution.evaluate("compound content", phase="routing", agent="claude")
        wrong_agent = self.constitution.evaluate("compound content", phase="lead", agent="gpt")
        self.assertIn("lead-claude-only-rule", self._rule_ids(match))
        self.assertNotIn("lead-claude-only-rule", self._rule_ids(wrong_phase))
        self.assertNotIn("lead-claude-only-rule", self._rule_ids(wrong_agent))

    def test_message_falls_back_to_description_when_message_missing(self) -> None:
        violations = self.constitution.evaluate("that comment was rude")
        polite = [v for v in violations if v.rule_id == "be-polite"]
        self.assertEqual(len(polite), 1)
        self.assertEqual(polite[0].message, "Responses should remain polite")
        self.assertEqual(polite[0].severity, ViolationSeverity.SOFT)

    def test_hard_rules_returns_only_hard_severity_rules(self) -> None:
        hard = self.constitution.hard_rules()
        rule_ids = [r.rule_id for r in hard]
        for expected_hard in ("no-secrets", "lead-only-rule", "lead-claude-only-rule"):
            self.assertIn(expected_hard, rule_ids)
        for unexpected_soft in ("no-profanity", "be-polite", "claude-only-rule"):
            self.assertNotIn(unexpected_soft, rule_ids)

    def test_soft_rules_returns_only_soft_severity_rules(self) -> None:
        soft = self.constitution.soft_rules()
        rule_ids = [r.rule_id for r in soft]
        for expected_soft in ("no-profanity", "be-polite", "claude-only-rule", "combo-pattern-and-keywords"):
            self.assertIn(expected_soft, rule_ids)
        for unexpected_hard in ("no-secrets", "lead-only-rule", "lead-claude-only-rule"):
            self.assertNotIn(unexpected_hard, rule_ids)

    def test_rules_for_phase_includes_phase_agnostic_and_specific_rules(self) -> None:
        lead_rules = self.constitution.rules_for_phase("lead")
        rule_ids = [r.rule_id for r in lead_rules]
        for expected in ("no-secrets", "lead-only-rule", "lead-claude-only-rule", "be-polite"):
            self.assertIn(expected, rule_ids)
        self.assertGreater(len(lead_rules), 0)

    def test_rules_for_phase_excludes_other_phase_specific_rules(self) -> None:
        routing_rules = self.constitution.rules_for_phase("routing")
        rule_ids = [r.rule_id for r in routing_rules]
        for unexpected in ("lead-only-rule", "lead-claude-only-rule"):
            self.assertNotIn(unexpected, rule_ids)
        for still_present in ("no-secrets", "no-profanity"):
            self.assertIn(still_present, rule_ids)

    def test_should_block_monitor_mode_never_blocks_any_violation(self) -> None:
        hard_only = self.constitution.evaluate("api_key = sk-leak")
        mixed = self.constitution.evaluate("api_key = sk-leak with badword inside")
        self.assertFalse(self.constitution.should_block(hard_only, EnforcementMode.MONITOR))
        self.assertFalse(self.constitution.should_block(mixed, EnforcementMode.MONITOR))
        self.assertGreater(len(hard_only), 0)

    def test_should_block_soft_mode_blocks_when_hard_violation_present(self) -> None:
        violations = self.constitution.evaluate("api_key = sk-leak in body")
        rule_ids = self._rule_ids(violations)
        self.assertIn("no-secrets", rule_ids)
        blocked = self.constitution.should_block(violations, EnforcementMode.SOFT)
        self.assertTrue(blocked)

    def test_should_block_soft_mode_does_not_block_soft_only_violations(self) -> None:
        violations = self.constitution.evaluate("that was rude and badword")
        rule_ids = self._rule_ids(violations)
        self.assertNotIn("no-secrets", rule_ids)
        blocked = self.constitution.should_block(violations, EnforcementMode.SOFT)
        self.assertFalse(blocked)

    def test_should_block_full_mode_blocks_any_violation_severity(self) -> None:
        soft_only = self.constitution.evaluate("that was rude")
        hard_only = self.constitution.evaluate("api_key = sk-leak")
        for violations in (soft_only, hard_only):
            self.assertGreater(len(violations), 0)
            self.assertTrue(self.constitution.should_block(violations, EnforcementMode.FULL))

    def test_should_block_returns_false_for_empty_violations_in_all_modes(self) -> None:
        empty: list[Violation] = []
        for mode in (EnforcementMode.MONITOR, EnforcementMode.SOFT, EnforcementMode.FULL):
            blocked = self.constitution.should_block(empty, mode)
            self.assertFalse(blocked)

    def test_pipeline_load_evaluate_secret_blocks_under_soft_mode(self) -> None:
        constitution = Constitution(self.constitution_path)
        text = "api_key = sk-pipeline123 leaked in lead phase"
        violations = constitution.evaluate(text, phase="lead", agent="claude")
        self.assertIn("no-secrets", self._rule_ids(violations))
        self.assertTrue(constitution.should_block(violations, EnforcementMode.SOFT))

    def test_pipeline_load_evaluate_clean_text_does_not_block_in_full_mode(self) -> None:
        constitution = Constitution(self.constitution_path)
        text = "everything in this response is polite, secure, and on topic"
        violations = constitution.evaluate(text, phase="verify", agent="codex")
        self.assertEqual(violations, [])
        self.assertFalse(constitution.should_block(violations, EnforcementMode.FULL))

    def test_pipeline_multiple_rules_match_yields_multiple_violations(self) -> None:
        text = "api_key = sk-leak plus badword and rude tone"
        violations = self.constitution.evaluate(text)
        rule_ids = self._rule_ids(violations)
        for expected in ("no-secrets", "no-profanity", "be-polite"):
            self.assertIn(expected, rule_ids)
        self.assertGreaterEqual(len(violations), 3)

    def test_pipeline_violation_carries_message_severity_and_rule_id(self) -> None:
        violations = self.constitution.evaluate("api_key = sk-fields-check")
        secret = [v for v in violations if v.rule_id == "no-secrets"]
        self.assertEqual(len(secret), 1)
        self.assertEqual(secret[0].rule_id, "no-secrets")
        self.assertEqual(secret[0].severity, ViolationSeverity.HARD)
        self.assertEqual(secret[0].message, "Output contains what appears to be a secret")


if __name__ == "__main__":
    unittest.main()
