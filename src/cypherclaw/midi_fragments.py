"""MIDI fragment extraction helpers for CypherClaw intake manifests."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Sequence

MIDI_HEADER_MAGIC: bytes = b"MThd"
TRACK_CHUNK_MAGIC: bytes = b"MTrk"
DRUM_CHANNEL: int = 9

_NOTE_NAMES: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "Bb",
    "B",
)

_CHORD_QUALITIES: tuple[tuple[str, frozenset[int]], ...] = (
    ("major", frozenset((0, 4, 7))),
    ("minor", frozenset((0, 3, 7))),
    ("diminished", frozenset((0, 3, 6))),
    ("augmented", frozenset((0, 4, 8))),
    ("sus2", frozenset((0, 2, 7))),
    ("sus4", frozenset((0, 5, 7))),
)

_CHORD_SUFFIXES: dict[str, str] = {
    "major": "",
    "minor": "m",
    "diminished": "dim",
    "augmented": "aug",
    "sus2": "sus2",
    "sus4": "sus4",
    "unknown": "?",
}

_MAJOR_KEY_NAMES: tuple[str, ...] = (
    "Cb",
    "Gb",
    "Db",
    "Ab",
    "Eb",
    "Bb",
    "F",
    "C",
    "G",
    "D",
    "A",
    "E",
    "B",
    "F#",
    "C#",
)

_MINOR_KEY_NAMES: tuple[str, ...] = (
    "Ab",
    "Eb",
    "Bb",
    "F",
    "C",
    "G",
    "D",
    "A",
    "E",
    "B",
    "F#",
    "C#",
    "G#",
    "D#",
    "A#",
)


_DRUM_ROLES: dict[int, str] = {
    35: "kick",
    36: "kick",
    37: "snare",
    38: "snare",
    39: "clap",
    40: "snare",
    41: "tom",
    42: "hihat",
    43: "tom",
    44: "hihat",
    45: "tom",
    46: "hihat",
    47: "tom",
    48: "tom",
    49: "cymbal",
    50: "tom",
    51: "ride",
    52: "cymbal",
    53: "ride",
    55: "cymbal",
    57: "cymbal",
    59: "ride",
}


@dataclass(frozen=True)
class MidiNote:
    track: int
    channel: int
    note: int
    velocity: int
    start_tick: int
    end_tick: int

    @property
    def duration_ticks(self) -> int:
        return self.end_tick - self.start_tick


@dataclass(frozen=True)
class MidiControlChange:
    track: int
    channel: int
    controller: int
    value: int
    tick: int


@dataclass(frozen=True)
class ParsedMidi:
    division: int
    time_signature: tuple[int, int]
    notes: tuple[MidiNote, ...]
    tempo_bpm: float | None = None
    key_signature: str | None = None
    track_count: int = 0
    control_changes: tuple[MidiControlChange, ...] = ()


def empty_midi_fragments() -> dict[str, object]:
    """Return the JSON-safe empty fragment payload shape."""

    return {
        "melodic_motifs": [],
        "rhythm_cells": [],
        "chord_progressions": [],
        "groove_patterns": [],
    }


def extract_midi_fragments(path: Path | str) -> dict[str, object]:
    """Extract motif, rhythm, chord, and groove fragments from a MIDI file."""

    parsed = _parse_midi_file(Path(path))
    if parsed is None:
        return empty_midi_fragments()

    return {
        "melodic_motifs": _extract_melodic_motifs(parsed.notes),
        "rhythm_cells": _extract_rhythm_cells(parsed.notes),
        "chord_progressions": _extract_chord_progressions(parsed.notes),
        "groove_patterns": _extract_groove_patterns(parsed),
    }


def _parse_midi_file(path: Path) -> ParsedMidi | None:
    try:
        data = path.read_bytes()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None

    if len(data) < 14 or data[:4] != MIDI_HEADER_MAGIC:
        return None

    header_length = int.from_bytes(data[4:8], "big")
    header_end = 8 + header_length
    if header_length < 6 or len(data) < header_end:
        return None

    division = int.from_bytes(data[12:14], "big")
    offset = header_end
    track_index = 0
    notes: list[MidiNote] = []
    control_changes: list[MidiControlChange] = []
    time_signature = [4, 4]
    tempo_holder: list[float | None] = [None]
    key_holder: list[str | None] = [None]

    while offset + 8 <= len(data):
        chunk_type = data[offset : offset + 4]
        chunk_length = int.from_bytes(data[offset + 4 : offset + 8], "big")
        chunk_start = offset + 8
        chunk_end = chunk_start + chunk_length
        if chunk_end > len(data):
            break
        if chunk_type == TRACK_CHUNK_MAGIC:
            _parse_track(
                data[chunk_start:chunk_end],
                track_index=track_index,
                notes=notes,
                control_changes=control_changes,
                time_signature=time_signature,
                tempo_holder=tempo_holder,
                key_holder=key_holder,
            )
            track_index += 1
        offset = chunk_end

    return ParsedMidi(
        division=division,
        time_signature=(time_signature[0], time_signature[1]),
        notes=tuple(sorted(notes, key=lambda n: (n.start_tick, n.track, n.channel, n.note))),
        tempo_bpm=tempo_holder[0],
        key_signature=key_holder[0],
        track_count=track_index,
        control_changes=tuple(
            sorted(
                control_changes,
                key=lambda c: (c.tick, c.track, c.channel, c.controller),
            )
        ),
    )


def _parse_track(
    track_data: bytes,
    *,
    track_index: int,
    notes: list[MidiNote],
    control_changes: list[MidiControlChange],
    time_signature: list[int],
    tempo_holder: list[float | None],
    key_holder: list[str | None],
) -> None:
    offset = 0
    tick = 0
    running_status: int | None = None
    active: DefaultDict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)

    while offset < len(track_data):
        read_delta = _read_varlen(track_data, offset)
        if read_delta is None:
            return
        delta, offset = read_delta
        tick += delta
        if offset >= len(track_data):
            return

        raw = track_data[offset]
        if raw & 0x80:
            status = raw
            offset += 1
            if status < 0xF0:
                running_status = status
        elif running_status is not None:
            status = running_status
        else:
            return

        if status == 0xFF:
            if offset >= len(track_data):
                return
            meta_type = track_data[offset]
            offset += 1
            read_length = _read_varlen(track_data, offset)
            if read_length is None:
                return
            length, offset = read_length
            payload = track_data[offset : offset + length]
            if len(payload) < length:
                return
            offset += length
            if meta_type == 0x2F:
                return
            if meta_type == 0x58 and length >= 2:
                time_signature[0] = max(1, payload[0])
                time_signature[1] = max(1, 2 ** payload[1])
            elif meta_type == 0x51 and length >= 3 and tempo_holder[0] is None:
                mpq = (payload[0] << 16) | (payload[1] << 8) | payload[2]
                if mpq > 0:
                    tempo_holder[0] = round(60_000_000 / mpq, 3)
            elif meta_type == 0x59 and length >= 2 and key_holder[0] is None:
                sf = payload[0] - 256 if payload[0] >= 128 else payload[0]
                mi = payload[1]
                if -7 <= sf <= 7 and mi in (0, 1):
                    root = (
                        _MINOR_KEY_NAMES[sf + 7] if mi == 1 else _MAJOR_KEY_NAMES[sf + 7]
                    )
                    key_holder[0] = f"{root} {'minor' if mi == 1 else 'major'}"
            continue

        if status in (0xF0, 0xF7):
            read_length = _read_varlen(track_data, offset)
            if read_length is None:
                return
            length, offset = read_length
            offset += length
            if offset > len(track_data):
                return
            continue

        event_type = status & 0xF0
        channel = status & 0x0F
        data_len = _channel_data_length(event_type)
        if data_len is None or offset + data_len > len(track_data):
            return
        data1 = track_data[offset]
        data2 = track_data[offset + 1] if data_len == 2 else 0
        offset += data_len

        if event_type == 0xB0:
            control_changes.append(
                MidiControlChange(
                    track=track_index,
                    channel=channel,
                    controller=data1,
                    value=data2,
                    tick=tick,
                )
            )
            continue

        if event_type == 0x90 and data2 > 0:
            active[(channel, data1)].append((tick, data2))
            continue

        if event_type == 0x80 or (event_type == 0x90 and data2 == 0):
            starts = active.get((channel, data1))
            if not starts:
                continue
            start_tick, velocity = starts.pop(0)
            if not starts:
                del active[(channel, data1)]
            if tick > start_tick:
                notes.append(
                    MidiNote(
                        track=track_index,
                        channel=channel,
                        note=data1,
                        velocity=velocity,
                        start_tick=start_tick,
                        end_tick=tick,
                    )
                )


def _read_varlen(data: bytes, offset: int) -> tuple[int, int] | None:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            return None
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
    return None


def _channel_data_length(event_type: int) -> int | None:
    if event_type in (0xC0, 0xD0):
        return 1
    if event_type in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
        return 2
    return None


def _extract_melodic_motifs(notes: Sequence[MidiNote]) -> list[dict[str, object]]:
    motifs: list[dict[str, object]] = []
    for (track, channel), voice_notes in _pitched_voices(notes).items():
        for window in _note_windows(voice_notes):
            if _has_duplicate_onsets(window):
                continue
            note_values = [note.note for note in window]
            durations = [note.duration_ticks for note in window]
            motifs.append(
                {
                    "track": track,
                    "channel": channel,
                    "start_tick": window[0].start_tick,
                    "length": len(window),
                    "notes": note_values,
                    "pitch_classes": [note % 12 for note in note_values],
                    "interval_pattern": [
                        b - a for a, b in zip(note_values, note_values[1:])
                    ],
                    "contour": _contour(note_values),
                    "duration_ticks": durations,
                    "duration_ratios": _ratios(durations),
                }
            )
    return motifs


def _extract_rhythm_cells(notes: Sequence[MidiNote]) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for (track, channel), voice_notes in _pitched_voices(notes).items():
        for window in _note_windows(voice_notes):
            if _has_duplicate_onsets(window):
                continue
            durations = [note.duration_ticks for note in window]
            onset_deltas = [
                b.start_tick - a.start_tick for a, b in zip(window, window[1:])
            ]
            if len(set(durations)) <= 1 and len(set(onset_deltas)) <= 1:
                continue
            cells.append(
                {
                    "track": track,
                    "channel": channel,
                    "start_tick": window[0].start_tick,
                    "length": len(window),
                    "duration_ticks": durations,
                    "duration_ratios": _ratios(durations),
                    "onset_delta_ticks": onset_deltas,
                    "onset_delta_ratios": _ratios(onset_deltas),
                }
            )
    return cells


def _pitched_voices(
    notes: Sequence[MidiNote],
) -> dict[tuple[int, int], list[MidiNote]]:
    voices: DefaultDict[tuple[int, int], list[MidiNote]] = defaultdict(list)
    for note in notes:
        if note.channel == DRUM_CHANNEL:
            continue
        voices[(note.track, note.channel)].append(note)
    return {
        key: sorted(value, key=lambda n: (n.start_tick, n.note))
        for key, value in voices.items()
    }


def _note_windows(notes: Sequence[MidiNote]) -> list[tuple[MidiNote, ...]]:
    windows: list[tuple[MidiNote, ...]] = []
    max_len = min(7, len(notes))
    for length in range(3, max_len + 1):
        for start in range(0, len(notes) - length + 1):
            windows.append(tuple(notes[start : start + length]))
    return windows


def _has_duplicate_onsets(notes: Sequence[MidiNote]) -> bool:
    return len({note.start_tick for note in notes}) != len(notes)


def _contour(notes: Sequence[int]) -> list[str]:
    contour: list[str] = []
    for a, b in zip(notes, notes[1:]):
        if b > a:
            contour.append("up")
        elif b < a:
            contour.append("down")
        else:
            contour.append("same")
    return contour


def _ratios(values: Sequence[int]) -> list[float]:
    positives = [value for value in values if value > 0]
    base = min(positives) if positives else 1
    return [round(value / base, 3) if base else 0.0 for value in values]


def _extract_chord_progressions(
    notes: Sequence[MidiNote],
) -> list[dict[str, object]]:
    by_onset: DefaultDict[int, list[MidiNote]] = defaultdict(list)
    for note in notes:
        if note.channel != DRUM_CHANNEL:
            by_onset[note.start_tick].append(note)

    chords: list[dict[str, object]] = []
    symbols: list[str] = []
    roots: list[str] = []
    qualities: list[str] = []
    start_ticks: list[int] = []
    for start_tick in sorted(by_onset):
        group = by_onset[start_tick]
        if len({note.note % 12 for note in group}) < 3:
            continue
        root_pc, quality = _identify_chord(group)
        root = _NOTE_NAMES[root_pc]
        symbol = f"{root}{_CHORD_SUFFIXES[quality]}"
        notes_at_onset = sorted(note.note for note in group)
        symbols.append(symbol)
        roots.append(root)
        qualities.append(quality)
        start_ticks.append(start_tick)
        chords.append(
            {
                "start_tick": start_tick,
                "root": root,
                "quality": quality,
                "symbol": symbol,
                "notes": notes_at_onset,
                "pitch_classes": sorted({note % 12 for note in notes_at_onset}),
                "duration_ticks": max(note.end_tick for note in group) - start_tick,
            }
        )

    if len(chords) < 2:
        return []

    return [
        {
            "symbols": symbols,
            "roots": roots,
            "qualities": qualities,
            "start_ticks": start_ticks,
            "chords": chords,
        }
    ]


def _identify_chord(notes: Sequence[MidiNote]) -> tuple[int, str]:
    ordered_pcs: list[int] = []
    for note in sorted(notes, key=lambda n: n.note):
        pc = note.note % 12
        if pc not in ordered_pcs:
            ordered_pcs.append(pc)
    pcs = frozenset(ordered_pcs)

    for root in ordered_pcs:
        intervals = frozenset((pc - root) % 12 for pc in pcs)
        for quality, required in _CHORD_QUALITIES:
            if required.issubset(intervals):
                return root, quality

    return ordered_pcs[0], "unknown"


def _extract_groove_patterns(parsed: ParsedMidi) -> list[dict[str, object]]:
    by_voice: DefaultDict[tuple[int, int], list[MidiNote]] = defaultdict(list)
    for note in parsed.notes:
        if note.channel == DRUM_CHANNEL:
            by_voice[(note.track, note.channel)].append(note)

    ticks_per_beat = parsed.division if 0 < parsed.division < 0x8000 else 0
    bar_ticks = _bar_ticks(parsed.division, parsed.time_signature)
    patterns: list[dict[str, object]] = []

    for (track, channel), drum_notes in sorted(by_voice.items()):
        ordered = sorted(drum_notes, key=lambda n: (n.start_tick, n.note))
        notes = [note.note for note in ordered]
        roles = [_DRUM_ROLES.get(note, f"drum_{note}") for note in notes]
        patterns.append(
            {
                "track": track,
                "channel": channel,
                "start_tick": ordered[0].start_tick,
                "drum_notes": notes,
                "drum_roles": roles,
                "pattern": "-".join(roles),
                "beat_positions": [
                    _beat_position(note.start_tick, ticks_per_beat)
                    for note in ordered
                ],
                "bar_positions": [
                    _beat_position(note.start_tick % bar_ticks, ticks_per_beat)
                    if bar_ticks > 0
                    else 0.0
                    for note in ordered
                ],
            }
        )
    return patterns


def _bar_ticks(division: int, time_signature: tuple[int, int]) -> int:
    if not 0 < division < 0x8000:
        return 0
    numerator, denominator = time_signature
    return max(1, round(division * numerator * (4 / denominator)))


def _beat_position(tick: int, ticks_per_beat: int) -> float:
    if ticks_per_beat <= 0:
        return 0.0
    return round(tick / ticks_per_beat, 3)
