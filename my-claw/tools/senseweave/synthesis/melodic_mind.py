"""MelodicMind -- real-time melodic generation with memory, chromaticism, and LLM guidance.

Replaces hardcoded melody arrays with a context-aware note generator.
Every note is a decision based on: recent notes, current chord, time of day,
mood, rhythm feel, and occasional LLM advice from a local Ollama instance.

Stdlib + requests only.  No numpy.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import time
from enum import Enum
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# ChromaticScale
# ---------------------------------------------------------------------------

# Major scale semitone offsets from root
_MAJOR_SEMITONES = [0, 2, 4, 5, 7, 9, 11]

# All 12 semitone offsets
ALL_SEMITONES = list(range(12))


class ChromaticScale:
    """Utilities for chromatic and diatonic pitch calculation."""

    def scale_tone(self, root: float, degree: int, octave: int = 0) -> float:
        """Return the frequency for a major-scale degree (1-7) at the given octave.

        degree 1 = root, degree 2 = whole step up, etc.
        octave 0 = root octave, octave 1 = one octave up.
        """
        deg_zero = (degree - 1) % 7
        oct_extra = (degree - 1) // 7
        semitones = _MAJOR_SEMITONES[deg_zero] + 12 * (octave + oct_extra)
        return root * (2.0 ** (semitones / 12.0))

    def chromatic_tone(self, root: float, semitones: int, octave: int = 0) -> float:
        """Return frequency for any semitone offset (0-11) from root at octave."""
        total_semi = semitones + 12 * octave
        return root * (2.0 ** (total_semi / 12.0))

    def neighbor_below(self, freq: float) -> float:
        """Half-step below the given frequency."""
        return freq / (2.0 ** (1.0 / 12.0))

    def neighbor_above(self, freq: float) -> float:
        """Half-step above the given frequency."""
        return freq * (2.0 ** (1.0 / 12.0))


_SCALE = ChromaticScale()


# ---------------------------------------------------------------------------
# RhythmFeel
# ---------------------------------------------------------------------------


class RhythmFeel(Enum):
    WALTZ = "waltz"           # 3/4, oom-pah-pah
    RAGTIME = "ragtime"       # 2/4, syncopated (notes BETWEEN beats)
    NOCTURNE = "nocturne"     # free, slow, long notes with ornaments
    BALLAD = "ballad"         # slow 4/4, sustained
    BEGUINE = "beguine"       # dotted Latin rhythm
    MARCH = "march"           # straight 2/4


def beat_duration(feel: RhythmFeel, bpm: float) -> float:
    """Seconds per beat at the given BPM."""
    return 60.0 / bpm


_ACCENT_PATTERNS: dict[RhythmFeel, list[int]] = {
    RhythmFeel.WALTZ:    [1, 0, 0],
    RhythmFeel.RAGTIME:  [0, 1, 0, 1],
    RhythmFeel.NOCTURNE: [1, 0, 0, 0],
    RhythmFeel.BALLAD:   [1, 0, 0, 0],
    RhythmFeel.BEGUINE:  [1, 0, 0, 1, 0],
    RhythmFeel.MARCH:    [1, 0, 1, 0],
}


def accent_pattern(feel: RhythmFeel) -> list[int]:
    """Which beats are strong (1) vs weak (0)."""
    return list(_ACCENT_PATTERNS[feel])


_SYNCOPATION: dict[RhythmFeel, float] = {
    RhythmFeel.WALTZ:    0.1,
    RhythmFeel.RAGTIME:  0.7,
    RhythmFeel.NOCTURNE: 0.3,
    RhythmFeel.BALLAD:   0.05,
    RhythmFeel.BEGUINE:  0.5,
    RhythmFeel.MARCH:    0.05,
}


def syncopation_probability(feel: RhythmFeel) -> float:
    """Probability of an off-beat note (0.0 = on-beat, 1.0 = always off-beat)."""
    return _SYNCOPATION[feel]


_TYPICAL_DURATIONS: dict[RhythmFeel, list[float]] = {
    RhythmFeel.WALTZ:    [1.0, 1.0, 0.5, 1.5, 2.0],
    RhythmFeel.RAGTIME:  [0.5, 0.75, 0.25, 1.0, 0.5],
    RhythmFeel.NOCTURNE: [2.0, 3.0, 1.5, 4.0, 1.0],
    RhythmFeel.BALLAD:   [1.0, 2.0, 1.5, 3.0, 0.75],
    RhythmFeel.BEGUINE:  [0.75, 1.0, 0.5, 1.5, 0.75],
    RhythmFeel.MARCH:    [0.5, 1.0, 0.5, 1.0, 0.25],
}


def typical_note_durations(feel: RhythmFeel) -> list[float]:
    """Common beat fractions for this rhythm feel."""
    return list(_TYPICAL_DURATIONS[feel])


# ---------------------------------------------------------------------------
# TimeOfDayPersonality
# ---------------------------------------------------------------------------


def personality_for_hour(hour: int) -> dict:
    """Return rhythm feel, tempo range, chromatic probability, and preferred key quality.

    Periods:
        Dawn      5-7:  ballad,   50-70,   low chromatic,  major
        Morning   8-11: waltz/march, 80-110, low chromatic, major
        Afternoon 12-16: ragtime,  100-130, moderate chromatic, major
        Evening   17-20: beguine,  70-100,  moderate chromatic, mixolydian
        Night     21-4:  nocturne, 40-70,   high chromatic, minor
    """
    if 5 <= hour <= 7:
        return {
            "feel": RhythmFeel.BALLAD,
            "tempo_range": (50, 70),
            "chromatic_probability": 0.08,
            "key_quality": "major",
        }
    elif 8 <= hour <= 11:
        return {
            "feel": random.choice([RhythmFeel.WALTZ, RhythmFeel.MARCH]),
            "tempo_range": (80, 110),
            "chromatic_probability": 0.1,
            "key_quality": "major",
        }
    elif 12 <= hour <= 16:
        return {
            "feel": RhythmFeel.RAGTIME,
            "tempo_range": (100, 130),
            "chromatic_probability": 0.25,
            "key_quality": "major",
        }
    elif 17 <= hour <= 20:
        return {
            "feel": RhythmFeel.BEGUINE,
            "tempo_range": (70, 100),
            "chromatic_probability": 0.2,
            "key_quality": "mixolydian",
        }
    else:
        # Night: 21-4
        return {
            "feel": RhythmFeel.NOCTURNE,
            "tempo_range": (40, 70),
            "chromatic_probability": 0.4,
            "key_quality": "minor",
        }


# ---------------------------------------------------------------------------
# MelodicMemory
# ---------------------------------------------------------------------------

_DEFAULT_MEMORY_PATH = "/home/user/cypherclaw-data/state/melodic_memory.json"


class MelodicMemory:
    """Stores melodic fragments that 'worked'. Persists to disk as JSON."""

    def __init__(self, path: str = _DEFAULT_MEMORY_PATH) -> None:
        self._path = Path(path)
        self._fragments: list[dict] = []
        self._load()

    # -- persistence --

    def _load(self) -> None:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text())
                self._fragments = data.get("fragments", [])
        except (json.JSONDecodeError, OSError):
            self._fragments = []

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"fragments": self._fragments}, indent=2))
            os.replace(str(tmp), str(self._path))
        except OSError:
            pass

    # -- public API --

    def store_fragment(self, notes: list[float], context: str, score: float) -> None:
        """Store a fragment with its context and quality score (0-1)."""
        self._fragments.append({
            "notes": notes,
            "context": context,
            "score": max(0.0, min(1.0, score)),
            "stored_at": time.time(),
            "root": notes[0] if notes else 0.0,
        })
        self._save()

    def recall_fragment(self, key_root: float, mood: str) -> list[float] | None:
        """Recall a stored fragment, transposed to the requested key.

        Searches for fragments whose context contains the mood keyword.
        Returns the highest-scored match transposed to key_root, or None.
        """
        candidates = [
            f for f in self._fragments
            if mood.lower() in f.get("context", "").lower()
        ]
        if not candidates:
            return None

        # Pick the highest-scored fragment
        best = max(candidates, key=lambda f: f.get("score", 0))
        notes = best["notes"]
        stored_root = best.get("root", notes[0] if notes else 1.0)
        if stored_root <= 0:
            return notes

        # Transpose: multiply all notes by (key_root / stored_root)
        ratio = key_root / stored_root
        return [n * ratio for n in notes]

    def get_recent(self, count: int = 5) -> list[dict]:
        """Return the most recently stored fragments."""
        return list(self._fragments[-count:])

    def get_recent_matching(
        self,
        keywords: list[str] | tuple[str, ...],
        *,
        count: int = 8,
        min_score: float = 0.0,
    ) -> list[dict]:
        """Return recent fragments whose context matches the given keywords.

        When matches exist, only matching fragments are returned, ranked by:
        1. number of matched keywords
        2. fragment score
        3. recency
        """
        normalized = [
            str(keyword).strip().lower()
            for keyword in keywords
            if str(keyword).strip()
        ]
        if not normalized:
            return [
                fragment
                for fragment in self.get_recent(count=count)
                if float(fragment.get("score", 0.0) or 0.0) >= min_score
            ]

        matches: list[tuple[int, float, float, dict]] = []
        for fragment in self._fragments:
            score = float(fragment.get("score", 0.0) or 0.0)
            if score < min_score:
                continue
            context = str(fragment.get("context", "") or "").lower()
            match_count = sum(1 for keyword in normalized if keyword in context)
            if match_count <= 0:
                continue
            stored_at = float(fragment.get("stored_at", 0.0) or 0.0)
            matches.append((match_count, score, stored_at, fragment))

        if not matches:
            return [
                fragment
                for fragment in self.get_recent(count=count)
                if float(fragment.get("score", 0.0) or 0.0) >= min_score
            ]

        matches.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [fragment for *_meta, fragment in matches[:count]]

    def prune(self, max_fragments: int = 200) -> None:
        """Keep only the top-scored fragments up to max_fragments."""
        if len(self._fragments) <= max_fragments:
            return
        # Sort by score descending, keep best
        self._fragments.sort(key=lambda f: f.get("score", 0), reverse=True)
        self._fragments = self._fragments[:max_fragments]
        self._save()


# ---------------------------------------------------------------------------
# MelodicMind — the core generator
# ---------------------------------------------------------------------------


class MelodicMind:
    """Context-aware melodic note generator.

    Every call to next_note() returns (freq_hz, duration_beats, accent) based on:
    - recent note history (contour continuation / reversal)
    - current chord consonance
    - chromatic probability (time-of-day driven)
    - rhythm feel (syncopation, duration palette)
    - humanized timing (Lewis micro-timing variation)
    - antecedent-consequent phrase tracking
    """

    def __init__(self, key_root: float, rhythm_feel: RhythmFeel, bpm: float) -> None:
        self._key_root = key_root
        self._rhythm_feel = rhythm_feel
        self._bpm = bpm
        self._chromatic_probability = 0.15  # default; overridden by personality
        self._recent: list[float] = []
        self._note_counter = 0
        self._current_degree = 1  # start on root
        self._memory = MelodicMemory.__new__(MelodicMemory)
        self._memory._fragments = []
        self._memory._path = Path(_DEFAULT_MEMORY_PATH)
        # Lewis rhythm concepts
        self.timing_feel: str = "human"  # "straight", "swing", "push", "human"
        self._energy: float = 0.5  # 0.0-1.0, affects timing bias
        self._phrase_position: int = 0  # position within current phrase
        self._phrase_length: int = 8  # notes per phrase half
        self._in_consequent: bool = False  # False = antecedent, True = consequent

    # -- configuration --

    def set_key(self, root: float) -> None:
        self._key_root = root

    def set_feel(self, feel: RhythmFeel, bpm: float) -> None:
        self._rhythm_feel = feel
        self._bpm = bpm

    def set_chromatic_probability(self, prob: float) -> None:
        self._chromatic_probability = max(0.0, min(1.0, prob))

    def set_energy(self, energy: float) -> None:
        """Set energy level (0.0-1.0) which affects humanized timing bias."""
        self._energy = max(0.0, min(1.0, energy))

    def set_timing_feel(self, feel: str) -> None:
        """Set timing feel: 'straight', 'swing', 'push', 'human'."""
        if feel not in ("straight", "swing", "push", "human"):
            raise ValueError(f"Unknown timing feel: {feel!r}")
        self.timing_feel = feel

    # -- humanized timing (Lewis micro-timing variation) --

    def humanize_duration(self, duration_beats: float) -> float:
        """Add +/-5-15ms of timing variation to prevent mechanical feel.

        Slightly early = driving, energetic
        Slightly late = laid-back, relaxed
        The bias shifts with mood/energy.

        Based on Andrew Lewis's "Rhythm: What it is and how to improve
        your sense of it".
        """
        if self.timing_feel == "straight":
            # Minimal variation: +/-2ms
            ms_offset = random.uniform(-2.0, 2.0)
        elif self.timing_feel == "swing":
            # Systematic late on off-beats (even note positions)
            if self._note_counter % 2 == 1:
                ms_offset = random.uniform(5.0, 15.0)  # late
            else:
                ms_offset = random.uniform(-3.0, 3.0)  # on-beat, minimal
        elif self.timing_feel == "push":
            # Systematic early: always slightly ahead
            ms_offset = random.uniform(-15.0, -5.0)
        else:
            # "human": random variation with energy-dependent bias
            magnitude = random.uniform(5.0, 15.0)
            if self._energy > 0.6:
                # High energy: bias early (driving)
                ms_offset = -magnitude * random.uniform(0.3, 1.0)
            elif self._energy < 0.4:
                # Low energy: bias late (laid-back)
                ms_offset = magnitude * random.uniform(0.3, 1.0)
            else:
                # Middle: unbiased random
                ms_offset = random.choice([-1, 1]) * magnitude

        # Convert ms to beat fraction: ms / (ms_per_beat)
        ms_per_beat = (60.0 / self._bpm) * 1000.0
        beat_offset = ms_offset / ms_per_beat
        return max(0.0625, duration_beats + beat_offset)

    # -- antecedent-consequent phrase pairs (Lewis) --

    def generate_phrase_pair(
        self,
        length: int = 8,
        chord_progression: list | None = None,
    ) -> tuple[list, list]:
        """Generate a question phrase and its answer.

        Antecedent (question): ends on a non-tonic note (tension, unresolved)
        Consequent (answer): starts similarly but ends on tonic (resolution)

        The two phrases share melodic material but differ in their endings.

        Based on Andrew Lewis's antecedent-consequent concept.
        """
        # Generate the antecedent phrase
        saved_degree = self._current_degree
        saved_counter = self._note_counter

        self._in_consequent = False
        self._phrase_position = 0
        antecedent = self.generate_phrase(length=length, chord_progression=chord_progression)

        # Force the last note of the antecedent to a non-tonic degree (2, 3, 5, or 7)
        non_tonic_degrees = [2, 3, 5, 7]
        end_degree = random.choice(non_tonic_degrees)
        octave = (end_degree - 1) // 7
        scale_deg = ((end_degree - 1) % 7) + 1
        end_freq = _SCALE.scale_tone(self._key_root, scale_deg, octave)
        last_ant = antecedent[-1]
        antecedent[-1] = (end_freq, last_ant[1], last_ant[2])

        # Record the opening notes of the antecedent (first 2-3 notes)
        shared_count = min(3, length // 2, len(antecedent))
        opening_notes = antecedent[:shared_count]

        # Generate the consequent phrase
        # Reset to start position so it can share opening material
        self._current_degree = saved_degree
        self._in_consequent = True
        self._phrase_position = 0

        # Build consequent: start with same opening, then diverge
        consequent: list[tuple[float, float, bool]] = []
        for note in opening_notes:
            consequent.append(note)
            self._note_counter += 1
            self._phrase_position += 1

        # Generate the divergent portion
        remaining = length - shared_count
        if remaining > 0:
            divergent = self.generate_phrase(
                length=remaining,
                chord_progression=chord_progression,
            )
            consequent.extend(divergent)

        # Force the last note of the consequent to tonic (degree 1)
        tonic_freq = _SCALE.scale_tone(self._key_root, 1, 0)
        last_con = consequent[-1]
        consequent[-1] = (tonic_freq, last_con[1], last_con[2])

        self._in_consequent = False
        return (antecedent, consequent)

    # -- nonperiodic event response (Lewis) --

    def respond_to_event(self, event_type: str) -> tuple[float, float, bool] | None:
        """Generate a musical response to a nonperiodic room event.

        event_type: "transient" (door/footstep), "speech" (someone talking),
                    "silence" (sudden quiet after noise)

        Returns a single note (freq, duration, accent) or None (acknowledge
        with silence).

        Based on Andrew Lewis's nonperiodic event response concept.

        Responses:
        - transient: short staccato note in the current key, accented
        - speech: rest (don't compete with talking)
        - silence: a long, quiet note (filling the new space)
        """
        if event_type == "transient":
            # Short staccato note in the current key, accented
            degree = random.choice([1, 3, 5])
            freq = _SCALE.scale_tone(self._key_root, degree, 0)
            duration = 0.25  # short staccato
            return (freq, duration, True)
        elif event_type == "speech":
            # Don't compete with talking — return None (silence)
            return None
        elif event_type == "silence":
            # Fill the new space with a long, quiet note
            freq = _SCALE.scale_tone(self._key_root, 1, 0)  # tonic
            duration = 4.0  # long sustained note
            return (freq, duration, False)
        return None

    # -- properties --

    @property
    def recent_notes(self) -> list[float]:
        """Last N notes for context."""
        return list(self._recent)

    def get_seed(self) -> list[float]:
        """Return the last 4 notes played — this is the song's seed/motif."""
        return list(self._recent[-4:]) if len(self._recent) >= 4 else list(self._recent)

    # -- internal helpers --

    def _direction(self) -> int:
        """Determine current melodic direction from last 3 notes.

        Returns 1 (ascending), -1 (descending), or 0 (static/ambiguous).
        """
        if len(self._recent) < 2:
            return 0
        tail = self._recent[-3:] if len(self._recent) >= 3 else self._recent[-2:]
        diffs = [tail[i + 1] - tail[i] for i in range(len(tail) - 1)]
        total = sum(diffs)
        if total > 0:
            return 1
        elif total < 0:
            return -1
        return 0

    def _choose_degree_step(self, current_chord: list[int]) -> int:
        """Choose how many scale degrees to move, and in which direction.

        Decision weights:
        - 50% stepwise (1-2 degrees, continuing or reversing contour)
        - 20% chord tone leap
        - 15% chromatic neighbor (handled at frequency level)
        - 10% repeat/rest (step=0)
        - 5%  surprise (large leap)
        """
        roll = random.random()
        direction = self._direction()

        if roll < 0.50:
            # Stepwise motion: contour continuation (60%) vs reversal (25%) vs random (15%)
            contour_roll = random.random()
            if contour_roll < 0.60:
                step_dir = direction if direction != 0 else random.choice([-1, 1])
            elif contour_roll < 0.85:
                step_dir = -direction if direction != 0 else random.choice([-1, 1])
            else:
                step_dir = random.choice([-1, 1])
            step_size = random.choice([1, 1, 2])
            return step_dir * step_size

        elif roll < 0.70:
            # Chord tone leap
            if current_chord:
                target = random.choice(current_chord)
                leap = target - self._current_degree
                if leap == 0:
                    leap = random.choice([-2, 2])
                return leap
            return random.choice([-2, 2])

        elif roll < 0.85:
            # Chromatic neighbor — handled later at the frequency level
            # Move 1 degree in either direction (the chromatic adjustment happens in next_note)
            return random.choice([-1, 1])

        elif roll < 0.95:
            # Repeat or rest
            return 0

        else:
            # Surprise: octave leap or distant interval
            return random.choice([-7, 7, -5, 5])

    def _is_chord_tone(self, degree: int, current_chord: list[int]) -> bool:
        """Check if degree is in the current chord (mod 7)."""
        norm = ((degree - 1) % 7) + 1
        chord_norms = [((d - 1) % 7) + 1 for d in current_chord]
        return norm in chord_norms

    def _apply_chromatic_color(self, freq: float, is_chord_tone: bool) -> float:
        """Possibly add chromatic color (half-step neighbor) to a non-chord tone."""
        if is_chord_tone:
            return freq
        if random.random() < self._chromatic_probability:
            # Approach from below or above
            if random.random() < 0.5:
                return _SCALE.neighbor_below(freq)
            else:
                return _SCALE.neighbor_above(freq)
        return freq

    def _choose_duration(self) -> float:
        """Pick a duration from the rhythm feel's typical palette, with syncopation."""
        durations = typical_note_durations(self._rhythm_feel)
        dur = random.choice(durations)
        # Syncopation: offset the note by half a beat
        if random.random() < syncopation_probability(self._rhythm_feel):
            dur *= random.choice([0.5, 0.75, 1.25])
        return max(0.125, dur)

    def _choose_accent(self) -> bool:
        """Determine accent based on the rhythm feel's accent pattern."""
        pattern = accent_pattern(self._rhythm_feel)
        beat_pos = self._note_counter % len(pattern)
        is_accented = pattern[beat_pos] == 1
        # Add some randomness
        if is_accented and random.random() < 0.7:
            return True
        if not is_accented and random.random() < 0.1:
            return True
        return False

    def _maybe_store_fragment(self) -> None:
        """Every 8 notes, check if the last 4 form an interesting pattern."""
        if self._note_counter % 8 != 0 or len(self._recent) < 4:
            return
        fragment = self._recent[-4:]
        # Check for interesting patterns: rising, falling, repeated interval
        diffs = [fragment[i + 1] - fragment[i] for i in range(len(fragment) - 1)]
        all_rising = all(d > 0 for d in diffs)
        all_falling = all(d < 0 for d in diffs)
        # Repeated interval: all diffs roughly equal
        if len(diffs) >= 2:
            avg = sum(abs(d) for d in diffs) / len(diffs)
            repeated = all(abs(abs(d) - avg) < avg * 0.3 for d in diffs) if avg > 0 else False
        else:
            repeated = False

        if all_rising or all_falling or repeated:
            score = 0.7 if (all_rising or all_falling) else 0.6
            self._memory.store_fragment(
                fragment,
                context=f"auto/{self._rhythm_feel.value}",
                score=score,
            )

    # -- public API --

    def next_note(
        self,
        current_chord: list[int],
        mood: str = "calm",
    ) -> tuple[float, float, bool]:
        """Generate the next note.

        Returns (freq_hz, duration_beats, accent).
        freq_hz = 0.0 means rest.

        Applies humanized timing and tracks phrase position for
        antecedent/consequent awareness.
        """
        step = self._choose_degree_step(current_chord)

        # Handle rest
        if step == 0 and random.random() < 0.5:
            # Actual rest
            dur = self._choose_duration()
            dur = self.humanize_duration(dur)
            accent = False
            self._note_counter += 1
            self._phrase_position += 1
            self._recent.append(0.0)
            self._maybe_store_fragment()
            return (0.0, dur, accent)

        # Apply step
        new_degree = self._current_degree + step
        # Clamp to 1-14 (two octaves)
        new_degree = max(1, min(14, new_degree))

        # Phrase-aware ending: if at the end of a phrase half,
        # bias toward tonic (consequent) or away from tonic (antecedent)
        if self._phrase_position == self._phrase_length - 1:
            if self._in_consequent:
                # End on tonic
                new_degree = 1
            else:
                # End on non-tonic (avoid degree 1 and 8)
                if ((new_degree - 1) % 7) + 1 == 1:
                    new_degree += random.choice([1, 2, 4])
                    new_degree = max(1, min(14, new_degree))

        self._current_degree = new_degree

        # Convert degree to frequency
        octave = (new_degree - 1) // 7
        scale_deg = ((new_degree - 1) % 7) + 1
        freq = _SCALE.scale_tone(self._key_root, scale_deg, octave)

        # Apply chromatic color
        chord_tone = self._is_chord_tone(new_degree, current_chord)
        freq = self._apply_chromatic_color(freq, chord_tone)

        dur = self._choose_duration()
        dur = self.humanize_duration(dur)
        accent = self._choose_accent()

        self._note_counter += 1
        self._phrase_position += 1
        self._recent.append(freq)
        self._maybe_store_fragment()

        return (freq, dur, accent)

    def generate_phrase(
        self,
        length: int = 8,
        chord_progression: list[list[int]] | None = None,
    ) -> list[tuple[float, float, bool]]:
        """Generate a complete phrase of the given length.

        If chord_progression is provided, each chord covers length/len(prog)
        notes (round-robin if shorter).
        """
        phrase: list[tuple[float, float, bool]] = []
        for i in range(length):
            if chord_progression:
                chord_idx = i % len(chord_progression)
                chord = chord_progression[chord_idx]
            else:
                chord = [1, 3, 5]
            phrase.append(self.next_note(chord))
        return phrase


# ---------------------------------------------------------------------------
# LLMAdvisor
# ---------------------------------------------------------------------------

# Keywords for parsing LLM responses
_FEEL_KEYWORDS: dict[str, str] = {
    "waltz": "waltz",
    "ragtime": "ragtime",
    "nocturne": "nocturne",
    "ballad": "ballad",
    "beguine": "beguine",
    "latin": "beguine",
    "march": "march",
}

_MOOD_KEYWORDS = [
    "calm", "melancholy", "excited", "happy", "peaceful",
    "energetic", "reflective", "playful", "dark", "bright",
    "nostalgic", "hopeful", "tense", "serene",
]


class LLMAdvisor:
    """Interface to a local Ollama model for musical guidance.

    All calls use think: false for speed.  Falls back to algorithmic
    defaults if the LLM is unavailable.
    """

    def __init__(
        self,
        model: str = "qwen3.5:4b",
        base_url: str = "http://localhost:11434",
        music_model: str | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._music_model = music_model  # e.g. "chatmusician" for ABC-aware prompts

    def _call(self, prompt: str, timeout: float = 10.0) -> str:
        """Send a prompt to Ollama and return the response text."""
        try:
            resp = requests.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "")
        except Exception:
            pass
        return ""

    @staticmethod
    def _extract_feel(text: str) -> str:
        """Extract a rhythm feel keyword from LLM text."""
        lower = text.lower()
        for kw, feel in _FEEL_KEYWORDS.items():
            if kw in lower:
                return feel
        return "ballad"

    @staticmethod
    def _extract_mood(text: str) -> str:
        """Extract a mood keyword from LLM text."""
        lower = text.lower()
        for mood in _MOOD_KEYWORDS:
            if mood in lower:
                return mood
        return "calm"

    @staticmethod
    def _extract_float(text: str, default: float = 0.5) -> float:
        """Extract a float score from LLM text (looks for patterns like 0.75)."""
        match = re.search(r"\b0?\.\d+\b", text)
        if match:
            try:
                val = float(match.group())
                return max(0.0, min(1.0, val))
            except ValueError:
                pass
        return default

    # -- public API --

    def get_intention(self, hour: int, mood: str, last_key: str) -> dict:
        """Ask LLM: what should the music feel like right now?

        Returns parsed params: tempo_hint, feel_hint, chromatic_hint, mood_hint.
        Falls back to personality_for_hour() on error.
        """
        prompt = (
            f"You are a musical director for a generative ambient system. "
            f"It is {hour}:00. The current mood is '{mood}', key is {last_key}. "
            f"In one sentence, describe the ideal tempo, rhythm feel "
            f"(waltz/ragtime/nocturne/ballad/beguine/march), "
            f"chromatic level (low/moderate/high), and mood."
        )
        text = self._call(prompt)

        if not text:
            # Fallback to algorithmic personality
            p = personality_for_hour(hour)
            return {
                "tempo_hint": sum(p["tempo_range"]) / 2.0,
                "feel_hint": p["feel"].value,
                "chromatic_hint": p["chromatic_probability"],
                "mood_hint": mood,
            }

        # Parse response
        feel = self._extract_feel(text)
        extracted_mood = self._extract_mood(text)

        # Tempo: look for a number in the response
        tempo_match = re.search(r"(\d{2,3})\s*(?:bpm|BPM)?", text)
        tempo = float(tempo_match.group(1)) if tempo_match else 90.0

        # Chromatic level
        lower = text.lower()
        if "high" in lower:
            chromatic = 0.4
        elif "moderate" in lower or "medium" in lower:
            chromatic = 0.25
        else:
            chromatic = 0.1

        return {
            "tempo_hint": tempo,
            "feel_hint": feel,
            "chromatic_hint": chromatic,
            "mood_hint": extracted_mood,
        }

    def critique_phrase(self, notes: list[float], key: str, feel: str) -> str:
        """Ask LLM: was this phrase interesting? What should change?"""
        freq_str = ", ".join(f"{f:.1f}" for f in notes[:8])
        prompt = (
            f"A generative music system just played these frequencies: [{freq_str}] "
            f"in key {key}, feel: {feel}. In one sentence, "
            f"was this phrase interesting and what should change?"
        )
        text = self._call(prompt)
        return text if text else "No LLM feedback available."

    def evaluate_fragment(self, notes: list[float]) -> float:
        """Ask LLM: is this fragment worth remembering? Returns 0.0-1.0 score."""
        freq_str = ", ".join(f"{f:.1f}" for f in notes[:8])
        prompt = (
            f"Rate this melodic fragment on a 0.0-1.0 scale for memorability: "
            f"[{freq_str}]. Reply with just a number like 0.75."
        )
        text = self._call(prompt)
        if text:
            return self._extract_float(text, default=0.5)
        return 0.5

    def suggest_next_chord(self, current_key: str, current_chord: str, mood: str) -> str:
        """Ask LLM: what chord should come next?"""
        prompt = (
            f"In {current_key}, current chord is {current_chord}, mood is {mood}. "
            f"What chord should come next? Reply with the Roman numeral (e.g. IV, vi)."
        )
        text = self._call(prompt)
        return text.strip() if text else "IV"

    def _call_music(self, prompt: str, timeout: float = 15.0) -> str:
        """Send a prompt to the music model (ChatMusician or default).

        Uses self._music_model if set, otherwise falls back to self._model.
        """
        model = self._music_model or self._model
        try:
            resp = requests.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "")
        except Exception:
            pass
        return ""

    def theory_query(self, abc_phrase: str, question: str) -> str:
        """Ask the music model a theory question about a specific phrase in ABC notation.

        When music_model is set to ChatMusician, formats the prompt in ABC-aware style.
        Falls back gracefully if the model is unavailable.
        """
        if self._music_model and "chatmusician" in self._music_model.lower():
            # ABC-aware prompt format for ChatMusician
            prompt = (
                f"Analyze this ABC notation phrase:\n\n"
                f"{abc_phrase}\n\n"
                f"Music theory question: {question}\n"
                f"Answer concisely."
            )
        else:
            # Standard prompt for qwen or other models
            prompt = (
                f"Given this musical phrase in ABC notation:\n{abc_phrase}\n\n"
                f"{question}"
            )
        text = self._call_music(prompt)
        return text if text else "No response from music model."


