"""Tests for MIDI fragment extraction from hand-crafted Standard MIDI files."""

from __future__ import annotations

import json
from pathlib import Path

from cypherclaw import midi_intake_daemon as mod


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


def _write_midi(
    path: Path,
    events: list[tuple[int, bytes]],
    *,
    division: int = 480,
) -> None:
    track = bytearray()
    last_tick = 0
    ordered = sorted(enumerate(events), key=lambda item: (item[1][0], item[0]))
    for _index, (tick, message) in ordered:
        track.extend(_varlen(tick - last_tick))
        track.extend(message)
        last_tick = tick
    track.extend(_varlen(0))
    track.extend(b"\xff\x2f\x00")

    header = (
        mod.MIDI_HEADER_MAGIC
        + (6).to_bytes(4, "big")
        + (0).to_bytes(2, "big")
        + (1).to_bytes(2, "big")
        + division.to_bytes(2, "big")
    )
    path.write_bytes(header + b"MTrk" + len(track).to_bytes(4, "big") + bytes(track))


def test_extracts_melodic_motifs_and_rhythm_cells_from_handcrafted_midi(
    tmp_path: Path,
) -> None:
    target = tmp_path / "melody.mid"
    events: list[tuple[int, bytes]] = []
    tick = 0
    for note, duration in ((60, 120), (62, 120), (64, 240), (67, 240), (69, 120)):
        events.append((tick, _note_on(0, note)))
        events.append((tick + duration, _note_off(0, note)))
        tick += duration
    _write_midi(target, events)

    fragments = mod.extract_midi_fragments(target)

    motifs = fragments["melodic_motifs"]
    assert all(3 <= motif["length"] <= 7 for motif in motifs)
    assert any(
        motif["notes"] == [60, 62, 64, 67]
        and motif["pitch_classes"] == [0, 2, 4, 7]
        and motif["interval_pattern"] == [2, 2, 3]
        and motif["contour"] == ["up", "up", "up"]
        and motif["duration_ticks"] == [120, 120, 240, 240]
        and motif["duration_ratios"] == [1.0, 1.0, 2.0, 2.0]
        for motif in motifs
    )

    rhythm_cells = fragments["rhythm_cells"]
    assert any(
        cell["duration_ticks"] == [120, 120, 240, 240]
        and cell["duration_ratios"] == [1.0, 1.0, 2.0, 2.0]
        and cell["onset_delta_ticks"] == [120, 120, 240]
        and cell["onset_delta_ratios"] == [1.0, 1.0, 2.0]
        for cell in rhythm_cells
    )


def test_extracts_chord_progression_from_block_chords(tmp_path: Path) -> None:
    target = tmp_path / "chords.mid"
    events: list[tuple[int, bytes]] = []

    def add_chord(start_tick: int, notes: tuple[int, int, int]) -> None:
        for note in notes:
            events.append((start_tick, _note_on(0, note)))
        for note in notes:
            events.append((start_tick + 480, _note_off(0, note)))

    add_chord(0, (60, 64, 67))
    add_chord(480, (65, 69, 72))
    add_chord(960, (67, 71, 74))
    add_chord(1440, (60, 64, 67))
    _write_midi(target, events)

    fragments = mod.extract_midi_fragments(target)

    progressions = fragments["chord_progressions"]
    assert len(progressions) == 1
    progression = progressions[0]
    assert progression["symbols"] == ["C", "F", "G", "C"]
    assert progression["roots"] == ["C", "F", "G", "C"]
    assert progression["qualities"] == ["major", "major", "major", "major"]
    assert progression["start_ticks"] == [0, 480, 960, 1440]


def test_extracts_groove_pattern_from_channel_ten_drums(tmp_path: Path) -> None:
    target = tmp_path / "drums.mid"
    events: list[tuple[int, bytes]] = []
    for tick, note in ((0, 36), (240, 42), (480, 38), (720, 42)):
        events.append((tick, _note_on(9, note)))
        events.append((tick + 60, _note_off(9, note)))
    _write_midi(target, events)

    fragments = mod.extract_midi_fragments(target)

    grooves = fragments["groove_patterns"]
    assert len(grooves) == 1
    groove = grooves[0]
    assert groove["drum_notes"] == [36, 42, 38, 42]
    assert groove["drum_roles"] == ["kick", "hihat", "snare", "hihat"]
    assert groove["pattern"] == "kick-hihat-snare-hihat"
    assert groove["beat_positions"] == [0.0, 0.5, 1.0, 1.5]
    assert groove["bar_positions"] == [0.0, 0.5, 1.0, 1.5]


def test_process_midi_file_writes_fragments_into_manifest(tmp_path: Path) -> None:
    target = tmp_path / "manifest.mid"
    events: list[tuple[int, bytes]] = []
    tick = 0
    for note, duration in ((60, 120), (62, 120), (64, 240), (67, 240)):
        events.append((tick, _note_on(0, note)))
        events.append((tick + duration, _note_off(0, note)))
        tick += duration
    _write_midi(target, events)

    event = mod.process_midi_file(target)

    manifest_path = Path(str(event["destination"])).with_suffix(".mid.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fragments = manifest["fragments"]
    assert any(
        motif["notes"] == [60, 62, 64, 67]
        for motif in fragments["melodic_motifs"]
    )
    assert any(
        cell["duration_ticks"] == [120, 120, 240, 240]
        for cell in fragments["rhythm_cells"]
    )
