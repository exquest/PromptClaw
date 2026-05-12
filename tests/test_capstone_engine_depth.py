"""Depth gate for capstone-engine tests."""
from __future__ import annotations

from sdp.fractal import classify_depth


def test_test_capstone_engine_reaches_depth_two() -> None:
    result = classify_depth("tests/test_capstone_engine.py")
    assert result.depth >= 2, result.reason
