"""Tests for run-path wiring: enabled kill-switch (1d) and graduation feed (1e)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.bootstrap import init_project
from promptclaw.config import load_config, save_config
from promptclaw.coherence.engine import CoherenceEngine, NullCoherenceEngine
from promptclaw.coherence.models import CoherenceConfig, Violation, ViolationSeverity
from promptclaw.orchestrator import PromptClawOrchestrator


class TestEnabledKillSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-1d-"))
        init_project(self.tmp, "KillSwitch")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_enabled_true_yields_real_engine(self):
        orch = PromptClawOrchestrator(self.tmp)
        self.assertIsInstance(orch.coherence, CoherenceEngine)

    def test_enabled_false_yields_null_engine(self):
        cfg = load_config(self.tmp)
        if cfg.coherence is None:
            cfg.coherence = CoherenceConfig()
        cfg.coherence.enabled = False
        save_config(self.tmp, cfg)
        orch = PromptClawOrchestrator(self.tmp)
        self.assertIsInstance(orch.coherence, NullCoherenceEngine)


class TestGraduationFeed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-1e-"))
        (self.tmp / "constitution.json").write_text(json.dumps({
            "rules": [{
                "id": "R1", "severity": "hard", "description": "d",
                "keywords": ["BADEVIDENCE"], "applies_to": ["verify"],
            }]
        }))
        self.engine = CoherenceEngine(CoherenceConfig(constitution_path="constitution.json"), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _violation(self):
        return Violation(rule_id="R1", severity=ViolationSeverity.HARD, message="m")

    def test_retry_clears_violation_is_true_positive(self):
        self.engine.note_override_outcome([self._violation()], "all clean now", phase="verify")
        self.assertEqual(self.engine.graduation_manager.stats.true_positives, 1)
        self.assertEqual(self.engine.graduation_manager.stats.false_positives, 0)

    def test_retry_keeps_violation_is_false_positive(self):
        self.engine.note_override_outcome([self._violation()], "still has BADEVIDENCE", phase="verify")
        self.assertEqual(self.engine.graduation_manager.stats.false_positives, 1)
        self.assertEqual(self.engine.graduation_manager.stats.true_positives, 0)

    def test_no_violations_records_nothing(self):
        self.engine.note_override_outcome([], "whatever", phase="verify")
        self.assertEqual(self.engine.graduation_manager.stats.total_observations, 0)

    def test_null_engine_runpath_noops(self):
        n = NullCoherenceEngine()
        self.assertIsNone(n.note_override_outcome([self._violation()], "x"))
        self.assertIsNone(n.record_graduation_observation(True))


if __name__ == "__main__":
    unittest.main()
