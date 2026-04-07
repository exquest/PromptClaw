"""Generative Scores -- musical score generation from narrative events and mood.

Bridges the narrative engine (B&P stories, arc tracking) and sensor fusion
(mood, presence, weather) to the music composer. Generates sequences of notes
as Score objects that the composer converts to frequencies and plays.

Stdlib only -- no numpy.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Scale / frequency constants
# ---------------------------------------------------------------------------

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_MAJOR_SCALE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]

# A4 = 440 Hz reference
_A4_HZ = 440.0

# Major keys: root name -> root frequency in octave 4
_KEY_ROOTS: dict[str, float] = {}
for _i, _name in enumerate(_NOTE_NAMES):
    # MIDI note number for this note in octave 4: C4=60, A4=69
    _midi = 60 + _i
    _KEY_ROOTS[_name] = _A4_HZ * (2.0 ** ((_midi - 69) / 12.0))

# Minor keys: use relative minor convention (e.g. "Am" -> A minor)
_MINOR_SCALE_SEMITONES = [0, 2, 3, 5, 7, 8, 10]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _scale_degree_to_freq(key: str, degree: int, octave_shift: int = 0) -> float:
    """Convert a 1-based scale degree in a given key to frequency in Hz.

    Degree 1 = root in octave 4, degree 8 = root one octave up.
    Supports degrees 1-8 for a single octave span.
    """
    is_minor = key.endswith("m")
    root_name = key.rstrip("m")
    if root_name not in _KEY_ROOTS:
        root_name = "C"

    root_freq = _KEY_ROOTS[root_name]
    semitones = _MINOR_SCALE_SEMITONES if is_minor else _MAJOR_SCALE_SEMITONES

    # Degree 1-7 maps to scale intervals, degree 8 = octave
    deg_zero = degree - 1  # 0-based
    octave_offset = deg_zero // 7
    scale_idx = deg_zero % 7

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


@dataclass
class Score:
    """A complete musical score: multiple phrases with global parameters."""
    phrases: list[Phrase]
    key: str                # e.g. "C", "Am"
    tempo_bpm: float
    mood: str               # descriptive mood string
    created_at: float       # unix timestamp


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


# ---------------------------------------------------------------------------
# Melody generation
# ---------------------------------------------------------------------------


def generate_melody(
    key: str,
    length: int = 8,
    contour: str = "arch",
) -> Phrase:
    """Create a melody phrase using scale degrees 1-8.

    Contours: "arch" (up then down), "descent" (falling),
    "ascent" (rising), "wave" (sine-like).

    Notes are consonant: stepwise motion with occasional leaps to chord tones.
    """
    contour_fn = _CONTOUR_FNS.get(contour, _contour_arch)
    targets = contour_fn(length)

    chord_tones = {1, 3, 5, 8}
    notes: list[Note] = []
    current_deg = int(round(_clamp(targets[0], 1.0, 8.0)))

    for i in range(length):
        target = targets[i]
        # Move toward target: stepwise (1-2), occasionally leap to chord tone
        diff = target - current_deg
        if abs(diff) <= 2:
            # Step toward target
            step = int(round(diff))
        elif random.random() < 0.3 and abs(diff) > 2:
            # Leap to nearest chord tone in the direction of target
            direction = 1 if diff > 0 else -1
            candidates = sorted(chord_tones, key=lambda d: abs(d - target))
            step = candidates[0] - current_deg
        else:
            # Stepwise: move 1-2 in the right direction
            direction = 1 if diff > 0 else -1
            step = direction * random.choice([1, 1, 2])

        current_deg = int(_clamp(current_deg + step, 1, 8))

        # Duration: slightly varied around 1 beat
        duration = random.choice([0.5, 0.75, 1.0, 1.0, 1.0, 1.5])

        # Accent on chord tones, first note, and downbeats
        accent = current_deg in chord_tones and random.random() < 0.3
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
) -> Phrase:
    """Create a bass line following a chord progression.

    Root on beat 1, fifth/third on weak beats.
    progression is a list of root scale degrees (e.g. [1, 4, 5, 1]).
    """
    notes: list[Note] = []

    for root_deg in progression:
        third_deg = root_deg + 2
        fifth_deg = root_deg + 4

        for beat in range(beats_per_chord):
            if beat == 0:
                # Root on beat 1
                notes.append(Note(
                    scale_degree=root_deg,
                    duration_beats=1.0,
                    accent=True,
                ))
            else:
                # Weak beats: alternate fifth and third
                deg = fifth_deg if beat % 2 == 1 else third_deg
                notes.append(Note(
                    scale_degree=deg,
                    duration_beats=0.75,
                    accent=False,
                ))

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


def score_from_mood(mood: dict) -> Score:
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

    # Tempo: 50 (sleepy) to 140 (energetic)
    activity = (energy + arousal) / 2.0
    tempo = 50.0 + activity * 90.0

    # Key selection
    if valence >= 0.5:
        key = random.choice(_MAJOR_KEYS)
    else:
        key = random.choice(_MINOR_KEYS)

    # Sleeping: minimal score
    is_sleeping = energy < 0.25 and arousal < 0.25

    if is_sleeping:
        melody = generate_melody(key, length=4, contour="descent")
        melody = Phrase(
            notes=[Note(n.scale_degree, n.duration_beats * 2.0, False) for n in melody.notes],
            voice="pad",
            dynamic="pp",
            role="melody",
        )
        mood_str = "sleeping"
        return Score(
            phrases=[melody],
            key=key,
            tempo_bpm=round(tempo, 1),
            mood=mood_str,
            created_at=time.time(),
        )

    # Determine contour from valence/energy
    if valence >= 0.6:
        contour = "arch"
    elif energy < 0.35:
        contour = "descent"
    elif energy >= 0.7:
        contour = "ascent"
    else:
        contour = random.choice(["arch", "wave"])

    # Number of phrases: 1-4 based on energy
    num_phrases = max(1, int(1 + energy * 3))

    # Note length factor: high energy -> shorter, low energy -> longer
    dur_factor = 1.5 - energy

    # Dynamic from energy
    if energy >= 0.7:
        dynamic = "f"
    elif energy >= 0.4:
        dynamic = "mf"
    elif energy >= 0.2:
        dynamic = "mp"
    else:
        dynamic = "p"

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

    # Melody phrase
    mel_length = max(4, int(8 * (0.5 + energy * 0.5)))
    melody = generate_melody(key, length=mel_length, contour=contour)
    melody = Phrase(
        notes=[Note(n.scale_degree, round(n.duration_beats * dur_factor, 2), n.accent) for n in melody.notes],
        voice=melody.voice,
        dynamic=dynamic,
        role="melody",
    )
    phrases.append(melody)

    # Bass line (if more than 1 phrase)
    if num_phrases >= 2:
        prog = random.choice([[1, 4, 5, 1], [1, 6, 4, 5], [1, 4, 1, 5], [1, 3, 4, 5]])
        bass = generate_bass_line(key, prog, beats_per_chord=3)
        bass = Phrase(
            notes=[Note(n.scale_degree, round(n.duration_beats * dur_factor, 2), n.accent) for n in bass.notes],
            voice=bass.voice,
            dynamic=dynamic,
            role="bass",
        )
        phrases.append(bass)

    # Counter melody (if 3+ phrases)
    if num_phrases >= 3:
        counter = generate_countermelody(melody)
        counter = Phrase(
            notes=[Note(n.scale_degree, round(n.duration_beats * dur_factor, 2), n.accent) for n in counter.notes],
            voice=counter.voice,
            dynamic=counter.dynamic,
            role="counter",
        )
        phrases.append(counter)

    # Color phrase (if 4 phrases)
    if num_phrases >= 4:
        color_notes = [
            Note(random.choice([1, 3, 5]), round(random.uniform(1.5, 3.0) * dur_factor, 2), False)
            for _ in range(4)
        ]
        phrases.append(Phrase(
            notes=color_notes,
            voice="pad",
            dynamic="p",
            role="color",
        ))

    return Score(
        phrases=phrases,
        key=key,
        tempo_bpm=round(tempo, 1),
        mood=mood_str,
        created_at=time.time(),
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

    result: list[list[tuple[float, float]]] = []

    for phrase in score.phrases:
        # Octave shift: bass goes down, color goes up
        if phrase.role == "bass":
            octave_shift = -1
        elif phrase.role == "color":
            octave_shift = 1
        else:
            octave_shift = 0

        phrase_freqs: list[tuple[float, float]] = []
        for note in phrase.notes:
            freq = _scale_degree_to_freq(score.key, note.scale_degree, octave_shift)
            dur_sec = note.duration_beats * beat_duration
            phrase_freqs.append((round(freq, 2), round(dur_sec, 4)))

        result.append(phrase_freqs)

    return result