# ---------------------------------------------------------------------------
# ABC Notation Utilities
# ---------------------------------------------------------------------------

# Note names in chromatic order starting from C
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# ABC octave notation: C, = octave below middle C, C = middle C, c = octave above
_A4_FREQ = 440.0


def freq_sequence_to_abc(freqs: list[float], key: str = "C", meter: str = "3/4") -> str:
    """Convert a sequence of frequencies to ABC notation string.

    ABC is the optimal format for feeding musical material to LLMs.
    ChatMusician is trained on ABC notation.

    Example output:
    X:1
    T:CypherClaw Phrase
    M:3/4
    K:Cmaj
    D F A d c B A F |
    """
    header = (
        f"X:1\n"
        f"T:CypherClaw Phrase\n"
        f"M:{meter}\n"
        f"K:{key}maj\n"
    )
    notes: list[str] = []
    for freq in freqs:
        if freq <= 0:
            notes.append("z")  # rest in ABC notation
            continue
        notes.append(_freq_to_abc_note(freq))

    return header + " ".join(notes) + " |"


def _freq_to_abc_note(freq: float) -> str:
    """Convert a single frequency to an ABC note name.

    ABC octave conventions:
        C, D, E, ...  = octave below middle C  (C3)
        C D E ...      = middle C octave        (C4)
        c d e ...      = octave above middle C  (C5)
        c' d' e' ...   = two octaves above      (C6)

    Uses A4=440Hz as the reference.
    """
    if freq <= 0:
        return "z"

    # Calculate semitones from A4
    semitones_from_a4 = 12.0 * math.log2(freq / _A4_FREQ)
    # MIDI note number (A4 = 69)
    midi = round(69 + semitones_from_a4)
    # Note name and octave
    note_idx = midi % 12  # 0=C, 1=C#, ...
    octave = midi // 12 - 1  # MIDI octave convention

    name = _NOTE_NAMES[note_idx]

    # ABC uses: C, = C3, C = C4, c = C5, c' = C6, c'' = C7
    # For sharps, ABC uses ^
    base = name[0]
    is_sharp = len(name) > 1 and name[1] == "#"
    prefix = "^" if is_sharp else ""

    if octave <= 3:
        # C3 and below: uppercase with commas
        abc = prefix + base
        commas = 4 - octave  # octave 3 = 1 comma, octave 2 = 2 commas
        if commas > 0:
            abc += "," * commas
    elif octave == 4:
        # C4 (middle C octave): uppercase, no modifier
        abc = prefix + base
    elif octave == 5:
        # C5: lowercase
        abc = prefix + base.lower()
    else:
        # C6+: lowercase with apostrophes
        abc = prefix + base.lower()
        apostrophes = octave - 5
        abc += "'" * apostrophes

    return abc


