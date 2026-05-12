"""Pitch, interval, scale, and mode library for CypherClaw's synthesis engine.

Provides:
- MIDI / frequency / note-name conversion
- Named intervals with consonance, character, and arc-phase metadata
- Scale and mode definitions (Western diatonic, pentatonic, symmetric,
  non-Western, and exotic)
- Microtonal ratio helpers (cents, just-intonation ratios)

Stdlib only -- no numpy.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from itertools import product
from typing import Literal, Sequence

# ---------------------------------------------------------------------------
# Note names and enharmonic helpers
# ---------------------------------------------------------------------------

NOTE_NAMES: tuple[str, ...] = (
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
)

ENHARMONIC_MAP: dict[str, str] = {
    "Db": "C#", "Eb": "D#", "Fb": "E", "Gb": "F#",
    "Ab": "G#", "Bb": "A#", "Cb": "B",
    "B#": "C", "E#": "F",
}

_NAME_TO_PC: dict[str, int] = {name: i for i, name in enumerate(NOTE_NAMES)}
for _alias, _canonical in ENHARMONIC_MAP.items():
    _NAME_TO_PC[_alias] = _NAME_TO_PC[_canonical]

A4_HZ: float = 440.0
A4_MIDI: int = 69

# ---------------------------------------------------------------------------
# Pitch helpers
# ---------------------------------------------------------------------------


def midi_to_freq(midi_note: int | float, *, a4: float = A4_HZ) -> float:
    return a4 * (2.0 ** ((float(midi_note) - A4_MIDI) / 12.0))


def freq_to_midi(freq: float, *, a4: float = A4_HZ) -> float:
    if freq <= 0:
        raise ValueError(f"frequency must be positive, got {freq}")
    return 12.0 * math.log2(freq / a4) + A4_MIDI


def note_name_to_pitch_class(name: str) -> int:
    pc = _NAME_TO_PC.get(name)
    if pc is None:
        raise ValueError(f"unknown note name: {name!r}")
    return pc


def note_name_to_midi(name: str, octave: int = 4) -> int:
    return note_name_to_pitch_class(name) + 12 * (octave + 1)


def midi_to_note_name(midi_note: int) -> tuple[str, int]:
    pc = midi_note % 12
    octave = (midi_note // 12) - 1
    return NOTE_NAMES[pc], octave


# ---------------------------------------------------------------------------
# Interval
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    """Rich metadata for a chromatic interval."""

    semitones: int
    name: str
    short_name: str
    consonance: str  # "perfect", "imperfect", "mild_dissonance", "sharp_dissonance"
    character: str
    arc_phase: str  # maps to scene order in harmonic_planner


INTERVALS: tuple[Interval, ...] = (
    Interval(0,  "perfect unison",  "P1",  "perfect",           "unity, identity",         "Resolution"),
    Interval(1,  "minor second",    "m2",  "sharp_dissonance",  "tension, proximity",      "Emergence"),
    Interval(2,  "major second",    "M2",  "mild_dissonance",   "stepping, motion",        "Emergence"),
    Interval(3,  "minor third",     "m3",  "imperfect",         "sadness, intimacy",       "Development"),
    Interval(4,  "major third",     "M3",  "imperfect",         "brightness, warmth",      "Theme"),
    Interval(5,  "perfect fourth",  "P4",  "perfect",           "suspension, openness",    "Bridge"),
    Interval(6,  "tritone",         "TT",  "sharp_dissonance",  "tension, instability",    "Development"),
    Interval(7,  "perfect fifth",   "P5",  "perfect",           "power, stability",        "Theme"),
    Interval(8,  "minor sixth",     "m6",  "imperfect",         "yearning, depth",         "Bridge"),
    Interval(9,  "major sixth",     "M6",  "imperfect",         "grace, warmth",           "Recap"),
    Interval(10, "minor seventh",   "m7",  "mild_dissonance",   "longing, pull",           "Development"),
    Interval(11, "major seventh",   "M7",  "sharp_dissonance",  "leading, aspiration",     "Resolution"),
    Interval(12, "perfect octave",  "P8",  "perfect",           "completion, renewal",     "Afterglow"),
)

INTERVAL_BY_SEMITONES: dict[int, Interval] = {iv.semitones: iv for iv in INTERVALS}
INTERVAL_BY_SHORT_NAME: dict[str, Interval] = {iv.short_name: iv for iv in INTERVALS}


def interval_between(midi_a: int, midi_b: int) -> Interval:
    semis = abs(midi_b - midi_a) % 12
    return INTERVAL_BY_SEMITONES[semis]


# ---------------------------------------------------------------------------
# Scale catalogue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scale:
    """A named scale defined by its semitone set from the root."""

    name: str
    semitones: tuple[int, ...]

    @property
    def pitch_classes(self) -> frozenset[int]:
        return frozenset(self.semitones)

    @property
    def degree_count(self) -> int:
        return len(self.semitones)

    def transpose(self, root_pc: int) -> frozenset[int]:
        return frozenset((root_pc + s) % 12 for s in self.semitones)

    def to_midi_notes(self, root_midi: int, *, octaves: int = 1) -> list[int]:
        notes: list[int] = []
        for octave in range(octaves):
            for s in self.semitones:
                notes.append(root_midi + s + 12 * octave)
        return notes

    def to_frequencies(self, root_midi: int, *, octaves: int = 1, a4: float = A4_HZ) -> list[float]:
        return [midi_to_freq(n, a4=a4) for n in self.to_midi_notes(root_midi, octaves=octaves)]

    def intervals(self) -> list[Interval]:
        return [INTERVAL_BY_SEMITONES[s % 12] for s in self.semitones]


# -- Western diatonic modes ------------------------------------------------

CHROMATIC          = Scale("chromatic",          (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11))
IONIAN             = Scale("ionian",             (0, 2, 4, 5, 7, 9, 11))
DORIAN             = Scale("dorian",             (0, 2, 3, 5, 7, 9, 10))
PHRYGIAN           = Scale("phrygian",           (0, 1, 3, 5, 7, 8, 10))
LYDIAN             = Scale("lydian",             (0, 2, 4, 6, 7, 9, 11))
MIXOLYDIAN         = Scale("mixolydian",         (0, 2, 4, 5, 7, 9, 10))
AEOLIAN            = Scale("aeolian",            (0, 2, 3, 5, 7, 8, 10))
LOCRIAN            = Scale("locrian",            (0, 1, 3, 5, 6, 8, 10))

MAJOR = IONIAN
MINOR = AEOLIAN

# -- Minor variants --------------------------------------------------------

HARMONIC_MINOR     = Scale("harmonic_minor",     (0, 2, 3, 5, 7, 8, 11))
MELODIC_MINOR      = Scale("melodic_minor",      (0, 2, 3, 5, 7, 9, 11))

# -- Pentatonic ------------------------------------------------------------

MAJOR_PENTATONIC   = Scale("major_pentatonic",   (0, 2, 4, 7, 9))
MINOR_PENTATONIC   = Scale("minor_pentatonic",   (0, 3, 5, 7, 10))

# -- Symmetric scales ------------------------------------------------------

WHOLE_TONE         = Scale("whole_tone",         (0, 2, 4, 6, 8, 10))
OCTATONIC_HW       = Scale("octatonic_hw",       (0, 1, 3, 4, 6, 7, 9, 10))
OCTATONIC_WH       = Scale("octatonic_wh",       (0, 2, 3, 5, 6, 8, 9, 11))

# -- Blues -----------------------------------------------------------------

BLUES              = Scale("blues",              (0, 3, 5, 6, 7, 10))

# -- Non-Western / exotic --------------------------------------------------

HIRAJOSHI          = Scale("hirajoshi",          (0, 2, 3, 7, 8))
IN_SEN             = Scale("in_sen",             (0, 1, 5, 7, 10))
PELOG              = Scale("pelog",              (0, 1, 3, 7, 8))
BHAIRAV            = Scale("bhairav",            (0, 1, 4, 5, 7, 8, 11))
HUNGARIAN_MINOR    = Scale("hungarian_minor",    (0, 2, 3, 6, 7, 8, 11))
PROMETHEUS         = Scale("prometheus",         (0, 2, 4, 6, 9, 10))

# -- Lookup tables ---------------------------------------------------------

SCALES: dict[str, Scale] = {
    "chromatic": CHROMATIC,
    "ionian": IONIAN,
    "major": MAJOR,
    "dorian": DORIAN,
    "phrygian": PHRYGIAN,
    "lydian": LYDIAN,
    "mixolydian": MIXOLYDIAN,
    "aeolian": AEOLIAN,
    "minor": MINOR,
    "locrian": LOCRIAN,
    "harmonic_minor": HARMONIC_MINOR,
    "melodic_minor": MELODIC_MINOR,
    "major_pentatonic": MAJOR_PENTATONIC,
    "minor_pentatonic": MINOR_PENTATONIC,
    "whole_tone": WHOLE_TONE,
    "octatonic_hw": OCTATONIC_HW,
    "octatonic_wh": OCTATONIC_WH,
    "blues": BLUES,
    "hirajoshi": HIRAJOSHI,
    "in_sen": IN_SEN,
    "pelog": PELOG,
    "bhairav": BHAIRAV,
    "hungarian_minor": HUNGARIAN_MINOR,
    "prometheus": PROMETHEUS,
}


def scale_by_name(name: str) -> Scale:
    key = name.lower().replace(" ", "_").replace("-", "_")
    result = SCALES.get(key)
    if result is None:
        raise ValueError(f"unknown scale: {name!r}")
    return result


# ---------------------------------------------------------------------------
# Chord construction and voicing
# ---------------------------------------------------------------------------

ChordRoot = int | str
VoicingStyle = Literal[
    "close",
    "open",
    "drop2",
    "drop3",
    "rootless",
    "guide_tone",
]


def _unique_intervals(intervals: Sequence[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    result: list[int] = []
    for interval in intervals:
        pc = interval % 12
        if pc not in seen:
            seen.add(pc)
            result.append(interval)
    return tuple(result)


CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    # Triads
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "diminished": (0, 3, 6),
    "augmented": (0, 4, 8),
    # Suspended and added-tone chords
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "add9": (0, 4, 7, 14),
    "madd9": (0, 3, 7, 14),
    "add11": (0, 4, 7, 17),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "69": (0, 4, 7, 9, 14),
    "m69": (0, 3, 7, 9, 14),
    # Seventh chords
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "mmaj7": (0, 3, 7, 11),
    "dim7": (0, 3, 6, 9),
    "m7b5": (0, 3, 6, 10),
    "aug7": (0, 4, 8, 10),
    "augmaj7": (0, 4, 8, 11),
    "7sus4": (0, 5, 7, 10),
    # Extensions
    "9": (0, 4, 7, 10, 14),
    "maj9": (0, 4, 7, 11, 14),
    "m9": (0, 3, 7, 10, 14),
    "11": (0, 4, 7, 10, 14, 17),
    "maj11": (0, 4, 7, 11, 14, 17),
    "m11": (0, 3, 7, 10, 14, 17),
    "9sus4": (0, 5, 7, 10, 14),
    "13": (0, 4, 7, 10, 14, 17, 21),
    "maj13": (0, 4, 7, 11, 14, 17, 21),
    "m13": (0, 3, 7, 10, 14, 17, 21),
    # Altered dominants
    "7b5": (0, 4, 6, 10),
    "7#5": (0, 4, 8, 10),
    "7b9": (0, 4, 7, 10, 13),
    "7#9": (0, 4, 7, 10, 15),
    "7#11": (0, 4, 7, 10, 18),
    "7b13": (0, 4, 7, 10, 20),
    "7b9b13": (0, 4, 7, 10, 13, 20),
    "7#9#5": (0, 4, 8, 10, 15),
    "13b9": (0, 4, 7, 10, 13, 17, 21),
    "7alt": (0, 4, 10, 13, 15, 18, 20),
}

_CHORD_QUALITY_ALIASES: dict[str, str] = {
    "": "major",
    "maj": "major",
    "major": "major",
    "m": "minor",
    "min": "minor",
    "minor": "minor",
    "dim": "diminished",
    "diminished": "diminished",
    "o": "diminished",
    "°": "diminished",
    "aug": "augmented",
    "augmented": "augmented",
    "+": "augmented",
    "dom7": "7",
    "dominant7": "7",
    "major7": "maj7",
    "ma7": "maj7",
    "major9": "maj9",
    "major11": "maj11",
    "major13": "maj13",
    "min7": "m7",
    "minor7": "m7",
    "min9": "m9",
    "minor9": "m9",
    "min11": "m11",
    "minor11": "m11",
    "min13": "m13",
    "minor13": "m13",
    "minmaj7": "mmaj7",
    "minorMajor7": "mmaj7",
    "minormajor7": "mmaj7",
    "mm7": "mmaj7",
    "mM7": "mmaj7",
    "halfdim7": "m7b5",
    "halfdiminished7": "m7b5",
    "ø": "m7b5",
    "ø7": "m7b5",
    "o7": "dim7",
    "°7": "dim7",
    "sus": "sus4",
    "6/9": "69",
    "m6/9": "m69",
    "min6": "m6",
    "minor6": "m6",
    "min69": "m69",
    "minor69": "m69",
    "minoradd9": "madd9",
    "minadd9": "madd9",
}
for _quality in CHORD_INTERVALS:
    _CHORD_QUALITY_ALIASES.setdefault(_quality, _quality)


@dataclass(frozen=True)
class Chord:
    """A chord defined as semitone intervals from a pitch-class root."""

    root: int
    quality: str
    intervals: tuple[int, ...]

    @property
    def pitch_classes(self) -> frozenset[int]:
        return frozenset((self.root + interval) % 12 for interval in self.intervals)

    def to_midi_notes(self, root_midi: int | None = None) -> list[int]:
        if root_midi is None:
            root_midi = 60 + self.root
        if root_midi % 12 != self.root:
            raise ValueError(
                f"root_midi {root_midi} is not pitch class {self.root}"
            )
        return [root_midi + interval for interval in self.intervals]


@dataclass(frozen=True, init=False)
class VoicingConfig:
    """Register and spacing constraints for generated chord voicings."""

    min_midi: int
    max_midi: int
    min_spacing: int
    max_spacing: int
    max_voicings: int

    def __init__(
        self,
        min_midi: int = 48,
        max_midi: int = 84,
        *,
        low: int | None = None,
        high: int | None = None,
        min_spacing: int = 0,
        max_spacing: int = 19,
        max_voicings: int = 64,
    ) -> None:
        if low is not None:
            min_midi = low
        if high is not None:
            max_midi = high
        if min_midi > max_midi:
            raise ValueError("min_midi must be <= max_midi")
        if min_spacing < 0:
            raise ValueError("min_spacing must be non-negative")
        if max_spacing < min_spacing:
            raise ValueError("max_spacing must be >= min_spacing")
        if max_voicings < 1:
            raise ValueError("max_voicings must be positive")

        object.__setattr__(self, "min_midi", min_midi)
        object.__setattr__(self, "max_midi", max_midi)
        object.__setattr__(self, "min_spacing", min_spacing)
        object.__setattr__(self, "max_spacing", max_spacing)
        object.__setattr__(self, "max_voicings", max_voicings)

    @property
    def low(self) -> int:
        return self.min_midi

    @property
    def high(self) -> int:
        return self.max_midi


def _normalize_note_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValueError("note name must be non-empty")
    return stripped[0].upper() + stripped[1:]


def _root_to_pitch_class(root: ChordRoot) -> int:
    if isinstance(root, int):
        return root % 12
    return note_name_to_pitch_class(_normalize_note_name(root))


def _normalize_quality_key(quality: str) -> str:
    raw = quality.strip()
    if raw.startswith("-"):
        return "m" + raw[1:].replace(" ", "").replace("_", "").replace("-", "").lower()
    if raw in {"M", "M7", "M9", "M11", "M13"}:
        return "maj" + raw[1:]

    key = raw.replace(" ", "").replace("_", "").replace("-", "")
    key = key.replace("Δ", "maj").replace("∆", "maj")
    return key.lower()


def _resolve_chord_quality(quality: str) -> tuple[str, tuple[int, ...]]:
    key = _normalize_quality_key(quality)
    canonical = _CHORD_QUALITY_ALIASES.get(key)
    if canonical is None:
        raise ValueError(f"unknown chord quality: {quality!r}")
    return canonical, CHORD_INTERVALS[canonical]


def chord_by_name(root: ChordRoot, quality: str = "major") -> Chord:
    """Build a chord from a root note/pitch class and quality name."""

    canonical, intervals = _resolve_chord_quality(quality)
    return Chord(
        root=_root_to_pitch_class(root),
        quality=canonical,
        intervals=_unique_intervals(intervals),
    )


_CHORD_SYMBOL_RE = re.compile(r"^\s*([A-Ga-g](?:#|b)?)(.*)\s*$")


def chord_from_symbol(symbol: str) -> Chord:
    """Parse compact chord symbols such as Cmaj7, F#7b9, or Bb13."""

    match = _CHORD_SYMBOL_RE.match(symbol)
    if match is None:
        raise ValueError(f"invalid chord symbol: {symbol!r}")

    root, quality = match.groups()
    quality = quality.strip()
    if "/" in quality:
        left, right = quality.rsplit("/", 1)
        if right and right[0].upper() in {"A", "B", "C", "D", "E", "F", "G"}:
            quality = left
    return chord_by_name(root, quality or "major")


