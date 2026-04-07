"""Theramini Duet -- musical intelligence for CypherClaw's duet responses.

Given what the Theramini is playing (pitch, onset rate, silence),
decide what CypherClaw should play back: key, register, density, and phrase.

Reads pitch analysis from audio_analysis.py (sibling module).
Stdlib only -- no numpy.
"""
from __future__ import annotations

import math
import os
import random
import sys
import time

# Allow importing audio_analysis from the parent tools directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from audio_analysis import pitch_to_nearest_key, pitch_to_note_name

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# A4 reference
_A4_HZ = 440.0

# Major-scale intervals in semitones from root
_MAJOR_SCALE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]

# Register boundaries (Hz)
_LOW_CEILING = 250.0   # below this = low register
_HIGH_FLOOR = 700.0    # above this = high register

# Duet entry thresholds
_MIN_CONFIDENCE = 0.3
_MAX_STALE_SECONDS = 10.0

# Density thresholds (onsets per second)
_FAST_ONSET_THRESHOLD = 2.0
_SLOW_ONSET_THRESHOLD = 0.5

# Duration multipliers per density class (in beats)
_DURATION_RANGES: dict[str, tuple[float, float]] = {
    "sparse": (1.5, 3.0),
    "moderate": (0.75, 1.5),
    "dense": (0.25, 0.75),
}

