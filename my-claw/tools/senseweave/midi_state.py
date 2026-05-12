"""MIDI State Tracker — tracks live input from CypherClaw MIDI devices.

Devices: Akai MAX25 keyboard, Theramini MIDI, Perform-VE MIDI.
Pure stdlib, no external MIDI libraries required.
"""
from __future__ import annotations

import re
import time
from typing import Optional

# Note name tables
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Flat-to-sharp mapping for name_to_note
_FLAT_TO_SHARP = {
    "Cb": "B", "Db": "C#", "Eb": "D#", "Fb": "E",
    "Gb": "F#", "Ab": "G#", "Bb": "A#",
}


def note_to_name(note: int) -> str:
    """Convert MIDI note number (0-127) to note name, e.g. 60 -> 'C4'."""
    octave = (note // 12) - 1
    name = _NOTE_NAMES[note % 12]
    return f"{name}{octave}"


def name_to_note(name: str) -> int:
    """Convert note name to MIDI note number, e.g. 'C4' -> 60.

    Supports sharps (C#4) and flats (Db4). Octave range: -1 to 9.
    """
    match = re.match(r"^([A-Ga-g][#b]?)([-]?\d+)$", name)
    if not match:
        raise ValueError(f"Invalid note name: {name!r}")

    note_part = match.group(1)
    octave = int(match.group(2))

    # Capitalize first letter
    note_part = note_part[0].upper() + note_part[1:]

    # Convert flats to sharps
    if note_part in _FLAT_TO_SHARP:
        note_part = _FLAT_TO_SHARP[note_part]

    if note_part not in _NOTE_NAMES:
        raise ValueError(f"Unknown note name: {note_part!r}")

    return _NOTE_NAMES.index(note_part) + (octave + 1) * 12


class MidiState:
    """Tracks the current state of MIDI input from connected devices.

    Attributes:
        notes_on: Set of currently held MIDI note numbers.
        last_note: Most recently played note number, or None.
        last_velocity: Velocity of the most recent note-on.
        sustain_pedal: Whether sustain pedal is engaged (CC#64).
        expression: Current expression pedal value (0-127, CC#11).
        pitch_bend: Current pitch bend value (0-16383, center=8192).
        mod_wheel: Current mod wheel value (0-127, CC#1).
        volume: Current volume value (0-127, CC#7).
        activity_rate: Notes per second over the recent window.
    """

    # Window size for activity rate measurement
    _ACTIVITY_WINDOW = 5.0  # seconds

    def __init__(self) -> None:
        self.notes_on: set[int] = set()
        self.last_note: Optional[int] = None
        self.last_velocity: int = 0
        self.sustain_pedal: bool = False
        self.expression: int = 100
        self.pitch_bend: int = 8192
        self.mod_wheel: int = 0
        self.volume: int = 100
        self._note_timestamps: list[float] = []

    @property
    def activity_rate(self) -> float:
        """Notes per second over the last N seconds."""
        self._prune_timestamps()
        if not self._note_timestamps:
            return 0.0
        window = self._ACTIVITY_WINDOW
        return len(self._note_timestamps) / window

    def _prune_timestamps(self) -> None:
        """Remove note timestamps older than the activity window."""
        cutoff = time.monotonic() - self._ACTIVITY_WINDOW
        self._note_timestamps = [t for t in self._note_timestamps if t >= cutoff]

    def note_on(self, note: int, velocity: int) -> None:
        """Handle a MIDI note-on event. Velocity 0 is treated as note-off."""
        if velocity == 0:
            self.note_off(note)
            return
        self.notes_on.add(note)
        self.last_note = note
        self.last_velocity = velocity
        self._note_timestamps.append(time.monotonic())

    def note_off(self, note: int) -> None:
        """Handle a MIDI note-off event."""
        self.notes_on.discard(note)

    def control_change(self, cc: int, value: int) -> None:
        """Handle a MIDI control change message.

        Recognized CCs:
        - 1:  Mod wheel
        - 7:  Volume
        - 11: Expression
        - 64: Sustain pedal (>= 64 = on)
        """
        if cc == 1:
            self.mod_wheel = value
        elif cc == 7:
            self.volume = value
        elif cc == 11:
            self.expression = value
        elif cc == 64:
            self.sustain_pedal = value >= 64

    def pitch_bend_change(self, value: int) -> None:
        """Handle a MIDI pitch bend message. Value range: 0-16383."""
        self.pitch_bend = value

    def to_dict(self) -> dict:
        """Serialize state for JSON transport."""
        return {
            "notes_on": sorted(self.notes_on),
            "last_note": self.last_note,
            "last_velocity": self.last_velocity,
            "sustain_pedal": self.sustain_pedal,
            "expression": self.expression,
            "pitch_bend": self.pitch_bend,
            "mod_wheel": self.mod_wheel,
            "volume": self.volume,
            "activity_rate": round(self.activity_rate, 3),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MidiState":
        """Deserialize from a dict (e.g. from JSON)."""
        ms = cls()
        ms.notes_on = set(data.get("notes_on", []))
        ms.last_note = data.get("last_note")
        ms.last_velocity = data.get("last_velocity", 0)
        ms.sustain_pedal = data.get("sustain_pedal", False)
        ms.expression = data.get("expression", 100)
        ms.pitch_bend = data.get("pitch_bend", 8192)
        ms.mod_wheel = data.get("mod_wheel", 0)
        ms.volume = data.get("volume", 100)
        return ms
