"""Tests for PhraseCaptureWriter — buffered phrase persistence."""
from __future__ import annotations

import json
import os
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.phrase_capture import (
    SAMPLE_METADATA_SCHEMA,
    PhraseCaptureWriter,
    validate_sample_metadata,
)
from senseweave.phrase_tracker import PhraseTracker


def _drive(
    writer: PhraseCaptureWriter,
    stream,
) -> list[Path]:
    """Drive a mocked input stream: iterable of (chunk, is_playing, now) tuples."""
    written: list[Path] = []
    for chunk, is_playing, now in stream:
        path = writer.feed(chunk, is_playing, now)
        if path is not None:
            written.append(path)
    return written


def _midi_note_on(note: int, velocity: int = 64) -> bytes:
    return bytes([0x90, note, velocity])


def _midi_note_off(note: int) -> bytes:
    return bytes([0x80, note, 0])


def _qualifying_keyboard_stream():
    note = _midi_note_on(60)
    off = _midi_note_off(60)
    yield (note, True, 100.0)
    yield (note, True, 102.0)
    yield (note, True, 104.0)
    yield (note, True, 105.0)  # phrase_started fires here
    yield (note, True, 106.0)
    yield (off, False, 107.0)  # phrase_ended fires here


def test_keyboard_phrase_writes_smf_on_phrase_ended(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    written = _drive(writer, _qualifying_keyboard_stream())

    assert len(written) == 1
    path = written[0]
    assert path.parent == tmp_path / "keyboard"
    assert path.suffix == ".mid"
    assert path.name.startswith("keyboard_")

    data = path.read_bytes()
    assert data.startswith(b"MThd")
    assert b"MTrk" in data
    # Note-on and note-off bytes both made it into the track.
    assert bytes([0x90, 60, 64]) in data
    assert bytes([0x80, 60, 0]) in data


def test_theramini_phrase_writes_wav_on_phrase_ended(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("theramini", tmp_path, sample_rate=8000)
    sr = 8000
    samples_per_tick = sr  # 1-second chunks
    tone = (np.sin(2 * np.pi * 440 * np.arange(samples_per_tick) / sr)).astype(np.float32)

    stream = [
        (tone, True, 0.0),
        (tone, True, 1.0),
        (tone, True, 2.0),
        (tone, True, 3.0),
        (tone, True, 4.0),
        (tone, True, 5.0),  # phrase_started
        (tone, True, 6.0),
        (None, False, 7.0),  # phrase_ended
    ]
    written = _drive(writer, stream)

    assert len(written) == 1
    path = written[0]
    assert path.parent == tmp_path / "theramini"
    assert path.suffix == ".wav"

    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == sr
        # 7 chunks of `sr` samples each were buffered (the False tick has no chunk).
        assert handle.getnframes() == samples_per_tick * 7


def test_subthreshold_burst_writes_nothing(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    stream = [
        (_midi_note_on(60), True, 0.0),
        (_midi_note_on(62), True, 1.5),
        (None, False, 2.5),  # only 2.5s — under the 5s threshold
    ]
    written = _drive(writer, stream)
    assert written == []
    assert not (tmp_path / "keyboard").exists() or list((tmp_path / "keyboard").iterdir()) == []
    assert writer.buffered_chunks == 0


def test_buffer_resets_between_phrases(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    note = _midi_note_on(60)
    stream = [
        (note, True, 0.0),
        (note, True, 5.0),
        (None, False, 6.0),
        (note, True, 100.0),
        (note, True, 105.0),
        (None, False, 106.0),
    ]
    written = _drive(writer, stream)
    assert len(written) == 2
    assert written[0] != written[1]
    assert writer.buffered_chunks == 0


def test_subthreshold_burst_does_not_taint_next_phrase(tmp_path: Path) -> None:
    """Bytes from a dropped burst must not appear in the next written phrase."""
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    burst_note = _midi_note_on(70, 30)
    real_note = _midi_note_on(60, 100)

    stream = [
        (burst_note, True, 0.0),
        (None, False, 2.0),  # short burst, dropped
        (real_note, True, 10.0),
        (real_note, True, 15.0),
        (None, False, 16.0),  # phrase_ended
    ]
    written = _drive(writer, stream)
    assert len(written) == 1
    data = written[0].read_bytes()
    assert bytes([0x90, 60, 100]) in data
    assert bytes([0x90, 70, 30]) not in data


def test_filename_contains_utc_timestamp(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    end_unix = datetime(2026, 4, 25, 18, 39, 59, tzinfo=timezone.utc).timestamp()
    stream = [
        (_midi_note_on(60), True, end_unix - 6.0),
        (_midi_note_on(60), True, end_unix - 1.0),
        (None, False, end_unix),
    ]
    written = _drive(writer, stream)
    assert len(written) == 1
    assert "20260425T183959Z" in written[0].name


def test_unknown_source_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        PhraseCaptureWriter("contact", tmp_path)  # type: ignore[arg-type]


def test_uses_injected_tracker_threshold(tmp_path: Path) -> None:
    tracker = PhraseTracker(threshold_seconds=2.0)
    writer = PhraseCaptureWriter("keyboard", tmp_path, tracker=tracker)
    stream = [
        (_midi_note_on(60), True, 0.0),
        (_midi_note_on(60), True, 2.0),  # phrase_started at custom threshold
        (None, False, 3.0),
    ]
    written = _drive(writer, stream)
    assert len(written) == 1


def test_idle_ticks_before_play_emit_nothing(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("theramini", tmp_path)
    silence = np.zeros(8, dtype=np.float32)
    stream = [
        (silence, False, 0.0),
        (None, False, 1.0),
        (silence, False, 100.0),
    ]
    written = _drive(writer, stream)
    assert written == []
    assert writer.buffered_chunks == 0


def test_smf_track_contains_tempo_and_end_meta(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    stream = [
        (_midi_note_on(60), True, 0.0),
        (_midi_note_on(60), True, 5.0),
        (None, False, 6.0),
    ]
    written = _drive(writer, stream)
    data = written[0].read_bytes()
    # Tempo meta: FF 51 03 <3-byte tempo>
    assert b"\xFF\x51\x03" in data
    # End-of-track meta: FF 2F 00
    assert data.endswith(b"\xFF\x2F\x00")


def _read_sidecar(audio_path: Path) -> dict:
    sidecar = audio_path.with_suffix(".json")
    assert sidecar.exists(), f"sidecar missing for {audio_path}"
    return json.loads(sidecar.read_text())


def test_sidecar_metadata_written_with_complete_schema(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    written = _drive(writer, _qualifying_keyboard_stream())
    meta = _read_sidecar(written[0])

    # Tag completeness — every schema key is present and non-extra.
    assert set(meta) == set(SAMPLE_METADATA_SCHEMA)
    # Schema validation passes for the produced payload.
    validate_sample_metadata(meta)


def test_sidecar_defaults_keyboard(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    written = _drive(writer, _qualifying_keyboard_stream())
    meta = _read_sidecar(written[0])

    assert meta["instrument"] == "keyboard"
    assert meta["source"] == "human"
    assert meta["song_id"] is None
    assert meta["key"] is None
    assert meta["tempo"] is None


def test_sidecar_defaults_theramini(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("theramini", tmp_path, sample_rate=8000)
    sr = 8000
    tone = np.zeros(sr, dtype=np.float32)
    stream = [
        (tone, True, 0.0),
        (tone, True, 5.0),
        (None, False, 6.0),
    ]
    written = _drive(writer, stream)
    meta = _read_sidecar(written[0])

    assert meta["instrument"] == "theramini"
    assert meta["source"] == "human"


def test_sidecar_carries_user_supplied_tags(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter(
        "keyboard",
        tmp_path,
        metadata={
            "instrument": "rhodes",
            "song_id": "improv-42",
            "key": "Dm",
            "tempo": 96.0,
        },
    )
    written = _drive(writer, _qualifying_keyboard_stream())
    meta = _read_sidecar(written[0])

    assert meta["instrument"] == "rhodes"
    assert meta["song_id"] == "improv-42"
    assert meta["key"] == "Dm"
    assert meta["tempo"] == 96.0
    assert meta["source"] == "human"


def test_set_metadata_updates_between_phrases(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    note = _midi_note_on(60)

    first_stream = [(note, True, 0.0), (note, True, 5.0), (None, False, 6.0)]
    written_first = _drive(writer, first_stream)
    meta_first = _read_sidecar(written_first[0])
    assert meta_first["key"] is None

    writer.set_metadata(key="G", tempo=140)

    second_stream = [(note, True, 100.0), (note, True, 105.0), (None, False, 106.0)]
    written_second = _drive(writer, second_stream)
    meta_second = _read_sidecar(written_second[0])
    assert meta_second["key"] == "G"
    assert meta_second["tempo"] == 140


def test_set_metadata_rejects_derived_or_unknown_fields(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    with pytest.raises(ValueError):
        writer.set_metadata(timestamp="2026-04-25T18:39:59Z")
    with pytest.raises(ValueError):
        writer.set_metadata(duration=12.0)
    with pytest.raises(ValueError):
        writer.set_metadata(performer="anthony")


def test_sidecar_timestamp_is_iso_utc(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    end_unix = datetime(2026, 4, 25, 18, 39, 59, tzinfo=timezone.utc).timestamp()
    stream = [
        (_midi_note_on(60), True, end_unix - 6.0),
        (_midi_note_on(60), True, end_unix - 1.0),
        (None, False, end_unix),
    ]
    written = _drive(writer, stream)
    meta = _read_sidecar(written[0])

    parsed = datetime.fromisoformat(meta["timestamp"].replace("Z", "+00:00"))
    assert parsed == datetime(2026, 4, 25, 18, 39, 59, tzinfo=timezone.utc)


def test_sidecar_duration_matches_phrase_length(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    note = _midi_note_on(60)
    stream = [
        (note, True, 100.0),
        (note, True, 105.0),
        (None, False, 107.5),
    ]
    written = _drive(writer, stream)
    meta = _read_sidecar(written[0])
    assert meta["duration"] == pytest.approx(7.5, abs=1e-6)


def test_sidecar_path_pairs_with_audio(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("theramini", tmp_path, sample_rate=8000)
    sr = 8000
    tone = np.zeros(sr, dtype=np.float32)
    stream = [
        (tone, True, 0.0),
        (tone, True, 5.0),
        (None, False, 6.0),
    ]
    written = _drive(writer, stream)
    audio = written[0]
    sidecar = audio.with_suffix(".json")

    assert sidecar.parent == audio.parent
    assert sidecar.stem == audio.stem
    assert sidecar.suffix == ".json"


def test_no_sidecar_when_subthreshold_burst_dropped(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    stream = [
        (_midi_note_on(60), True, 0.0),
        (None, False, 2.0),
    ]
    _drive(writer, stream)
    target = tmp_path / "keyboard"
    if target.exists():
        assert not any(p.suffix == ".json" for p in target.iterdir())


def test_validator_rejects_missing_keys() -> None:
    incomplete = {
        "instrument": "keyboard",
        "song_id": None,
        "key": None,
        "tempo": None,
        "timestamp": "2026-04-25T18:39:59Z",
        # duration missing
        "source": "human",
    }
    with pytest.raises(ValueError, match="missing required keys"):
        validate_sample_metadata(incomplete)


def test_validator_rejects_unknown_keys() -> None:
    payload = {k: _placeholder(k) for k in SAMPLE_METADATA_SCHEMA}
    payload["mystery"] = "x"
    with pytest.raises(ValueError, match="unknown keys"):
        validate_sample_metadata(payload)


def test_validator_rejects_wrong_types() -> None:
    payload = {k: _placeholder(k) for k in SAMPLE_METADATA_SCHEMA}
    payload["tempo"] = "fast"  # should be number-or-None
    with pytest.raises(ValueError, match="tempo"):
        validate_sample_metadata(payload)


def _placeholder(key: str):
    defaults = {
        "instrument": "keyboard",
        "song_id": None,
        "key": None,
        "tempo": None,
        "timestamp": "2026-04-25T18:39:59Z",
        "duration": 6.0,
        "source": "human",
    }
    return defaults[key]


def test_chunks_can_carry_multiple_midi_messages(tmp_path: Path) -> None:
    writer = PhraseCaptureWriter("keyboard", tmp_path)
    composite = _midi_note_on(60) + _midi_note_on(64) + _midi_note_on(67)
    stream = [
        (composite, True, 0.0),
        (composite, True, 5.0),
        (b"", False, 6.0),
    ]
    written = _drive(writer, stream)
    data = written[0].read_bytes()
    assert bytes([0x90, 60, 64]) in data
    assert bytes([0x90, 64, 64]) in data
    assert bytes([0x90, 67, 64]) in data
