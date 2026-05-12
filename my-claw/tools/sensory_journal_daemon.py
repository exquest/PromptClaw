"""Sensory journal daemon for fused organism-state transitions."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from senseweave.sensory_journal import JournalEntry, log_event


FUSED_STATE_PATH = Path("/tmp/organism_state.json")
JOURNAL_PATH = Path("/home/user/cypherclaw-data/state/sensory_journal.jsonl")
FUSED = str(FUSED_STATE_PATH)
JOURNAL = str(JOURNAL_PATH)
DEFAULT_INTERVAL_SECONDS = 5.0
ENERGY_SHIFT_THRESHOLD = 0.15


@dataclass(frozen=True)
class SensorySnapshot:
    """Normalized fields the journal daemon cares about."""

    theramini_playing: bool = False
    theramini_pitch: str | None = None
    room_transient: bool = False
    room_activity: str = "quiet"
    energy: float = 0.5


@dataclass(frozen=True)
class JournalEventSpec:
    """Pending event ready to be written to the sensory journal."""

    event_type: str
    description: str
    sensor_source: str
    mood: dict[str, float] | None = None


def read_fused_state(fused_path: str | Path = FUSED_STATE_PATH) -> dict[str, Any]:
    """Read one fused organism-state JSON object."""

    try:
        data = json.loads(Path(fused_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def snapshot_from_state(state: Mapping[str, Any]) -> SensorySnapshot:
    """Normalize the fused state into one stable daemon snapshot."""

    theramini = _mapping_section(state, "theramini")
    room = _mapping_section(state, "room")
    mood = _mapping_section(state, "organism_mood")
    pitch = theramini.get("pitch")
    activity = room.get("activity", "quiet")

    return SensorySnapshot(
        theramini_playing=bool(theramini.get("playing", False)),
        theramini_pitch=str(pitch) if pitch is not None else None,
        room_transient=bool(room.get("transient", False)),
        room_activity=str(activity),
        energy=_float_value(mood.get("energy", 0.5), default=0.5),
    )


def events_from_snapshots(
    current: SensorySnapshot,
    previous: SensorySnapshot | None = None,
) -> list[JournalEventSpec]:
    """Build ordered journal events for significant state transitions."""

    prior = previous or SensorySnapshot()
    events: list[JournalEventSpec] = []

    if current.theramini_playing and not prior.theramini_playing:
        pitch = current.theramini_pitch or "unknown pitch"
        events.append(
            JournalEventSpec(
                event_type="theramini_start",
                description=f"Theramini started playing near {pitch}.",
                sensor_source="theramini",
            )
        )

    if current.room_transient and not prior.room_transient:
        events.append(
            JournalEventSpec(
                event_type="room_transient",
                description=(
                    "Room transient detected during "
                    f"{current.room_activity} activity."
                ),
                sensor_source="room",
            )
        )

    if abs(current.energy - prior.energy) > ENERGY_SHIFT_THRESHOLD:
        events.append(
            JournalEventSpec(
                event_type="mood_shift",
                description=(
                    "Organism energy shifted from "
                    f"{prior.energy:.2f} to {current.energy:.2f}."
                ),
                sensor_source="organism_mood",
                mood={"energy": round(current.energy, 4)},
            )
        )

    return events


def write_events(
    events: Sequence[JournalEventSpec],
    journal_path: str | Path = JOURNAL_PATH,
) -> list[JournalEntry]:
    """Append pending event specs to the sensory journal."""

    return [
        log_event(
            event.event_type,
            event.description,
            event.sensor_source,
            mood=event.mood,
            journal_path=str(journal_path),
        )
        for event in events
    ]


def process_once(
    *,
    fused_path: str | Path = FUSED_STATE_PATH,
    journal_path: str | Path = JOURNAL_PATH,
    previous: SensorySnapshot | None = None,
) -> tuple[SensorySnapshot, list[JournalEntry]]:
    """Read fused state, detect transitions, write journal entries."""

    snapshot = snapshot_from_state(read_fused_state(fused_path))
    entries = write_events(
        events_from_snapshots(snapshot, previous),
        journal_path=journal_path,
    )
    return snapshot, entries


def run_daemon(
    *,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    max_iterations: int = 0,
    fused_path: str | Path = FUSED_STATE_PATH,
    journal_path: str | Path = JOURNAL_PATH,
) -> None:
    """Run the sensory journal daemon loop."""

    previous: SensorySnapshot | None = None
    iteration = 0
    while True:
        try:
            previous, _entries = process_once(
                fused_path=fused_path,
                journal_path=journal_path,
                previous=previous,
            )
        except Exception as exc:  # pragma: no cover - defensive daemon guard
            print(f"[sensory_journal_daemon] cycle failed: {exc}", file=sys.stderr)

        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            break
        time.sleep(interval)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="CypherClaw sensory journal daemon")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--fused-path", default=str(FUSED_STATE_PATH))
    parser.add_argument("--journal-path", default=str(JOURNAL_PATH))
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    max_iterations = 1 if args.once else args.max_iterations
    try:
        run_daemon(
            interval=args.interval,
            max_iterations=max_iterations,
            fused_path=args.fused_path,
            journal_path=args.journal_path,
        )
    except KeyboardInterrupt:
        return 130
    return 0


def _mapping_section(
    state: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    value = state.get(key, {})
    return value if isinstance(value, Mapping) else {}


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    raise SystemExit(main())