def chord_pitch_classes(root: ChordRoot, quality: str = "major") -> frozenset[int]:
    return chord_by_name(root, quality).pitch_classes


def _normalize_voicing_style(style: str) -> str:
    key = style.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "drop_2": "drop2",
        "drop_3": "drop3",
        "guide": "guide_tone",
        "guide_tones": "guide_tone",
        "guidetone": "guide_tone",
        "root_less": "rootless",
    }
    normalized = aliases.get(key, key)
    valid = {"close", "open", "drop2", "drop3", "rootless", "guide_tone"}
    if normalized not in valid:
        raise ValueError(f"unknown voicing style: {style!r}")
    return normalized


def _intervals_for_voicing(chord: Chord, style: str) -> tuple[int, ...]:
    intervals = _unique_intervals(chord.intervals)
    if style == "guide_tone":
        thirds = [interval for interval in intervals if interval % 12 in {3, 4}]
        sevenths = [interval for interval in intervals if interval % 12 in {10, 11}]
        guide_tones = thirds[:1] + sevenths[:1]
        return tuple(guide_tones or intervals[:2])

    if style == "rootless":
        rootless = [interval for interval in intervals if interval % 12 != 0]
        if len(rootless) > 4:
            without_optional = [
                interval for interval in rootless if interval % 12 not in {5, 7}
            ]
            if len(without_optional) >= 2:
                rootless = without_optional
        return tuple(rootless[:4] or intervals)

    return intervals


