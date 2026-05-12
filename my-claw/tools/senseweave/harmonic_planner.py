"""Harmonic planning for CypherClaw's tracker and keyboard grimoire.

This module is the canonical home for:

- parsing and normalizing key specs, including modal spellings
- mapping key specs to scale semitone collections
- deriving keyboard "grimoire" harmony hints from live MIDI state
- choosing bounded per-song harmony plans and scene-level modulation
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .pedals_to_key import key_shift_from_pedal_pattern, pedal_to_harmonic_shift
from .reharmonizer import reharm_plan_for_song

_NOTE_ORDER = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "Bb", "B")
_ROOT_TO_INDEX = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "F": 5,
    "E#": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}

_MODE_SEMITONES = {
    "ionian": [0, 2, 4, 5, 7, 9, 11],
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "major_pentatonic": [0, 2, 4, 7, 9],
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "hirajoshi": [0, 2, 3, 7, 8],
}

_MODE_ALIASES = {
    "major": "ionian",
    "ionian": "ionian",
    "minor": "aeolian",
    "aeolian": "aeolian",
    "dorian": "dorian",
    "mixolydian": "mixolydian",
    "lydian": "lydian",
    "phrygian": "phrygian",
    "harmonic minor": "harmonic_minor",
    "harmonic_minor": "harmonic_minor",
    "melodic minor": "melodic_minor",
    "melodic_minor": "melodic_minor",
    "major pentatonic": "major_pentatonic",
    "major_pentatonic": "major_pentatonic",
    "minor pentatonic": "minor_pentatonic",
    "minor_pentatonic": "minor_pentatonic",
    "hirajoshi": "hirajoshi",
}

_MINORISH_MODES = {
    "aeolian",
    "dorian",
    "phrygian",
    "harmonic_minor",
    "melodic_minor",
    "minor_pentatonic",
    "hirajoshi",
}
_BRIGHT_MODES = {"ionian", "lydian", "mixolydian", "major_pentatonic"}

_FAMILY_MODE_CYCLES = {
    "default": ("ionian", "aeolian", "dorian", "mixolydian"),
    "nocturne": ("aeolian", "dorian", "harmonic_minor", "hirajoshi"),
    "ember": ("dorian", "ionian", "mixolydian", "major_pentatonic"),
    "drift": ("dorian", "aeolian", "mixolydian", "major_pentatonic"),
    "bloom": ("ionian", "lydian", "mixolydian", "major_pentatonic"),
    "pulse": ("mixolydian", "ionian", "lydian", "dorian"),
    "forge": ("harmonic_minor", "dorian", "phrygian", "minor_pentatonic"),
}

_STATE_TIME_KEYS = ("last_activity", "last_update", "timestamp", "updated")
_KEYBOARD_MAX_AGE_S = 15.0
_GARDEN_MAX_AGE_S = 180.0
_INNER_MAX_AGE_S = 180.0
_SCENE_ORDER = (
    "Emergence",
    "Theme",
    "Development",
    "Bridge",
    "Recap",
    "Release",
    "Resolution",
    "Afterglow",
)
_CADENCE_TARGET_ROOT = {
    "authentic": 1,
    "plagal": 1,
    "suspended": 1,
    "half": 5,
    "deceptive": 6,
}


@dataclass(frozen=True)
class HarmonicPlan:
    """The resolved harmonic center and its scene-level modulation path."""

    key: str
    root: str
    mode: str
    source: str
    chord_palette: str
    voicing_profile: str
    modulation_intent: str
    scene_keys: dict[str, str]
    section_functions: dict[str, str]
    section_cadences: dict[str, str]
    section_progressions: dict[str, tuple[int, ...]]
    section_chord_degrees: dict[str, tuple[tuple[int, ...], ...]]
    modulation_path: tuple[str, ...]
    reharm_strategy: str
    next_key: str
    section_harmonic_functions: dict[str, str]
    section_transition_intents: dict[str, str]
    strategy: str = "diatonic"


def _normalize_root(root: str | None) -> str | None:
    if not root:
        return None
    normalized = root.strip()
    if not normalized:
        return None
    normalized = normalized[0].upper() + normalized[1:]
    if normalized not in _ROOT_TO_INDEX:
        return None
    return _NOTE_ORDER[_ROOT_TO_INDEX[normalized]]


def _root_from_index(index: int) -> str:
    return _NOTE_ORDER[index % 12]


def normalize_key_spec(value: str | None) -> str | None:
    """Canonicalize major/minor/modal key spellings."""

    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None

    if raw.endswith("m") and len(raw) <= 3:
        root = _normalize_root(raw[:-1])
        return f"{root}m" if root is not None else None

    root = _normalize_root(raw)
    if root is not None:
        return root

    pieces = raw.replace(":", " ").replace("-", " ").split()
    if len(pieces) < 2:
        return None
    root = _normalize_root(pieces[0])
    if root is None:
        return None
    mode_name = _MODE_ALIASES.get(" ".join(pieces[1:]).lower())
    if mode_name is None:
        return None
    if mode_name == "ionian":
        return root
    if mode_name == "aeolian":
        return f"{root}m"
    return f"{root}:{mode_name}"


def key_root(key_spec: str) -> str:
    normalized = normalize_key_spec(key_spec) or "C"
    if normalized.endswith("m") and ":" not in normalized:
        return normalized[:-1]
    if ":" in normalized:
        return normalized.split(":", 1)[0]
    return normalized


def key_mode(key_spec: str) -> str:
    normalized = normalize_key_spec(key_spec) or "C"
    if normalized.endswith("m") and ":" not in normalized:
        return "aeolian"
    if ":" in normalized:
        return normalized.split(":", 1)[1]
    return "ionian"


def is_minorish_key(key_spec: str) -> bool:
    return key_mode(key_spec) in _MINORISH_MODES


def scale_semitones_for_key(key_spec: str) -> list[int]:
    return list(_MODE_SEMITONES.get(key_mode(key_spec), _MODE_SEMITONES["ionian"]))


def compose_key_spec(root: str, mode: str) -> str:
    canonical_root = _normalize_root(root) or "C"
    canonical_mode = _MODE_ALIASES.get(mode.lower().replace("-", " "), mode)
    if canonical_mode == "ionian":
        return canonical_root
    if canonical_mode == "aeolian":
        return f"{canonical_root}m"
    if canonical_mode not in _MODE_SEMITONES:
        canonical_mode = "ionian"
    return f"{canonical_root}:{canonical_mode}"


def display_key_spec(key_spec: str) -> str:
    root = key_root(key_spec)
    mode = key_mode(key_spec)
    if mode == "ionian":
        return f"{root} major"
    if mode == "aeolian":
        return f"{root} minor"
    return f"{root} {mode.replace('_', ' ')}"


def _state_age_seconds(state: Mapping[str, object], now: float) -> float | None:
    for key in _STATE_TIME_KEYS:
        value = state.get(key)
        if isinstance(value, (int, float)):
            return max(0.0, now - float(value))
    return None


def _is_fresh(state: Mapping[str, object], now: float, *, max_age_s: float) -> bool:
    age = _state_age_seconds(state, now)
    return age is not None and age <= max_age_s


def _notes_from_midi_state(midi_state: Mapping[str, object]) -> list[int]:
    notes_on = midi_state.get("notes_on")
    if isinstance(notes_on, Sequence) and not isinstance(notes_on, (str, bytes)):
        values = [int(note) for note in notes_on if isinstance(note, (int, float))]
        if values:
            return sorted(values)
    return []


def _intervals_from_root(notes: Sequence[int]) -> set[int]:
    root_pitch_class = notes[0] % 12
    return {(note % 12 - root_pitch_class) % 12 for note in notes}


def _infer_mode_from_keyboard(intervals: set[int], *, expression: int, fallback_mode: str) -> str:
    if 3 in intervals and 4 not in intervals:
        if 11 in intervals or expression >= 96:
            return "harmonic_minor"
        if 9 in intervals:
            return "dorian"
        return "aeolian"
    if 4 in intervals and 3 not in intervals:
        if 6 in intervals:
            return "lydian"
        if 10 in intervals:
            return "mixolydian"
        if expression >= 100:
            return "lydian"
        return "ionian"
    if expression >= 110:
        return "harmonic_minor" if fallback_mode in _MINORISH_MODES else "lydian"
    return fallback_mode


def keyboard_grimoire_from_midi_state(
    midi_state: Mapping[str, object],
    *,
    now: float,
    fallback_key: str = "C",
) -> dict[str, object]:
    """Turn current keyboard notes and pedals into a harmonic suggestion."""

    if not midi_state:
        return {}
    if not _is_fresh(midi_state, now, max_age_s=_KEYBOARD_MAX_AGE_S):
        return {}
    if not midi_state.get("playing"):
        return {}

    notes = _notes_from_midi_state(midi_state)
    if not notes:
        return {}

    root = _root_from_index(notes[0] % 12)
    expression_value = midi_state.get("expression", midi_state.get("mod_wheel", 0))
    expression = int(expression_value) if isinstance(expression_value, (int, float)) else 0
    sustain = bool(midi_state.get("sustain_pedal", False))
    intervals = _intervals_from_root(notes)
    fallback_mode = key_mode(fallback_key)
    mode = _infer_mode_from_keyboard(intervals, expression=expression, fallback_mode=fallback_mode)
    harmonic_shift = pedal_to_harmonic_shift(sustain, expression)
    pedal_events = midi_state.get("recent_pedal_events", [])
    if not isinstance(pedal_events, Sequence):
        pedal_events = []
    rapid_pattern = key_shift_from_pedal_pattern(
        [(float(t), bool(v)) for t, v in pedal_events if isinstance(t, (int, float))]
    )

    return {
        "root": root,
        "mode": mode,
        "suggested_key": compose_key_spec(root, mode),
        "chord_palette": "extended" if harmonic_shift["suggest_extensions"] else "open",
        "voicing_profile": "pedal_point" if sustain else "open",
        "modulation_intent": "modulate" if rapid_pattern == "modulate" else "steady",
        "tension": harmonic_shift["tension"],
        "hold_chord": harmonic_shift["hold_chord"],
    }


def _candidate_modes(family: str, mood: Mapping[str, float]) -> tuple[str, ...]:
    cycle = _FAMILY_MODE_CYCLES.get(family, _FAMILY_MODE_CYCLES["default"])
    valence = float(mood.get("valence", 0.5))
    if valence >= 0.58:
        bright = tuple(mode for mode in cycle if mode in _BRIGHT_MODES)
        return bright or cycle
    if valence <= 0.42:
        dark = tuple(mode for mode in cycle if mode in _MINORISH_MODES)
        return dark or cycle
    return cycle


def _related_roots(root: str) -> list[str]:
    idx = _ROOT_TO_INDEX[_normalize_root(root) or "C"]
    return [
        _root_from_index(idx),
        _root_from_index(idx + 7),
        _root_from_index(idx + 5),
        _root_from_index(idx + 2),
        _root_from_index(idx + 9),
    ]


def _scene_key_map(
    key_spec: str,
    *,
    family: str,
    modulation_intent: str,
    song_num: int,
) -> dict[str, str]:
    root = key_root(key_spec)
    mode = key_mode(key_spec)
    related = _related_roots(root)
    cycle = _candidate_modes(family, {"valence": 0.5})
    cycle_index = song_num % max(1, len(cycle))
    development_mode = cycle[(cycle_index + 1) % len(cycle)] if cycle else mode
    recap_mode = cycle[(cycle_index + 2) % len(cycle)] if cycle else mode
    resolution_mode = "aeolian" if mode in _MINORISH_MODES else "ionian"

    if modulation_intent != "modulate":
        development_key = compose_key_spec(related[1], development_mode if family in {"pulse", "bloom", "forge"} else mode)
        recap_key = compose_key_spec(root, recap_mode if family in {"drift", "forge"} else mode)
    else:
        development_key = compose_key_spec(related[1], development_mode)
        recap_key = compose_key_spec(related[2], recap_mode)

    return {
        "Emergence": key_spec,
        "Theme": key_spec,
        "Development": development_key,
        "Recap": recap_key,
        "Resolution": compose_key_spec(root, resolution_mode),
    }


def _wrap_degree(degree: int) -> int:
    return ((degree - 1) % 7) + 1


def _clamp_degree(degree: int) -> int:
    return max(1, min(7, int(degree)))


def _cadence_target_root(cadence: str) -> int | None:
    return _CADENCE_TARGET_ROOT.get(cadence)


def _triad_degrees(root_degree: int) -> tuple[int, int, int]:
    root = _clamp_degree(root_degree)
    return (root, _wrap_degree(root + 2), _wrap_degree(root + 4))


def _section_progression_roots(
    section: object,
    *,
    song_num: int,
    section_index: int,
) -> tuple[int, ...]:
    bank = getattr(section, "progression", ())
    if not isinstance(bank, Sequence) or isinstance(bank, (str, bytes)) or not bank:
        roots: tuple[int, ...] = (1, 4, 5, 1)
    else:
        selected = bank[(song_num + section_index) % len(bank)]
        if not isinstance(selected, Sequence) or isinstance(selected, (str, bytes)):
            roots = (1, 4, 5, 1)
        else:
            roots = tuple(_clamp_degree(int(degree)) for degree in selected)

    cadence_target = _cadence_target_root(str(getattr(section, "cadence", "") or ""))
    if roots and cadence_target is not None:
        return (*roots[:-1], cadence_target)
    return roots


def _section_progression_map(
    sections: Mapping[str, object],
    *,
    song_num: int,
) -> dict[str, tuple[int, ...]]:
    return {
        scene_name: _section_progression_roots(
            section,
            song_num=song_num,
            section_index=index,
        )
        for index, (scene_name, section) in enumerate(sections.items())
    }


def _section_chord_degree_map(
    progressions: Mapping[str, Sequence[int]],
) -> dict[str, tuple[tuple[int, ...], ...]]:
    return {
        scene_name: tuple(_triad_degrees(int(root)) for root in roots)
        for scene_name, roots in progressions.items()
    }


def pivot_degree(from_key: str, to_key: str) -> int | None:
    """Find the lowest diatonic degree in from_key whose pitch class is also diatonic in to_key."""
    from_root_idx = _ROOT_TO_INDEX.get(_normalize_root(key_root(from_key)) or "C", 0)
    to_root_idx = _ROOT_TO_INDEX.get(_normalize_root(key_root(to_key)) or "C", 0)
    from_semitones = scale_semitones_for_key(from_key)
    to_semitones = scale_semitones_for_key(to_key)
    to_pcs = {(s + to_root_idx) % 12 for s in to_semitones}
    for i, s in enumerate(from_semitones):
        if (s + from_root_idx) % 12 in to_pcs:
            return i + 1
    return None


def common_tones(from_key: str, to_key: str) -> frozenset[int]:
    """Return pitch classes shared by two keys' diatonic collections."""
    from_root_idx = _ROOT_TO_INDEX.get(_normalize_root(key_root(from_key)) or "C", 0)
    to_root_idx = _ROOT_TO_INDEX.get(_normalize_root(key_root(to_key)) or "C", 0)
    from_pcs = frozenset((s + from_root_idx) % 12 for s in scale_semitones_for_key(from_key))
    to_pcs = frozenset((s + to_root_idx) % 12 for s in scale_semitones_for_key(to_key))
    return from_pcs & to_pcs


