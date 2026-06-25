"""Tests for cross-process persistence of trust, graduation, and event sequence (Phase 1c).

Trust scores, graduation stats/mode, and per-run sequence numbers must survive across engine
instances (processes), while the pure in-memory path (no db_path) stays intact for existing tests.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from promptclaw.coherence.graduation import GraduationManager
from promptclaw.coherence.models import CoherenceConfig, EnforcementMode
from promptclaw.coherence.trust import TrustManager


class TestTrustPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-persist-"))
        self.db = self.tmp / "coherence.db"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_trust_persists_across_instances(self):
        m1 = TrustManager(db_path=self.db)
        m1.apply_hard_violation("codex")
        score = m1.get_score("codex").score
        m1.close()
        m2 = TrustManager(db_path=self.db)
        self.assertAlmostEqual(m2.get_score("codex").score, score)
        self.assertEqual(m2.get_score("codex").hard_violations, 1)

    def test_in_memory_when_no_db(self):
        m = TrustManager()
        m.apply_soft_violation("x")
        # a fresh in-memory manager has no recollection
        self.assertEqual(TrustManager().get_score("x").score, TrustManager.INITIAL_SCORE)


class TestGraduationPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-grad-"))
        self.db = self.tmp / "coherence.db"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stats_and_mode_persist_across_instances(self):
        g1 = GraduationManager(CoherenceConfig(enforcement_mode="monitor"), db_path=self.db)
        for _ in range(20):
            g1.record_observation(True)
        self.assertEqual(g1.evaluate_promotion(), EnforcementMode.SOFT)
        g1.close()
        g2 = GraduationManager(CoherenceConfig(enforcement_mode="monitor"), db_path=self.db)
        self.assertEqual(g2.current_mode, EnforcementMode.SOFT)  # graduation accumulated across runs
        self.assertEqual(g2.stats.total_observations, 20)

    def test_in_memory_when_no_db(self):
        g = GraduationManager(CoherenceConfig(enforcement_mode="monitor"))
        for _ in range(20):
            g.record_observation(True)
        g.evaluate_promotion()
        fresh = GraduationManager(CoherenceConfig(enforcement_mode="monitor"))
        self.assertEqual(fresh.stats.total_observations, 0)


class TestEnginePersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pc-eng-persist-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _engine(self):
        from promptclaw.coherence.engine import CoherenceEngine
        return CoherenceEngine(CoherenceConfig(), self.tmp)

    def test_sequence_seeded_across_instances(self):
        e1 = self._engine()
        e1.emit("run-1", "coherence.pre_lead")
        e1.emit("run-1", "coherence.post_lead")  # seq 0, 1
        e2 = self._engine()
        ev = e2.emit("run-1", "coherence.finalize")
        self.assertEqual(ev.sequence_number, 2)  # continues, not restarts at 0

    def test_engine_adopts_persisted_graduation_mode(self):
        e1 = self._engine()
        for _ in range(20):
            e1.graduation_manager.record_observation(True)
        e1.graduation_manager.evaluate_promotion()  # -> SOFT, persisted
        e2 = self._engine()
        self.assertEqual(e2.config.mode, EnforcementMode.SOFT)


if __name__ == "__main__":
    unittest.main()