def abc_to_freq_hints(abc_response: str) -> list[str]:
    """Parse ABC note names from an LLM response back to note name hints.

    Returns list of note names like ['D', 'F#', 'A'] that the composer
    can use to guide the melodic mind.

    Strips octave modifiers and ABC-specific prefixes, returning just
    the pitch class names.
    """
    # Match ABC notes: optional accidental (^ or _), letter, optional octave (,' )
    pattern = re.compile(r"([\^_]?)([A-Ga-g])([,\']*)")
    hints: list[str] = []
    for match in pattern.finditer(abc_response):
        accidental, letter, _octave = match.groups()
        name = letter.upper()
        if accidental == "^":
            name += "#"
        elif accidental == "_":
            name += "b"
        hints.append(name)
    return hints


# ---------------------------------------------------------------------------
# RoomPulse — entrain to the room's natural rhythms (Lewis)
# ---------------------------------------------------------------------------

_ROOM_ACTIVITY_PATH = "/tmp/room_activity.json"
_ROOM_PULSE_MAX_HISTORY = 256


class RoomPulse:
    """Entrain to the room's natural rhythms via contact mic data.

    Reads /tmp/room_activity.json and extracts rhythmic patterns
    from the heartbeat (case vibration) sensor.

    Based on Andrew Lewis's room pulse entrainment concept.
    """

    def __init__(self) -> None:
        self._rms_history: list[float] = []
        self._estimated_bpm: float = 0.0

    def feed_rms(self, rms: float) -> None:
        """Feed a new RMS reading from the contact mic."""
        self._rms_history.append(rms)
        if len(self._rms_history) > _ROOM_PULSE_MAX_HISTORY:
            self._rms_history = self._rms_history[-_ROOM_PULSE_MAX_HISTORY:]

    def estimate_room_tempo(self) -> float:
        """Estimate the room's natural pulse in BPM.

        Returns 0.0 if no clear rhythm detected.
        Uses autocorrelation on the RMS history.
        """
        hist = self._rms_history
        if len(hist) < 16:
            self._estimated_bpm = 0.0
            return 0.0

        # Normalize: subtract mean
        mean_val = sum(hist) / len(hist)
        centered = [v - mean_val for v in hist]

        # Autocorrelation for lags corresponding to 30-200 BPM
        # Assuming ~10 readings per second (100ms sample interval)
        samples_per_sec = 10.0
        min_lag = max(1, int(samples_per_sec * 60.0 / 200.0))  # 200 BPM
        max_lag = min(len(centered) // 2, int(samples_per_sec * 60.0 / 30.0))  # 30 BPM

        if min_lag >= max_lag:
            self._estimated_bpm = 0.0
            return 0.0

        n = len(centered)
        variance = sum(c * c for c in centered) / n
        if variance < 1e-9:
            self._estimated_bpm = 0.0
            return 0.0

        # Compute autocorrelation for each lag
        lag_corrs: list[tuple[int, float]] = []
        for lag in range(min_lag, max_lag + 1):
            corr = 0.0
            for i in range(n - lag):
                corr += centered[i] * centered[i + lag]
            corr /= (n - lag)
            lag_corrs.append((lag, corr))

        if not lag_corrs:
            self._estimated_bpm = 0.0
            return 0.0

        # Find the first strong peak: scan from shortest lag, accept the first
        # lag whose correlation exceeds 50% of the global maximum.  This avoids
        # locking onto subharmonics (longer lags that are integer multiples of
        # the true period).
        global_max = max(c for _, c in lag_corrs)
        threshold = global_max * 0.5

        best_lag = 0
        best_corr = 0.0
        for lag, corr in lag_corrs:
            if corr >= threshold:
                best_lag = lag
                best_corr = corr
                break

        if best_corr < variance * 0.2:
            self._estimated_bpm = 0.0
            return 0.0

        if best_lag == 0:
            self._estimated_bpm = 0.0
            return 0.0

        bpm = (samples_per_sec * 60.0) / best_lag
        self._estimated_bpm = bpm
        return bpm

    def suggest_tempo_adjustment(self, current_bpm: float) -> float:
        """Suggest a tempo adjustment to move toward the room's pulse.

        Returns a small delta (+/-5 BPM max) to gradually entrain.
        Doesn't lock -- just gently nudges.
        """
        room_bpm = self._estimated_bpm
        if room_bpm <= 0.0:
            return 0.0

        diff = room_bpm - current_bpm
        # Clamp to +/-5 BPM
        clamped = max(-5.0, min(5.0, diff))
        # Gentle nudge: only move 30% of the way
        return clamped * 0.3

    def read_room_state(self) -> None:
        """Read /tmp/room_activity.json and feed RMS values."""
        try:
            path = Path(_ROOM_ACTIVITY_PATH)
            if not path.exists():
                return
            data = json.loads(path.read_text())
            # Expect {"heartbeat": {"rms_history": [...]}} or
            # {"rms": [...]} or {"heartbeat_rms": float}
            if isinstance(data, dict):
                rms_list = data.get("heartbeat", {}).get("rms_history", [])
                if not rms_list:
                    rms_list = data.get("rms", [])
                if not rms_list:
                    single = data.get("heartbeat_rms")
                    if single is not None:
                        rms_list = [float(single)]
                for val in rms_list:
                    self.feed_rms(float(val))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
