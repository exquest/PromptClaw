"""Phrase tracker — detects continuous play sessions across MIDI/audio listeners.

Watches a stream of (is_playing, now) ticks and emits 'phrase_started' once a
continuous play session has lasted past the threshold, then 'phrase_ended' when
the player stops. Stdlib only.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

PhraseEvent = Literal["phrase_started", "phrase_ended"]
PhraseTick = tuple[bool, float]

DEFAULT_PHRASE_THRESHOLD_SECONDS = 5.0
_MILLISECOND = Decimal("0.001")


@dataclass(frozen=True)
class PhraseBoundary:
    """One phrase boundary emitted while scanning a listener tick stream."""

    event: PhraseEvent
    timestamp: float
    duration_seconds: float


@dataclass(frozen=True)
class PhraseStreamSummary:
    """Aggregate phrase metrics plus the boundary records they came from."""

    phrase_count: int
    total_phrase_seconds: float
    longest_phrase_seconds: float
    events: tuple[PhraseBoundary, ...]


@dataclass
class PhraseTracker:
    """Detects continuous play sessions and emits phrase boundary events.

    Parameters
    ----------
    threshold_seconds:
        How long a continuous play session must last before it is treated as a
        phrase. Defaults to 5 seconds.

    Notes
    -----
    Call :meth:`update` once per tick with the listener's current
    ``is_playing`` flag. The return value is the boundary event triggered by
    that tick, or ``None`` if no transition occurred.
    """

    threshold_seconds: float = DEFAULT_PHRASE_THRESHOLD_SECONDS
    _play_start: Optional[float] = None
    _phrase_active: bool = False

    @property
    def phrase_active(self) -> bool:
        return self._phrase_active

    @property
    def play_start(self) -> Optional[float]:
        return self._play_start

    def play_duration(self, now: float) -> float:
        """Seconds of continuous play up to ``now``. Zero when not playing."""
        if self._play_start is None:
            return 0.0
        return max(0.0, now - self._play_start)

    def update(self, is_playing: bool, now: float) -> Optional[PhraseEvent]:
        """Advance the tracker. Returns the boundary event for this tick."""
        if is_playing:
            if self._play_start is None:
                self._play_start = now
                return None
            if not self._phrase_active and (now - self._play_start) >= self.threshold_seconds:
                self._phrase_active = True
                return "phrase_started"
            return None

        self._play_start = None
        if self._phrase_active:
            self._phrase_active = False
            return "phrase_ended"
        return None

    def reset(self) -> None:
        """Drop all state without emitting an event."""
        self._play_start = None
        self._phrase_active = False


def track_phrase_boundaries(
    ticks: Iterable[PhraseTick],
    *,
    threshold_seconds: float = DEFAULT_PHRASE_THRESHOLD_SECONDS,
) -> tuple[PhraseBoundary, ...]:
    """Return typed boundary events emitted by scanning ``ticks`` once."""
    tracker = PhraseTracker(threshold_seconds=threshold_seconds)
    boundaries: list[PhraseBoundary] = []
    for is_playing, timestamp in ticks:
        now = float(timestamp)
        duration_before_update = tracker.play_duration(now)
        event = tracker.update(bool(is_playing), now)
        if event is None:
            continue
        duration = (
            duration_before_update
            if event == "phrase_ended"
            else tracker.play_duration(now)
        )
        boundaries.append(
            PhraseBoundary(
                event=event,
                timestamp=now,
                duration_seconds=duration,
            )
        )
    return tuple(boundaries)


def summarize_phrase_stream(
    ticks: Iterable[PhraseTick],
    *,
    threshold_seconds: float = DEFAULT_PHRASE_THRESHOLD_SECONDS,
) -> PhraseStreamSummary:
    """Summarize completed phrases from a listener tick stream."""
    events = track_phrase_boundaries(ticks, threshold_seconds=threshold_seconds)
    completed_durations = tuple(
        event.duration_seconds for event in events if event.event == "phrase_ended"
    )
    if completed_durations:
        total_phrase_seconds = sum(completed_durations)
        longest_phrase_seconds = max(completed_durations)
    else:
        total_phrase_seconds = 0.0
        longest_phrase_seconds = 0.0
    return PhraseStreamSummary(
        phrase_count=len(completed_durations),
        total_phrase_seconds=total_phrase_seconds,
        longest_phrase_seconds=longest_phrase_seconds,
        events=events,
    )


def phrase_status_snapshot(
    tracker: PhraseTracker,
    now: float,
    *,
    event: PhraseEvent | None = None,
) -> dict[str, bool | float | str]:
    """Return the stable phrase status payload used by live listeners."""
    snapshot: dict[str, bool | float | str] = {
        "phrase_active": tracker.phrase_active,
        "phrase_duration_seconds": _rounded_play_duration(tracker, now),
    }
    if event is not None:
        snapshot["phrase_event"] = event
    return snapshot


def _rounded_play_duration(tracker: PhraseTracker, now: float) -> float:
    if tracker.play_start is None:
        return 0.0
    duration = Decimal(str(now)) - Decimal(str(tracker.play_start))
    if duration < 0:
        duration = Decimal("0.0")
    return float(duration.quantize(_MILLISECOND, rounding=ROUND_HALF_UP))


__all__ = [
    "DEFAULT_PHRASE_THRESHOLD_SECONDS",
    "PhraseBoundary",
    "PhraseEvent",
    "PhraseStreamSummary",
    "PhraseTick",
    "PhraseTracker",
    "phrase_status_snapshot",
    "summarize_phrase_stream",
    "track_phrase_boundaries",
]
