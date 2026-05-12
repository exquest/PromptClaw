"""Depth-2 tests for promptclaw.coherence.trust [frac-0038].

Verifies the typed canonical TrustEventPlan path, apply_event routing, the
JSON-safe fleet_summary, and the fractal depth uplift to >= 2.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptclaw.coherence.trust import (
    TrustEventPlan,
    TrustManager,
    trust_event_plans,
)


TRUST_MODULE_PATH = Path("promptclaw/coherence/trust.py")


def test_trust_event_plans_describe_canonical_events() -> None:
    plans = trust_event_plans()

    by_name = {plan.name: plan for plan in plans}
    assert set(by_name.keys()) == {
        "hard_violation",
        "soft_violation",
        "compliant_action",
    }

    hard = by_name["hard_violation"]
    soft = by_name["soft_violation"]
    compliant = by_name["compliant_action"]

    assert hard.delta == TrustManager.HARD_PENALTY
    assert hard.counter_field == "hard_violations"
    assert soft.delta == TrustManager.SOFT_PENALTY
    assert soft.counter_field == "soft_violations"
    assert compliant.delta == TrustManager.COMPLIANT_REWARD
    assert compliant.counter_field == "compliant_actions"

    for plan in plans:
        assert isinstance(plan, TrustEventPlan)
        assert plan.description, "every canonical plan must carry a description"


def test_apply_event_routes_through_canonical_plan() -> None:
    tm = TrustManager()

    plans = {plan.name: plan for plan in trust_event_plans()}
    new_score = tm.apply_event("agent-x", plans["compliant_action"])

    score = tm.get_score("agent-x")
    assert new_score == pytest.approx(0.52)
    assert score.score == pytest.approx(0.52)
    assert score.compliant_actions == 1
    assert score.hard_violations == 0
    assert score.soft_violations == 0
    assert score.last_updated != ""


def test_legacy_apply_methods_route_through_apply_event() -> None:
    tm = TrustManager()

    captured: list[TrustEventPlan] = []
    original_apply_event = tm.apply_event

    def wrapped(agent: str, plan: TrustEventPlan) -> float:
        captured.append(plan)
        return original_apply_event(agent, plan)

    tm.apply_event = wrapped  # type: ignore[method-assign]

    tm.apply_hard_violation("agent-a")
    tm.apply_soft_violation("agent-a")
    tm.apply_compliant_action("agent-a")

    assert [plan.name for plan in captured] == [
        "hard_violation",
        "soft_violation",
        "compliant_action",
    ]


def test_fleet_summary_is_json_safe_and_sorted() -> None:
    tm = TrustManager()
    tm.apply_hard_violation("zeta-agent")  # 0.2
    tm.apply_hard_violation("zeta-agent")  # clamped at 0 -> 0.0 actually 0.2-0.3=-0.1->0.0
    tm.apply_compliant_action("alpha-agent")  # 0.52
    tm.apply_soft_violation("mid-agent")  # 0.45

    summary = tm.fleet_summary()

    json.dumps(summary)  # must not raise

    assert summary["initial_score"] == TrustManager.INITIAL_SCORE
    assert summary["hard_penalty"] == TrustManager.HARD_PENALTY
    assert summary["soft_penalty"] == TrustManager.SOFT_PENALTY
    assert summary["compliant_reward"] == TrustManager.COMPLIANT_REWARD
    assert summary["restriction_threshold"] == TrustManager.RESTRICTION_THRESHOLD

    rows = summary["agents"]
    assert [row["agent"] for row in rows] == [
        "alpha-agent",
        "mid-agent",
        "zeta-agent",
    ]

    zeta = next(row for row in rows if row["agent"] == "zeta-agent")
    assert zeta["score"] == pytest.approx(0.0)
    assert zeta["hard_violations"] == 2
    assert zeta["restricted"] is True

    alpha = next(row for row in rows if row["agent"] == "alpha-agent")
    assert alpha["compliant_actions"] == 1
    assert alpha["restricted"] is False

    assert summary["restricted_count"] == 1
    assert summary["agent_count"] == 3


def test_fleet_summary_empty_manager_returns_zero_restricted() -> None:
    tm = TrustManager()

    summary = tm.fleet_summary()

    assert summary["agents"] == []
    assert summary["agent_count"] == 0
    assert summary["restricted_count"] == 0


def test_apply_event_rejects_unknown_counter_field() -> None:
    tm = TrustManager()
    bogus = TrustEventPlan(
        name="bogus",
        delta=0.0,
        counter_field="not_a_real_field",
        description="invalid",
    )

    with pytest.raises(ValueError, match="not_a_real_field"):
        tm.apply_event("agent-a", bogus)


def test_trust_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(TRUST_MODULE_PATH)

    assert result.depth >= 2, result.reason
