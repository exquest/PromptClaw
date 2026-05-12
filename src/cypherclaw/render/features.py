from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib import import_module
from os import PathLike
from typing import Any


ScorePath = str | bytes | PathLike[str] | PathLike[bytes]

FEATURE_METADATA_KEYS: tuple[str, ...] = (
    "harmonic_charge",
    "melodic_charge",
    "metric_weight",
    "is_cadential",
    "contour_apex",
    "contour_apex_index",
)

_KEY_PITCH_CLASSES = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "E#": 5,
    "F": 5,
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

_MODE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "ionian": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
}


@dataclass(frozen=True)
class FeatureNote:
    onset_beat: float
    duration_beat: float
    pitch: int


@dataclass(frozen=True)
class PhraseFeatures:
    harmonic_charge: float
    melodic_charge: float
    metric_weight: float
    is_cadential: bool
    contour_apex: float
    contour_apex_index: int | None


def load_score(path: ScorePath) -> Any:
    """Load a score through partitura without making partitura a render import side effect."""

    try:
        partitura = import_module("partitura")
    except ImportError as exc:
        raise RuntimeError("partitura is required for score feature extraction") from exc
    return partitura.load_score(str(path))


def phrase_features_from_score_path(
    path: ScorePath,
    *,
    phrase_beats: float = 4.0,
    key: str = "C",
) -> tuple[PhraseFeatures, ...]:
    return phrase_features_from_score(load_score(path), phrase_beats=phrase_beats, key=key)


def phrase_features_from_score(
    score: Any,
    *,
    phrase_beats: float = 4.0,
    key: str = "C",
) -> tuple[PhraseFeatures, ...]:
    notes = extract_score_notes(score)
    return compute_phrase_features(notes, phrase_beats=phrase_beats, key=key)


def extract_score_notes(score: Any) -> tuple[FeatureNote, ...]:
    note_array = _score_note_array(score)
    names = getattr(getattr(note_array, "dtype", None), "names", None)
    if not names:
        return ()

    notes: list[FeatureNote] = []
    for row in note_array:
        onset = _row_float(row, names, ("onset_beat", "onset_quarter", "onset_div"))
        duration = _row_float(row, names, ("duration_beat", "duration_quarter", "duration_div"))
        pitch = _row_int(row, names, ("pitch", "midi_pitch"))
        if pitch is None:
            continue
        notes.append(
            FeatureNote(
                onset_beat=onset,
                duration_beat=max(0.0, duration),
                pitch=pitch,
            )
        )
    return tuple(sorted(notes, key=lambda note: (note.onset_beat, note.pitch)))


