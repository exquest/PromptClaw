"""Bridge MIDI vocabulary fragments into score-tree composition.

The MIDI vocabulary store keeps extraction-native data. This module turns that
data into composer-friendly phrase material and deterministic scene citations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, cast

from cypherclaw import midi_vocabulary_store


DEFAULT_CURIOSITY = 0.15
VOCABULARY_METADATA_KEYS: tuple[str, ...] = (
    "vocabulary_fragment_id",
    "vocabulary_fragment_kind",
    "vocabulary_fragment_source",
    "vocabulary_transform",
    "vocabulary_degree_pattern",
    "vocabulary_duration_pattern",
    "vocabulary_source_key",
    "vocabulary_source_tempo",
    "vocabulary_curiosity",
)

_MAJOR_PITCH_CLASS_TO_DEGREE = {
    0: 1,
    2: 2,
    4: 3,
    5: 4,
    7: 5,
    9: 6,
    11: 7,
}


@dataclass(frozen=True)
class VocabularyFragment:
    """Composer-ready material derived from one vocabulary DB row."""

    fragment_id: int
    source_file: str
    kind: str
    degree_pattern: tuple[int, ...]
    duration_pattern: tuple[float, ...]
    source_key: str
    source_tempo: float | None
    harmonic_context: Mapping[str, Any]


@dataclass(frozen=True)
class VocabularyCitation:
    """A deterministic decision to use one fragment in one scene."""

    scene_name: str
    fragment: VocabularyFragment
    curiosity: float
    decision_value: float
    transform: str = "degree_seed"

    @property
    def fragment_id(self) -> int:
        return self.fragment.fragment_id

    def to_scene_metadata(self) -> dict[str, str]:
        metadata = {
            "vocabulary_fragment_id": str(self.fragment.fragment_id),
            "vocabulary_fragment_kind": self.fragment.kind,
            "vocabulary_fragment_source": self.fragment.source_file,
            "vocabulary_transform": self.transform,
            "vocabulary_degree_pattern": json.dumps(list(self.fragment.degree_pattern)),
            "vocabulary_duration_pattern": json.dumps(list(self.fragment.duration_pattern)),
            "vocabulary_source_key": self.fragment.source_key,
            "vocabulary_curiosity": f"{self.curiosity:.3f}",
        }
        if self.fragment.source_tempo is not None:
            metadata["vocabulary_source_tempo"] = f"{self.fragment.source_tempo:.3f}"
        return metadata

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "scene_name": self.scene_name,
            "fragment_id": self.fragment.fragment_id,
            "kind": self.fragment.kind,
            "source_file": self.fragment.source_file,
            "degree_pattern": list(self.fragment.degree_pattern),
            "duration_pattern": list(self.fragment.duration_pattern),
            "source_key": self.fragment.source_key,
            "curiosity": round(self.curiosity, 3),
            "decision_value": round(self.decision_value, 6),
            "transform": self.transform,
        }
        if self.fragment.source_tempo is not None:
            payload["source_tempo"] = self.fragment.source_tempo
        return payload


def load_vocabulary_fragments(
    db_path: Path | str,
    *,
    kinds: Sequence[str] = ("melodic_motif", "rhythm_cell"),
    limit: int = 256,
) -> tuple[VocabularyFragment, ...]:
    """Load vocabulary rows and normalize them for composer use."""

    path = Path(db_path)
    if not path.exists() or limit <= 0:
        return ()

    fragments: list[VocabularyFragment] = []
    try:
        conn = midi_vocabulary_store.connect(path)
    except (OSError, sqlite3.Error):
        return ()
    try:
        for kind in kinds:
            rows = midi_vocabulary_store.query_fragments(conn, kind=kind)
            for row in rows:
                fragment = _fragment_from_row(row)
                if fragment is None:
                    continue
                fragments.append(fragment)
                if len(fragments) >= limit:
                    return tuple(fragments)
    except (OSError, sqlite3.Error, ValueError, TypeError, json.JSONDecodeError):
        return tuple(fragments)
    finally:
        conn.close()
    return tuple(fragments)


def plan_vocabulary_citations(
    scene_names: Sequence[str],
    fragments: Sequence[VocabularyFragment],
    *,
    curiosity: float = DEFAULT_CURIOSITY,
    seed: str = "",
) -> dict[str, VocabularyCitation]:
    """Choose fragment citations at a rate governed by curiosity.

    The decision is deterministic for a scene list, seed, and curiosity so
    tests and re-renders can verify the citation rate without relying on the
    process-global random state.
    """

    bounded_curiosity = _clamp(float(curiosity), 0.0, 1.0)
    if bounded_curiosity <= 0.0 or not scene_names:
        return {}

    melodic_fragments = tuple(fragment for fragment in fragments if fragment.kind == "melodic_motif")
    candidate_fragments = melodic_fragments or tuple(fragments)
    if not candidate_fragments:
        return {}

    citations: dict[str, VocabularyCitation] = {}
    for scene_name in scene_names:
        decision_value = _unit_hash("vocabulary-cite", seed, scene_name)
        if bounded_curiosity < 1.0 and decision_value >= bounded_curiosity:
            continue
        fragment_index = int(
            _unit_hash("vocabulary-fragment", seed, scene_name)
            * len(candidate_fragments)
        )
        fragment_index = min(fragment_index, len(candidate_fragments) - 1)
        citations[str(scene_name)] = VocabularyCitation(
            scene_name=str(scene_name),
            fragment=candidate_fragments[fragment_index],
            curiosity=bounded_curiosity,
            decision_value=decision_value,
        )
    return citations


def scene_vocabulary_log_suffix(metadata: Mapping[str, object]) -> str:
    """Return the composer log suffix for a scene vocabulary citation."""

    fragment_id = str(metadata.get("vocabulary_fragment_id", "") or "").strip()
    if not fragment_id:
        return ""
    kind = str(metadata.get("vocabulary_fragment_kind", "") or "").strip()
    source = str(metadata.get("vocabulary_fragment_source", "") or "").strip()
    parts = [f"vocabulary_fragment_id={fragment_id}"]
    if kind:
        parts.append(f"vocabulary_fragment_kind={kind}")
    if source:
        parts.append(f"vocabulary_fragment_source={source}")
    return " " + " ".join(parts)


def citation_metadata_from_payload(payload: Mapping[str, object]) -> dict[str, str]:
    """Convert an arrangement-plan citation payload back into scene metadata."""

    metadata: dict[str, str] = {}
    fragment_id = payload.get("fragment_id")
    if fragment_id is None:
        return metadata
    metadata["vocabulary_fragment_id"] = str(fragment_id)
    if payload.get("kind"):
        metadata["vocabulary_fragment_kind"] = str(payload["kind"])
    if payload.get("source_file"):
        metadata["vocabulary_fragment_source"] = str(payload["source_file"])
    metadata["vocabulary_transform"] = str(payload.get("transform") or "degree_seed")
    degree_pattern = payload.get("degree_pattern")
    if isinstance(degree_pattern, Sequence) and not isinstance(
        degree_pattern, (str, bytes)
    ):
        metadata["vocabulary_degree_pattern"] = json.dumps(list(degree_pattern))
    duration_pattern = payload.get("duration_pattern")
    if isinstance(duration_pattern, Sequence) and not isinstance(
        duration_pattern, (str, bytes)
    ):
        metadata["vocabulary_duration_pattern"] = json.dumps(list(duration_pattern))
    if payload.get("source_key"):
        metadata["vocabulary_source_key"] = str(payload["source_key"])
    if payload.get("source_tempo") is not None:
        metadata["vocabulary_source_tempo"] = str(payload["source_tempo"])
    curiosity = payload.get("curiosity")
    if curiosity is not None:
        try:
            metadata["vocabulary_curiosity"] = f"{float(cast(Any, curiosity)):.3f}"
        except (TypeError, ValueError):
            metadata["vocabulary_curiosity"] = str(curiosity)
    return metadata


def _fragment_from_row(row: sqlite3.Row) -> VocabularyFragment | None:
    kind = str(row["kind"] or "")
    interval_pattern = _number_list(row["interval_pattern_json"])
    duration_pattern = _duration_pattern(row["duration_pattern_json"])
    harmonic_context = _mapping(row["harmonic_context_json"])

    degree_pattern: tuple[int, ...] = ()
    if kind == "melodic_motif":
        degree_pattern = _degrees_from_pitch_classes(harmonic_context.get("pitch_classes"))
        if not degree_pattern:
            degree_pattern = _degrees_from_intervals(interval_pattern)
    elif kind == "rhythm_cell" and duration_pattern:
        degree_pattern = tuple(1 for _ in duration_pattern)

    if not degree_pattern:
        return None
    if not duration_pattern:
        duration_pattern = tuple(1.0 for _ in degree_pattern)

    source_tempo = row["source_tempo"]
    tempo: float | None
    try:
        tempo = None if source_tempo is None else float(source_tempo)
    except (TypeError, ValueError):
        tempo = None

    return VocabularyFragment(
        fragment_id=int(row["id"]),
        source_file=str(row["source_file"] or ""),
        kind=kind,
        degree_pattern=degree_pattern,
        duration_pattern=duration_pattern,
        source_key=str(row["source_key"] or ""),
        source_tempo=tempo,
        harmonic_context=harmonic_context,
    )


def _number_list(raw: object) -> tuple[float, ...]:
    values = _json_sequence(raw)
    numbers: list[float] = []
    for value in values:
        try:
            numbers.append(float(cast(Any, value)))
        except (TypeError, ValueError):
            continue
    return tuple(numbers)


def _duration_pattern(raw: object) -> tuple[float, ...]:
    return tuple(_clamp(value, 0.25, 8.0) for value in _number_list(raw))


def _mapping(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    data = json.loads(str(raw))
    if not isinstance(data, Mapping):
        return {}
    return {str(key): value for key, value in data.items()}


def _json_sequence(raw: object) -> tuple[object, ...]:
    if raw is None:
        return ()
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return tuple(raw)
    data = json.loads(str(raw))
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        return tuple(data)
    return ()


def _degrees_from_pitch_classes(raw: object) -> tuple[int, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    degrees: list[int] = []
    for value in raw:
        try:
            pitch_class = int(value) % 12
        except (TypeError, ValueError):
            continue
        degree = _MAJOR_PITCH_CLASS_TO_DEGREE.get(pitch_class)
        if degree is not None:
            degrees.append(degree)
    return tuple(degrees)


def _degrees_from_intervals(intervals: Sequence[float]) -> tuple[int, ...]:
    if not intervals:
        return ()
    degrees = [1]
    current = 1
    for interval in intervals:
        step = 1 if interval >= 0 else -1
        current += step
        while current < 1:
            current += 7
        while current > 7:
            current -= 7
        degrees.append(current)
    return tuple(degrees)


def _unit_hash(*parts: object) -> float:
    payload = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
