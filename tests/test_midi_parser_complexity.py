"""Unit tests covering MIDI parser behavior across complexity tiers (T-018).

Each test synthesizes a Standard MIDI File of a different shape — single track,
multi-track, control changes, pitch bend, and a fully-loaded mixed file — and
asserts that ``_parse_midi_file`` recovers tempo, key signature, tracks, and
control change events as expected.
"""

from __future__ import annotations

from pathlib import Path

from cypherclaw.midi_fragments import (
    MIDI_HEADER_MAGIC,
    MidiControlChange,
    _parse_midi_file,
)


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


def _meta_tempo(bpm: float) -> bytes:
    mpq = round(60_000_000 / bpm)
    return b"\xff\x51\x03" + bytes(
        [(mpq >> 16) & 0xFF, (mpq >> 8) & 0xFF, mpq & 0xFF]
    )


def _meta_key(sf: int, mi: int) -> bytes:
    sf_byte = sf & 0xFF
    return b"\xff\x59\x02" + bytes([sf_byte, mi])


def _meta_time_signature(numerator: int, denominator_pow2: int) -> bytes:
    return b"\xff\x58\x04" + bytes([numerator, denominator_pow2, 24, 8])


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
    fmt = 1 if len(tracks) > 1 else 0
    header = (
        MIDI_HEADER_MAGIC
        + (6).to_bytes(4, "big")
        + fmt.to_bytes(2, "big")
        + len(tracks).to_bytes(2, "big")
        + division.to_bytes(2, "big")
    )
    path.write_bytes(header + b"".join(_track_chunk(track) for track in tracks))


def test_single_track_extracts_tempo_key_and_tracks(tmp_path: Path) -> None:
    target = tmp_path / "single_track.mid"
    _write_midi(
        target,
        [
            [
                (0, _meta_tempo(120.0)),
                (0, _meta_key(0, 0)),
                (0, _meta_time_signature(4, 2)),
                (0, _note_on(0, 60)),
                (240, _note_off(0, 60)),
                (240, _note_on(0, 64)),
                (480, _note_off(0, 64)),
            ],
        ],
    )

    parsed = _parse_midi_file(target)

    assert parsed is not None
    assert parsed.track_count == 1
    assert parsed.tempo_bpm == 120.0
    assert parsed.key_signature == "C major"
    assert parsed.time_signature == (4, 4)
    assert parsed.control_changes == ()
    assert [(note.note, note.duration_ticks) for note in parsed.notes] == [
        (60, 240),
        (64, 240),
    ]


def test_multi_track_counts_each_track_and_merges_notes(tmp_path: Path) -> None:
    target = tmp_path / "multi_track.mid"
    _write_midi(
        target,
        [
            [
                (0, _meta_tempo(90.0)),
                (0, _meta_key(-3, 1)),  # C minor (3 flats, minor)
            ],
            [
                (0, _note_on(0, 60)),
                (480, _note_off(0, 60)),
            ],
            [
                (0, _note_on(1, 67)),
                (480, _note_off(1, 67)),
            ],
            [
                (0, _note_on(2, 72)),
                (480, _note_off(2, 72)),
            ],
        ],
    )

    parsed = _parse_midi_file(target)

    assert parsed is not None
    assert parsed.track_count == 4
    assert parsed.tempo_bpm == 90.0
    assert parsed.key_signature == "C minor"
    tracks_seen = sorted({note.track for note in parsed.notes})
    assert tracks_seen == [1, 2, 3]
    channels_seen = sorted({note.channel for note in parsed.notes})
    assert channels_seen == [0, 1, 2]


def test_control_change_events_are_captured(tmp_path: Path) -> None:
    target = tmp_path / "cc_data.mid"
    _write_midi(
        target,
        [
            [
                (0, _meta_tempo(100.0)),
                (0, _meta_key(2, 0)),  # D major (2 sharps)
                (0, _control_change(0, 7, 100)),  # volume
                (0, _control_change(0, 10, 64)),  # pan
                (240, _control_change(0, 64, 127)),  # sustain on
                (240, _note_on(0, 62)),
                (480, _note_off(0, 62)),
                (480, _control_change(0, 64, 0)),  # sustain off
            ],
        ],
    )

    parsed = _parse_midi_file(target)

    assert parsed is not None
    assert parsed.tempo_bpm == 100.0
    assert parsed.key_signature == "D major"
    assert parsed.control_changes == (
        MidiControlChange(track=0, channel=0, controller=7, value=100, tick=0),
        MidiControlChange(track=0, channel=0, controller=10, value=64, tick=0),
        MidiControlChange(track=0, channel=0, controller=64, value=127, tick=240),
        MidiControlChange(track=0, channel=0, controller=64, value=0, tick=480),
    )


def test_pitch_bend_does_not_corrupt_notes_or_cc(tmp_path: Path) -> None:
    target = tmp_path / "pitch_bend.mid"
    _write_midi(
        target,
        [
            [
                (0, _meta_tempo(140.0)),
                (0, _meta_key(-1, 1)),  # D minor (1 flat, minor)
                (0, _note_on(0, 60)),
                (100, _pitch_bend(0, 0, 64)),  # centered bend
                (200, _pitch_bend(0, 0x7F, 0x7F)),  # max bend
                (300, _pitch_bend(0, 0, 64)),
                (480, _note_off(0, 60)),
                (480, _control_change(0, 1, 90)),  # mod wheel after bends
            ],
        ],
    )

    parsed = _parse_midi_file(target)

    assert parsed is not None
    assert parsed.tempo_bpm == 140.0
    assert parsed.key_signature == "D minor"
    # The pitch-bend stream must not be misparsed as notes or CCs.
    assert len(parsed.notes) == 1
    note = parsed.notes[0]
    assert note.note == 60
    assert note.duration_ticks == 480
    assert parsed.control_changes == (
        MidiControlChange(track=0, channel=0, controller=1, value=90, tick=480),
    )


def test_complex_file_with_tempo_key_tracks_and_cc(tmp_path: Path) -> None:
    target = tmp_path / "complex.mid"
    _write_midi(
        target,
        [
            [
                (0, _meta_tempo(96.0)),
                (0, _meta_key(1, 0)),  # G major
                (0, _meta_time_signature(3, 2)),  # 3/4
            ],
            [
                (0, _control_change(0, 7, 110)),
                (0, _note_on(0, 67)),
                (480, _note_off(0, 67)),
                (480, _note_on(0, 71)),
                (960, _note_off(0, 71)),
            ],
            [
                (0, _control_change(1, 10, 32)),
                (0, _pitch_bend(1, 0, 64)),
                (0, _note_on(1, 55)),
                (960, _note_off(1, 55)),
            ],
        ],
        division=240,
    )

    parsed = _parse_midi_file(target)

    assert parsed is not None
    assert parsed.division == 240
    assert parsed.track_count == 3
    assert parsed.tempo_bpm == 96.0
    assert parsed.key_signature == "G major"
    assert parsed.time_signature == (3, 4)

    # Two tracks contribute notes; the metadata track contributes none.
    note_tracks = sorted({note.track for note in parsed.notes})
    assert note_tracks == [1, 2]
    assert len(parsed.notes) == 3

    cc_pairs = [(cc.track, cc.controller, cc.value) for cc in parsed.control_changes]
    assert (1, 7, 110) in cc_pairs
    assert (2, 10, 32) in cc_pairs
    # Only true CCs should appear — no pitch-bend or note bytes leaking in.
    assert all(0 <= cc.controller <= 127 for cc in parsed.control_changes)
    assert len(parsed.control_changes) == 2