def compute_phrase_features(
    notes: Sequence[FeatureNote],
    *,
    phrase_beats: float = 4.0,
    key: str = "C",
) -> tuple[PhraseFeatures, ...]:
    if phrase_beats <= 0:
        raise ValueError("phrase_beats must be positive")

    phrases: dict[int, list[FeatureNote]] = {}
    for note in notes:
        phrase_index = int(note.onset_beat // phrase_beats)
        phrases.setdefault(phrase_index, []).append(note)
    return tuple(
        compute_features_for_notes(phrases[index], key=key)
        for index in sorted(phrases)
    )


def feature_metadata_for_phrase(
    notes: Sequence[object],
    *,
    key: str = "C",
) -> dict[str, str]:
    features = compute_features_for_notes(_feature_notes_from_phrase(notes, key=key), key=key)
    return features_to_metadata(features)


def features_to_metadata(features: PhraseFeatures) -> dict[str, str]:
    metadata = {
        "harmonic_charge": _format_float(features.harmonic_charge),
        "melodic_charge": _format_float(features.melodic_charge),
        "metric_weight": _format_float(features.metric_weight),
        "is_cadential": str(features.is_cadential).lower(),
        "contour_apex": _format_float(features.contour_apex),
    }
    if features.contour_apex_index is not None:
        metadata["contour_apex_index"] = str(features.contour_apex_index)
    return metadata


def annotate_events_with_phrase_features(
    events: Iterable[object],
    features: Sequence[PhraseFeatures],
) -> list[object]:
    annotated = list(events)
    for event in annotated:
        phrase_index = _event_phrase_index(event)
        if phrase_index is None and len(features) == 1:
            phrase_index = 0
        if phrase_index is None or phrase_index < 0 or phrase_index >= len(features):
            continue
        annotate_event(event, features[phrase_index])
    return annotated


def annotate_event(event: object, features: PhraseFeatures, *, note_index: int | None = None) -> None:
    setattr(event, "harmonic_charge", features.harmonic_charge)
    setattr(event, "melodic_charge", features.melodic_charge)
    setattr(event, "metric_weight", features.metric_weight)
    setattr(event, "is_cadential", features.is_cadential)
    setattr(event, "contour_apex", features.contour_apex)
    setattr(event, "contour_apex_index", features.contour_apex_index)
    if note_index is not None:
        setattr(event, "is_contour_apex", note_index == features.contour_apex_index)

    metadata = getattr(event, "metadata", None)
    if isinstance(metadata, dict):
        metadata.update(features_to_metadata(features))


def compute_features_for_notes(notes: Sequence[FeatureNote], *, key: str = "C") -> PhraseFeatures:
    if not notes:
        return PhraseFeatures(
            harmonic_charge=0.0,
            melodic_charge=0.0,
            metric_weight=0.0,
            is_cadential=False,
            contour_apex=0.0,
            contour_apex_index=None,
        )

    total_duration = sum(max(note.duration_beat, 0.0) for note in notes)
    if total_duration <= 0:
        total_duration = float(len(notes))

    harmonic = sum(
        tonal_pitch_space_distance(note.pitch, key=key) * _note_weight(note)
        for note in notes
    ) / total_duration
    metric = sum(
        metric_weight_for_onset(note.onset_beat) * _note_weight(note)
        for note in notes
    ) / total_duration
    apex_index = _contour_apex_index(notes)
    return PhraseFeatures(
        harmonic_charge=_clamp01(harmonic),
        melodic_charge=_melodic_charge(notes),
        metric_weight=_clamp01(metric),
        is_cadential=_is_cadential(notes, key=key),
        contour_apex=_contour_apex_position(apex_index, len(notes)),
        contour_apex_index=apex_index,
    )


def tonal_pitch_space_distance(pitch: int, *, key: str = "C") -> float:
    """Return a normalized Lerdahl-style basic-space distance from tonic."""

    root, mode = _parse_key(key)
    intervals = _MODE_INTERVALS[mode]
    triad_third = intervals[2]
    relative_pc = (int(pitch) - root) % 12
    levels = (
        (0,),
        (0, 7),
        (0, triad_third, 7),
        intervals,
        tuple(range(12)),
    )
    missing_levels = sum(1 for level in levels[:-1] if relative_pc not in level)
    return missing_levels / max(1, len(levels) - 1)


def metric_weight_for_onset(onset_beat: float) -> float:
    beat = onset_beat % 4.0
    if _near(beat, 0.0) or _near(beat, 4.0):
        return 1.0
    if _near(beat, 2.0):
        return 0.75
    if _near(beat, 1.0) or _near(beat, 3.0):
        return 0.5
    return 0.25


def _score_note_array(score: Any) -> Any:
    if hasattr(score, "note_array"):
        return score.note_array()
    parts = getattr(score, "parts", ())
    if parts:
        return parts[0].note_array()
    raise ValueError("score object does not expose a partitura note_array")


def _feature_notes_from_phrase(notes: Sequence[object], *, key: str) -> tuple[FeatureNote, ...]:
    onset = 0.0
    feature_notes: list[FeatureNote] = []
    for note in notes:
        duration = float(getattr(note, "duration_beats", 1.0) or 0.0)
        degree = int(getattr(note, "scale_degree", 0) or 0)
        if degree > 0:
            feature_notes.append(
                FeatureNote(
                    onset_beat=onset,
                    duration_beat=max(0.0, duration),
                    pitch=_degree_to_midi(degree, key=key),
                )
            )
        onset += max(0.0, duration)
    return tuple(feature_notes)


def _degree_to_midi(degree: int, *, key: str) -> int:
    root, mode = _parse_key(key)
    intervals = _MODE_INTERVALS[mode]
    zero_based = max(0, degree - 1)
    octave = zero_based // len(intervals)
    interval = intervals[zero_based % len(intervals)]
    return 60 + root + interval + (12 * octave)


def _parse_key(key: str) -> tuple[int, str]:
    raw = (key or "C").strip()
    if ":" in raw:
        root_name, mode_name = raw.split(":", 1)
        mode = mode_name.strip().lower() or "major"
    elif raw.endswith("m") and len(raw) > 1:
        root_name = raw[:-1]
        mode = "minor"
    else:
        root_name = raw
        mode = "major"
    root = _KEY_PITCH_CLASSES.get(root_name.strip(), 0)
    return root, mode if mode in _MODE_INTERVALS else "major"


def _row_float(row: Any, names: Sequence[str], candidates: Sequence[str]) -> float:
    for name in candidates:
        if name in names:
            return float(row[name])
    return 0.0


def _row_int(row: Any, names: Sequence[str], candidates: Sequence[str]) -> int | None:
    for name in candidates:
        if name in names:
            return int(row[name])
    return None


def _note_weight(note: FeatureNote) -> float:
    return max(note.duration_beat, 0.0) or 1.0


def _melodic_charge(notes: Sequence[FeatureNote]) -> float:
    if len(notes) < 2:
        return 0.0
    intervals = [
        abs(notes[index].pitch - notes[index - 1].pitch)
        for index in range(1, len(notes))
    ]
    return _clamp01((sum(intervals) / len(intervals)) / 12.0)


def _is_cadential(notes: Sequence[FeatureNote], *, key: str) -> bool:
    if len(notes) < 2:
        return False
    root, _mode = _parse_key(key)
    final_pc = (notes[-1].pitch - root) % 12
    penultimate_pc = (notes[-2].pitch - root) % 12
    if final_pc == 0:
        return penultimate_pc in {2, 5, 7, 11}
    if final_pc == 7:
        return penultimate_pc in {0, 2, 5, 11}
    return False


def _contour_apex_index(notes: Sequence[FeatureNote]) -> int | None:
    if not notes:
        return None
    return max(range(len(notes)), key=lambda index: (notes[index].pitch, -index))


def _contour_apex_position(apex_index: int | None, note_count: int) -> float:
    if apex_index is None:
        return 0.0
    if note_count <= 1:
        return 0.0
    return apex_index / (note_count - 1)


def _event_phrase_index(event: object) -> int | None:
    for source in (event, getattr(event, "phrase", None)):
        if source is None:
            continue
        value = getattr(source, "phrase_index", None)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _format_float(value: float) -> str:
    return f"{_clamp01(value):.3f}"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _near(value: float, target: float) -> bool:
    return abs(value - target) < 1e-6
