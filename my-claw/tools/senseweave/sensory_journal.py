"""Sensory Journal — records significant sensory events for CypherClaw's narrative engine.

Each event is appended as a JSONL line to a journal file.  The journal
serves as long-term memory for the narrative engine, mood tracking, and
the Basalt & Pebble comic strip generator.

All I/O uses atomic appends.  Stdlib only.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Default path
# ---------------------------------------------------------------------------

_DEFAULT_JOURNAL_PATH = "/home/user/cypherclaw-data/state/sensory_journal.jsonl"


# ---------------------------------------------------------------------------
# JournalEntry dataclass
# ---------------------------------------------------------------------------


@dataclass
class JournalEntry:
    """A single sensory event record."""

    timestamp: float
    event_type: str
    description: str
    sensor_source: str
    mood_snapshot: dict | None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _entry_to_dict(entry: JournalEntry) -> dict:
    """Convert a JournalEntry to a JSON-serialisable dict."""
    return asdict(entry)


def _dict_to_entry(data: dict) -> JournalEntry:
    """Reconstruct a JournalEntry from a dict."""
    return JournalEntry(
        timestamp=data["timestamp"],
        event_type=data["event_type"],
        description=data["description"],
        sensor_source=data["sensor_source"],
        mood_snapshot=data.get("mood_snapshot"),
        metadata=data.get("metadata", {}),
    )


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------


def log_event(
    event_type: str,
    description: str,
    sensor_source: str,
    mood: dict | None = None,
    journal_path: str = _DEFAULT_JOURNAL_PATH,
) -> JournalEntry:
    """Append a sensory event to the journal file.

    Parameters
    ----------
    event_type : str
        Category of event (e.g. "sound", "motion", "touch").
    description : str
        Human-readable description.
    sensor_source : str
        Which sensor produced the event (e.g. "contact_mic", "porch_eye").
    mood : dict | None
        Optional mood snapshot at the time of the event.
    journal_path : str
        Path to the JSONL journal file.

    Returns
    -------
    JournalEntry
        The entry that was written.
    """
    entry = JournalEntry(
        timestamp=time.time(),
        event_type=event_type,
        description=description,
        sensor_source=sensor_source,
        mood_snapshot=mood,
        metadata={},
    )

    # Ensure parent directory exists
    Path(journal_path).parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(_entry_to_dict(entry)) + "\n"

    # Atomic append (O_APPEND is atomic on POSIX for reasonable line sizes)
    fd = os.open(journal_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)

    return entry


# ---------------------------------------------------------------------------
# read_recent
# ---------------------------------------------------------------------------


def read_recent(
    count: int = 20,
    journal_path: str = _DEFAULT_JOURNAL_PATH,
) -> list[JournalEntry]:
    """Read the last N entries from the journal.

    Parameters
    ----------
    count : int
        Maximum number of entries to return.
    journal_path : str
        Path to the JSONL journal file.

    Returns
    -------
    list[JournalEntry]
        Most recent entries, ordered oldest-first.
    """
    lines = _read_lines(journal_path)
    if not lines:
        return []

    tail = lines[-count:] if count < len(lines) else lines
    return [_dict_to_entry(json.loads(line)) for line in tail if line.strip()]


# ---------------------------------------------------------------------------
# read_since
# ---------------------------------------------------------------------------


def read_since(
    since_timestamp: float,
    journal_path: str = _DEFAULT_JOURNAL_PATH,
) -> list[JournalEntry]:
    """Read entries with timestamp >= since_timestamp.

    Parameters
    ----------
    since_timestamp : float
        Unix timestamp threshold.
    journal_path : str
        Path to the JSONL journal file.

    Returns
    -------
    list[JournalEntry]
        Matching entries, ordered oldest-first.
    """
    lines = _read_lines(journal_path)
    entries: list[JournalEntry] = []
    for line in lines:
        if not line.strip():
            continue
        data = json.loads(line)
        if data["timestamp"] >= since_timestamp:
            entries.append(_dict_to_entry(data))
    return entries


# ---------------------------------------------------------------------------
# summarize_period
# ---------------------------------------------------------------------------


def summarize_period(
    hours: float = 24.0,
    journal_path: str = _DEFAULT_JOURNAL_PATH,
) -> dict:
    """Summarize events over a time period.

    Parameters
    ----------
    hours : float
        How far back to look.
    journal_path : str
        Path to the JSONL journal file.

    Returns
    -------
    dict with keys:
        total_events     : int
        events_by_type   : dict[str, int]
        sensors_by_count : dict[str, int]
    """
    cutoff = time.time() - hours * 3600.0
    entries = read_since(cutoff, journal_path=journal_path)

    events_by_type: dict[str, int] = {}
    sensors_by_count: dict[str, int] = {}

    for entry in entries:
        events_by_type[entry.event_type] = events_by_type.get(entry.event_type, 0) + 1
        sensors_by_count[entry.sensor_source] = sensors_by_count.get(entry.sensor_source, 0) + 1

    return {
        "total_events": len(entries),
        "events_by_type": events_by_type,
        "sensors_by_count": sensors_by_count,
    }


# ---------------------------------------------------------------------------
# is_novel_event
# ---------------------------------------------------------------------------


def is_novel_event(
    event_type: str,
    description: str,
    lookback_hours: float = 1.0,
    journal_path: str = _DEFAULT_JOURNAL_PATH,
) -> bool:
    """Check whether a similar event was logged recently.

    An event is considered "not novel" if an entry with the same event_type
    AND description exists within the lookback window.

    Parameters
    ----------
    event_type : str
        Category to match.
    description : str
        Description to match.
    lookback_hours : float
        How far back to search.
    journal_path : str
        Path to the JSONL journal file.

    Returns
    -------
    bool
        True if the event is novel (no recent match), False otherwise.
    """
    cutoff = time.time() - lookback_hours * 3600.0
    entries = read_since(cutoff, journal_path=journal_path)

    for entry in entries:
        if entry.event_type == event_type and entry.description == description:
            return False

    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_lines(path: str) -> list[str]:
    """Read all lines from a file, returning [] on missing/empty."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.readlines()
    except (FileNotFoundError, OSError):
        return []
