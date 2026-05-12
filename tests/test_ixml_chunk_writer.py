"""Tests for WAV iXML chunk writer."""
from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.ixml_chunk_writer import read_ixml, write_ixml

SAMPLE_RATE = 16000


def _make_wav(path: Path, *, frames: int = 1600) -> None:
    samples = [0] * frames
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(
            b"".join(
                int(s).to_bytes(2, "little", signed=True) for s in samples
            )
        )


def test_roundtrip_single_key(tmp_path: Path) -> None:
    wav = tmp_path / "test.wav"
    _make_wav(wav)
    write_ixml(wav, {"scene": "forest"})
    result = read_ixml(wav)
    assert result == {"scene": "forest"}


def test_roundtrip_multiple_keys(tmp_path: Path) -> None:
    wav = tmp_path / "test.wav"
    _make_wav(wav)
    meta = {
        "activity_mode": "grain_cloud",
        "wet_mix": "0.42",
        "grain_density_hz": "8.0",
        "sensor_id": "contact-mic-01",
    }
    write_ixml(wav, meta)
    assert read_ixml(wav) == meta


def test_empty_metadata(tmp_path: Path) -> None:
    wav = tmp_path / "test.wav"
    _make_wav(wav)
    write_ixml(wav, {})
    assert read_ixml(wav) == {}


def test_no_ixml_returns_empty(tmp_path: Path) -> None:
    wav = tmp_path / "test.wav"
    _make_wav(wav)
    assert read_ixml(wav) == {}


def test_wav_still_readable_after_ixml(tmp_path: Path) -> None:
    wav = tmp_path / "test.wav"
    _make_wav(wav, frames=SAMPLE_RATE)
    write_ixml(wav, {"key": "value"})
    with wave.open(str(wav), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == SAMPLE_RATE
        assert handle.getnframes() == SAMPLE_RATE


def test_invalid_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not a wav file")
    try:
        write_ixml(bad, {"k": "v"})
        assert False, "should have raised"
    except ValueError:
        pass
    try:
        read_ixml(bad)
        assert False, "should have raised"
    except ValueError:
        pass


def test_special_characters_in_values(tmp_path: Path) -> None:
    wav = tmp_path / "test.wav"
    _make_wav(wav)
    meta = {"note": "loud & clear", "path": "/tmp/<test>", "quote": 'say "hi"'}
    write_ixml(wav, meta)
    assert read_ixml(wav) == meta
