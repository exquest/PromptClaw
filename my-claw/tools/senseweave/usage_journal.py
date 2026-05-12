from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

# The storage path as defined by the requirement
JOURNAL_PATH = Path("samples/usage_journal.jsonl")


def _as_text_list(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        text = values.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        if isinstance(decoded, list):
            return [str(value) for value in decoded if str(value).strip()]
        if decoded is None:
            return []
        return [str(decoded)]
    if isinstance(values, Sequence) and not isinstance(values, (bytes, bytearray)):
        return [str(value) for value in values if str(value).strip()]
    return [str(values)]


def _ordered_unique_transformations(samples_played: Sequence["SamplePlay"]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for sample in samples_played:
        for transform in sample.transformations:
            if transform in seen:
                continue
            seen.add(transform)
            ordered.append(transform)
    return ordered


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


@dataclass
class SamplePlay:
    sample_id: str
    source: str
    transposition: int
    fx_preset: str
    played_at_row: int
    transformations: list[str] = field(default_factory=list)
    source_kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "source": self.source,
            "source_kind": self.source_kind,
            "transposition": self.transposition,
            "fx_preset": self.fx_preset,
            "played_at_row": self.played_at_row,
            "transformations": list(self.transformations),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SamplePlay":
        raw_source_kind = data.get("source_kind")
        source_kind = str(raw_source_kind) if raw_source_kind else "unknown"
        return cls(
            sample_id=str(data.get("sample_id", "")),
            source=str(data.get("source", "")),
            transposition=_int_value(data.get("transposition", 0)),
            fx_preset=str(data.get("fx_preset", "")),
            played_at_row=_int_value(data.get("played_at_row", 0)),
            transformations=_as_text_list(data.get("transformations")),
            source_kind=source_kind,
        )


@dataclass
class JournalEntry:
    piece_id: str
    timestamp: str
    samples_played: list[SamplePlay]
    arc_payoff: str
    mode: str = ""
    transformations: list[str] = field(default_factory=list)
    clicks: int = 0

    @property
    def started_at(self) -> str:
        return self.timestamp

    @property
    def samples_used(self) -> list[SamplePlay]:
        return self.samples_played

    def to_dict(self) -> dict[str, Any]:
        samples_payload = [sample.to_dict() for sample in self.samples_played]
        transformations = (
            list(self.transformations)
            if self.transformations
            else _ordered_unique_transformations(self.samples_played)
        )
        return {
            "piece_id": self.piece_id,
            "timestamp": self.timestamp,
            "started_at": self.timestamp,
            "mode": self.mode,
            "samples_played": samples_payload,
            "samples_used": samples_payload,
            "transformations": transformations,
            "arc_payoff": self.arc_payoff,
            "clicks": self.clicks,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JournalEntry":
        samples_raw = data.get("samples_played")
        if not samples_raw:
            samples_raw = data.get("samples_used", [])
        samples_played = [
            SamplePlay.from_dict(sample)
            for sample in samples_raw
            if isinstance(sample, Mapping)
        ]
        transformations = _as_text_list(data.get("transformations"))
        if not transformations:
            transformations = _ordered_unique_transformations(samples_played)
        timestamp = str(data.get("timestamp") or data.get("started_at") or "")
        return cls(
            piece_id=str(data.get("piece_id", "")),
            timestamp=timestamp,
            samples_played=samples_played,
            arc_payoff=str(data.get("arc_payoff", "")),
            mode=str(data.get("mode", "")),
            transformations=transformations,
            clicks=_int_value(data.get("clicks", 0)),
        )


def append_to_journal(entry: JournalEntry, path: Path = JOURNAL_PATH) -> None:
    """Append a JournalEntry to the JSONL file and fsync for durability."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.to_dict()) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_journal(path: Path = JOURNAL_PATH) -> list[JournalEntry]:
    """Read all journal entries from the JSONL file."""
    entries: list[JournalEntry] = []
    if not path.exists():
        return entries
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                entries.append(JournalEntry.from_dict(json.loads(line)))
    return entries


@dataclass
class SampleUsageTracker:
    """Accumulate sample events emitted during a piece's playback."""

    piece_id: str | None = None
    timestamp: str | None = None
    samples_played: list[SamplePlay] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.piece_id is not None

    def start_piece(self, piece_id: str, timestamp: str) -> None:
        self.piece_id = piece_id
        self.timestamp = timestamp
        self.samples_played = []

    def record_play(
        self,
        *,
        sample_id: str,
        source: str,
        transposition: int,
        fx_preset: str,
        played_at_row: int,
        transformations: Sequence[str] = (),
        source_kind: str = "",
    ) -> SamplePlay:
        if self.piece_id is None:
            raise RuntimeError("SampleUsageTracker.record_play called before start_piece")
        play = SamplePlay(
            sample_id=sample_id,
            source=source,
            transposition=transposition,
            fx_preset=fx_preset,
            played_at_row=played_at_row,
            transformations=[str(value) for value in transformations if str(value).strip()],
            source_kind=source_kind,
        )
        self.samples_played.append(play)
        return play

    def finish_piece(
        self,
        arc_payoff: str = "",
        *,
        mode: str = "",
        clicks: int = 0,
    ) -> JournalEntry:
        if self.piece_id is None or self.timestamp is None:
            raise RuntimeError("SampleUsageTracker.finish_piece called before start_piece")
        entry = JournalEntry(
            piece_id=self.piece_id,
            timestamp=self.timestamp,
            samples_played=list(self.samples_played),
            arc_payoff=arc_payoff,
            mode=mode,
            transformations=_ordered_unique_transformations(self.samples_played),
            clicks=clicks,
        )
        self.piece_id = None
        self.timestamp = None
        self.samples_played = []
        return entry


def derive_arc_payoff_summary(*, arc_payoff_score: float, sample_count: int) -> str:
    """Render a short textual summary from a numeric arc-payoff score."""
    if arc_payoff_score >= 0.6:
        band = "strong"
    elif arc_payoff_score >= 0.3:
        band = "moderate"
    else:
        band = "weak"
    return f"{band} payoff (score={arc_payoff_score:.2f}) over {sample_count} sample(s)"


def record_scheduled_sample_event(tracker: SampleUsageTracker, event: object) -> SamplePlay | None:
    """Fold one runtime sample event into the journal tracker.

    Non-sample events are ignored. Sample ids currently fall back to the
    tracker's stable trigger key because the live selector-backed sample id
    is not yet attached to runtime events in this checkout.
    """
    if str(getattr(event, "role", "")) != "sample":
        return None

    metadata = dict(getattr(event, "metadata", {}) or {})
    scene_metadata = dict(getattr(event, "scene_metadata", {}) or {})
    sample_id = str(
        metadata.get("sample_id")
        or metadata.get("sample_trigger_key")
        or f"{getattr(event, 'scene_name', 'sample')}:{getattr(event, 'row', 0)}"
    )
    source = str(
        metadata.get("sample_gesture_source")
        or scene_metadata.get("sample_gesture_source")
        or metadata.get("source")
        or "sample_gesture"
    )
    fx_preset = str(
        metadata.get("sample_gesture_mode")
        or scene_metadata.get("sample_gesture_mode")
        or getattr(event, "voice", "")
        or "sample"
    )
    transposition = _int_value(
        metadata.get("pitch_transpose_semitones", metadata.get("sample_pitch_transpose", 0))
    )
    transformations = _as_text_list(
        metadata.get("sample_gesture_transforms")
        or scene_metadata.get("sample_gesture_transforms")
    )
    source_kind = _derive_source_kind(metadata, scene_metadata)
    return tracker.record_play(
        sample_id=sample_id,
        source=source,
        transposition=transposition,
        fx_preset=fx_preset,
        played_at_row=_int_value(getattr(event, "row", 0)),
        transformations=transformations,
        source_kind=source_kind,
    )


def _derive_source_kind(
    metadata: Mapping[str, Any], scene_metadata: Mapping[str, Any]
) -> str:
    explicit = (
        metadata.get("source_kind")
        or scene_metadata.get("source_kind")
        or metadata.get("sample_origin")
        or scene_metadata.get("sample_origin")
    )
    if explicit:
        return str(explicit)
    if metadata.get("generated_by") or scene_metadata.get("generated_by"):
        return "generated"
    if metadata.get("library_path") or scene_metadata.get("library_path"):
        return "library"
    return "gesture"


def post_piece_hook(
    tracker: SampleUsageTracker,
    *,
    arc_payoff_score: float,
    journal_path: Path = JOURNAL_PATH,
    mode: str = "",
    clicks: int = 0,
) -> JournalEntry:
    """Finalize tracker state into a durable journal entry."""
    sample_count = len(tracker.samples_played)
    summary = derive_arc_payoff_summary(
        arc_payoff_score=arc_payoff_score,
        sample_count=sample_count,
    )
    entry = tracker.finish_piece(
        arc_payoff=summary,
        mode=mode,
        clicks=clicks,
    )
    append_to_journal(entry, path=journal_path)
    return entry
