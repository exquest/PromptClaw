"""Depth gate for quota-aware agent selector tests."""
from __future__ import annotations

from sdp.fractal import classify_depth


def test_test_agent_selector_quota_reaches_depth_two() -> None:
    result = classify_depth("tests/test_agent_selector_quota.py")
    assert result.depth >= 2, result.reason
