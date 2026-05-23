"""Faithful-transmission MIDI event loader for CypherClaw intake."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cypherclaw.midi_fragments import _parse_midi_file


@dataclass(frozen=True)
class FaithfulMidiEvent:
    """A source MIDI note event preserved for faithful transmission."""

    pitch: int
    duration: int
    velocity: int

    def to_dict(self) -> dict[str, int]:
        """Return the JSON-safe event shape used in intake manifests."""

        return {
            "pitch": self.pitch,
            "duration": self.duration,
            "velocity": self.velocity,
        }


def load_faithful_midi_events(path: Path | str) -> tuple[FaithfulMidiEvent, ...]:
    """Load ordered ``(pitch, duration, velocity)`` note events from ``path``.

    Durations are source MIDI ticks. Non-note MIDI data is ignored by the shared
    Standard MIDI File parser, and malformed or unreadable files return an
    empty event tuple.
    """

    parsed = _parse_midi_file(Path(path))
    if parsed is None:
        return ()

    return tuple(
        FaithfulMidiEvent(
            pitch=note.note,
            duration=note.duration_ticks,
            velocity=note.velocity,
        )
        for note in parsed.notes
        if note.duration_ticks > 0
    )
