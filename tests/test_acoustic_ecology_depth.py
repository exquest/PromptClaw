"""Depth gate for installation-aware acoustic ecology tests."""
from __future__ import annotations

from sdp.fractal import classify_depth


def test_test_acoustic_ecology_reaches_depth_two() -> None:
    result = classify_depth("tests/test_acoustic_ecology.py")
    assert result.depth >= 2, result.reason
