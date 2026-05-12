"""MIDI keyboard listener for CypherClaw's keyboard grimoire.

Reads live MIDI data from the in-room keyboards, tracks notes and pedals, and
writes a canonical `/tmp/midi_keyboard_state.json` for the composer.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

from senseweave.harmonic_planner import keyboard_grimoire_from_midi_state
from senseweave.midi_state import MidiState, note_to_name
from senseweave.phrase_capture_runtime import ActiveSongPhraseCapture
from senseweave.phrase_tracker import PhraseTracker

STATE_FILE = Path("/tmp/midi_keyboard_state.json")
_KEYBOARD_HINTS = ("akai", "max25", "microkey", "keyboard")
_IGNORE_HINTS = ("theremini", "perform-ve", "scarlett")


def midi_to_freq(note: int) -> float:
    return 440.0 * (2 ** ((note - 69) / 12.0))


def write_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(str(tmp), str(STATE_FILE))


def discover_keyboard_devices(amidi_listing: str | None = None) -> list[str]:
    """Return `/dev/midi*` devices matching the keyboard controllers."""

    verify_device_paths = amidi_listing is None
    if amidi_listing is None:
        try:
            result = subprocess.run(
                ["amidi", "-l"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            amidi_listing = result.stdout
        except Exception:
            amidi_listing = ""

    devices: list[str] = []
    for line in amidi_listing.splitlines():
        line = line.strip()
        if not line.startswith("IO  hw:"):
            continue
        lowered = line.lower()
        if any(hint in lowered for hint in _IGNORE_HINTS):
            continue
        if not any(hint in lowered for hint in _KEYBOARD_HINTS):
            continue
        try:
            hw = line.split()[1]
            card = int(hw.split(",")[0].split(":")[1])
        except Exception:
            continue
        path = f"/dev/midi{card}"
        if (not verify_device_paths or os.path.exists(path)) and path not in devices:
            devices.append(path)

    if devices:
        return sorted(devices)

    fallback = [
        path
        for path in sorted(Path("/dev").glob("midi*"))
        if path.name not in {"midi3", "midi8"}
    ]
    return [str(path) for path in fallback]


def apply_midi_message(
    midi_state: MidiState,
    active_notes: dict[int, dict[str, float | int | str]],
    recent_pedal_events: list[tuple[float, bool]],
    *,
    status: int,
    data1: int,
    data2: int,
    now: float,
    last_activity: float,
) -> float:
    """Apply one decoded MIDI message into the tracked keyboard state."""

    msg_type = status & 0xF0
    if msg_type == 0x90:
        note, velocity = data1, data2
        midi_state.note_on(note, velocity)
        if velocity > 0:
            active_notes[note] = {
                "freq": midi_to_freq(note),
                "name": note_to_name(note),
                "velocity": velocity,
                "time": now,
            }
            return now
        active_notes.pop(note, None)
        return last_activity
    if msg_type == 0x80:
        note = data1
        midi_state.note_off(note)
        active_notes.pop(note, None)
        return last_activity
    if msg_type == 0xB0:
        cc, value = data1, data2
        previous_sustain = midi_state.sustain_pedal
        midi_state.control_change(cc, value)
        if cc == 64 and midi_state.sustain_pedal != previous_sustain:
            recent_pedal_events.append((now, midi_state.sustain_pedal))
            del recent_pedal_events[:-8]
        return now
    if msg_type == 0xE0:
        midi_state.pitch_bend_change((data2 << 7) | data1)
        return now
    if msg_type == 0xD0:
        return now
    if msg_type == 0xC0:
        return now
    return last_activity


def build_state(
    midi_state: MidiState,
    active_notes: dict[int, dict[str, float | int | str]],
    recent_pedal_events: list[tuple[float, bool]],
    *,
    last_activity: float,
    now: float,
    active_devices: list[str] | None = None,
    phrase_tracker: PhraseTracker | None = None,
) -> dict:
    """Build the canonical keyboard state payload."""

    active = [
        active_notes[note]
        for note in sorted(active_notes)
        if now - float(active_notes[note]["time"]) < 8.0
    ]
    playing = len(active) > 0
    phrase_event = phrase_tracker.update(playing, now) if phrase_tracker else None
    state = {
        "timestamp": now,
        "playing": playing,
        "notes_on": sorted(note for note in active_notes if now - float(active_notes[note]["time"]) < 8.0),
        "notes": [str(note["name"]) for note in active],
        "freqs": [float(note["freq"]) for note in active],
        "velocities": [int(note["velocity"]) for note in active],
        "last_activity": last_activity,
        "recent_pedal_events": [(round(ts, 4), bool(value)) for ts, value in recent_pedal_events[-8:]],
        "active_devices": active_devices or [],
    }
    midi_snapshot = midi_state.to_dict()
    for key in (
        "last_note",
        "last_velocity",
        "sustain_pedal",
        "expression",
        "pitch_bend",
        "mod_wheel",
        "volume",
        "activity_rate",
    ):
        state[key] = midi_snapshot[key]
    grimoire = keyboard_grimoire_from_midi_state(state, now=now)
    state.update(grimoire)
    if phrase_tracker is not None:
        state["phrase_active"] = phrase_tracker.phrase_active
        state["phrase_duration_seconds"] = round(phrase_tracker.play_duration(now), 3)
        if phrase_event is not None:
            state["phrase_event"] = phrase_event
            print(
                f"phrase_event: {phrase_event} "
                f"duration={state['phrase_duration_seconds']}s",
                flush=True,
            )
    return state


def _open_devices(devices: list[str]) -> dict[str, int]:
    fds: dict[str, int] = {}
    for dev in devices:
        try:
            fds[dev] = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
    return fds


def _close_device(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def capture_phrase_from_state(
    capture: ActiveSongPhraseCapture | None,
    *,
    chunk: bytes | None,
    state: Mapping[str, Any],
) -> Path | None:
    """Feed the active-song phrase capture wrapper from serialized state."""
    if capture is None:
        return None
    return capture.feed(
        chunk,
        bool(state.get("playing", False)),
        float(state.get("timestamp", 0.0) or 0.0),
    )


def run(devices: list[str] | None = None) -> None:
    print("MIDI keyboard listener online", flush=True)

    midi_state = MidiState()
    active_notes: dict[int, dict[str, float | int | str]] = {}
    recent_pedal_events: list[tuple[float, bool]] = []
    last_activity = 0.0
    fds: dict[str, int] = {}
    phrase_tracker = PhraseTracker()
    phrase_capture = ActiveSongPhraseCapture("keyboard")

    while True:
        if not fds:
            target_devices = devices or discover_keyboard_devices()
            fds = _open_devices(target_devices)
            write_state(
                build_state(
                    midi_state,
                    active_notes,
                    recent_pedal_events,
                    last_activity=last_activity,
                    now=time.time(),
                    active_devices=sorted(fds),
                    phrase_tracker=phrase_tracker,
                )
            )
            if not fds:
                time.sleep(1.0)
                continue

        capture_chunk: bytes | None = None
        for dev, fd in list(fds.items()):
            try:
                data = os.read(fd, 256)
            except BlockingIOError:
                continue
            except OSError:
                _close_device(fd)
                del fds[dev]
                continue
            if not data:
                continue
            capture_chunk = (capture_chunk or b"") + data

            now = time.time()
            i = 0
            while i < len(data):
                status = data[i]
                if status & 0x80 == 0:
                    i += 1
                    continue
                msg_type = status & 0xF0
                if msg_type in (0x90, 0x80, 0xB0, 0xE0) and i + 2 < len(data):
                    last_activity = apply_midi_message(
                        midi_state,
                        active_notes,
                        recent_pedal_events,
                        status=status,
                        data1=data[i + 1],
                        data2=data[i + 2],
                        now=now,
                        last_activity=last_activity,
                    )
                    i += 3
                    continue
                if msg_type in (0xC0, 0xD0) and i + 1 < len(data):
                    last_activity = apply_midi_message(
                        midi_state,
                        active_notes,
                        recent_pedal_events,
                        status=status,
                        data1=data[i + 1],
                        data2=0,
                        now=now,
                        last_activity=last_activity,
                    )
                    i += 2
                    continue
                i += 1

        now = time.time()
        active_notes = {
            note: info
            for note, info in active_notes.items()
            if now - float(info["time"]) < 8.0
        }
        write_state(
            state := build_state(
                midi_state,
                active_notes,
                recent_pedal_events,
                last_activity=last_activity,
                now=now,
                active_devices=sorted(fds),
                phrase_tracker=phrase_tracker,
            )
        )
        capture_phrase_from_state(
            phrase_capture,
            chunk=capture_chunk,
            state=state,
        )
        time.sleep(0.05)


if __name__ == "__main__":
    run()
