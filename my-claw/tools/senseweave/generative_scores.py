"""Generative Scores -- musical score generation from narrative events and mood.

Bridges the narrative engine (B&P stories, arc tracking) and sensor fusion
(mood, presence, weather) to the music composer. Generates sequences of notes
as Score objects that the composer converts to frequencies and plays.

Stdlib only -- no numpy.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .harmonic_planner import scale_semitones_for_key
from .hook_engine import build_hook_profile

# ---------------------------------------------------------------------------
# Scale / frequency constants
# ---------------------------------------------------------------------------

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_EQUIVALENTS = {
    "Bb": "A#",
    "Eb": "D#",
    "Ab": "G#",
    "Db": "C#",
    "Gb": "F#",
}

_MAJOR_SCALE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]

# A4 = 440 Hz reference
_A4_HZ = 440.0

# Major keys: root name -> root frequency in octave 4
_KEY_ROOTS: dict[str, float] = {}
for _i, _name in enumerate(_NOTE_NAMES):
    # MIDI note number for this note in octave 4: C4=60, A4=69
    _midi = 60 + _i
    _KEY_ROOTS[_name] = _A4_HZ * (2.0 ** ((_midi - 69) / 12.0))
for _flat, _sharp in _FLAT_EQUIVALENTS.items():
    _KEY_ROOTS[_flat] = _KEY_ROOTS[_sharp]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _scale_degree_to_freq(key: str, degree: int, octave_shift: int = 0) -> float:
    """Convert a 1-based scale degree in a given key to frequency in Hz.

    Degree 1 = root in octave 4. Modal keys are supported in the form
    ``"D:dorian"`` or ``"C:lydian"`` alongside legacy major/minor spellings.
    """
    is_minor = key.endswith("m") and ":" not in key
    root_name = key.rstrip("m") if is_minor else key.split(":", 1)[0]
    if root_name not in _KEY_ROOTS:
        root_name = "C"

    root_freq = _KEY_ROOTS[root_name]
    semitones = scale_semitones_for_key(key)

    deg_zero = degree - 1  # 0-based
    octave_offset = deg_zero // len(semitones)
    scale_idx = deg_zero % len(semitones)

    semi = semitones[scale_idx] + 12 * octave_offset + 12 * octave_shift
    return root_freq * (2.0 ** (semi / 12.0))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Note:
    """A single note in a phrase."""
    scale_degree: int       # 1-8 within the key
    duration_beats: float   # in beats
    accent: bool            # accented note


@dataclass
class Phrase:
    """A sequence of notes with performance metadata."""
    notes: list[Note]
    voice: str              # which synth (e.g. "pluck", "pad", "gong")
    dynamic: str            # "pp", "p", "mp", "mf", "f", "ff"
    role: str               # "melody", "bass", "counter", "color"
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class Score:
    """A complete musical score: multiple phrases with global parameters."""
    phrases: list[Phrase]
    key: str                # e.g. "C", "Am"
    tempo_bpm: float
    mood: str               # descriptive mood string
    created_at: float       # unix timestamp
    metadata: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Contour generators (return target degrees for each position)
# ---------------------------------------------------------------------------


def _contour_arch(length: int) -> list[float]:
    """Arch: starts low, rises to midpoint, falls back."""
    targets = []
    mid = (length - 1) / 2.0
    for i in range(length):
        # Normalized position on arch: 0 at ends, 1 at peak
        t = 1.0 - abs(i - mid) / max(mid, 1.0)
        targets.append(1.0 + t * 7.0)  # degree 1 to 8
    return targets


def _contour_descent(length: int) -> list[float]:
    """Descending: starts high, ends low."""
    targets = []
    for i in range(length):
        t = i / max(length - 1, 1)
        targets.append(8.0 - t * 7.0)  # 8 down to 1
    return targets


def _contour_ascent(length: int) -> list[float]:
    """Ascending: starts low, ends high."""
    targets = []
    for i in range(length):
        t = i / max(length - 1, 1)
        targets.append(1.0 + t * 7.0)  # 1 up to 8
    return targets


def _contour_wave(length: int) -> list[float]:
    """Wave: sine-like oscillation."""
    targets = []
    for i in range(length):
        t = i / max(length - 1, 1)
        # One full sine cycle centered around 4.5
        val = 4.5 + 3.5 * math.sin(2.0 * math.pi * t)
        targets.append(val)
    return targets


_CONTOUR_FNS = {
    "arch": _contour_arch,
    "descent": _contour_descent,
    "ascent": _contour_ascent,
    "wave": _contour_wave,
}

_MELODIC_OFFSET_CELLS = {
    "glide": [0, 1, 0, -1],
    "orbit": [0, 2, 1, 3, 1],
    "fan": [0, 2, 4, 2],
    "ripple": [0, 1, 2, 1, -1],
    "drift": [0, -1, 1, 0, -2],
    "torch": [0, 3, 1, 4, 2],
}

_RHYTHM_CELLS = {
    "plain": [1.0, 1.0, 1.0, 1.0],
    "breath": [1.5, 0.75, 1.0, 1.25],
    "skip": [0.5, 0.5, 1.0, 1.5],
    "lilt": [0.75, 0.75, 1.0, 1.5],
    "hover": [1.5, 1.0, 1.5, 0.75],
    "stride": [0.5, 1.0, 0.5, 1.0, 1.5],
}

_FAMILY_MELODIC_CELLS = {
    "default": ("glide", "orbit", "ripple"),
    "ember": ("orbit", "fan", "ripple"),
    "drift": ("glide", "drift", "ripple"),
    "nocturne": ("glide", "drift"),
    "bloom": ("orbit", "ripple", "fan"),
    "pulse": ("fan", "torch", "orbit"),
    "forge": ("torch", "fan", "orbit"),
}

_FAMILY_RHYTHM_CELLS = {
    "default": ("plain", "lilt"),
    "ember": ("lilt", "plain", "breath"),
    "drift": ("breath", "hover", "plain"),
    "nocturne": ("hover", "breath"),
    "bloom": ("lilt", "skip", "plain"),
    "pulse": ("skip", "stride", "plain"),
    "forge": ("stride", "skip", "plain"),
}

_CADENCE_DURATION_SCALE = {
    "sleep": 1.45,
    "wind_down": 1.2,
    "wake_ramp": 1.05,
    "occupied_day": 0.95,
    "away_practice": 0.82,
}

_CADENCE_LEAP_LIMIT = {
    "sleep": 1,
    "wind_down": 2,
    "wake_ramp": 2,
    "occupied_day": 3,
    "away_practice": 4,
}

_CADENCE_ACCENT_BIAS = {
    "sleep": 0.1,
    "wind_down": 0.14,
    "wake_ramp": 0.2,
    "occupied_day": 0.28,
    "away_practice": 0.34,
}

_DYNAMIC_ORDER = ("pp", "p", "mp", "mf", "f", "ff")

_PATCH_DURATION_SCALE = {
    "house_monastery": 1.22,
    "house_chamber": 1.06,
    "house_garden": 0.98,
    "house_procession": 0.86,
    "house_workshop": 0.94,
}

_PATCH_DYNAMIC_SHIFT = {
    "house_monastery": -2,
    "house_chamber": -1,
    "house_garden": 0,
    "house_procession": 1,
    "house_workshop": 0,
}

_PATCH_ACCENT_MULTIPLIER = {
    "house_monastery": 0.55,
    "house_chamber": 0.85,
    "house_garden": 0.95,
    "house_procession": 1.3,
    "house_workshop": 1.15,
}

_PATCH_LEAP_MULTIPLIER = {
    "house_monastery": 0.55,
    "house_chamber": 0.85,
    "house_garden": 0.95,
    "house_procession": 1.15,
    "house_workshop": 1.28,
}

_PATCH_COMPING_STYLES = {
    "house_monastery": ("pedal", "drone_pulse"),
    "house_chamber": ("broken", "root_walk", "pedal"),
    "house_garden": ("rolling_fifth", "broken", "stride"),
    "house_procession": ("stride", "syncopated", "offbeat"),
    "house_workshop": ("syncopated", "walking", "drone_pulse"),
}

_PATCH_PROGRESSIONS = {
    "house_monastery": ([1, 1, 5, 1], [1, 5, 1, 4], [1, 1, 4, 1]),
    "house_chamber": ([1, 4, 5, 1], [1, 6, 4, 5], [1, 2, 5, 1]),
    "house_garden": ([1, 3, 4, 1], [1, 5, 6, 4], [1, 4, 2, 5]),
    "house_procession": ([1, 5, 6, 4], [1, 4, 5, 1], [1, 7, 4, 5]),
    "house_workshop": ([1, 2, 5, 1], [1, 6, 2, 5], [1, 7, 4, 1]),
}

_PROGRESSION_PROFILES = {
    "stillness": ([1, 1, 5, 1], [1, 5, 1, 1], [1, 1, 4, 1]),
    "awakening": ([1, 2, 5, 1], [1, 4, 2, 5], [1, 3, 4, 1]),
    "open_day": ([1, 4, 5, 1], [1, 5, 6, 4], [1, 3, 4, 1], [1, 2, 5, 1]),
    "lift": ([1, 5, 6, 4], [1, 4, 5, 1], [1, 7, 4, 5], [1, 2, 5, 1]),
    "shadow_play": ([1, 5, 1, 6], [1, 4, 7, 1], [1, 7, 4, 1], [1, 6, 2, 5]),
    "settling": ([1, 1, 4, 1], [1, 5, 1, 4], [1, 4, 1, 5], [1, 1, 5, 1]),
    "procession": ([1, 5, 6, 4], [1, 4, 5, 1], [1, 7, 4, 5], [1, 6, 4, 5]),
    "experiment": ([1, 2, 5, 1], [1, 6, 2, 5], [1, 7, 4, 1], [1, 3, 7, 4]),
}

_DEFAULT_PROGRESSIONS = (
    [1, 4, 5, 1],
    [1, 6, 4, 5],
    [1, 4, 1, 5],
    [1, 3, 4, 5],
    [1, 5, 6, 4],
    [1, 2, 5, 1],
)

_DEFAULT_ROLE_OCTAVE_SHIFT = {
    "bass": -3,
    "melody": 0,
    "counter": 2,
    "color": 3,
}

_PATCH_ROLE_OCTAVE_SHIFT = {
    "house_monastery": {
        "bass": -3,
        "melody": -1,
        "counter": 0,
        "color": 1,
    },
    "house_chamber": {
        "bass": -3,
        "melody": 0,
        "counter": 1,
        "color": 2,
    },
    "house_garden": {
        "bass": -3,
        "melody": 0,
        "counter": 1,
        "color": 2,
    },
    "house_procession": {
        "bass": -3,
        "melody": 1,
        "counter": 2,
        "color": 3,
    },
    "house_workshop": {
        "bass": -3,
        "melody": 0,
        "counter": 2,
        "color": 3,
    },
}


def _make_seeded_rng(*parts: object, variation_seed: int | None = None):
    if variation_seed is None:
        return random
    payload = "|".join(str(part) for part in (*parts, variation_seed))
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _shift_dynamic(dynamic: str, delta: int) -> str:
    try:
        idx = _DYNAMIC_ORDER.index(dynamic)
    except ValueError:
        idx = _DYNAMIC_ORDER.index("mf")
    return _DYNAMIC_ORDER[max(0, min(len(_DYNAMIC_ORDER) - 1, idx + delta))]


def _contour_for_patch(
    default: str,
    *,
    patch_name: str,
    energy: float,
    valence: float,
    arousal: float,
) -> str:
    if patch_name == "house_monastery":
        return "descent" if energy < 0.65 else "arch"
    if patch_name == "house_chamber":
        return "arch" if valence >= 0.45 else default
    if patch_name == "house_garden":
        return "wave" if valence >= 0.45 else "arch"
    if patch_name == "house_procession":
        return "ascent" if energy >= 0.4 else "arch"
    if patch_name == "house_workshop":
        return "ascent" if arousal >= 0.65 else "wave"
    return default


def role_octave_shift_for_patch(role: str, patch_name: str = "") -> int:
    shifts = _PATCH_ROLE_OCTAVE_SHIFT.get(patch_name, _DEFAULT_ROLE_OCTAVE_SHIFT)
    return shifts.get(role, 0)


def _wrap_scale_degree(degree: int) -> int:
    return ((degree - 1) % 7) + 1


def _merge_progression_banks(*banks: Sequence[Sequence[int]]) -> tuple[list[int], ...]:
    merged: list[list[int]] = []
    seen: set[tuple[int, ...]] = set()
    for bank in banks:
        for progression in bank:
            frozen = tuple(int(degree) for degree in progression)
            if frozen in seen:
                continue
            seen.add(frozen)
            merged.append(list(frozen))
    return tuple(merged)


def _motif_offsets(
    length: int,
    *,
    family: str,
    cadence_state: str,
    energy: float,
    rng,
) -> list[int]:
    family_key = family if family in _FAMILY_MELODIC_CELLS else "default"
    cell_name = rng.choice(_FAMILY_MELODIC_CELLS[family_key])
    cell = list(_MELODIC_OFFSET_CELLS[cell_name])
    if len(cell) > 1:
        rotation = rng.randrange(len(cell))
        cell = cell[rotation:] + cell[:rotation]
    if rng.random() < 0.35:
        cell = [-value for value in cell]
    if cadence_state in {"sleep", "wind_down"} and rng.random() < 0.6:
        cell = list(reversed(cell))

    base_limit = _CADENCE_LEAP_LIMIT.get(cadence_state, 2)
    family_scale = 1.2 if family in {"forge", "pulse"} else 0.75 if family in {"drift", "nocturne"} else 1.0
    energy_scale = 0.75 + (energy * 0.8)
    limit = max(1, int(round(base_limit * family_scale)))

    offsets: list[int] = []
    for index in range(length):
        raw = cell[index % len(cell)]
        shaped = int(round(raw * energy_scale))
        offsets.append(max(-limit, min(limit, shaped)))
    return offsets


def _rhythm_pattern(
    length: int,
    *,
    family: str,
    cadence_state: str,
    energy: float,
    rng,
) -> list[float]:
    family_key = family if family in _FAMILY_RHYTHM_CELLS else "default"
    cell_name = rng.choice(_FAMILY_RHYTHM_CELLS[family_key])
    cell = list(_RHYTHM_CELLS[cell_name])
    duration_scale = _CADENCE_DURATION_SCALE.get(cadence_state, 1.0) * (1.15 - energy * 0.35)
    return [
        round(_clamp(cell[index % len(cell)] * duration_scale, 0.5, 2.5), 2)
        for index in range(length)
    ]


def _degree_distance(key: str, freq_hz: float, degree: int) -> float:
    target = _scale_degree_to_freq(key, degree)
    return abs(math.log(max(freq_hz, 1.0) / max(target, 1.0)))


def _nearest_scale_degree_for_freq(key: str, freq_hz: float) -> int:
    candidates = range(1, 9)
    return min(candidates, key=lambda degree: _degree_distance(key, freq_hz, degree))


def _coerce_memory_fragment(fragment: Mapping[str, object]) -> list[float]:
    raw_notes = fragment.get("notes")
    if not isinstance(raw_notes, Sequence) or isinstance(raw_notes, (str, bytes)):
        return []
    notes = [float(value) for value in raw_notes if isinstance(value, (int, float)) and float(value) > 0.0]
    if len(notes) < 4:
        return []
    span = max(notes) / max(min(notes), 1.0)
    if span > 2.15:
        return []
    return notes


def _answer_memory_degrees(degrees: Sequence[int]) -> list[int]:
    """Turn a recalled fragment into a related answering gesture."""
    answered = [int(_clamp(degree, 1, 8)) for degree in degrees]
    if len(answered) < 2:
        return answered
    if len(answered) >= 3 and abs(answered[-2] - answered[-3]) > 2:
        direction = 1 if answered[-2] > answered[-3] else -1
        answered[-2] = int(_clamp(answered[-3] + direction, 1, 8))
    answered[-1] = 1 if answered[-2] <= 3 else 3
    return answered


def _memory_phrase_targets(
    key: str,
    *,
    memory_fragments: Sequence[Mapping[str, object]],
    family: str,
    cadence_state: str,
    progression_profile: str,
    rng,
) -> list[int]:
    usable: list[tuple[float, list[float], str]] = []
    for fragment in memory_fragments:
        if not isinstance(fragment, Mapping):
            continue
        notes = _coerce_memory_fragment(fragment)
        if not notes:
            continue
        usable.append(
            (
                float(fragment.get("score", 0.0) or 0.0),
                notes,
                str(fragment.get("context", "") or ""),
            )
        )
    if not usable:
        return []

    def _rank(item: tuple[float, list[float], str]) -> tuple[float, float]:
        score, _notes, context = item
        context_lower = context.lower()
        context_bonus = 0.0
        if family and family.lower() in context_lower:
            context_bonus += 0.15
        if cadence_state and cadence_state.lower() in context_lower:
            context_bonus += 0.1
        if progression_profile and progression_profile.lower() in context_lower:
            context_bonus += 0.16
        if "tracker" in context_lower:
            context_bonus += 0.05
        return (score + context_bonus, float(len(_notes)))

    ranked = sorted(usable, key=_rank, reverse=True)
    _score, notes, context = ranked[0]
    source_root = max(notes[0], 1.0)
    target_root = _scale_degree_to_freq(key, 1)
    transposed = [target_root * (freq_hz / source_root) for freq_hz in notes]
    degrees = [_nearest_scale_degree_for_freq(key, freq_hz) for freq_hz in transposed]

    context_lower = context.lower()
    family_match = family and family.lower() in context_lower
    profile_match = progression_profile and progression_profile.lower() in context_lower
    transform = "identity"
    if cadence_state in {"sleep", "wind_down"}:
        transform = "reverse" if rng.random() < 0.55 else "identity"
    elif family_match and profile_match and rng.random() < 0.65:
        transform = "answer"
    elif family in {"forge", "pulse"} and rng.random() < 0.45:
        transform = "rotate"
    elif rng.random() < 0.2:
        transform = "reverse"

    if transform == "reverse":
        degrees = list(reversed(degrees))
    elif transform == "rotate" and len(degrees) > 1:
        degrees = degrees[1:] + degrees[:1]
    elif transform == "answer":
        degrees = _answer_memory_degrees(degrees)

    return [int(_clamp(degree, 1, 8)) for degree in degrees]


def _apply_hook_degrees(phrase: Phrase, degrees: Sequence[int]) -> Phrase:
    if not degrees or not phrase.notes:
        return phrase
    hooked_notes = list(phrase.notes)
    hook_span = min(len(hooked_notes), max(1, len(degrees) - 1))
    for index, degree in enumerate(degrees[:hook_span]):
        hooked_notes[index] = Note(
            scale_degree=int(_clamp(degree, 1, 8)),
            duration_beats=hooked_notes[index].duration_beats,
            accent=True if index == 0 else hooked_notes[index].accent,
        )
    return Phrase(
        notes=hooked_notes,
        voice=phrase.voice,
        dynamic=phrase.dynamic,
        role=phrase.role,
        metadata=dict(phrase.metadata),
    )


def _shape_patch_ending(phrase: Phrase, *, patch_name: str) -> Phrase:
    if len(phrase.notes) < 2:
        return phrase
    notes = list(phrase.notes)
    first = notes[0].scale_degree
    last = notes[-1].scale_degree
    if patch_name == "house_monastery" and last > first:
        notes[-1] = Note(scale_degree=max(1, first - 1), duration_beats=notes[-1].duration_beats, accent=notes[-1].accent)
    elif patch_name == "house_procession" and last < first:
        notes[-1] = Note(scale_degree=min(8, first + 2), duration_beats=notes[-1].duration_beats, accent=True)
    return Phrase(notes=notes, voice=phrase.voice, dynamic=phrase.dynamic, role=phrase.role, metadata=dict(phrase.metadata))


# ---------------------------------------------------------------------------
# Melody generation
# ---------------------------------------------------------------------------


def generate_melody(
    key: str,
    length: int = 8,
    contour: str = "arch",
    *,
    family: str = "default",
    cadence_state: str = "",
    patch_name: str = "",
    progression_profile: str = "",
    energy: float = 0.5,
    valence: float = 0.5,
    arousal: float = 0.5,
    variation_seed: int | None = None,
    memory_fragments: Sequence[Mapping[str, object]] | None = None,
) -> Phrase:
    """Create a melody phrase using scale degrees 1-8.

    Contours: "arch" (up then down), "descent" (falling),
    "ascent" (rising), "wave" (sine-like).

    Notes are consonant: stepwise motion with occasional leaps to chord tones.
    """
    contour_fn = _CONTOUR_FNS.get(contour, _contour_arch)
    targets = contour_fn(length)
    rng = _make_seeded_rng(
        key,
        length,
        contour,
        family,
        cadence_state,
        patch_name,
        progression_profile,
        round(energy, 3),
        round(valence, 3),
        round(arousal, 3),
        variation_seed=variation_seed,
    )
    motif_offsets = _motif_offsets(
        length,
        family=family,
        cadence_state=cadence_state,
        energy=energy,
        rng=rng,
    )
    rhythm = _rhythm_pattern(
        length,
        family=family,
        cadence_state=cadence_state,
        energy=energy,
        rng=rng,
    )
    memory_targets = []
    if memory_fragments:
        memory_targets = _memory_phrase_targets(
            key,
            memory_fragments=memory_fragments,
            family=family,
            cadence_state=cadence_state,
            progression_profile=progression_profile,
            rng=rng,
        )

    chord_tones = {1, 3, 5, 8}
    notes: list[Note] = []
    initial_target = (
        memory_targets[0]
        if memory_targets
        else _clamp(targets[0] + motif_offsets[0], 1.0, 8.0)
    )
    current_deg = int(round(_clamp(initial_target, 1.0, 8.0)))
    leap_bias = 0.18 + (0.18 * arousal) + (0.12 if family in {"forge", "pulse"} else 0.0)
    leap_bias *= _PATCH_LEAP_MULTIPLIER.get(patch_name, 1.0)
    step_limit = _CADENCE_LEAP_LIMIT.get(cadence_state, 2)
    if cadence_state in {"sleep", "wind_down"}:
        leap_bias *= 0.45

    for i in range(length):
        if i < len(memory_targets):
            target = float(memory_targets[i])
        else:
            target = _clamp(targets[i] + motif_offsets[i], 1.0, 8.0)
        # Move toward target: stepwise (1-2), occasionally leap to chord tone
        diff = target - current_deg
        if abs(diff) <= 2:
            # Step toward target
            step = int(round(diff))
        elif rng.random() < leap_bias and abs(diff) > 2:
            # Leap to nearest chord tone in the direction of target
            candidates = sorted(chord_tones, key=lambda d: abs(d - target))
            step = candidates[0] - current_deg
        else:
            # Stepwise: move 1-2 in the right direction
            direction = 1 if diff > 0 else -1
            step = direction * rng.choice([1, 1, 2])

        step = max(-step_limit, min(step_limit, step))

        current_deg = int(_clamp(current_deg + step, 1, 8))

        duration = rhythm[i]

        # Accent on chord tones, first note, and downbeats
        accent_chance = _CADENCE_ACCENT_BIAS.get(cadence_state, 0.22)
        accent_chance *= _PATCH_ACCENT_MULTIPLIER.get(patch_name, 1.0)
        accent = current_deg in chord_tones and rng.random() < accent_chance
        if i == 0:
            accent = True

        notes.append(Note(
            scale_degree=current_deg,
            duration_beats=duration,
            accent=accent,
        ))

    return Phrase(
        notes=notes,
        voice="pluck",
        dynamic="mf",
        role="melody",
    )


# ---------------------------------------------------------------------------
# Bass line generation
# ---------------------------------------------------------------------------


def generate_bass_line(
    key: str,
    progression: list[int],
    beats_per_chord: int = 3,
    *,
    pattern_style: str = "root_walk",
    variation_seed: int | None = None,
) -> Phrase:
    """Create a bass line following a chord progression.

    Root on beat 1, fifth/third on weak beats.
    progression is a list of root scale degrees (e.g. [1, 4, 5, 1]).
    """
    notes: list[Note] = []
    rng = _make_seeded_rng(
        key,
        tuple(progression),
        beats_per_chord,
        pattern_style,
        variation_seed=variation_seed,
    )

    for root_deg in progression:
        low_root = _wrap_scale_degree(root_deg)
        third_deg = _wrap_scale_degree(root_deg + 2)
        fifth_deg = _wrap_scale_degree(root_deg + 4)
        pattern: list[tuple[int, float, bool]]

        if pattern_style == "pedal":
            pattern = [(low_root, 1.0, True)]
            for _ in range(max(0, beats_per_chord - 1)):
                pattern.append((low_root, 1.0, False))
        elif pattern_style == "drone_pulse":
            pattern = [(low_root, 1.5, True)]
            for beat in range(1, beats_per_chord):
                deg = low_root if beat % 2 == 1 else fifth_deg
                dur = 0.5 if beat % 2 == 1 else 1.0
                pattern.append((deg, dur, beat == beats_per_chord - 1))
        elif pattern_style == "stride":
            pattern = [(low_root, 1.0, True)]
            for beat in range(1, beats_per_chord):
                deg = fifth_deg if beat % 2 == 1 else third_deg
                dur = 0.5 if beat < beats_per_chord - 1 else 1.0
                pattern.append((deg, dur, beat == beats_per_chord - 1))
        elif pattern_style == "rolling_fifth":
            pattern = [(low_root, 0.75, True)]
            for beat in range(1, beats_per_chord):
                deg = fifth_deg if beat % 2 else low_root
                pattern.append((deg, 0.75, False))
        elif pattern_style == "broken":
            pattern = [(low_root, 0.75, True)]
            for beat in range(1, beats_per_chord):
                deg = (third_deg, fifth_deg, low_root, fifth_deg)[beat % 4]
                pattern.append((deg, 0.75 if beat % 2 else 0.5, False))
        elif pattern_style == "syncopated":
            pattern = [(low_root, 0.5, True)]
            for beat in range(1, beats_per_chord):
                deg = rng.choice([third_deg, fifth_deg, low_root])
                pattern.append((deg, 0.5 if beat % 2 else 1.0, beat == beats_per_chord - 1))
        elif pattern_style == "walking":
            pattern = [(low_root, 0.5, True)]
            for beat in range(1, beats_per_chord):
                deg = (third_deg, fifth_deg, _wrap_scale_degree(root_deg + 1), low_root)[beat % 4]
                pattern.append((deg, 0.5, beat == beats_per_chord - 1))
        elif pattern_style == "offbeat":
            pattern = [(low_root, 0.5, False)]
            for beat in range(1, beats_per_chord):
                deg = fifth_deg if beat % 2 else third_deg
                pattern.append((deg, 1.0 if beat % 2 else 0.5, beat % 2 == 1))
        else:
            pattern = [(low_root, 1.0, True)]
            for beat in range(1, beats_per_chord):
                deg = fifth_deg if beat % 2 == 1 else third_deg
                pattern.append((deg, 0.75, False))

        for degree, duration, accent in pattern[:beats_per_chord]:
            notes.append(
                Note(
                    scale_degree=degree,
                    duration_beats=duration,
                    accent=accent,
                )
            )

    return Phrase(
        notes=notes,
        voice="pluck",
        dynamic="mf",
        role="bass",
    )


# ---------------------------------------------------------------------------
# Countermelody generation
# ---------------------------------------------------------------------------


def generate_countermelody(melody: Phrase) -> Phrase:
    """Generate contrary motion counterpoint against a melody.

    When melody goes up, counter goes down. Offset by 1-2 scale degrees
    for call-and-response feel.
    """
    notes: list[Note] = []
    if not melody.notes:
        return Phrase(notes=[], voice="pluck", dynamic="mp", role="counter")

    # Start the counter in the opposite register from the melody
    mel_start = melody.notes[0].scale_degree
    counter_deg = int(_clamp(9 - mel_start, 1, 8))  # mirror around 4.5

    for i, mel_note in enumerate(melody.notes):
        if i > 0:
            # Contrary motion: move opposite to melody
            mel_dir = mel_note.scale_degree - melody.notes[i - 1].scale_degree
            if mel_dir > 0:
                step = -random.choice([1, 1, 2])
            elif mel_dir < 0:
                step = random.choice([1, 1, 2])
            else:
                # Melody holds -- slight movement
                step = random.choice([-1, 0, 1])
            counter_deg = int(_clamp(counter_deg + step, 1, 8))

        # Offset duration slightly for call-and-response feel
        dur = mel_note.duration_beats * random.choice([0.75, 1.0, 1.0, 1.25])

        notes.append(Note(
            scale_degree=counter_deg,
            duration_beats=round(dur, 2),
            accent=mel_note.accent and random.random() < 0.5,
        ))

    return Phrase(
        notes=notes,
        voice="pluck",
        dynamic="mp",
        role="counter",
    )


# ---------------------------------------------------------------------------
# Score from mood
# ---------------------------------------------------------------------------

_MAJOR_KEYS = ["C", "D", "E", "F", "G", "A", "B"]
_MINOR_KEYS = ["Am", "Dm", "Em", "Gm", "Bm"]


def score_from_mood(
    mood: dict,
    *,
    song_num: int = 0,
    family: str = "default",
    cadence_state: str = "",
    patch_name: str = "",
    progression_profile: str = "",
    memory_fragments: Sequence[Mapping[str, object]] | None = None,
    repertoire_hint: Mapping[str, object] | None = None,
) -> Score:
    """Generate a complete score from organism mood.

    Mood dict keys: energy (0-1), valence (0-1), arousal (0-1).

    - high energy: faster tempo, shorter notes, more phrases
    - high valence: major key, arch contours, more accents
    - low energy: slower, longer notes, descent contours
    - sleeping (low energy + low arousal): minimal, one slow phrase, pp dynamic
    """
    energy = _clamp(mood.get("energy", 0.5), 0.0, 1.0)
    valence = _clamp(mood.get("valence", 0.5), 0.0, 1.0)
    arousal = _clamp(mood.get("arousal", 0.5), 0.0, 1.0)
    variation_seed = None
    if song_num or family != "default" or cadence_state:
        variation_seed = song_num or 1
    rng = _make_seeded_rng(
        round(energy, 3),
        round(valence, 3),
        round(arousal, 3),
        family,
        cadence_state,
        patch_name,
        progression_profile,
        variation_seed=variation_seed,
    )
    hook_profile = build_hook_profile(
        family=family,
        progression_profile=progression_profile,
        cadence_state=cadence_state or ("sleep" if energy < 0.25 and arousal < 0.25 else "occupied_day"),
        song_num=song_num or 1,
        mood={"energy": energy, "valence": valence, "arousal": arousal},
        repertoire_hint=repertoire_hint,
    )

    # Tempo: 50 (sleepy) to 140 (energetic)
    activity = (energy + arousal) / 2.0
    tempo = 50.0 + activity * 90.0

    # Key selection
    if valence >= 0.5:
        key = rng.choice(_MAJOR_KEYS)
    else:
        key = rng.choice(_MINOR_KEYS)

    # Sleeping: minimal score
    is_sleeping = energy < 0.25 and arousal < 0.25

    if is_sleeping:
        melody = generate_melody(
            key,
            length=4,
            contour="descent",
            family=family,
            cadence_state=cadence_state or "sleep",
            patch_name=patch_name,
            progression_profile=progression_profile,
            energy=energy,
            valence=valence,
            arousal=arousal,
            variation_seed=variation_seed,
            memory_fragments=memory_fragments,
        )
        melody = Phrase(
            notes=[Note(n.scale_degree, n.duration_beats * 2.0, False) for n in melody.notes],
            voice="pad",
            dynamic="pp",
            role="melody",
        )
        if not memory_fragments:
            melody = _apply_hook_degrees(melody, hook_profile.anchor_degrees)
        melody = _shape_patch_ending(melody, patch_name=patch_name)
        mood_str = "sleeping"
        return Score(
            phrases=[melody],
            key=key,
            tempo_bpm=round(tempo, 1),
            mood=mood_str,
            created_at=time.time(),
            metadata={
                "song_title": hook_profile.title,
                "text_hook": hook_profile.text_hook,
                "hook_class": hook_profile.hook_class,
                "hook_anchor_degrees": json.dumps(list(hook_profile.anchor_degrees)),
                "hook_answer_degrees": json.dumps(list(hook_profile.answer_degrees)),
                "groove_family": hook_profile.groove_family,
                "section_intent": hook_profile.section_intent,
                **(
                    {"repertoire_source_title": str(repertoire_hint.get("source_title", ""))}
                    if repertoire_hint and repertoire_hint.get("source_title")
                    else {}
                ),
                **({"patch_name": patch_name} if patch_name else {}),
                **({"progression_profile": progression_profile} if progression_profile else {}),
            },
        )

    # Determine contour from valence/energy
    if valence >= 0.6:
        contour = "arch"
    elif energy < 0.35:
        contour = "descent"
    elif energy >= 0.7:
        contour = "ascent"
    else:
        contour = rng.choice(["arch", "wave"])
    contour = _contour_for_patch(
        contour,
        patch_name=patch_name,
        energy=energy,
        valence=valence,
        arousal=arousal,
    )

    # Number of phrases: 1-4 based on energy
    num_phrases = max(1, int(1 + energy * 3))

    # Note length factor: high energy -> shorter, low energy -> longer
    dur_factor = (1.5 - energy) * _PATCH_DURATION_SCALE.get(patch_name, 1.0)

    # Dynamic from energy
    if energy >= 0.7:
        dynamic = "f"
    elif energy >= 0.4:
        dynamic = "mf"
    elif energy >= 0.2:
        dynamic = "mp"
    else:
        dynamic = "p"
    dynamic = _shift_dynamic(dynamic, _PATCH_DYNAMIC_SHIFT.get(patch_name, 0))

    # Mood string
    if energy >= 0.7 and valence >= 0.6:
        mood_str = "excited"
    elif valence >= 0.6:
        mood_str = "happy"
    elif valence < 0.4 and energy < 0.4:
        mood_str = "melancholy"
    elif energy >= 0.6:
        mood_str = "energetic"
    else:
        mood_str = "calm"

    phrases: list[Phrase] = []
    comping_style_cycle = {
        "default": ("root_walk", "broken"),
        "ember": ("root_walk", "pedal", "broken"),
        "drift": ("pedal", "broken"),
        "nocturne": ("pedal", "root_walk"),
        "bloom": ("broken", "root_walk", "stride"),
        "pulse": ("stride", "syncopated", "broken"),
        "forge": ("syncopated", "stride", "broken"),
    }
    comping_styles = _PATCH_COMPING_STYLES.get(
        patch_name,
        comping_style_cycle.get(family, comping_style_cycle["default"]),
    )
    if cadence_state in {"sleep", "wind_down"}:
        comping_styles = ("pedal", "root_walk")
    comping_style = comping_styles[song_num % len(comping_styles)] if song_num else comping_styles[0]

    # Melody phrase
    mel_length = max(4, int(8 * (0.5 + energy * 0.5)))
    melody = generate_melody(
        key,
        length=mel_length,
        contour=contour,
        family=family,
        cadence_state=cadence_state,
        patch_name=patch_name,
        progression_profile=progression_profile,
        energy=energy,
        valence=valence,
        arousal=arousal,
        variation_seed=variation_seed,
        memory_fragments=memory_fragments,
    )
    melody = Phrase(
        notes=[Note(n.scale_degree, round(n.duration_beats * dur_factor, 2), n.accent) for n in melody.notes],
        voice=melody.voice,
        dynamic=dynamic,
        role="melody",
    )
    if not memory_fragments:
        melody = _apply_hook_degrees(melody, hook_profile.anchor_degrees)
    melody = _shape_patch_ending(melody, patch_name=patch_name)
    phrases.append(melody)

    # Bass line (if more than 1 phrase)
    if num_phrases >= 2:
        progression_bank = _merge_progression_banks(
            _PROGRESSION_PROFILES.get(progression_profile, ()),
            _PATCH_PROGRESSIONS.get(patch_name, ()),
            _DEFAULT_PROGRESSIONS,
        )
        prog = list(rng.choice(progression_bank))
        bass = generate_bass_line(
            key,
            prog,
            beats_per_chord=4 if patch_name in {"house_monastery", "house_procession"} else 3,
            pattern_style=comping_style,
            variation_seed=variation_seed,
        )
        bass = Phrase(
            notes=[Note(n.scale_degree, round(n.duration_beats * dur_factor, 2), n.accent) for n in bass.notes],
            voice=bass.voice,
            dynamic=_shift_dynamic(dynamic, -1 if patch_name == "house_monastery" else 0),
            role="bass",
        )
        phrases.append(bass)

    # Counter melody (if 3+ phrases)
    if num_phrases >= 3:
        counter = generate_countermelody(melody)
        counter = Phrase(
            notes=[Note(n.scale_degree, round(n.duration_beats * dur_factor, 2), n.accent) for n in counter.notes],
            voice=counter.voice,
            dynamic=_shift_dynamic(counter.dynamic, _PATCH_DYNAMIC_SHIFT.get(patch_name, 0)),
            role="counter",
        )
        phrases.append(counter)

    # Color phrase (if 4 phrases)
    if num_phrases >= 4:
        color_notes = [
            Note(rng.choice([1, 3, 5]), round(rng.uniform(1.5, 3.0) * dur_factor, 2), False)
            for _ in range(4)
        ]
        phrases.append(Phrase(
            notes=color_notes,
            voice="pad",
            dynamic=_shift_dynamic("p", _PATCH_DYNAMIC_SHIFT.get(patch_name, 0) - 1),
            role="color",
        ))

    return Score(
        phrases=phrases,
        key=key,
        tempo_bpm=round(tempo, 1),
        mood=mood_str,
        created_at=time.time(),
        metadata={
            "song_title": hook_profile.title,
            "text_hook": hook_profile.text_hook,
            "hook_class": hook_profile.hook_class,
            "hook_anchor_degrees": json.dumps(list(hook_profile.anchor_degrees)),
            "hook_answer_degrees": json.dumps(list(hook_profile.answer_degrees)),
            "groove_family": hook_profile.groove_family,
            "section_intent": json.dumps(
                {
                    "Theme": hook_profile.section_intent,
                    "Development": "expand the hook",
                    "Recap": "answer the hook",
                    "Resolution": "release the hook",
                }
            ),
            **(
                {"repertoire_source_title": str(repertoire_hint.get("source_title", ""))}
                if repertoire_hint and repertoire_hint.get("source_title")
                else {}
            ),
            **({"patch_name": patch_name} if patch_name else {}),
            **({"progression_profile": progression_profile} if progression_profile else {}),
        },
    )


# ---------------------------------------------------------------------------
# Score from narrative event
# ---------------------------------------------------------------------------


def score_from_narrative_event(event_type: str, description: str) -> Score:
    """Generate a score from a narrative event.

    Known event types:
    - "sunrise": ascending melody in major key
    - "visitor": fanfare-like phrase with accents
    - "rain": descending minor melody
    - "quiet_night": slow minimal score
    - default: moderate arch melody
    """
    now = time.time()

    if event_type == "sunrise":
        key = random.choice(["C", "D", "G"])
        melody = generate_melody(key, length=8, contour="ascent")
        melody = Phrase(
            notes=melody.notes,
            voice="pluck",
            dynamic="mf",
            role="melody",
        )
        return Score(
            phrases=[melody],
            key=key,
            tempo_bpm=100.0,
            mood="hopeful",
            created_at=now,
        )

    if event_type == "visitor":
        key = random.choice(["C", "G", "D"])
        # Fanfare: short, accented, chord-tone heavy
        fanfare_notes = [
            Note(1, 0.5, True),
            Note(3, 0.5, True),
            Note(5, 0.75, True),
            Note(8, 1.0, True),
            Note(5, 0.5, False),
            Note(8, 1.5, True),
        ]
        fanfare = Phrase(
            notes=fanfare_notes,
            voice="pluck",
            dynamic="f",
            role="melody",
        )
        return Score(
            phrases=[fanfare],
            key=key,
            tempo_bpm=120.0,
            mood="alert",
            created_at=now,
        )

    if event_type == "rain":
        key = random.choice(["Am", "Dm", "Em"])
        melody = generate_melody(key, length=8, contour="descent")
        melody = Phrase(
            notes=[Note(n.scale_degree, n.duration_beats * 1.5, n.accent) for n in melody.notes],
            voice="pad",
            dynamic="mp",
            role="melody",
        )
        return Score(
            phrases=[melody],
            key=key,
            tempo_bpm=72.0,
            mood="reflective",
            created_at=now,
        )

    if event_type == "quiet_night":
        key = random.choice(["Am", "Em"])
        melody = generate_melody(key, length=4, contour="descent")
        melody = Phrase(
            notes=[Note(n.scale_degree, n.duration_beats * 2.0, False) for n in melody.notes],
            voice="pad",
            dynamic="pp",
            role="melody",
        )
        return Score(
            phrases=[melody],
            key=key,
            tempo_bpm=60.0,
            mood="peaceful",
            created_at=now,
        )

    # Default: moderate arch melody
    key = random.choice(_MAJOR_KEYS)
    melody = generate_melody(key, length=8, contour="arch")
    return Score(
        phrases=[melody],
        key=key,
        tempo_bpm=96.0,
        mood="neutral",
        created_at=now,
    )


# ---------------------------------------------------------------------------
# Score to frequencies
# ---------------------------------------------------------------------------


def score_to_frequencies(score: Score) -> list[list[tuple[float, float]]]:
    """Convert scale degrees to actual frequencies for each phrase.

    Returns list of phrases, each a list of (freq_hz, duration_seconds).
    Bass-role phrases are shifted down one octave.
    """
    beat_duration = 60.0 / score.tempo_bpm  # seconds per beat
    patch_name = score.metadata.get("patch_name", "")

    result: list[list[tuple[float, float]]] = []

    for phrase in score.phrases:
        octave_shift = role_octave_shift_for_patch(phrase.role, patch_name)

        phrase_freqs: list[tuple[float, float]] = []
        for note in phrase.notes:
            freq = _scale_degree_to_freq(score.key, note.scale_degree, octave_shift)
            dur_sec = note.duration_beats * beat_duration
            phrase_freqs.append((round(freq, 2), round(dur_sec, 4)))

        result.append(phrase_freqs)

    return result
