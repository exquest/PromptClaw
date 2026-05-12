"""Unit tests for PhraseTracker — 5-second continuous-play threshold."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.phrase_tracker import (
    DEFAULT_PHRASE_THRESHOLD_SECONDS,
    PhraseTracker,
)


def test_default_threshold_is_five_seconds() -> None:
    assert DEFAULT_PHRASE_THRESHOLD_SECONDS == 5.0
    assert PhraseTracker().threshold_seconds == 5.0


def test_no_event_before_threshold() -> None:
    tracker = PhraseTracker()
    assert tracker.update(True, 0.0) is None  # play starts
    assert tracker.update(True, 2.0) is None
    assert tracker.update(True, 4.999) is None
    assert tracker.phrase_active is False


def test_emits_phrase_started_at_threshold() -> None:
    tracker = PhraseTracker()
    tracker.update(True, 0.0)
    assert tracker.update(True, 5.0) == "phrase_started"
    assert tracker.phrase_active is True


def test_emits_phrase_started_only_once_per_session() -> None:
    tracker = PhraseTracker()
    tracker.update(True, 0.0)
    assert tracker.update(True, 5.0) == "phrase_started"
    assert tracker.update(True, 6.0) is None
    assert tracker.update(True, 30.0) is None


def test_emits_phrase_ended_when_play_stops_after_threshold() -> None:
    tracker = PhraseTracker()
    tracker.update(True, 0.0)
    tracker.update(True, 5.0)  # phrase_started
    assert tracker.update(False, 7.0) == "phrase_ended"
    assert tracker.phrase_active is False
    assert tracker.play_duration(8.0) == 0.0


def test_no_phrase_ended_for_short_burst() -> None:
    tracker = PhraseTracker()
    tracker.update(True, 0.0)
    assert tracker.update(False, 2.0) is None
    assert tracker.phrase_active is False


def test_short_burst_does_not_arm_a_later_phrase_started() -> None:
    """A <5s burst followed by silence then play must restart the timer."""
    tracker = PhraseTracker()
    tracker.update(True, 0.0)
    tracker.update(False, 2.0)  # short burst, no event
    tracker.update(True, 3.0)  # new session begins
    assert tracker.update(True, 7.5) is None  # only 4.5s into new session
    assert tracker.update(True, 8.0) == "phrase_started"  # 5.0s into new session


def test_full_phrase_cycle_then_new_phrase() -> None:
    tracker = PhraseTracker()
    tracker.update(True, 0.0)
    assert tracker.update(True, 5.0) == "phrase_started"
    assert tracker.update(False, 6.0) == "phrase_ended"

    tracker.update(True, 10.0)
    assert tracker.update(True, 14.999) is None
    assert tracker.update(True, 15.0) == "phrase_started"


def test_play_duration_tracks_elapsed_play_time() -> None:
    tracker = PhraseTracker()
    assert tracker.play_duration(0.0) == 0.0
    tracker.update(True, 100.0)
    assert tracker.play_duration(102.5) == 2.5
    tracker.update(False, 103.0)
    assert tracker.play_duration(110.0) == 0.0


def test_custom_threshold() -> None:
    tracker = PhraseTracker(threshold_seconds=2.0)
    tracker.update(True, 0.0)
    assert tracker.update(True, 1.99) is None
    assert tracker.update(True, 2.0) == "phrase_started"


def test_reset_clears_active_phrase_without_emitting() -> None:
    tracker = PhraseTracker()
    tracker.update(True, 0.0)
    tracker.update(True, 5.0)
    assert tracker.phrase_active is True
    tracker.reset()
    assert tracker.phrase_active is False
    assert tracker.play_start is None
    # After reset, a fresh play session must traverse the full threshold again.
    tracker.update(True, 6.0)
    assert tracker.update(True, 10.999) is None
    assert tracker.update(True, 11.0) == "phrase_started"


def test_starts_in_idle_state() -> None:
    tracker = PhraseTracker()
    assert tracker.phrase_active is False
    assert tracker.play_start is None
    # An is_playing=False tick before any play must not emit anything.
    assert tracker.update(False, 0.0) is None
    assert tracker.update(False, 100.0) is None
