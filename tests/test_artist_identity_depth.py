"""Depth gate for artist-identity tests."""
from __future__ import annotations

from sdp.fractal import classify_depth


def test_test_artist_identity_reaches_depth_two() -> None:
    result = classify_depth("tests/test_artist_identity.py")
    assert result.depth >= 2, result.reason
