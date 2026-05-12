"""Depth-2 Theramini MIDI listener — locked test surface for frac-0036."""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest


TOOLS_PATH = Path(__file__).parent.parent / "my-claw" / "tools"


def test_module_import_is_side_effect_free() -> None:
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(TOOLS_PATH)!r})
        import theramini_midi as midi
        expected = (
            "midi_to_freq",
            "midi_to_name",
            "parse_midi_messages",
            "apply_midi_event",
            "process_buffer",
            "render_state",
            "write_state",
            "read_midi_buffer",
            "process_once",
            "run_daemon",
        )
        print(",".join(name for name in expected if hasattr(midi, name)))
        """
    )

    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"theramini_midi import did not return: {exc}")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().split(",") == [
        "midi_to_freq",
        "midi_to_name",
        "parse_midi_messages",
        "apply_midi_event",
        "process_buffer",
        "render_state",
        "write_state",
        "read_midi_buffer",
        "process_once",
        "run_daemon",
    ]


def _midi_module() -> ModuleType:
    if str(TOOLS_PATH) not in sys.path:
        sys.path.insert(0, str(TOOLS_PATH))
    return importlib.import_module("theramini_midi")


def test_parse_and_apply_midi_events() -> None:
    midi = _midi_module()

    # 0x90 60 100 = Note On C4 vel 100
    # 0xB0 01 064 = CC mod_wheel = 64
    # 0xE0 00 040h(=64) = pitch bend lsb=0 msb=64 -> 8192
    # 0x80 60 000 = Note Off C4
    # trailing partial 0x90 (incomplete) should remain in buffer
    buf = bytes([0x90, 60, 100, 0xB0, 1, 64, 0xE0, 0x00, 0x40, 0x80, 60, 0, 0x90])
    events, remaining = midi.parse_midi_messages(buf)

    assert remaining == bytes([0x90])
    kinds = [event.kind for event in events]
    assert kinds == ["note_on", "cc", "pitch_bend", "note_off"]
    assert events[0].data1 == 60
    assert events[0].data2 == 100
    assert events[1].data1 == 1
    assert events[1].data2 == 64
    assert events[2].data1 == 0
    assert events[2].data2 == 64
    assert events[3].data1 == 60
    assert events[3].data2 == 0

    # frozen dataclass
    assert dataclasses.is_dataclass(events[0])
    assert getattr(events[0], "__dataclass_params__").frozen

    state = midi.MidiState()
    state = midi.apply_midi_event(state, events[0], now=100.0)
    assert state.current_note == 60
    assert state.last_note_time == 100.0
    assert state.silence_start == 0.0

    state = midi.apply_midi_event(state, events[1], now=100.1)
    assert state.cc_values[1] == 64

    state = midi.apply_midi_event(state, events[2], now=100.2)
    assert state.pitch_bend == 8192

    state = midi.apply_midi_event(state, events[3], now=100.3)
    assert state.current_note is None
    assert state.silence_start == 100.3


def test_render_state_for_active_note() -> None:
    midi = _midi_module()
    state = midi.MidiState(
        current_note=69,  # A4
        last_note_time=500.0,
        silence_start=0.0,
        cc_values={1: 32, 11: 100},
        pitch_bend=8192,
    )

    payload = midi.render_state(state, now=500.5)

    assert payload["is_playing"] is True
    assert payload["pitch_hz"] == pytest.approx(440.0)
    assert payload["pitch_note"] == "A4"
    assert payload["pitch_confidence"] == 1.0
    assert payload["state"] == "playing"
    assert payload["consecutive_silence_ms"] == 0
    assert payload["midi_cc"]["raw"] == {"1": 32, "11": 100}
    assert payload["midi_cc"]["mod_wheel"] == 32
    assert payload["midi_cc"]["expression"] == 100
    assert payload["pitch_bend"] == 8192
    assert payload["timestamp"] == pytest.approx(500.5)


def test_render_state_for_silent_window() -> None:
    midi = _midi_module()
    state = midi.MidiState(
        current_note=None,
        last_note_time=400.0,
        silence_start=400.5,
        cc_values={},
        pitch_bend=8192,
    )

    payload = midi.render_state(state, now=403.5)

    assert payload["is_playing"] is False
    assert payload["pitch_hz"] is None
    assert payload["pitch_note"] is None
    assert payload["pitch_confidence"] == 0.0
    assert payload["state"] == "silence"
    assert payload["consecutive_silence_ms"] == 3000
    assert payload["conversation"]["phase"] == "listening"


def test_process_once_writes_state_for_note_on(tmp_path: Path) -> None:
    midi = _midi_module()
    state_path = tmp_path / "theramini_state.json"

    read_fd, write_fd = os.pipe()
    try:
        os.set_blocking(read_fd, False)
        # Note On C4 vel 100
        os.write(write_fd, bytes([0x90, 60, 100]))

        new_state, remaining, payload = midi.process_once(
            state=midi.MidiState(),
            fd=read_fd,
            buf=b"",
            now=1234.0,
            state_path=state_path,
        )
    finally:
        os.close(read_fd)
        os.close(write_fd)

    assert new_state.current_note == 60
    assert new_state.last_note_time == 1234.0
    assert remaining == b""
    assert payload["is_playing"] is True
    assert payload["pitch_note"] == "C4"
    assert payload["pitch_hz"] == pytest.approx(261.63, abs=0.1)

    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["is_playing"] is True
    assert on_disk["pitch_note"] == "C4"
    assert on_disk["timestamp"] == pytest.approx(1234.0)


def test_run_daemon_writes_no_device_state(tmp_path: Path) -> None:
    midi = _midi_module()
    state_path = tmp_path / "theramini_state.json"
    missing_device = tmp_path / "does_not_exist_midi"

    midi.run_daemon(
        device=str(missing_device),
        interval=0.0,
        max_iterations=1,
        state_path=state_path,
    )

    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["is_playing"] is False
    assert on_disk["pitch_hz"] is None
    assert on_disk["pitch_note"] is None
    assert on_disk["state"] == "no_device"
    assert "consecutive_silence_ms" in on_disk


def test_theramini_midi_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/theramini_midi.py")
    assert result.depth >= 2, result.reason
