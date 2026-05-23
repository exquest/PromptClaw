"""End-to-end integration test for T-019: a dropped MIDI file appears as
vocabulary within 60 seconds.

Drops a hand-crafted MIDI into the daemon's watched inbox while the daemon
runs in poll mode against a `--vocabulary-db`, then asserts fragment rows
appear in the SQLite vocabulary store inside the 60-second budget.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from cypherclaw import midi_intake_daemon as mod
from cypherclaw import midi_vocabulary_store as store

VOCABULARY_BUDGET_SECONDS = 60.0


def _varlen(value: int) -> bytes:
    parts = [value & 0x7F]
    value >>= 7
    while value:
        parts.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(parts)


def _note_on(channel: int, note: int, velocity: int = 96) -> bytes:
    return bytes([0x90 | channel, note, velocity])


def _note_off(channel: int, note: int) -> bytes:
    return bytes([0x80 | channel, note, 0])


def _write_melody_midi(path: Path, *, division: int = 480) -> None:
    """Write a single-track MIDI with a melodic motif that yields fragments."""

    events: list[tuple[int, bytes]] = []
    tick = 0
    for note, duration in ((60, 120), (62, 120), (64, 240), (67, 240), (69, 120)):
        events.append((tick, _note_on(0, note)))
        events.append((tick + duration, _note_off(0, note)))
        tick += duration

    track = bytearray()
    last_tick = 0
    ordered = sorted(enumerate(events), key=lambda item: (item[1][0], item[0]))
    for _index, (event_tick, message) in ordered:
        track.extend(_varlen(event_tick - last_tick))
        track.extend(message)
        last_tick = event_tick
    track.extend(_varlen(0))
    track.extend(b"\xff\x2f\x00")  # End of Track

    header = (
        mod.MIDI_HEADER_MAGIC
        + (6).to_bytes(4, "big")
        + (0).to_bytes(2, "big")
        + (1).to_bytes(2, "big")
        + division.to_bytes(2, "big")
    )
    path.write_bytes(
        header + b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)
    )


def test_dropped_midi_appears_as_vocabulary_within_budget(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    vocab_db = tmp_path / "midi_vocabulary.sqlite"

    stop_event = threading.Event()
    daemon_thread = threading.Thread(
        target=mod.main,
        kwargs={
            "argv": [
                "--watch-dir", str(inbox),
                "--poll",
                "--poll-interval", "0.1",
                "--vocabulary-db", str(vocab_db),
            ],
            "stop_event": stop_event,
        },
        daemon=True,
    )
    daemon_thread.start()

    try:
        # Give the daemon a moment to enter its watch loop before dropping.
        time.sleep(0.2)

        drop = inbox / "seed.mid"
        _write_melody_midi(drop)
        dropped_at = time.monotonic()

        rows: list = []
        deadline = dropped_at + VOCABULARY_BUDGET_SECONDS
        while time.monotonic() < deadline:
            if vocab_db.exists():
                conn = store.connect(vocab_db)
                try:
                    rows = store.query_fragments(conn, source_file="seed.mid")
                finally:
                    conn.close()
                if rows:
                    break
            time.sleep(0.1)

        elapsed = time.monotonic() - dropped_at

        assert rows, (
            f"vocabulary rows did not appear within {VOCABULARY_BUDGET_SECONDS}s "
            f"(elapsed={elapsed:.2f}s)"
        )
        assert elapsed < VOCABULARY_BUDGET_SECONDS, (
            f"timing budget exceeded: elapsed={elapsed:.2f}s"
        )
        assert any(row["kind"] == "melodic_motif" for row in rows)
    finally:
        stop_event.set()
        daemon_thread.join(timeout=5.0)


def test_process_midi_file_ingests_into_vocabulary_db(tmp_path: Path) -> None:
    """Unit-level sanity check for the new `vocabulary_db_path` hook."""

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    drop = inbox / "seed.mid"
    _write_melody_midi(drop)

    vocab_db = tmp_path / "midi_vocabulary.sqlite"

    event = mod.process_midi_file(drop, vocabulary_db_path=vocab_db)

    assert event["status"] == "processed"
    assert vocab_db.exists()

    conn = store.connect(vocab_db)
    try:
        rows = store.query_fragments(conn, source_file="seed.mid")
    finally:
        conn.close()

    assert rows, "expected at least one ingested vocabulary row"
    assert any(row["kind"] == "melodic_motif" for row in rows)


def test_process_midi_file_skips_vocabulary_when_path_none(tmp_path: Path) -> None:
    drop = tmp_path / "seed.mid"
    _write_melody_midi(drop)

    mod.process_midi_file(drop)  # vocabulary_db_path defaults to None

    # No DB created when no path is supplied.
    assert not (tmp_path / "midi_vocabulary.sqlite").exists()
