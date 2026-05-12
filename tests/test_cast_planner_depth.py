"""Depth gate for cast-planner tests."""
from __future__ import annotations

from sdp.fractal import classify_depth


def test_test_cast_planner_reaches_depth_two() -> None:
    result = classify_depth("tests/test_cast_planner.py")
    assert result.depth >= 2, result.reason
