"""Structured diff between an original and an ablated rendered score."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..generative_scores import Score


@dataclass(frozen=True)
class NoteDelta:
    """A single changed field on a note within a phrase."""

    phrase_index: int
    note_index: int
    field: str
    original: object
    ablated: object


@dataclass(frozen=True)
class PhraseDelta:
    """A single changed field on a phrase (dynamics, voice, role, metadata)."""

    phrase_index: int
    field: str
    original: object
    ablated: object


@dataclass(frozen=True)
class ScoreDelta:
    """Structured delta between an original and ablated score render."""

    note_changes: tuple[NoteDelta, ...]
    phrase_changes: tuple[PhraseDelta, ...]
    added_phrases: tuple[int, ...]
    removed_phrases: tuple[int, ...]
    tempo_delta: float
    key_changed: bool

    @property
    def empty(self) -> bool:
        return not (
            self.note_changes
            or self.phrase_changes
            or self.added_phrases
            or self.removed_phrases
            or self.tempo_delta
            or self.key_changed
        )

    def summary(self) -> str:
        if self.empty:
            return "no changes"
        parts: list[str] = []
        if self.key_changed:
            parts.append("key changed")
        if self.tempo_delta:
            sign = "+" if self.tempo_delta > 0 else ""
            parts.append(f"tempo {sign}{self.tempo_delta:.1f} bpm")
        if self.removed_phrases:
            parts.append(f"{len(self.removed_phrases)} phrase(s) removed")
        if self.added_phrases:
            parts.append(f"{len(self.added_phrases)} phrase(s) added")
        notes_by_field: dict[str, int] = {}
        for nd in self.note_changes:
            notes_by_field[nd.field] = notes_by_field.get(nd.field, 0) + 1
        for fld, count in sorted(notes_by_field.items()):
            parts.append(f"{count} note {fld} change(s)")
        dynamics_count = sum(
            1 for pd in self.phrase_changes if pd.field == "dynamic"
        )
        if dynamics_count:
            parts.append(f"{dynamics_count} dynamic change(s)")
        other_phrase = sum(
            1 for pd in self.phrase_changes if pd.field != "dynamic"
        )
        if other_phrase:
            parts.append(f"{other_phrase} other phrase change(s)")
        return "; ".join(parts)


def _diff_notes(
    phrase_index: int,
    original_notes: list[object],
    ablated_notes: list[object],
) -> list[NoteDelta]:
    deltas: list[NoteDelta] = []
    paired = min(len(original_notes), len(ablated_notes))
    for i in range(paired):
        orig = original_notes[i]
        abl = ablated_notes[i]
        for attr in ("scale_degree", "duration_beats", "accent"):
            ov = getattr(orig, attr)
            av = getattr(abl, attr)
            if ov != av:
                deltas.append(NoteDelta(phrase_index, i, attr, ov, av))
    for i in range(paired, len(original_notes)):
        orig = original_notes[i]
        for attr in ("scale_degree", "duration_beats", "accent"):
            deltas.append(
                NoteDelta(phrase_index, i, attr, getattr(orig, attr), None)
            )
    for i in range(paired, len(ablated_notes)):
        abl = ablated_notes[i]
        for attr in ("scale_degree", "duration_beats", "accent"):
            deltas.append(
                NoteDelta(phrase_index, i, attr, None, getattr(abl, attr))
            )
    return deltas


_PHRASE_FIELDS = ("dynamic", "voice", "role")


def diff_scores(original: Score, ablated: Score) -> ScoreDelta:
    """Compare two score renders and return a structured delta."""
    note_changes: list[NoteDelta] = []
    phrase_changes: list[PhraseDelta] = []

    paired = min(len(original.phrases), len(ablated.phrases))

    for idx in range(paired):
        op = original.phrases[idx]
        ap = ablated.phrases[idx]
        for fld in _PHRASE_FIELDS:
            ov = getattr(op, fld)
            av = getattr(ap, fld)
            if ov != av:
                phrase_changes.append(PhraseDelta(idx, fld, ov, av))
        if op.metadata != ap.metadata:
            phrase_changes.append(PhraseDelta(idx, "metadata", op.metadata, ap.metadata))
        note_changes.extend(_diff_notes(idx, op.notes, ap.notes))

    removed = tuple(range(paired, len(original.phrases)))
    added = tuple(range(paired, len(ablated.phrases)))

    return ScoreDelta(
        note_changes=tuple(note_changes),
        phrase_changes=tuple(phrase_changes),
        added_phrases=added,
        removed_phrases=removed,
        tempo_delta=round(ablated.tempo_bpm - original.tempo_bpm, 4),
        key_changed=original.key != ablated.key,
    )
