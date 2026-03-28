"""Tests for the TrustManager and TrustScore."""

import pytest

from promptclaw.coherence.trust import TrustManager, TrustScore


class TestTrustScoreInitialization:
    def test_initial_score_is_0_5(self):
        tm = TrustManager()
        ts = tm.get_score("agent-a")
        assert ts.score == 0.5

    def test_get_score_creates_new_for_unknown_agent(self):
        tm = TrustManager()
        ts = tm.get_score("brand-new-agent")
        assert isinstance(ts, TrustScore)
        assert ts.agent == "brand-new-agent"
        assert ts.score == TrustManager.INITIAL_SCORE
        assert ts.hard_violations == 0
        assert ts.soft_violations == 0
        assert ts.compliant_actions == 0
        assert ts.last_updated != ""

    def test_get_score_returns_same_object(self):
        tm = TrustManager()
        ts1 = tm.get_score("agent-a")
        ts2 = tm.get_score("agent-a")
        assert ts1 is ts2


class TestHardViolation:
    def test_apply_hard_violation_drops_by_0_3(self):
        tm = TrustManager()
        new_score = tm.apply_hard_violation("agent-a")
        assert new_score == pytest.approx(0.2)
        assert tm.get_score("agent-a").hard_violations == 1

    def test_hard_violation_increments_counter(self):
        tm = TrustManager()
        tm.apply_hard_violation("agent-a")
        tm.apply_hard_violation("agent-a")
        assert tm.get_score("agent-a").hard_violations == 2


class TestSoftViolation:
    def test_apply_soft_violation_drops_by_0_05(self):
        tm = TrustManager()
        new_score = tm.apply_soft_violation("agent-a")
        assert new_score == pytest.approx(0.45)
        assert tm.get_score("agent-a").soft_violations == 1

    def test_soft_violation_increments_counter(self):
        tm = TrustManager()
        tm.apply_soft_violation("agent-a")
        tm.apply_soft_violation("agent-a")
        tm.apply_soft_violation("agent-a")
        assert tm.get_score("agent-a").soft_violations == 3


class TestCompliantAction:
    def test_apply_compliant_action_increases_by_0_02(self):
        tm = TrustManager()
        new_score = tm.apply_compliant_action("agent-a")
        assert new_score == pytest.approx(0.52)
        assert tm.get_score("agent-a").compliant_actions == 1

    def test_compliant_action_increments_counter(self):
        tm = TrustManager()
        for _ in range(5):
            tm.apply_compliant_action("agent-a")
        assert tm.get_score("agent-a").compliant_actions == 5


class TestScoreClamping:
    def test_score_clamps_to_0_after_many_hard_violations(self):
        tm = TrustManager()
        # Starting at 0.5, three hard violations = 0.5 - 0.9 = -0.4 -> clamped to 0.0
        tm.apply_hard_violation("agent-a")
        tm.apply_hard_violation("agent-a")
        new_score = tm.apply_hard_violation("agent-a")
        assert new_score == 0.0
        assert tm.get_score("agent-a").score == 0.0

    def test_score_clamps_to_1_after_many_compliant_actions(self):
        tm = TrustManager()
        # Starting at 0.5, need 26 compliant actions to exceed 1.0: 0.5 + 26*0.02 = 1.02 -> clamped
        for _ in range(50):
            new_score = tm.apply_compliant_action("agent-a")
        assert new_score == 1.0
        assert tm.get_score("agent-a").score == 1.0


class TestShouldRestrict:
    def test_should_restrict_true_when_below_threshold(self):
        tm = TrustManager()
        # Drop from 0.5 to 0.2, then one more soft to go to 0.15
        tm.apply_hard_violation("agent-a")  # 0.2
        tm.apply_soft_violation("agent-a")  # 0.15
        assert tm.should_restrict("agent-a") is True

    def test_should_restrict_false_when_at_threshold(self):
        tm = TrustManager()
        tm.apply_hard_violation("agent-a")  # 0.5 - 0.3 = 0.2
        assert tm.should_restrict("agent-a") is False

    def test_should_restrict_false_at_initial_score(self):
        tm = TrustManager()
        assert tm.should_restrict("agent-a") is False


class TestMultipleAgents:
    def test_agents_have_independent_scores(self):
        tm = TrustManager()
        tm.apply_hard_violation("agent-a")
        tm.apply_compliant_action("agent-b")

        assert tm.get_score("agent-a").score == pytest.approx(0.2)
        assert tm.get_score("agent-b").score == pytest.approx(0.52)
        assert tm.get_score("agent-a").hard_violations == 1
        assert tm.get_score("agent-b").hard_violations == 0

    def test_all_scores_returns_all_tracked(self):
        tm = TrustManager()
        tm.get_score("agent-a")
        tm.get_score("agent-b")
        tm.get_score("agent-c")
        all_scores = tm.all_scores()
        assert len(all_scores) == 3
        assert set(all_scores.keys()) == {"agent-a", "agent-b", "agent-c"}
