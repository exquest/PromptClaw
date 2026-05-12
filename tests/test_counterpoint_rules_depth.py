"""Depth-2 counterpoint_rules helpers - locked test surface for frac-0009."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.counterpoint_rules import (  # noqa: E402
    CounterpointFit,
    MotionProfile,
    counterpoint_pair_summary,
    motion_profile,
    rank_counterpoint_rules,
    recommend_counterpoint_rule,
    score_counterpoint_fit,
)


def test_motion_profile_counts_motion_types() -> None:
    leader = (60, 62, 64, 64, 65)
    follower = (67, 65, 67, 67, 67)

    profile = motion_profile(leader, follower)

    assert isinstance(profile, MotionProfile)
    assert profile.transitions == 4
    assert profile.contrary_count == 1
    assert profile.parallel_count == 1
    assert profile.static_count == 1
    assert profile.oblique_count == 1
    assert profile.dominant_motion == "contrary"
    assert profile.stepwise_rate == pytest.approx(1.0)


def test_score_counterpoint_fit_combines_registry_and_resolution_metrics() -> None:
    leader = (60, 62, 64, 65)
    follower = (67, 65, 62, 60)

    fit = score_counterpoint_fit(
        "contrary",
        leader,
        follower,
        leader_role="melody",
        follower_role="counter",
        phase="Conversation",
    )

    assert isinstance(fit, CounterpointFit)
    assert fit.rule_id == "contrary"
    assert fit.voice_pair_ok is True
    assert fit.motion.dominant_motion == "contrary"
    assert fit.motion_match_rate == pytest.approx(1.0)
    assert fit.dissonance.unresolved_count == 0
    assert fit.preferred_interval_rate == pytest.approx(0.75)
    assert 0.0 <= fit.score <= 1.0
    assert fit.score >= 0.80
    assert fit.passed is True


def test_recommendation_prefers_contrary_for_contrary_motion_pair() -> None:
    leader = (60, 62, 64, 65)
    follower = (67, 65, 62, 60)

    ranked = rank_counterpoint_rules(
        leader,
        follower,
        leader_role="melody",
        follower_role="counter",
        phase="Conversation",
    )
    recommendation = recommend_counterpoint_rule(
        leader,
        follower,
        leader_role="melody",
        follower_role="counter",
        phase="Conversation",
    )

    assert len(ranked) >= 2
    assert ranked[0].rule_id == "contrary"
    assert recommendation == ranked[0]
    assert recommendation.score >= ranked[1].score


def test_counterpoint_pair_summary_is_stable_and_meaningful() -> None:
    leader = (60, 62, 64, 65)
    follower = (67, 65, 62, 60)

    summary = counterpoint_pair_summary(
        leader,
        follower,
        leader_role="melody",
        follower_role="counter",
        phase="Conversation",
    )

    assert summary == {
        "recommended_rule": "contrary",
        "label": "Contrary Motion",
        "phase": "Conversation",
        "leader_role": "melody",
        "follower_role": "counter",
        "score": pytest.approx(0.892),
        "passed": True,
        "dominant_motion": "contrary",
        "stepwise_rate": pytest.approx(1.0),
        "preferred_interval_rate": pytest.approx(0.75),
        "resolution_rate": pytest.approx(1.0),
        "unresolved_dissonances": 0,
    }
