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

    # -- configuration --

    def set_key(self, root: float) -> None:
        self._key_root = root

    def set_feel(self, feel: RhythmFeel, bpm: float) -> None:
        self._rhythm_feel = feel
        self._bpm = bpm

    def set_chromatic_probability(self, prob: float) -> None:
        self._chromatic_probability = max(0.0, min(1.0, prob))

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
        """
        step = self._choose_degree_step(current_chord)

        # Handle rest
        if step == 0 and random.random() < 0.5:
            # Actual rest
            dur = self._choose_duration()
            accent = False
            self._note_counter += 1
            self._recent.append(0.0)
            self._maybe_store_fragment()
            return (0.0, dur, accent)

        # Apply step
        new_degree = self._current_degree + step
        # Clamp to 1-14 (two octaves)
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
        accent = self._choose_accent()

        self._note_counter += 1
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
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

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
