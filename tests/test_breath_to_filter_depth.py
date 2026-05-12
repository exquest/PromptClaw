"""Depth gate for breath-to-filter tests."""
from __future__ import annotations

from sdp.fractal import classify_depth


def test_test_breath_to_filter_reaches_depth_two() -> None:
    result = classify_depth("tests/test_breath_to_filter.py")
    assert result.depth >= 2, result.reason
