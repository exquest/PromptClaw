"""Depth gate for generation request tests."""
from __future__ import annotations

from sdp.fractal import classify_depth


def test_test_generation_request_reaches_depth_two() -> None:
    result = classify_depth("tests/test_generation_request.py")
    assert result.depth >= 2, result.reason