def _notes_for_pitch_class(pc: int, config: VoicingConfig) -> tuple[int, ...]:
    return tuple(
        note
        for note in range(config.min_midi, config.max_midi + 1)
        if note % 12 == pc
    )


def _spacing_ok(voicing: tuple[int, ...], config: VoicingConfig) -> bool:
    return all(
        config.min_spacing <= higher - lower <= config.max_spacing
        for lower, higher in zip(voicing, voicing[1:])
    )


def _is_close_voicing(
    voicing: tuple[int, ...],
    target_pcs: frozenset[int],
    config: VoicingConfig,
) -> bool:
    chord_tones = [
        note
        for note in range(config.min_midi, config.max_midi + 1)
        if note % 12 in target_pcs
    ]
    indexes = {note: index for index, note in enumerate(chord_tones)}
    if any(note not in indexes for note in voicing):
        return False
    selected = [indexes[note] for note in voicing]
    return selected == list(range(selected[0], selected[0] + len(selected)))


def _sort_voicings(voicings: set[tuple[int, ...]]) -> list[tuple[int, ...]]:
    return sorted(voicings, key=lambda notes: (notes[-1] - notes[0], notes))


def _candidate_voicings(
    chord: Chord,
    intervals: tuple[int, ...],
    config: VoicingConfig,
    style: str,
) -> list[tuple[int, ...]]:
    target_pcs = frozenset((chord.root + interval) % 12 for interval in intervals)
    pitch_classes = tuple((chord.root + interval) % 12 for interval in intervals)
    note_options = [_notes_for_pitch_class(pc, config) for pc in pitch_classes]
    if not note_options or any(not options for options in note_options):
        return []

    voicings: set[tuple[int, ...]] = set()
    for notes in product(*note_options):
        voicing = tuple(sorted(notes))
        if pitch_class_set(voicing) != target_pcs:
            continue
        if not _spacing_ok(voicing, config):
            continue

        is_close = _is_close_voicing(voicing, target_pcs, config)
        if style == "close" and not is_close:
            continue
        if style == "open" and is_close:
            continue
        voicings.add(voicing)

    return _sort_voicings(voicings)[: config.max_voicings]


