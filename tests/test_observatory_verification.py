"""Tests for observatory verification metrics."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

from observatory import Observatory


def test_verification_metrics_empty() -> None:
    obs = Observatory(":memory:")

    metrics = obs.get_verification_metrics(days=1)

    assert metrics["total_actions"] == 0
    assert metrics["verification_rate"] == 0.0
    obs.close()


def test_verification_metrics_populated() -> None:
    obs = Observatory(":memory:")

    obs.record_verification("action1", "claude", "codex", "medium", True, corrected=True, agreed=True)
    obs.record_verification("action2", "gemini", "claude", "high", True, passed_first_try=True, agreed=True)
    obs.record_verification(
        "action3",
        "claude",
        "gemini",
        "high",
        True,
        passed_first_try=False,
        fix_cycles=2,
        escalated=True,
        agreed=False,
    )
    obs.record_verification("action4", "codex", "claude", "critical", True, passed_first_try=True, agreed=True)
    obs.record_verification("action5", "claude", None, "low", False)

    metrics = obs.get_verification_metrics(days=1)

    assert metrics["total_actions"] == 5
    assert metrics["total_verified"] == 4
    assert metrics["verification_rate"] == 80.0
    assert abs(metrics["pass_rate"] - 66.66) < 0.1
    assert metrics["correction_rate"] == 100.0
    assert abs(metrics["avg_fix_cycles"] - 0.66) < 0.1
    assert abs(metrics["escalation_rate"] - 33.33) < 0.1
    assert abs(metrics["agreement_rate"] - 75.0) < 0.1

    claude_metrics = obs.get_verification_metrics(days=1, agent="claude")
    assert claude_metrics["total_actions"] == 3
    assert claude_metrics["total_verified"] == 2
    obs.close()
