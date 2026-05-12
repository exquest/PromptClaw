"""Depth gate for section arrangement engine tests."""
from __future__ import annotations

from sdp.fractal import classify_depth


def test_test_arrangement_engine_reaches_depth_two() -> None:
    result = classify_depth("tests/test_arrangement_engine.py")
    assert result.depth >= 2, result.reason