def _drop_voicings(
    chord: Chord,
    intervals: tuple[int, ...],
    config: VoicingConfig,
    drop_from_top: int,
) -> list[tuple[int, ...]]:
    if len(intervals) < drop_from_top:
        return []

    target_pcs = frozenset((chord.root + interval) % 12 for interval in intervals)
    close_voicings = _candidate_voicings(chord, intervals, config, "close")
    voicings: set[tuple[int, ...]] = set()
    for close_voicing in close_voicings:
        notes = list(close_voicing)
        notes[len(notes) - drop_from_top] -= 12
        voicing = tuple(sorted(notes))
        if voicing[0] < config.min_midi or voicing[-1] > config.max_midi:
            continue
        if pitch_class_set(voicing) != target_pcs:
            continue
        if not _spacing_ok(voicing, config):
            continue
        voicings.add(voicing)

    return _sort_voicings(voicings)[: config.max_voicings]


def _coerce_chord(chord: Chord | str) -> Chord:
    if isinstance(chord, Chord):
        return chord
    return chord_from_symbol(chord)


def generate_voicings(
    chord: Chord | str,
    *,
    style: VoicingStyle | str = "close",
    config: VoicingConfig | None = None,
) -> list[tuple[int, ...]]:
    """Generate unique voicings that satisfy register and spacing limits."""

    resolved_chord = _coerce_chord(chord)
    resolved_config = config or VoicingConfig()
    resolved_style = _normalize_voicing_style(style)
    intervals = _intervals_for_voicing(resolved_chord, resolved_style)

    if resolved_style == "drop2":
        return _drop_voicings(resolved_chord, intervals, resolved_config, 2)
    if resolved_style == "drop3":
        return _drop_voicings(resolved_chord, intervals, resolved_config, 3)
    if resolved_style in {"rootless", "guide_tone"}:
        resolved_style = "close"

    return _candidate_voicings(
        resolved_chord,
        intervals,
        resolved_config,
        resolved_style,
    )


