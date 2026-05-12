"""Depth-2 PhraseTracker helpers - locked test surface for frac-0013."""
from __future__ import annotations

import dataclasses
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.phrase_tracker import (  # noqa: E402
    PhraseBoundary,
    PhraseStreamSummary,
    PhraseTracker,
    phrase_status_snapshot,
    summarize_phrase_stream,
    track_phrase_boundaries,
)


def _mixed_stream() -> tuple[tuple[bool, float], ...]:
    return (
        (True, 10.0),
        (True, 14.9),
        (True, 15.0),
        (False, 18.0),
        (True, 30.0),
        (False, 31.0),
        (True, 40.0),
        (True, 46.0),
        (False, 47.5),
    )


def test_track_phrase_boundaries_returns_typed_started_and_ended_events() -> None:
    boundaries = track_phrase_boundaries(_mixed_stream())

    assert boundaries == (
        PhraseBoundary("phrase_started", 15.0, 5.0),
        PhraseBoundary("phrase_ended", 18.0, 8.0),
        PhraseBoundary("phrase_started", 46.0, 6.0),
        PhraseBoundary("phrase_ended", 47.5, 7.5),
    )
    assert dataclasses.is_dataclass(boundaries[0])
    assert getattr(boundaries[0], "__dataclass_params__").frozen


def test_summarize_phrase_stream_counts_completed_phrases() -> None:
    summary = summarize_phrase_stream(_mixed_stream())

    assert isinstance(summary, PhraseStreamSummary)
    assert summary.phrase_count == 2
    assert summary.total_phrase_seconds == pytest.approx(15.5)
    assert summary.longest_phrase_seconds == pytest.approx(8.0)
    assert summary.events[-1] == PhraseBoundary("phrase_ended", 47.5, 7.5)


def test_phrase_status_snapshot_matches_listener_payload_shape() -> None:
    tracker = PhraseTracker()
    tracker.update(True, 100.0)
    event = tracker.update(True, 105.0)
    before_play_start = tracker.play_start

    snapshot = phrase_status_snapshot(tracker, 106.2345, event=event)

    assert snapshot == {
        "phrase_active": True,
        "phrase_duration_seconds": 6.235,
        "phrase_event": "phrase_started",
    }
    assert tracker.play_start == before_play_start
    assert tracker.phrase_active is True

    ended_event = tracker.update(False, 107.0)
    ended_snapshot = phrase_status_snapshot(tracker, 107.0, event=ended_event)

    assert ended_snapshot == {
        "phrase_active": False,
        "phrase_duration_seconds": 0.0,
        "phrase_event": "phrase_ended",
    }


def test_phrase_tracker_reaches_depth_two() -> None:
    sdp_src = "/Users/anthony/Programming/sdp-cli/src"
    if sdp_src not in sys.path:
        sys.path.insert(0, sdp_src)
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/phrase_tracker.py")
    assert result.depth >= 2, result.reason
