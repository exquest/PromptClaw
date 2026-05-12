"""Depth gate for audio-analysis tests."""
from __future__ import annotations

from sdp.fractal import classify_depth


def test_test_audio_analysis_reaches_depth_two() -> None:
    result = classify_depth("tests/test_audio_analysis.py")
    assert result.depth >= 2, result.reason
