"""Tests for the GraduationManager and GraduationStats."""

import pytest

from promptclaw.coherence.graduation import GraduationManager, GraduationStats
from promptclaw.coherence.models import CoherenceConfig, EnforcementMode


def make_config(
    mode: str = "monitor",
    auto_graduate: bool = True,
    confidence_threshold: float = 0.85,
    fp_threshold: float = 0.05,
) -> CoherenceConfig:
    return CoherenceConfig(
        enforcement_mode=mode,
        auto_graduate=auto_graduate,
        graduation_confidence_threshold=confidence_threshold,
        graduation_false_positive_threshold=fp_threshold,
    )


class TestInitialMode:
    def test_initial_mode_matches_config_monitor(self):
        gm = GraduationManager(make_config(mode="monitor"))
        assert gm.current_mode == EnforcementMode.MONITOR

    def test_initial_mode_matches_config_soft(self):
        gm = GraduationManager(make_config(mode="soft"))
        assert gm.current_mode == EnforcementMode.SOFT

    def test_initial_mode_matches_config_full(self):
        gm = GraduationManager(make_config(mode="full"))
        assert gm.current_mode == EnforcementMode.FULL


class TestMonitorToSoft:
    def test_promotes_with_sufficient_confidence_and_observations(self):
        gm = GraduationManager(make_config(mode="monitor", confidence_threshold=0.85))
        # 18 true positives out of 20 = 0.9 confidence > 0.85
        for _ in range(18):
            gm.record_observation(was_true_positive=True)
        for _ in range(2):
            gm.record_observation(was_true_positive=False)
        result = gm.evaluate_promotion()
        assert result == EnforcementMode.SOFT
        assert gm.current_mode == EnforcementMode.SOFT

    def test_stays_monitor_with_insufficient_observations(self):
        gm = GraduationManager(make_config(mode="monitor", confidence_threshold=0.85))
        # Only 10 observations (need 20), even with perfect confidence
        for _ in range(10):
            gm.record_observation(was_true_positive=True)
        result = gm.evaluate_promotion()
        assert result == EnforcementMode.MONITOR
        assert gm.current_mode == EnforcementMode.MONITOR

    def test_stays_monitor_with_low_confidence(self):
        gm = GraduationManager(make_config(mode="monitor", confidence_threshold=0.85))
        # 10 true positives out of 20 = 0.5 confidence < 0.85
        for _ in range(10):
            gm.record_observation(was_true_positive=True)
        for _ in range(10):
            gm.record_observation(was_true_positive=False)
        result = gm.evaluate_promotion()
        assert result == EnforcementMode.MONITOR
        assert gm.current_mode == EnforcementMode.MONITOR


class TestSoftToFull:
    def test_promotes_with_low_fp_rate_and_enough_runs(self):
        gm = GraduationManager(make_config(mode="soft", fp_threshold=0.05))
        # 20 true positives, 0 false positives = 0.0 FP rate < 0.05
        for _ in range(20):
            gm.record_observation(was_true_positive=True)
        for _ in range(10):
            gm.increment_run()
        result = gm.evaluate_promotion()
        assert result == EnforcementMode.FULL
        assert gm.current_mode == EnforcementMode.FULL

    def test_stays_soft_with_high_false_positive_rate(self):
        gm = GraduationManager(make_config(mode="soft", fp_threshold=0.05))
        # 8 true positives, 2 false positives = 0.2 FP rate > 0.05
        for _ in range(8):
            gm.record_observation(was_true_positive=True)
        for _ in range(2):
            gm.record_observation(was_true_positive=False)
        for _ in range(10):
            gm.increment_run()
        result = gm.evaluate_promotion()
        assert result == EnforcementMode.SOFT
        assert gm.current_mode == EnforcementMode.SOFT

    def test_stays_soft_with_insufficient_runs(self):
        gm = GraduationManager(make_config(mode="soft", fp_threshold=0.05))
        for _ in range(20):
            gm.record_observation(was_true_positive=True)
        for _ in range(5):  # Only 5 runs, need 10
            gm.increment_run()
        result = gm.evaluate_promotion()
        assert result == EnforcementMode.SOFT
        assert gm.current_mode == EnforcementMode.SOFT


