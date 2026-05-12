"""Tests for the coherence engine facade."""

import json
import shutil
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from promptclaw.coherence.engine import CoherenceEngine, NullCoherenceEngine
from promptclaw.coherence.models import (
    CoherenceConfig,
    EnforcementMode,
    ViolationSeverity,
)


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


class TestCoherenceEngineEndToEnd(unittest.TestCase):
    """Depth-2 end-to-end coverage for the coherence facade public surface."""

    def setUp(self) -> None:
        self.temp_dirs: list[Path] = []

    def tearDown(self) -> None:
        for path in self.temp_dirs:
            shutil.rmtree(path, ignore_errors=True)

    def _new_project(self) -> Path:
        path = Path(tempfile.mkdtemp(prefix="promptclaw-coherence-e2e-"))
        (path / ".promptclaw").mkdir()
        self.temp_dirs.append(path)
        return path

    def _close_engine(self, engine: CoherenceEngine) -> None:
        engine.event_store.close()
        engine.decision_store.close()

    def _drive_full_lifecycle(
        self,
        engine: CoherenceEngine,
        run_id: str,
        lead: str = "claude",
        verifier: str = "codex",
    ) -> list:
        engine.pre_routing(run_id, "implement helper", "memory snapshot")
        engine.post_routing(run_id, {"lead_agent": lead, "verifier": verifier})
        engine.pre_lead(run_id, lead, "implement helper")
        engine.post_lead(run_id, lead, "implementation output")
        engine.pre_verify(run_id, verifier, "implementation output")
        engine.post_verify(run_id, verifier, "PASS")
        engine.finalize(run_id)
        return engine.replay(run_id)

    def test_full_hook_lifecycle_persists_events_in_order(self) -> None:
        project = self._new_project()
        engine = CoherenceEngine(CoherenceConfig(), project)

        events = self._drive_full_lifecycle(engine, "run-lifecycle")

        expected_types = [
            "coherence.pre_routing",
            "coherence.post_routing",
            "coherence.pre_lead",
            "coherence.post_lead",
            "coherence.pre_verify",
            "coherence.post_verify",
            "coherence.finalize",
        ]
        expected_phases = [
            "routing",
            "routing",
            "lead",
            "lead",
            "verify",
            "verify",
            "complete",
        ]
        self.assertEqual([e.event_type for e in events], expected_types)
        self.assertEqual([e.phase for e in events], expected_phases)
        self.assertEqual(
            [e.sequence_number for e in events], list(range(len(expected_types)))
        )
        for event in events:
            self.assertEqual(event.run_id, "run-lifecycle")
            self.assertTrue(event.event_id)
            self.assertTrue(event.timestamp)

        # Persistence: rebuild engine against the same project and replay.
        self._close_engine(engine)
        rebuilt = CoherenceEngine(CoherenceConfig(), project)
        replayed = rebuilt.replay("run-lifecycle")
        self.assertEqual(
            [e.event_type for e in replayed], expected_types
        )
        self.assertEqual(
            [e.sequence_number for e in replayed], list(range(len(expected_types)))
        )
        self._close_engine(rebuilt)

    def test_constitution_blocks_in_full_mode_and_passes_in_monitor_mode(self) -> None:
        rules = {
            "rules": [
                {
                    "id": "no-secret",
                    "severity": "hard",
                    "description": "Output must not leak secrets.",
                    "keywords": ["password", "api_key"],
                    "applies_to": ["lead", "verify", "routing"],
                    "message": "secret leak",
                },
                {
                    "id": "prefer-tests",
                    "severity": "soft",
                    "description": "Prefer covering changes with tests.",
                    "keywords": ["todo:test"],
                    "applies_to": ["lead"],
                },
            ]
        }

        offending_outputs = {
            "post_routing": {"lead_agent": "claude", "plan": "leak password later"},
            "post_lead": "implementation done; todo:test follow-up; api_key=abc",
            "post_verify": "PASS but mentions password handling",
        }

        # FULL mode: hard violations must block; soft violations also block.
        full_project = self._new_project()
        full_config = CoherenceConfig(
            constitution_path="constitution.json",
            enforcement_mode="full",
        )
        (full_project / "constitution.json").write_text(json.dumps(rules))
        full_engine = CoherenceEngine(full_config, full_project)
        try:
            verdicts = {
                "post_routing": full_engine.post_routing(
                    "run-full", offending_outputs["post_routing"]
                ),
                "post_lead": full_engine.post_lead(
                    "run-full", "claude", offending_outputs["post_lead"]
                ),
                "post_verify": full_engine.post_verify(
                    "run-full", "codex", offending_outputs["post_verify"]
                ),
            }
            for hook, verdict in verdicts.items():
                self.assertFalse(
                    verdict.approved, f"{hook} should be blocked in FULL mode"
                )
                self.assertGreater(len(verdict.violations), 0, hook)
                self.assertEqual(verdict.mode, EnforcementMode.FULL)

            # post_lead carries both rule ids; trust delta should be negative.
            lead_violation_ids = {v.rule_id for v in verdicts["post_lead"].violations}
            self.assertIn("no-secret", lead_violation_ids)
            self.assertIn("prefer-tests", lead_violation_ids)
            self.assertLess(verdicts["post_lead"].trust_delta, 0.0)
            self.assertEqual(
                verdicts["post_lead"].violations[0].severity,
                next(
                    v.severity
                    for v in verdicts["post_lead"].violations
                    if v.rule_id == "no-secret"
                ),
            )

            # Hard severity propagates from the constitution.
            hard_severities = [
                v.severity
                for v in verdicts["post_lead"].violations
                if v.rule_id == "no-secret"
            ]
            self.assertEqual(hard_severities, [ViolationSeverity.HARD])
        finally:
            self._close_engine(full_engine)

        # MONITOR mode: same offending text logs violations but does NOT block.
        monitor_project = self._new_project()
        monitor_config = CoherenceConfig(
            constitution_path="constitution.json",
            enforcement_mode="monitor",
        )
        (monitor_project / "constitution.json").write_text(json.dumps(rules))
        monitor_engine = CoherenceEngine(monitor_config, monitor_project)
        try:
            for hook_name, call in (
                (
                    "post_routing",
                    lambda: monitor_engine.post_routing(
                        "run-monitor", offending_outputs["post_routing"]
                    ),
                ),
                (
                    "post_lead",
                    lambda: monitor_engine.post_lead(
                        "run-monitor", "claude", offending_outputs["post_lead"]
                    ),
                ),
                (
                    "post_verify",
                    lambda: monitor_engine.post_verify(
                        "run-monitor", "codex", offending_outputs["post_verify"]
                    ),
                ),
            ):
                verdict = call()
                self.assertTrue(
                    verdict.approved, f"{hook_name} should pass in MONITOR mode"
                )
                self.assertGreater(len(verdict.violations), 0, hook_name)
                self.assertEqual(verdict.mode, EnforcementMode.MONITOR)
        finally:
            self._close_engine(monitor_engine)

    def test_decision_injection_includes_recorded_titles(self) -> None:
        project = self._new_project()
        engine = CoherenceEngine(CoherenceConfig(), project)
        try:
            decision_a = engine.record_decision(
                title="Use SQLite for coherence storage",
                context="Coherence event store needs durable persistence.",
                decision_text="Persist coherence events in SQLite under .promptclaw.",
                rationale="No external service dependency for local runs.",
                tags=["storage", "coherence"],
                file_paths=["promptclaw/coherence/event_store.py"],
            )
            decision_b = engine.record_decision(
                title="Constitutional rules live in repo root",
                context="Operators edit constitution.yaml beside the code.",
                decision_text="Look up constitution_path relative to project_root.",
                rationale="Keeps governance auditable in version control.",
                tags=["governance"],
                file_paths=["constitution.yaml"],
            )

            cases = [
                ("pre_routing", "Add SQLite-backed coherence storage helpers."),
                ("pre_lead", "Update constitutional rules used by routing."),
                ("pre_verify", "Verify SQLite event persistence behavior."),
            ]
            seen_titles: set[str] = set()
            for hook_name, task_text in cases:
                hook = getattr(engine, hook_name)
                if hook_name == "pre_routing":
                    verdict = hook("run-decisions", task_text, "memory")
                elif hook_name == "pre_lead":
                    verdict = hook("run-decisions", "claude", task_text)
                else:
                    verdict = hook("run-decisions", "codex", task_text)
                self.assertTrue(verdict.approved, hook_name)
                self.assertIn("## Active Decisions", verdict.injected_context)
                for title in (decision_a.title, decision_b.title):
                    if title.split()[0].lower() in task_text.lower():
                        if title in verdict.injected_context:
                            seen_titles.add(title)

            # At least one of the recorded titles must have surfaced in the
            # injected context across the swept cases.
            self.assertTrue(seen_titles, "expected at least one decision title injected")
        finally:
            self._close_engine(engine)

    def test_finalize_steps_graduation_and_records_observations(self) -> None:
        project = self._new_project()
        engine = CoherenceEngine(CoherenceConfig(), project)
        try:
            for index in range(3):
                run_id = f"run-finalize-{index}"
                engine.record_graduation_observation(was_true_positive=index % 2 == 0)
                verdict = engine.finalize(run_id)
                self.assertTrue(verdict.approved)
                self.assertEqual(verdict.mode, EnforcementMode.MONITOR)

            stats = engine.graduation_manager.stats
            self.assertEqual(stats.runs_in_current_mode, 3)
            self.assertEqual(stats.total_observations, 3)
            self.assertEqual(stats.true_positives, 2)
            self.assertEqual(stats.false_positives, 1)
            self.assertEqual(engine.graduation_manager.current_mode, EnforcementMode.MONITOR)
        finally:
            self._close_engine(engine)

    def test_replay_payload_round_trips_through_json(self) -> None:
        project = self._new_project()
        engine = CoherenceEngine(CoherenceConfig(), project)
        try:
            self._drive_full_lifecycle(engine, "run-json")
            events = engine.replay("run-json")
            payload = [asdict(event) for event in events]
            encoded = json.dumps(payload, sort_keys=True)
            decoded = json.loads(encoded)
            self.assertEqual(len(decoded), 7)
            for index, item in enumerate(decoded):
                self.assertEqual(item["sequence_number"], index)
                self.assertEqual(item["run_id"], "run-json")
                self.assertIsInstance(item["payload"], dict)
        finally:
            self._close_engine(engine)

    def test_null_engine_smoke_loop_stays_approved_and_empty(self) -> None:
        engine = NullCoherenceEngine()
        run_ids = ["null-1", "null-2", "null-3"]
        for run_id in run_ids:
            engine.emit(run_id, "noop")
            verdicts = [
                engine.pre_routing(run_id, "task", "memory"),
                engine.post_routing(run_id, {"lead_agent": "claude"}),
                engine.pre_lead(run_id, "claude", "task"),
                engine.post_lead(run_id, "claude", "output"),
                engine.pre_verify(run_id, "codex", "lead output"),
                engine.post_verify(run_id, "codex", "PASS"),
                engine.finalize(run_id),
            ]
            for verdict in verdicts:
                self.assertTrue(verdict.approved)
                self.assertEqual(verdict.violations, [])
                self.assertEqual(verdict.injected_context, "")
            self.assertEqual(engine.replay(run_id), [])


if __name__ == "__main__":
    unittest.main()
