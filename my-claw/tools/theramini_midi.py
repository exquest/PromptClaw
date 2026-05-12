"""Theramini MIDI listener — reads pitch from Moog Theremini MIDI output.

The daemon polls a MIDI byte stream produced by the Moog Theremini and writes
``/tmp/theramini_state.json`` with current pitch, note name, playing state,
CC controls, and pitch bend. The shared duet contract is added by
``senseweave.theramini_duet.normalize_theramini_state``.

The module is import-safe: importing it does not start a loop, so the helpers
below can be exercised directly from tests.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, os.path.dirname(__file__))
from senseweave.theramini_duet import normalize_theramini_state  # noqa: E402

STATE_FILE = Path("/tmp/theramini_state.json")
DEFAULT_DEVICE = "/dev/midi3"
DEFAULT_INTERVAL_SECONDS = 0.05  # 20 Hz update rate
NO_DEVICE_INTERVAL_SECONDS = 2.0
PLAYING_TIMEOUT_SECONDS = 2.0
READ_BUFFER_SIZE = 256

MidiEventKind = Literal["note_on", "note_off", "cc", "pitch_bend"]


@dataclass(frozen=True)
class MidiEvent:
    """One parsed MIDI message."""

    kind: MidiEventKind
    data1: int
    data2: int


@dataclass
class MidiState:
    """Mutable per-cycle Theremini state shared by parse/render helpers."""

    current_note: int | None = None
    last_note_time: float = 0.0
    silence_start: float = 0.0
    cc_values: dict[int, int] = field(default_factory=dict)
    pitch_bend: int = 8192


def midi_to_freq(note: int) -> float:
    """Convert a MIDI note number to Hz (A4 = 69 = 440 Hz)."""
    return 440.0 * (2 ** ((note - 69) / 12.0))


def midi_to_name(note: int) -> str:
    """Convert a MIDI note number to a note name like ``C4``."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[note % 12]}{note // 12 - 1}"


def parse_midi_messages(buf: bytes) -> tuple[list[MidiEvent], bytes]:
    """Parse complete MIDI messages out of ``buf``.

    Returns the parsed events and the remaining bytes (a partial message at
    the tail or any non-status leading bytes that were skipped past).
    """
    events: list[MidiEvent] = []
    data = bytes(buf)
    while data:
        status = data[0]
        if status & 0x80 == 0:
            data = data[1:]
            continue

        msg_type = status & 0xF0
        if msg_type in (0xC0, 0xD0):
            if len(data) < 2:
                break
            data = data[2:]
            continue

        if len(data) < 3:
            break

        d1 = data[1]
        d2 = data[2]
        if msg_type == 0x90:
            events.append(MidiEvent("note_on", d1, d2))
        elif msg_type == 0x80:
            events.append(MidiEvent("note_off", d1, d2))
        elif msg_type == 0xB0:
            events.append(MidiEvent("cc", d1, d2))
        elif msg_type == 0xE0:
            events.append(MidiEvent("pitch_bend", d1, d2))
        data = data[3:]
    return events, data


def apply_midi_event(
    state: MidiState, event: MidiEvent, *, now: float
) -> MidiState:
    """Return a new ``MidiState`` after applying one parsed event."""
    current_note = state.current_note
    last_note_time = state.last_note_time
    silence_start = state.silence_start
    cc_values = dict(state.cc_values)
    pitch_bend = state.pitch_bend

    if event.kind == "note_on":
        if event.data2 > 0:
            current_note = event.data1
            last_note_time = now
            silence_start = 0.0
        elif current_note == event.data1:
            current_note = None
            silence_start = now
    elif event.kind == "note_off":
        if current_note == event.data1:
            current_note = None
            silence_start = now
    elif event.kind == "cc":
        cc_values[event.data1] = event.data2
    elif event.kind == "pitch_bend":
        pitch_bend = event.data1 | (event.data2 << 7)

    return MidiState(
        current_note=current_note,
        last_note_time=last_note_time,
        silence_start=silence_start,
        cc_values=cc_values,
        pitch_bend=pitch_bend,
    )


def process_buffer(
    state: MidiState, buf: bytes, *, now: float
) -> tuple[MidiState, bytes]:
    """Parse complete events from ``buf`` and return new state + remainder."""
    events, remaining = parse_midi_messages(buf)
    new_state = state
    for event in events:
        new_state = apply_midi_event(new_state, event, now=now)
    return new_state, remaining


