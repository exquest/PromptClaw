"""Integration tests for the PromptClaw Coherence Engine.

Tests the full orchestrator flow with constitutional enforcement,
trust scoring, event replay, decision injection, and graduation.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.bootstrap import init_project
from promptclaw.config import load_config, save_config
from promptclaw.coherence.engine import CoherenceEngine
from promptclaw.coherence.models import CoherenceConfig, EnforcementMode, ViolationSeverity
from promptclaw.orchestrator import PromptClawOrchestrator


class CoherenceIntegrationTests(unittest.TestCase):
    """Integration tests for coherence engine wired into the orchestrator."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="promptclaw-integration-"))
        init_project(self.temp_dir, "Integration Test")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _write_constitution(self, rules: list[dict]) -> None:
        """Write a constitution.json to the temp project and update config."""
        constitution = {"rules": rules}
        (self.temp_dir / "constitution.json").write_text(json.dumps(constitution))
        config = load_config(self.temp_dir)
        config.coherence.constitution_path = "constitution.json"
        save_config(self.temp_dir, config)

    def _set_enforcement_mode(self, mode: str) -> None:
        """Update the enforcement_mode in the project config."""
        config = load_config(self.temp_dir)
        config.coherence.enforcement_mode = mode
        save_config(self.temp_dir, config)

    def _run_clear_task(self, orchestrator: PromptClawOrchestrator, title: str = "Clear Task") -> "RunState":
        """Run a clear (non-ambiguous) task that completes without pausing."""
        return orchestrator.run(
            "Implement a small Python utility module with unit tests.",
            title=title,
        )

    # ------------------------------------------------------------------
    # 1. Full run with no constitution
    # ------------------------------------------------------------------

    def test_full_run_no_constitution(self):
        """A normal run completes with coherence enabled but no constitution file.

        Events should be logged in the SQLite database and trust scores
        should increase for compliant actions.
        """
        orchestrator = PromptClawOrchestrator(self.temp_dir)
        state = self._run_clear_task(orchestrator)

        self.assertEqual(state.status, "complete")
        self.assertTrue((self.temp_dir / state.final_summary_path).exists())

        # Events must have been persisted in the coherence event store
        events = orchestrator.coherence.replay(state.run_id)
        self.assertGreater(len(events), 0, "Expected coherence events to be logged")

        # All events should carry the correct run_id
        for ev in events:
            self.assertEqual(ev.run_id, state.run_id)

        # Trust should have increased for the lead agent (compliant, no violations)
        lead_agent = state.lead_agent
        trust_score = orchestrator.coherence.trust_manager.get_score(lead_agent)
        self.assertGreater(
            trust_score.score,
            orchestrator.coherence.trust_manager.INITIAL_SCORE,
            "Trust should increase for compliant actions",
        )
        self.assertGreater(trust_score.compliant_actions, 0)
        self.assertEqual(trust_score.hard_violations, 0)
        self.assertEqual(trust_score.soft_violations, 0)

    # ------------------------------------------------------------------
    # 2. Full run with constitution — no violations
    # ------------------------------------------------------------------

    def test_full_run_constitution_no_violations(self):
        """A run with a 'no-secrets' hard rule completes cleanly when
        the mock agent output does not contain secrets.
        """
        self._write_constitution([
            {
                "id": "no-secrets",
                "severity": "hard",
                "description": "No secrets or API keys in output",
                "pattern": r"(sk-[a-zA-Z0-9]{20,}|AKIA[A-Z0-9]{16})",
                "message": "Output must not contain API keys or secrets",
            }
        ])

        orchestrator = PromptClawOrchestrator(self.temp_dir)
        state = self._run_clear_task(orchestrator)

        self.assertEqual(state.status, "complete")

        # No violations should be recorded
        events = orchestrator.coherence.replay(state.run_id)
        self.assertGreater(len(events), 0)

        # Trust should increase (no violations)
        lead_agent = state.lead_agent
        trust_score = orchestrator.coherence.trust_manager.get_score(lead_agent)
        self.assertGreater(trust_score.score, orchestrator.coherence.trust_manager.INITIAL_SCORE)
        self.assertEqual(trust_score.hard_violations, 0)

    # ------------------------------------------------------------------
    # 3. Constitution blocks lead output in soft mode
    # ------------------------------------------------------------------

    def test_constitution_blocks_lead_output_soft_mode(self):
        """In soft enforcement mode, a hard rule violation in post_lead
        should set approved=False in the verdict.
        """
        self._write_constitution([
            {
                "id": "no-forbidden",
                "severity": "hard",
                "description": "Forbids the FORBIDDEN_PATTERN marker",
                "pattern": "FORBIDDEN_PATTERN",
                "message": "Output contains FORBIDDEN_PATTERN",
            }
        ])
        self._set_enforcement_mode("soft")

        orchestrator = PromptClawOrchestrator(self.temp_dir)
        engine = orchestrator.coherence

        # Directly test post_lead with text that triggers the rule
        run_id = "test-soft-block-run"
        verdict = engine.post_lead(
            run_id=run_id,
            agent="codex",
            output_text="Here is the output: FORBIDDEN_PATTERN detected in the code.",
        )

        self.assertFalse(verdict.approved, "Soft mode should block on hard violations")
        self.assertEqual(len(verdict.violations), 1)
        self.assertEqual(verdict.violations[0].rule_id, "no-forbidden")
        self.assertEqual(verdict.violations[0].severity, ViolationSeverity.HARD)
        self.assertEqual(verdict.mode, EnforcementMode.SOFT)

    # ------------------------------------------------------------------
    # 4. Monitor mode never blocks
    # ------------------------------------------------------------------

    def test_monitor_mode_never_blocks(self):
        """In monitor mode, violations are detected but approved is always True."""
        self._write_constitution([
            {
                "id": "no-forbidden",
                "severity": "hard",
                "description": "Forbids the FORBIDDEN_PATTERN marker",
                "pattern": "FORBIDDEN_PATTERN",
                "message": "Output contains FORBIDDEN_PATTERN",
            }
        ])
        self._set_enforcement_mode("monitor")

        orchestrator = PromptClawOrchestrator(self.temp_dir)
        engine = orchestrator.coherence

        run_id = "test-monitor-run"
        verdict = engine.post_lead(
            run_id=run_id,
            agent="codex",
            output_text="This has FORBIDDEN_PATTERN in it.",
        )

        # Violation detected
        self.assertEqual(len(verdict.violations), 1)
        self.assertEqual(verdict.violations[0].rule_id, "no-forbidden")

        # But NOT blocked in monitor mode
        self.assertTrue(verdict.approved, "Monitor mode must never block")
        self.assertEqual(verdict.mode, EnforcementMode.MONITOR)

    # ------------------------------------------------------------------
    # 5. Decision injection into prompts
    # ------------------------------------------------------------------

    def test_decision_injection_into_prompts(self):
        """A recorded decision should appear in the lead prompt file
        when the task text has matching keywords.
        """
        orchestrator = PromptClawOrchestrator(self.temp_dir)
        engine = orchestrator.coherence

        # Record a decision with keywords that will match our task
        engine.record_decision(
            title="Use Redis for caching",
            context="We evaluated caching options",
            decision_text="Use Redis vector sets instead of in-memory dicts",
            rationale="Persistence and scalability",
            tags=["caching", "redis"],
            file_paths=["promptclaw/cache.py"],
        )

        # Run a task whose text overlaps with the decision keywords.
        # Include "Python" so the heuristic router does not flag ambiguity
        # (code + module without a language triggers a clarification question).
        state = orchestrator.run(
            "Implement a Python Redis caching layer and provide a concise plan.",
            title="Redis Cache Task",
        )

        self.assertEqual(state.status, "complete")

        # Find the lead prompt file
        run_prompts_dir = self.temp_dir / ".promptclaw" / "runs" / state.run_id / "prompts"
        lead_prompt_files = list(run_prompts_dir.glob("lead-*.md"))
        self.assertGreater(len(lead_prompt_files), 0, "Expected at least one lead prompt file")

        lead_prompt_text = lead_prompt_files[0].read_text()
        self.assertIn(
            "Use Redis for caching",
            lead_prompt_text,
            "Decision title should appear in the lead prompt",
        )
        self.assertIn(
            "Active Decisions",
            lead_prompt_text,
            "Decision context header should appear in the lead prompt",
        )

    # ------------------------------------------------------------------
    # 6. Trust scoring across runs
    # ------------------------------------------------------------------

    def test_trust_scoring_across_runs(self):
        """Trust scores accumulate correctly across multiple runs
        for the same agent.
        """
        orchestrator = PromptClawOrchestrator(self.temp_dir)
        initial_score = orchestrator.coherence.trust_manager.INITIAL_SCORE

        state1 = self._run_clear_task(orchestrator, title="Trust Run 1")
        self.assertEqual(state1.status, "complete")
        lead_agent = state1.lead_agent

        score_after_1 = orchestrator.coherence.trust_manager.get_score(lead_agent).score
        self.assertGreater(score_after_1, initial_score)

        state2 = self._run_clear_task(orchestrator, title="Trust Run 2")
        self.assertEqual(state2.status, "complete")

        # The same lead agent should get picked (heuristic routing is deterministic
        # for similar tasks), so trust should keep accumulating
        score_after_2 = orchestrator.coherence.trust_manager.get_score(lead_agent).score
        self.assertGreaterEqual(
            score_after_2,
            score_after_1,
            "Trust should not decrease across compliant runs",
        )

        compliant_count = orchestrator.coherence.trust_manager.get_score(lead_agent).compliant_actions
        self.assertGreaterEqual(compliant_count, 2, "Expected at least 2 compliant actions across 2 runs")

    # ------------------------------------------------------------------
    # 7. Event replay
    # ------------------------------------------------------------------

    def test_event_replay(self):
        """Events replayed for a run should be in order and contain
        the expected hook event types.
        """
        orchestrator = PromptClawOrchestrator(self.temp_dir)
        state = self._run_clear_task(orchestrator)

        events = orchestrator.coherence.replay(state.run_id)
        self.assertGreater(len(events), 0)

        # Events should be in sequence order
        seq_numbers = [e.sequence_number for e in events]
        self.assertEqual(seq_numbers, sorted(seq_numbers), "Events must be in sequence order")

        # All events should have the correct run_id
        for ev in events:
            self.assertEqual(ev.run_id, state.run_id)

        # We expect at least the coherence hook events to be present
        event_types = {e.event_type for e in events}
        # The orchestrator emits its own events via coherence.emit() for each _log call,
        # plus the coherence hooks emit their own events (coherence.pre_routing, etc.)
        expected_coherence_hooks = {
            "coherence.pre_routing",
            "coherence.post_routing",
            "coherence.pre_lead",
            "coherence.finalize",
        }
        for hook_type in expected_coherence_hooks:
            self.assertIn(
                hook_type,
                event_types,
                f"Expected coherence hook event '{hook_type}' in replay",
            )

    # ------------------------------------------------------------------
    # 8. Graduation observation recording
    # ------------------------------------------------------------------

    def test_graduation_observation_recording(self):
        """Calling record_graduation_observation updates graduation stats."""
        orchestrator = PromptClawOrchestrator(self.temp_dir)
        engine = orchestrator.coherence
        gm = engine.graduation_manager

        # Initial state
        self.assertEqual(gm.stats.total_observations, 0)
        self.assertEqual(gm.stats.true_positives, 0)
        self.assertEqual(gm.stats.false_positives, 0)

        # Record several observations
        engine.record_graduation_observation(True)
        engine.record_graduation_observation(True)
        engine.record_graduation_observation(False)
        engine.record_graduation_observation(True)

        self.assertEqual(gm.stats.total_observations, 4)
        self.assertEqual(gm.stats.true_positives, 3)
        self.assertEqual(gm.stats.false_positives, 1)

        # Confidence should be 3/4 = 0.75
        self.assertAlmostEqual(gm.stats.confidence, 0.75, places=2)

        # False positive rate should be 1/4 = 0.25
        self.assertAlmostEqual(gm.stats.false_positive_rate, 0.25, places=2)

    # ------------------------------------------------------------------
    # Additional: Soft violation in soft mode does NOT block
    # ------------------------------------------------------------------

    def test_soft_violation_does_not_block_in_soft_mode(self):
        """In soft enforcement mode, a soft-severity violation should NOT block.
        Only hard violations cause blocking in soft mode.
        """
        self._write_constitution([
            {
                "id": "style-warning",
                "severity": "soft",
                "description": "Warns about informal language",
                "keywords": ["yolo", "lol"],
                "message": "Output uses informal language",
            }
        ])
        self._set_enforcement_mode("soft")

        orchestrator = PromptClawOrchestrator(self.temp_dir)
        engine = orchestrator.coherence

        verdict = engine.post_lead(
            run_id="test-soft-severity",
            agent="codex",
            output_text="This output says yolo a lot.",
        )

        # Violation detected
        self.assertEqual(len(verdict.violations), 1)
        self.assertEqual(verdict.violations[0].severity, ViolationSeverity.SOFT)

        # But not blocked (soft mode only blocks on hard violations)
        self.assertTrue(verdict.approved, "Soft violations should not block in soft mode")

    # ------------------------------------------------------------------
    # Additional: Full mode blocks on any violation
    # ------------------------------------------------------------------

    def test_full_mode_blocks_on_soft_violation(self):
        """In full enforcement mode, even a soft violation causes blocking."""
        self._write_constitution([
            {
                "id": "style-warning",
                "severity": "soft",
                "description": "Warns about informal language",
                "keywords": ["yolo"],
                "message": "Output uses informal language",
            }
        ])
        self._set_enforcement_mode("full")

        orchestrator = PromptClawOrchestrator(self.temp_dir)
        engine = orchestrator.coherence

        verdict = engine.post_lead(
            run_id="test-full-block",
            agent="codex",
            output_text="This output says yolo.",
        )

        self.assertFalse(verdict.approved, "Full mode should block on any violation")
        self.assertEqual(verdict.mode, EnforcementMode.FULL)

    # ------------------------------------------------------------------
    # Additional: Trust penalty on violations
    # ------------------------------------------------------------------

    def test_trust_penalty_on_hard_violation(self):
        """Hard violations should decrease trust score."""
        self._write_constitution([
            {
                "id": "no-forbidden",
                "severity": "hard",
                "description": "Forbids FORBIDDEN_PATTERN",
                "pattern": "FORBIDDEN_PATTERN",
                "message": "Forbidden pattern detected",
            }
        ])
        self._set_enforcement_mode("monitor")

        orchestrator = PromptClawOrchestrator(self.temp_dir)
        engine = orchestrator.coherence
        tm = engine.trust_manager

        initial = tm.INITIAL_SCORE

        # Trigger a hard violation via post_lead
        engine.post_lead(
            run_id="test-trust-penalty",
            agent="codex",
            output_text="Contains FORBIDDEN_PATTERN here.",
        )

        score = tm.get_score("codex")
        self.assertLess(
            score.score,
            initial,
            "Trust should decrease after a hard violation",
        )
        self.assertEqual(score.hard_violations, 1)

    # ------------------------------------------------------------------
    # Additional: Finalization increments graduation run counter
    # ------------------------------------------------------------------

    def test_finalize_increments_graduation_runs(self):
        """Each finalize() call should increment the graduation run counter."""
        orchestrator = PromptClawOrchestrator(self.temp_dir)
        engine = orchestrator.coherence
        gm = engine.graduation_manager

        self.assertEqual(gm.stats.runs_in_current_mode, 0)

        state = self._run_clear_task(orchestrator)
        self.assertEqual(state.status, "complete")
        self.assertGreaterEqual(gm.stats.runs_in_current_mode, 1)

        state2 = self._run_clear_task(orchestrator, title="Finalize Run 2")
        self.assertEqual(state2.status, "complete")
        self.assertGreaterEqual(gm.stats.runs_in_current_mode, 2)


if __name__ == "__main__":
    unittest.main()
