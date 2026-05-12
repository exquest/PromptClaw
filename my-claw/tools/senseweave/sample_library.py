"""Sample library vocabulary, record schema, and on-disk SQLite store.

Defines the controlled `CHARACTER_TAGS` vocabulary used to describe the
timbral character of recorded and curated samples. `SampleRecord` carries
the sample-id, on-disk path, capture source, validated character tags,
pitch (Hz), arc-phase context, mood, and capture timestamp.

`SampleLibrary(root)` opens (or creates) ``index.sqlite`` under ``root``,
maintains a `samples` row per record alongside an FTS5 index over
`character_tags`, and exposes :meth:`SampleLibrary.find` for querying by
source / tag-overlap / pitch-band / arc-phase / mood-range with
most-recent-first ordering. A corrupted index is detected on open and
rebuilt empty so callers can re-add records from canonical state.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


SAMPLE_SUBDIRS: tuple[str, ...] = (
    "library",
    "self",
    "room",
    "contact",
    "theramini",
    "keyboard",
)


@dataclass(frozen=True)
class SampleLibraryLayout:
    """Resolved paths for the cypherclaw sample library directory tree.

    See ``docs/cypherclaw-sample-directory-layout.md``. ``self_`` maps to
    the on-disk ``self/`` subdir (the trailing underscore avoids the
    dataclass field-name clash with the implicit ``self`` parameter).
    """

    base: Path
    library: Path
    self_: Path
    room: Path
    contact: Path
    theramini: Path
    keyboard: Path

    def as_dict(self) -> dict[str, Path]:
        """Return a mapping keyed by on-disk subdir name (``self`` not ``self_``)."""
        return {
            "library": self.library,
            "self": self.self_,
            "room": self.room,
            "contact": self.contact,
            "theramini": self.theramini,
            "keyboard": self.keyboard,
        }


def create_sample_library_layout(base_path: Path | str) -> SampleLibraryLayout:
    """Create the six cypherclaw sample subdirs idempotently under ``base_path``.

    Creates ``base_path`` and each subdir (``library/``, ``self/``,
    ``room/``, ``contact/``, ``theramini/``, ``keyboard/``) with
    ``parents=True, exist_ok=True``. Returns a :class:`SampleLibraryLayout`
    with resolved paths. Pre-existing directories are left untouched;
    pre-existing files at any target path raise ``NotADirectoryError``.
    """
    base = Path(base_path)
    base.mkdir(parents=True, exist_ok=True)
    if not base.is_dir():
        raise NotADirectoryError(f"sample library base is not a directory: {base}")

    resolved: dict[str, Path] = {}
    for name in SAMPLE_SUBDIRS:
        sub = base / name
        if sub.exists() and not sub.is_dir():
            raise NotADirectoryError(f"sample subdir path is not a directory: {sub}")
        sub.mkdir(parents=True, exist_ok=True)
        resolved[name] = sub

    return SampleLibraryLayout(
        base=base,
        library=resolved["library"],
        self_=resolved["self"],
        room=resolved["room"],
        contact=resolved["contact"],
        theramini=resolved["theramini"],
        keyboard=resolved["keyboard"],
    )


def init_sample_storage(base_path: Path | str) -> SampleLibraryLayout:
    """Create the sample directory layout and bootstrap ``index.sqlite``."""
    layout = create_sample_library_layout(base_path)
    bootstrap_sample_index(layout.base / "index.sqlite")
    return layout


CHARACTER_TAGS: frozenset[str] = frozenset(
    {
        "warm",
        "metallic",
        "wind",
        "pulse",
        "voice",
        "mechanical",
        "water",
        "sustained",
        "transient",
        "percussive",
        "harmonic",
        "noisy",
    }
)


SOURCE_VALUES: frozenset[str] = frozenset(
    {
        "human",
        "library",
        "self",
        "room",
        "contact",
        "theramini",
        "keyboard",
        "generated",
    }
)


@dataclass(frozen=True)
class SampleRecord:
    """Sample-library record.

    Only ``character_tags`` is required (validated against
    :data:`CHARACTER_TAGS`). The remaining fields default to "unset"
    sentinels so the T-025 vocabulary tests can keep constructing
    tag-only records; :meth:`SampleLibrary.add` requires ``path`` to be
    set and the file to exist on disk.
    """

    character_tags: frozenset[str]
    sample_id: str = ""
    path: Optional[Path] = None
    source: str = ""
    pitch_hz: Optional[float] = None
    arc_phase: Optional[str] = None
    mood: Optional[float] = None
    captured_at: Optional[datetime] = None
    arc_context: dict | str = ""
    pitch: Optional[float] = None
    duration: float = 0.0
    rms: float = 0.0
    peak: float = 0.0
    transient_density: float = 0.0
    extras: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        tags = frozenset(self.character_tags)
        unknown = tags - CHARACTER_TAGS
        if unknown:
            raise ValueError(
                f"unknown character_tags: {sorted(unknown)}; "
                f"allowed: {sorted(CHARACTER_TAGS)}"
            )
        if not isinstance(self.character_tags, frozenset):
            object.__setattr__(self, "character_tags", tags)
        if self.source and self.source not in SOURCE_VALUES:
            raise ValueError(
                f"unknown source: {self.source!r}; "
                f"allowed: {sorted(SOURCE_VALUES)}"
            )
        if not isinstance(self.extras, Mapping):
            raise TypeError("extras must be a mapping of string keys/values")
        normalized_extras = {
            str(key): str(value)
            for key, value in dict(self.extras).items()
        }
        if normalized_extras != self.extras:
            object.__setattr__(self, "extras", normalized_extras)
        if self.rms < 0:
            raise ValueError(f"rms must be non-negative, got {self.rms}")
        if self.peak < 0:
            raise ValueError(f"peak must be non-negative, got {self.peak}")
        if self.transient_density < 0:
            raise ValueError(
                f"transient_density must be non-negative, got {self.transient_density}"
            )
        if self.peak < self.rms:
            raise ValueError(
                f"peak ({self.peak}) must be >= rms ({self.rms})"
            )

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict for catalog persistence."""
        return {
            "character_tags": sorted(self.character_tags),
            "sample_id": self.sample_id,
            "path": str(self.path) if self.path is not None else None,
            "source": self.source,
            "pitch_hz": self.pitch_hz,
            "arc_phase": self.arc_phase,
            "mood": self.mood,
            "captured_at": (
                self.captured_at.isoformat()
                if self.captured_at is not None
                else None
            ),
            "arc_context": self.arc_context,
            "pitch": self.pitch,
            "duration": self.duration,
            "rms": self.rms,
            "peak": self.peak,
            "transient_density": self.transient_density,
            "extras": dict(self.extras),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "SampleRecord":
        """Restore from a dict produced by :meth:`to_dict`, coercing types."""
        data = dict(payload)
        tags_value = data.get("character_tags", ())
        data["character_tags"] = frozenset(tags_value) if tags_value else frozenset()
        path_value = data.get("path")
        data["path"] = Path(path_value) if path_value is not None else None
        captured_value = data.get("captured_at")
        if isinstance(captured_value, str):
            data["captured_at"] = datetime.fromisoformat(captured_value)
        extras_value = data.get("extras", {})
        data["extras"] = dict(extras_value) if isinstance(extras_value, Mapping) else {}
        return cls(**data)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (1, CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS samples (
    sample_id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    source TEXT NOT NULL,
    character_tags TEXT NOT NULL,
    pitch_hz REAL,
    arc_phase TEXT,
    mood REAL,
    captured_at TEXT NOT NULL,
    record_json TEXT NOT NULL DEFAULT '{}'
);
CREATE VIRTUAL TABLE IF NOT EXISTS samples_tags_fts USING fts5(
    sample_id UNINDEXED,
    character_tags,
    tokenize='unicode61'
);
"""

def bootstrap_sample_index(db_path: Path | str) -> None:
    """Create the SQLite index file at the given path with an initial schema stub."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()



class SampleLibrary:
    """On-disk sample store backed by ``index.sqlite`` under ``root``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "index.sqlite"
        self._conn: sqlite3.Connection
        self._open()

    def _open(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            check = conn.execute("PRAGMA integrity_check").fetchone()
            if check is None or (check[0] or "").lower() != "ok":
                conn.close()
                self._rebuild()
                return
            self._conn = conn
            self._ensure_schema()
        except sqlite3.DatabaseError:
            self._rebuild()

    def _rebuild(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._conn = conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)
        columns = {
            str(row["name"])
            for row in self._conn.execute("PRAGMA table_info(samples)")
        }
        if "record_json" not in columns:
            self._conn.execute(
                "ALTER TABLE samples ADD COLUMN record_json TEXT NOT NULL DEFAULT '{}'"
            )
        self._conn.commit()

    def add(self, record: SampleRecord) -> str:
        """Persist ``record`` and verify its on-disk file exists.

        Returns the assigned ``sample_id`` (auto-generated if the record
        did not carry one). Raises ``FileNotFoundError`` if ``path`` is
        unset or missing.
        """
        if record.path is None:
            raise FileNotFoundError("SampleRecord.path is required to persist")
        path = Path(record.path)
        if not path.exists():
            raise FileNotFoundError(f"sample file missing: {path}")

        sample_id = record.sample_id or uuid.uuid4().hex
        captured = record.captured_at or datetime.now(timezone.utc)
        tags_text = " ".join(sorted(record.character_tags))
        stored_record = replace(
            record,
            sample_id=sample_id,
            path=path,
            captured_at=captured,
        )
        record_json = json.dumps(stored_record.to_dict(), sort_keys=True)

        self._conn.execute(
            """
            INSERT OR REPLACE INTO samples
                (sample_id, path, source, character_tags,
                 pitch_hz, arc_phase, mood, captured_at, record_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                str(path),
                record.source,
                tags_text,
                record.pitch_hz,
                record.arc_phase,
                record.mood,
                captured.isoformat(),
                record_json,
            ),
        )
        self._conn.execute(
            "DELETE FROM samples_tags_fts WHERE sample_id = ?", (sample_id,)
        )
        self._conn.execute(
            "INSERT INTO samples_tags_fts (sample_id, character_tags) VALUES (?, ?)",
            (sample_id, tags_text),
        )
        self._conn.commit()
        return sample_id

    def find(
        self,
        *,
        source: Optional[str] = None,
        character_any: Optional[Iterable[str]] = None,
        character_all: Optional[Iterable[str]] = None,
        pitch_band: Optional[tuple[float, float]] = None,
        arc_phase: Optional[str] = None,
        mood_range: Optional[tuple[float, float]] = None,
        limit: Optional[int] = None,
    ) -> list[SampleRecord]:
        """Return records matching the given filters, most-recent-first."""
        clauses: list[str] = []
        params: list[object] = []

        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if arc_phase is not None:
            clauses.append("arc_phase = ?")
            params.append(arc_phase)
        if pitch_band is not None:
            lo, hi = pitch_band
            clauses.append("pitch_hz IS NOT NULL AND pitch_hz BETWEEN ? AND ?")
            params.extend([lo, hi])
        if mood_range is not None:
            lo, hi = mood_range
            clauses.append("mood IS NOT NULL AND mood BETWEEN ? AND ?")
            params.extend([lo, hi])
        if character_any:
            any_tags = [t for t in character_any if t]
            if any_tags:
                fts_query = " OR ".join(any_tags)
                clauses.append(
                    "sample_id IN (SELECT sample_id FROM samples_tags_fts "
                    "WHERE samples_tags_fts MATCH ?)"
                )
                params.append(fts_query)

        sql = "SELECT * FROM samples"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY captured_at DESC, sample_id DESC"

        rows = list(self._conn.execute(sql, params))

        if character_all:
            required = {t for t in character_all if t}
            if required:
                rows = [
                    r
                    for r in rows
                    if required.issubset(set((r["character_tags"] or "").split()))
                ]

        if limit is not None:
            rows = rows[:limit]

        return [self._row_to_record(r) for r in rows]

    def _row_to_record(self, row: sqlite3.Row) -> SampleRecord:
        payload_text = row["record_json"] if "record_json" in row.keys() else None
        if isinstance(payload_text, str) and payload_text not in {"", "{}"}:
            payload = json.loads(payload_text)
            return SampleRecord.from_dict(payload)
        tags_text = row["character_tags"] or ""
        tags = frozenset(tags_text.split()) if tags_text else frozenset()
        captured = datetime.fromisoformat(row["captured_at"])
        return SampleRecord(
            character_tags=tags,
            sample_id=row["sample_id"],
            path=Path(row["path"]),
            source=row["source"],
            pitch_hz=row["pitch_hz"],
            arc_phase=row["arc_phase"],
            mood=row["mood"],
            captured_at=captured,
            extras={},
        )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SampleLibrary":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
