"""Tests for faithful-transmission MIDI loading (T-017a)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from cypherclaw import midi_intake_daemon as mod
from cypherclaw.midi_loader import FaithfulMidiEvent, load_faithful_midi_events


def _varlen(value: int) -> bytes:
    if value < 0:
        raise ValueError("varlen value must be non-negative")
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


def _control_change(channel: int, controller: int, value: int) -> bytes:
    return bytes([0xB0 | channel, controller, value])


def _pitch_bend(channel: int, lsb: int, msb: int) -> bytes:
    return bytes([0xE0 | channel, lsb, msb])


def _program_change(channel: int, program: int) -> bytes:
    return bytes([0xC0 | channel, program])


def _track_chunk(events: list[tuple[int, bytes]]) -> bytes:
    track = bytearray()
    last_tick = 0
    ordered = sorted(enumerate(events), key=lambda item: (item[1][0], item[0]))
    for _index, (tick, message) in ordered:
        track.extend(_varlen(tick - last_tick))
        track.extend(message)
        last_tick = tick
    track.extend(_varlen(0))
    track.extend(b"\xff\x2f\x00")
    return b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)


def _write_midi(
    path: Path,
    tracks: list[list[tuple[int, bytes]]],
    *,
    division: int = 480,
) -> None:
    header = (
        mod.MIDI_HEADER_MAGIC
        + (6).to_bytes(4, "big")
        + (1 if len(tracks) > 1 else 0).to_bytes(2, "big")
        + len(tracks).to_bytes(2, "big")
        + division.to_bytes(2, "big")
    )
    path.write_bytes(header + b"".join(_track_chunk(track) for track in tracks))


def _event_dicts(events: tuple[FaithfulMidiEvent, ...]) -> list[dict[str, int]]:
    return [event.to_dict() for event in events]


def test_load_faithful_midi_events_returns_ordered_pitch_duration_velocity(
    tmp_path: Path,
) -> None:
    target = tmp_path / "line.mid"
    _write_midi(
        target,
        [
            [
                (0, _note_on(0, 60, 81)),
                (120, _note_off(0, 60)),
                (120, _note_on(0, 64, 72)),
                (360, _note_off(0, 64)),
                (360, _note_on(0, 67, 110)),
                (480, _note_off(0, 67)),
            ],
        ],
    )

    events = load_faithful_midi_events(target)

    assert events == (
        FaithfulMidiEvent(pitch=60, duration=120, velocity=81),
        FaithfulMidiEvent(pitch=64, duration=240, velocity=72),
        FaithfulMidiEvent(pitch=67, duration=120, velocity=110),
    )
    assert _event_dicts(events) == [
        {"pitch": 60, "duration": 120, "velocity": 81},
        {"pitch": 64, "duration": 240, "velocity": 72},
        {"pitch": 67, "duration": 120, "velocity": 110},
    ]


def test_load_faithful_midi_events_merges_tracks_and_ignores_control_data(
    tmp_path: Path,
) -> None:
    target = tmp_path / "arrangement.mid"
    _write_midi(
        target,
        [
            [
                (0, _program_change(0, 12)),
                (0, _note_on(0, 72, 70)),
                (20, _control_change(0, 64, 127)),
                (180, _note_off(0, 72)),
            ],
            [
                (60, _pitch_bend(1, 0, 64)),
                (60, _note_on(1, 55, 101)),
                (300, _note_on(1, 55, 0)),
                (300, _note_on(1, 59, 91)),
                (420, _note_off(1, 59)),
            ],
        ],
    )

    events = load_faithful_midi_events(target)

    assert events == (
        FaithfulMidiEvent(pitch=72, duration=180, velocity=70),
        FaithfulMidiEvent(pitch=55, duration=240, velocity=101),
        FaithfulMidiEvent(pitch=59, duration=120, velocity=91),
    )


def test_process_midi_file_faithful_mode_writes_events_and_bypasses_fragments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "faithful.mid"
    _write_midi(
        target,
        [
            [
                (0, _note_on(0, 60, 99)),
                (96, _note_off(0, 60)),
                (96, _note_on(0, 62, 64)),
                (240, _note_off(0, 62)),
            ],
        ],
        division=96,
    )

    def fail_extract(_path: Path | str) -> dict[str, object]:
        raise AssertionError("faithful mode must bypass fragment extraction")

    monkeypatch.setattr(mod, "extract_midi_fragments", fail_extract)

    event = mod.process_midi_file(target, faithful_transmission=True)

    manifest_path = Path(str(event["destination"])).with_suffix(".mid.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "faithful_transmission"
    assert manifest["faithful_events"] == [
        {"pitch": 60, "duration": 96, "velocity": 99},
        {"pitch": 62, "duration": 144, "velocity": 64},
    ]
    assert manifest["fragments"] == mod.empty_midi_fragments()


def test_process_midi_file_default_mode_keeps_fragment_extraction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "fragments.mid"
    _write_midi(
        target,
        [
            [
                (0, _note_on(0, 60, 99)),
                (96, _note_off(0, 60)),
                (96, _note_on(0, 62, 64)),
                (240, _note_off(0, 62)),
            ],
        ],
        division=96,
    )
    fragments = {
        "melodic_motifs": [{"notes": [60, 62]}],
        "rhythm_cells": [],
        "chord_progressions": [],
        "groove_patterns": [],
    }
    calls: list[Path] = []

    def fake_extract(path: Path | str) -> dict[str, object]:
        calls.append(Path(path))
        return fragments

    monkeypatch.setattr(mod, "extract_midi_fragments", fake_extract)

    event = mod.process_midi_file(target)

    manifest_path = Path(str(event["destination"])).with_suffix(".mid.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "fragment_extraction"
    assert manifest["fragments"] == fragments
    assert "faithful_events" not in manifest
    assert calls == [target]


def test_parse_args_and_main_wire_faithful_transmission_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    args = mod.parse_args(["--faithful-transmission"])
    assert args.faithful_transmission is True

    call_order: list[str] = []
    captured_dispatch: dict[str, object] = {}
    process_calls: list[tuple[Path, bool]] = []

    def fake_bootstrap_identity() -> None:
        call_order.append("bootstrap_identity")

    class FakeAnnouncer:
        def maybe_announce(self) -> None:
            call_order.append("maybe_announce")

    def fake_watch_loop(
        watch_dir: Path | str,
        stop_event: threading.Event,
        **kwargs: object,
    ) -> None:
        call_order.append("watch_loop")
        captured_dispatch["dispatch"] = kwargs["dispatch"]

    def fake_process_midi_file(
        path: Path | str,
        *,
        faithful_transmission: bool = False,
        **_kwargs: object,
    ) -> dict[str, object]:
        process_calls.append((Path(path), faithful_transmission))
        return {"status": "processed"}

    monkeypatch.setattr(mod, "bootstrap_identity", fake_bootstrap_identity)
    monkeypatch.setattr(mod, "FirstBootAnnouncer", FakeAnnouncer)
    monkeypatch.setattr(mod, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod, "watch_loop", fake_watch_loop)
    monkeypatch.setattr(mod, "process_midi_file", fake_process_midi_file)

    assert (
        mod.main(
            ["--watch-dir", str(tmp_path), "--faithful-transmission"],
            stop_event=threading.Event(),
        )
        == 0
    )

    dispatch = captured_dispatch["dispatch"]
    assert callable(dispatch)
    dispatch(tmp_path / "source.mid")
    assert process_calls == [(tmp_path / "source.mid", True)]
    assert call_order == ["bootstrap_identity", "maybe_announce", "watch_loop"]