def _average_pitch(voicing: Sequence[int]) -> float:
    return sum(voicing) / len(voicing)


def _voice_leading_cost(voicing: tuple[int, ...], previous: Sequence[int]) -> float:
    ordered_previous = tuple(sorted(previous))
    shared_count = min(len(voicing), len(ordered_previous))
    motion = sum(
        abs(voicing[index] - ordered_previous[index])
        for index in range(shared_count)
    )
    length_penalty = 12 * abs(len(voicing) - len(ordered_previous))
    center_shift = abs(_average_pitch(voicing) - _average_pitch(ordered_previous))
    return motion + length_penalty + (center_shift / 100.0)


def choose_voicing(
    chord: Chord | str,
    *,
    previous: Sequence[int] | None = None,
    style: VoicingStyle | str = "close",
    config: VoicingConfig | None = None,
) -> tuple[int, ...]:
    """Choose one voicing, preferring smooth motion from previous notes."""

    resolved_config = config or VoicingConfig()
    voicings = generate_voicings(chord, style=style, config=resolved_config)
    if not voicings:
        raise ValueError("no voicing fits the configured register and spacing")

    if previous:
        return min(
            voicings,
            key=lambda notes: (
                _voice_leading_cost(notes, previous),
                notes[-1] - notes[0],
                notes,
            ),
        )

    register_center = (resolved_config.min_midi + resolved_config.max_midi) / 2.0
    return min(
        voicings,
        key=lambda notes: (
            abs(_average_pitch(notes) - register_center),
            notes[-1] - notes[0],
            notes,
        ),
    )