def _modulation_path(scene_keys: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(scene_keys[name] for name in _SCENE_ORDER if name in scene_keys)


def _default_palette(mode: str, family: str) -> str:
    if family in {"forge", "pulse"}:
        return "extended"
    if mode in _MINORISH_MODES:
        return "suspended"
    return "open"


def _default_voicing(mode: str, family: str) -> str:
    if family in {"nocturne", "drift"}:
        return "wide"
    if mode in _MINORISH_MODES:
        return "close"
    return "open"


def _default_progression_profile(family: str, cadence_state: str, mood: Mapping[str, float]) -> str:
    if cadence_state in {"sleep", "wind_down"}:
        return "stillness"
    if cadence_state == "away_practice":
        return "experiment"
    energy = float(mood.get("energy", 0.5) or 0.5)
    if family == "pulse":
        return "procession"
    if family == "forge":
        return "experiment"
    if family in {"drift", "nocturne"}:
        return "settling"
    if energy >= 0.7:
        return "lift"
    return "open_day"


def resolve_harmonic_plan(
    initial_key: str,
    *,
    song_num: int,
    mood: Mapping[str, float],
    family: str,
    cadence_state: str = "",
    progression_profile: str = "",
    garden_state: Mapping[str, object],
    outdoor_state: Mapping[str, object],
    midi_state: Mapping[str, object],
    inner_state: Mapping[str, object],
    now: float,
    intent: str = "",
) -> HarmonicPlan:
    """Resolve the live harmonic center for one tracker song."""

    strategy = "post-tonal" if intent == "avant-garde" else "diatonic"
    seed_key = normalize_key_spec(initial_key) or "C"
    keyboard = keyboard_grimoire_from_midi_state(midi_state, now=now, fallback_key=seed_key)

    source = "carry"
    base_key = seed_key
    chord_palette = ""
    voicing_profile = ""
    modulation_intent = "steady"

    if keyboard:
        base_key = str(keyboard["suggested_key"])
        source = "keyboard"
        chord_palette = str(keyboard["chord_palette"])
        voicing_profile = str(keyboard["voicing_profile"])
        modulation_intent = str(keyboard["modulation_intent"])
    elif _is_fresh(inner_state, now, max_age_s=_INNER_MAX_AGE_S):
        suggested = normalize_key_spec(str(inner_state.get("suggested_key", "")))
        if suggested is not None:
            base_key = suggested
            source = "inner"
    elif _is_fresh(garden_state, now, max_age_s=_GARDEN_MAX_AGE_S):
        suggested = normalize_key_spec(str(garden_state.get("music_key", "")))
        if suggested is not None:
            base_key = suggested
            source = "garden"

    base_root = key_root(base_key)
    base_mode = key_mode(base_key)
    mode = base_mode
    if source != "keyboard":
        explicit_mode = ":" in (normalize_key_spec(base_key) or "") or base_key.endswith("m")
        if not explicit_mode or source == "carry":
            mode_cycle = _candidate_modes(family, mood)
            if mode_cycle:
                mode = mode_cycle[song_num % len(mode_cycle)]
        brightness_value = outdoor_state.get("brightness", 0.5)
        brightness = float(brightness_value) if isinstance(brightness_value, (int, float)) else 0.5
        if brightness > 0.72 and mode in _MINORISH_MODES:
            mode = "lydian" if family in {"bloom", "pulse"} else "ionian"
        elif brightness < 0.18 and mode in _BRIGHT_MODES:
            mode = "dorian" if family in {"drift", "ember"} else "aeolian"

    key_spec = compose_key_spec(base_root, mode)
    chord_palette = chord_palette or _default_palette(mode, family)
    voicing_profile = voicing_profile or _default_voicing(mode, family)
    scene_keys = _scene_key_map(
        key_spec,
        family=family,
        modulation_intent=modulation_intent,
        song_num=song_num,
    )
    next_mode_cycle = _candidate_modes(family, mood)
    next_mode = next_mode_cycle[(song_num + 1) % len(next_mode_cycle)] if next_mode_cycle else mode
    next_root = _related_roots(base_root)[2 if source in {"carry", "garden"} else 0]
    resolved_profile = progression_profile or _default_progression_profile(family, cadence_state, mood)
    reharm = reharm_plan_for_song(
        resolved_profile,
        family=family,
        cadence_state=cadence_state,
        mode=mode,
        song_num=song_num,
    )
    section_progressions = _section_progression_map(reharm.sections, song_num=song_num)
    section_chord_degrees = _section_chord_degree_map(section_progressions)
    next_key = (
        compose_key_spec(next_root, next_mode)
        if source != "keyboard"
        else scene_keys["Resolution"]
    )

    return HarmonicPlan(
        key=key_spec,
        root=key_root(key_spec),
        mode=key_mode(key_spec),
        source=source,
        chord_palette=chord_palette,
        voicing_profile=voicing_profile,
        modulation_intent=modulation_intent,
        scene_keys=scene_keys,
        section_functions={name: section.function for name, section in reharm.sections.items()},
        section_cadences={name: section.cadence for name, section in reharm.sections.items()},
        section_progressions=section_progressions,
        section_chord_degrees=section_chord_degrees,
        modulation_path=_modulation_path(scene_keys),
        reharm_strategy=reharm.strategy,
        next_key=next_key,
        strategy=strategy,
        section_harmonic_functions={
            name: section.harmonic_function for name, section in reharm.sections.items()
        },
        section_transition_intents={
            name: section.transition_intent for name, section in reharm.sections.items()
        },
    )