class TestFullMode:
    def test_full_never_promotes_further(self):
        gm = GraduationManager(make_config(mode="full"))
        for _ in range(50):
            gm.record_observation(was_true_positive=True)
        for _ in range(20):
            gm.increment_run()
        result = gm.evaluate_promotion()
        assert result == EnforcementMode.FULL
        assert gm.current_mode == EnforcementMode.FULL


class TestAutoGraduateDisabled:
    def test_prevents_monitor_to_soft(self):
        gm = GraduationManager(make_config(mode="monitor", auto_graduate=False))
        for _ in range(20):
            gm.record_observation(was_true_positive=True)
        result = gm.evaluate_promotion()
        assert result == EnforcementMode.MONITOR

    def test_prevents_soft_to_full(self):
        gm = GraduationManager(make_config(mode="soft", auto_graduate=False))
        for _ in range(20):
            gm.record_observation(was_true_positive=True)
        for _ in range(10):
            gm.increment_run()
        result = gm.evaluate_promotion()
        assert result == EnforcementMode.SOFT


class TestRecordObservation:
    def test_true_positive_increments_correctly(self):
        gm = GraduationManager(make_config())
        gm.record_observation(was_true_positive=True)
        assert gm.stats.total_observations == 1
        assert gm.stats.true_positives == 1
        assert gm.stats.false_positives == 0

    def test_false_positive_increments_correctly(self):
        gm = GraduationManager(make_config())
        gm.record_observation(was_true_positive=False)
        assert gm.stats.total_observations == 1
        assert gm.stats.true_positives == 0
        assert gm.stats.false_positives == 1

    def test_mixed_observations(self):
        gm = GraduationManager(make_config())
        gm.record_observation(was_true_positive=True)
        gm.record_observation(was_true_positive=True)
        gm.record_observation(was_true_positive=False)
        assert gm.stats.total_observations == 3
        assert gm.stats.true_positives == 2
        assert gm.stats.false_positives == 1


class TestIncrementRun:
    def test_increment_run_updates_counter(self):
        gm = GraduationManager(make_config())
        assert gm.stats.runs_in_current_mode == 0
        gm.increment_run()
        assert gm.stats.runs_in_current_mode == 1
        gm.increment_run()
        gm.increment_run()
        assert gm.stats.runs_in_current_mode == 3


class TestPromotionResetsRuns:
    def test_monitor_to_soft_resets_runs(self):
        gm = GraduationManager(make_config(mode="monitor", confidence_threshold=0.85))
        for _ in range(20):
            gm.record_observation(was_true_positive=True)
        for _ in range(5):
            gm.increment_run()
        assert gm.stats.runs_in_current_mode == 5
        gm.evaluate_promotion()
        assert gm.current_mode == EnforcementMode.SOFT
        assert gm.stats.runs_in_current_mode == 0

    def test_soft_to_full_resets_runs(self):
        gm = GraduationManager(make_config(mode="soft", fp_threshold=0.05))
        for _ in range(20):
            gm.record_observation(was_true_positive=True)
        for _ in range(15):
            gm.increment_run()
        assert gm.stats.runs_in_current_mode == 15
        gm.evaluate_promotion()
        assert gm.current_mode == EnforcementMode.FULL
        assert gm.stats.runs_in_current_mode == 0


class TestGraduationStatsProperties:
    def test_confidence_with_no_observations(self):
        stats = GraduationStats()
        assert stats.confidence == 0.0

    def test_false_positive_rate_with_no_observations(self):
        stats = GraduationStats()
        assert stats.false_positive_rate == 1.0

    def test_confidence_calculation(self):
        stats = GraduationStats(total_observations=10, true_positives=8, false_positives=2)
        assert stats.confidence == pytest.approx(0.8)

    def test_false_positive_rate_calculation(self):
        stats = GraduationStats(total_observations=20, true_positives=19, false_positives=1)
        assert stats.false_positive_rate == pytest.approx(0.05)