def render_state(state: MidiState, *, now: float) -> dict[str, Any]:
    """Render the JSON payload after ``normalize_theramini_state``."""
    is_playing = (
        state.current_note is not None
        and (now - state.last_note_time) < PLAYING_TIMEOUT_SECONDS
    )
    payload: dict[str, Any] = {
        "timestamp": float(now),
        "is_playing": bool(is_playing),
        "pitch_hz": midi_to_freq(state.current_note) if state.current_note is not None else None,
        "pitch_note": midi_to_name(state.current_note) if state.current_note is not None else None,
        "pitch_confidence": 1.0 if is_playing else 0.0,
        "state": "playing" if is_playing else "silence",
        "consecutive_silence_ms": (
            int((now - state.silence_start) * 1000) if state.silence_start > 0 else 0
        ),
        "midi_cc": {"raw": _stringify_cc_keys(state.cc_values)},
        "pitch_bend": state.pitch_bend,
    }
    return normalize_theramini_state(payload, now=now)


def write_state(
    payload: Mapping[str, Any], state_path: str | Path = STATE_FILE
) -> None:
    """Atomically write the rendered payload via a ``.tmp`` rename."""
    target = Path(state_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload)), encoding="utf-8")
    os.replace(str(tmp), str(target))


def read_midi_buffer(fd: int, size: int = READ_BUFFER_SIZE) -> bytes:
    """Read up to ``size`` bytes from a non-blocking MIDI fd."""
    try:
        return os.read(fd, size)
    except BlockingIOError:
        return b""
    except OSError:
        return b""


def process_once(
    *,
    state: MidiState,
    fd: int,
    buf: bytes,
    now: float | None = None,
    state_path: str | Path = STATE_FILE,
) -> tuple[MidiState, bytes, dict[str, Any]]:
    """Run one daemon cycle and return (new state, remaining buf, payload)."""
    timestamp = time.time() if now is None else float(now)
    chunk = read_midi_buffer(fd)
    new_state, remaining = process_buffer(state, buf + chunk, now=timestamp)
    payload = render_state(new_state, now=timestamp)
    write_state(payload, state_path)
    return new_state, remaining, payload


def run_daemon(
    *,
    device: str | Path = DEFAULT_DEVICE,
    interval: float = DEFAULT_INTERVAL_SECONDS,
    max_iterations: int = 0,
    state_path: str | Path = STATE_FILE,
) -> None:
    """Run the Theremini MIDI listener loop."""
    try:
        fd = os.open(str(device), os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        _run_no_device_loop(
            interval=NO_DEVICE_INTERVAL_SECONDS,
            max_iterations=max_iterations,
            state_path=state_path,
        )
        return

    state = MidiState()
    buf = b""
    iteration = 0
    try:
        while True:
            state, buf, _payload = process_once(
                state=state, fd=fd, buf=buf, state_path=state_path
            )
            iteration += 1
            if max_iterations > 0 and iteration >= max_iterations:
                break
            if interval > 0:
                time.sleep(interval)
    finally:
        os.close(fd)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Theramini MIDI listener")
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--state-path", default=str(STATE_FILE))
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    max_iterations = 1 if args.once else args.max_iterations
    try:
        run_daemon(
            device=args.device,
            interval=args.interval,
            max_iterations=max_iterations,
            state_path=args.state_path,
        )
    except KeyboardInterrupt:
        return 130
    return 0


def _run_no_device_loop(
    *,
    interval: float,
    max_iterations: int,
    state_path: str | Path,
) -> None:
    silence_start = time.time()
    iteration = 0
    while True:
        now = time.time()
        state = MidiState(silence_start=silence_start)
        payload = render_state(state, now=now)
        payload["state"] = "no_device"
        write_state(payload, state_path)
        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            break
        if interval > 0:
            time.sleep(interval)


def _stringify_cc_keys(cc_values: Mapping[int, int]) -> dict[str, int]:
    return {str(key): int(value) for key, value in _ordered_items(cc_values)}


def _ordered_items(cc_values: Mapping[int, int]) -> Iterable[tuple[int, int]]:
    return sorted(cc_values.items())


if __name__ == "__main__":
    raise SystemExit(main())