# Octave shifts per register
_REGISTER_OCTAVE_SHIFT: dict[str, int] = {
    "low": -1,
    "mid": 0,
    "high": 1,
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _note_name_to_freq(note_name: str, octave: int) -> float:
    """Convert a note name (e.g. 'A') and octave to frequency in Hz.

    Uses A4 = 440 Hz as reference.
    """
    _names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    try:
        semitone = _names.index(note_name)
    except ValueError:
        return _A4_HZ  # fallback

    # MIDI number: C4 = 60, A4 = 69
    midi = (octave + 1) * 12 + semitone
    return _A4_HZ * (2.0 ** ((midi - 69) / 12.0))


def _root_freq_for_key(key_name: str) -> float:
    """Return the frequency of the key root in octave 4."""
    return _note_name_to_freq(key_name, 4)


def _scale_freqs(key_name: str, scale_notes: list[str], octave: int) -> list[float]:
    """Return frequencies for all scale degrees in a given octave."""
    freqs = []
    root_idx_map = {
        "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
        "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
    }
    for note in scale_notes:
        freqs.append(_note_name_to_freq(note, octave))
    # Fix: notes that wrap around (e.g. B in D major) should be in the right octave.
    # If a note's frequency is less than the root, bump it up an octave.
    root_freq = _note_name_to_freq(key_name, octave)
    fixed = []
    for i, f in enumerate(freqs):
        if f < root_freq - 1.0:  # small tolerance
            fixed.append(f * 2.0)
        else:
            fixed.append(f)
    return sorted(fixed)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def suggest_response_key(their_pitch_hz: float) -> tuple[str, float]:
    """Given detected pitch, return (key_name, root_freq) for the response.

    Uses pitch_to_nearest_key from audio_analysis.py to find the key,
    then returns the root frequency in octave 4.
    """
    key_name, _scale = pitch_to_nearest_key(their_pitch_hz)
    root_freq = _root_freq_for_key(key_name)
    return key_name, root_freq


def suggest_response_register(their_pitch_hz: float) -> str:
    """Suggest a complementary register.

    If they're playing high, suggest 'low'.
    If they're playing mid, suggest 'mid'.
    If they're playing low, suggest 'high'.
    """
    if their_pitch_hz >= _HIGH_FLOOR:
        return "low"
    elif their_pitch_hz <= _LOW_CEILING:
        return "high"
    else:
        return "mid"


def suggest_response_density(their_onset_rate: float) -> str:
    """Suggest inverse density based on their onset rate (onsets/sec).

    Fast playing (>2/s) -> 'sparse' (long held notes).
    Slow playing (<0.5/s) -> 'moderate' (gentle response).
    Medium playing -> 'dense' (fill in the gaps).
    """
    if their_onset_rate > _FAST_ONSET_THRESHOLD:
        return "sparse"
    elif their_onset_rate < _SLOW_ONSET_THRESHOLD:
        return "moderate"
    else:
        return "dense"


def suggest_response_phrase(
    key_root: float,
    register: str,
    density: str,
) -> list[tuple[float, float]]:
    """Generate a response phrase as [(freq_hz, duration_beats)].

    Builds from the scale of the nearest key to key_root.
    Phrase length is 3-6 notes. Register shifts the octave.
    Density controls note durations.
    """
    key_name, scale_notes = pitch_to_nearest_key(key_root)

    # Base octave is 4; shift by register
    octave = 4 + _REGISTER_OCTAVE_SHIFT.get(register, 0)
    freqs = _scale_freqs(key_name, scale_notes, octave)

    if not freqs:
        # Fallback: just use the root
        freqs = [key_root]

    # Duration range from density
    dur_lo, dur_hi = _DURATION_RANGES.get(density, (0.5, 1.0))

    # Phrase length: 3-6 notes
    phrase_len = random.randint(3, 6)

    phrase: list[tuple[float, float]] = []
    prev_idx = random.randint(0, len(freqs) - 1)

    for _ in range(phrase_len):
        # Prefer stepwise motion: move by 0, 1, or 2 scale degrees
        step = random.choice([-2, -1, -1, 0, 1, 1, 2])
        idx = max(0, min(len(freqs) - 1, prev_idx + step))
        freq = freqs[idx]
        duration = round(random.uniform(dur_lo, dur_hi), 2)
        phrase.append((round(freq, 2), duration))
        prev_idx = idx

    return phrase


def calculate_wait_beats(consecutive_silence_ms: int, beat_duration: float) -> int:
    """How many beats to wait after they stop before responding.

    Returns 0 if they're still playing (silence_ms == 0).
    Returns 2-4 beats after they stop, scaling with silence duration.
    """
    if consecutive_silence_ms <= 0:
        return 0

    # Scale from 2 beats at 500ms silence to 4 beats at 3000ms+
    silence_sec = consecutive_silence_ms / 1000.0
    # Linear interpolation: 0.5s -> 2 beats, 3.0s -> 4 beats
    t = min(1.0, max(0.0, (silence_sec - 0.5) / 2.5))
    beats = 2.0 + t * 2.0
    return min(4, max(2, round(beats)))


def should_enter_duet(theramini_state: dict) -> bool:
    """Return True if a human is actually playing the Theramini.

    Checks:
    - is_playing is True
    - pitch_confidence above threshold
    - timestamp is fresh (not stale)
    - not an idle tone
    """
    try:
        if not theramini_state.get("is_playing", False):
            return False

        if theramini_state.get("idle_tone", False):
            return False

        confidence = theramini_state.get("pitch_confidence", 0.0)
        if confidence < _MIN_CONFIDENCE:
            return False

        timestamp = theramini_state.get("timestamp", 0)
        if time.time() - timestamp > _MAX_STALE_SECONDS:
            return False

        if theramini_state.get("pitch_hz") is None:
            return False

        return True
    except (TypeError, KeyError, ValueError):
        return False


def should_exit_duet(
    theramini_state: dict,
    silence_threshold_ms: int = 5000,
) -> bool:
    """Return True if they've stopped playing long enough to exit duet mode.

    Exits when:
    - consecutive_silence_ms exceeds threshold
    - timestamp is stale (listener may have died)
    """
    try:
        # Stale timestamp = exit (fail safe)
        timestamp = theramini_state.get("timestamp", 0)
        if time.time() - timestamp > _MAX_STALE_SECONDS:
            return True

        silence_ms = theramini_state.get("consecutive_silence_ms", 0)
        if silence_ms >= silence_threshold_ms:
            return True

        return False
    except (TypeError, KeyError, ValueError):
        return True