voice_chord = choose_voicing


# ---------------------------------------------------------------------------
# Microtonal / ratio helpers
# ---------------------------------------------------------------------------


def ratio_to_cents(ratio: float) -> float:
    if ratio <= 0:
        raise ValueError(f"ratio must be positive, got {ratio}")
    return 1200.0 * math.log2(ratio)


def cents_to_ratio(cents: float) -> float:
    return 2.0 ** (cents / 1200.0)


def just_interval_freq(base_freq: float, numerator: int, denominator: int) -> float:
    if denominator == 0:
        raise ValueError("denominator must be non-zero")
    return base_freq * numerator / denominator


JUST_RATIOS: dict[str, tuple[int, int]] = {
    "unison":        (1, 1),
    "minor_second":  (16, 15),
    "major_second":  (9, 8),
    "minor_third":   (6, 5),
    "major_third":   (5, 4),
    "perfect_fourth": (4, 3),
    "tritone":       (45, 32),
    "perfect_fifth": (3, 2),
    "minor_sixth":   (8, 5),
    "major_sixth":   (5, 3),
    "minor_seventh": (9, 5),
    "major_seventh": (15, 8),
    "octave":        (2, 1),
}


def pitch_class_set(notes: Sequence[int]) -> frozenset[int]:
    return frozenset(n % 12 for n in notes)


# ---------------------------------------------------------------------------
# Post-tonal and Spectral Helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PitchClassSet:
    """A set of pitch classes."""
    pitch_classes: frozenset[int]
    
    @classmethod
    def from_prime_form(cls, form: Sequence[int]) -> "PitchClassSet":
        return cls(frozenset(p % 12 for p in form))

def spectral_partials(fundamental_hz: float, count: int, stretch: float = 1.0) -> list[float]:
    """Generate harmonic or inharmonic partials from a fundamental."""
    partials = []
    for i in range(1, count + 1):
        freq = fundamental_hz * i * (stretch ** (i - 1))
        partials.append(freq)
    return partials

def quarter_tone_to_freq(midi_note_qt: float, a4: float = A4_HZ) -> float:
    """Convert a potentially fractional MIDI note (e.g. 60.5) to frequency."""
    return a4 * (2.0 ** ((midi_note_qt - A4_MIDI) / 12.0))

def just_intonation_chord(base_freq: float, ratios: Sequence[tuple[int, int]]) -> list[float]:
    """Generate a chord using just intonation ratios."""
    return [just_interval_freq(base_freq, num, den) for num, den in ratios]
