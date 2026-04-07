"""Korsakov Ch.4 Accompaniment — density-reactive patterns for the composer.

Six accompaniment types ranked by energy:
1. Sustained (held note, no rhythm)
2. Repeated chords (waltz oom-pah-pah)
3. Tremolo (rapid alternation)
4. Arpeggiated (chord tones spread across time)
5. Broken figures (irregular arpeggio)
6. Ostinato (repeating melodic cell, transposed per chord)

The inverse rule: when melody is dense, accompaniment simplifies.
When melody rests, accompaniment fills.
"""
from __future__ import annotations

import math
import random
import time


# === DENSITY TRACKING ===

class DensityTracker:
    """Track melody note density over a sliding window."""

    def __init__(self, window_seconds: float = 4.0):
        self.window = window_seconds
        self._timestamps: list[float] = []

    def note_played(self) -> None:
        """Record that a melody note was just played."""
        self._timestamps.append(time.time())
        self._prune()

    def density(self) -> float:
        """Notes per second over the window."""
        self._prune()
        if not self._timestamps:
            return 0.0
        return len(self._timestamps) / self.window

    def is_resting(self, silence_threshold: float = 1.5) -> bool:
        """True if no notes played in the last silence_threshold seconds."""
        if not self._timestamps:
            return True
        return (time.time() - self._timestamps[-1]) > silence_threshold

    def _prune(self) -> None:
        cutoff = time.time() - self.window
        self._timestamps = [t for t in self._timestamps if t > cutoff]


def select_accompaniment_type(density: float, is_resting: bool) -> int:
    """Select accompaniment type (1-6) based on melody density.

    Inverse rule: high melody density → low accompaniment type.
    Melody resting → higher accompaniment type (fill the gap).
    """
    if is_resting:
        return random.choice([4, 5])  # arpeggiated or broken
    if density > 3.0:
        return 1  # sustained — get out of the way
    if density > 2.0:
        return 2  # repeated chords
    if density > 1.0:
        return 3  # tremolo or simple arpeggio
    return random.choice([2, 4])  # moderate — waltz or arpeggio


# === ACCOMPANIMENT PATTERNS ===
# Each returns a list of (freq, amp, release) tuples to play

def make_scale(root: float) -> list[float]:
    """Major scale from root, 2 octaves."""
    semitones = [0, 2, 4, 5, 7, 9, 11]
    return [root * (2 ** ((s + 12 * o) / 12)) for o in range(3) for s in semitones]


def sustained(root: float, fifth: float, beat: float, loud: float = 0.5) -> list[tuple[float, float, float, float]]:
    """Type 1: Held chord tone. One note, long release.
    Returns [(freq, amp, release, wait)]"""
    return [(root / 2, 0.06 * loud, beat * 6, beat * 3)]


def repeated_chords(root: float, fifth: float, beat: float, loud: float = 0.7) -> list[tuple[float, float, float, float]]:
    """Type 2: Waltz oom-pah-pah."""
    return [
        (root / 2, 0.18 * loud, 0.45, beat),
        (fifth / 2, 0.08 * loud, 0.3, beat),
        (fifth / 2, 0.06 * loud, 0.25, beat),
    ]


def tremolo(root: float, fifth: float, beat: float, loud: float = 0.5) -> list[tuple[float, float, float, float]]:
    """Type 3: Rapid alternation between third and fifth."""
    scale = make_scale(root)
    third = scale[2] if len(scale) > 2 else root * 1.26
    notes = []
    for _ in range(6):
        notes.append((third, 0.03 * loud, 0.15, beat / 2))
        notes.append((fifth, 0.03 * loud, 0.15, beat / 2))
    return notes


def arpeggiated(root: float, fifth: float, beat: float, loud: float = 0.6) -> list[tuple[float, float, float, float]]:
    """Type 4: Chord tones spread across time — root, third, fifth ascending."""
    scale = make_scale(root)
    third = scale[2] if len(scale) > 2 else root * 1.26
    return [
        (root / 2, 0.12 * loud, 0.5, beat),
        (third / 2, 0.08 * loud, 0.4, beat),
        (fifth / 2, 0.06 * loud, 0.35, beat),
    ]


def broken_figure(root: float, fifth: float, beat: float, loud: float = 0.5) -> list[tuple[float, float, float, float]]:
    """Type 5: Irregular arpeggio — fifth, root, third, fifth(up)."""
    scale = make_scale(root)
    third = scale[2] if len(scale) > 2 else root * 1.26
    return [
        (fifth / 2, 0.08 * loud, 0.3, beat * 0.75),
        (root / 2, 0.10 * loud, 0.35, beat * 0.5),
        (third / 2, 0.06 * loud, 0.3, beat * 0.75),
        (fifth, 0.04 * loud, 0.25, beat),
    ]


def ostinato_cell(root: float, fifth: float, beat: float, loud: float = 0.4) -> list[tuple[float, float, float, float]]:
    """Type 6: Short repeating melodic cell — 3 descending scale notes.
    Transposed to chord root."""
    scale = make_scale(root)
    # Pick 3 descending notes from mid-scale
    start = min(4, len(scale) - 3)
    return [
        (scale[start + 2], 0.05 * loud, 0.25, beat * 0.67),
        (scale[start + 1], 0.04 * loud, 0.2, beat * 0.67),
        (scale[start], 0.05 * loud, 0.3, beat * 0.67),
    ]


PATTERNS = {
    1: sustained,
    2: repeated_chords,
    3: tremolo,
    4: arpeggiated,
    5: broken_figure,
    6: ostinato_cell,
}


def get_pattern(
    pattern_type: int,
    root: float,
    fifth: float,
    beat: float,
    loud: float = 0.7,
) -> list[tuple[float, float, float, float]]:
    """Get accompaniment pattern by type number.

    Returns list of (freq, amp, release, wait_after) tuples.
    """
    fn = PATTERNS.get(pattern_type, repeated_chords)
    return fn(root, fifth, beat, loud)


# === PEDAL POINT ===

def pedal_note(root: float, beat: float, loud: float = 0.4) -> tuple[float, float, float]:
    """Gong pedal point — strike on tonic, let it ring.
    Returns (freq, amp, release)."""
    return (root / 4, 0.015 * loud, beat * 12)


def should_pedal(bar_number: int, bars_per_phrase: int = 4) -> bool:
    """True at phrase boundaries (every N bars)."""
    return bar_number % bars_per_phrase == 0


# === BREATHING ===

def breathing_swell(
    melody_density: float,
    melody_resting: bool,
    current_type: int,
) -> int:
    """Adjust accompaniment type based on breathing.

    Melody resting → swell up (higher type number = more activity).
    Melody active → thin out (lower type number).
    """
    if melody_resting and current_type < 5:
        return current_type + 1
    if melody_density > 2.0 and current_type > 1:
        return current_type - 1
    return current_type


# === TRANSITION ===

def should_transition_gradually(
    current_type: int,
    target_type: int,
) -> bool:
    """True if the type change is small enough for gradual transition.
    Large jumps (>2) signal section boundaries and should be abrupt."""
    return abs(current_type - target_type) <= 2
