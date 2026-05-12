"""Tests for the sampler BufferLoader load/free OSC handshakes."""
from __future__ import annotations

import os
import sys
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sampler_buffers import BufferLoader, BufferRecord


class _RecordingOSC:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list]] = []

    def send_message(self, address: str, args: list) -> None:
        self.calls.append((address, list(args)))


def _write_wav(path: Path, *, frames: int, channels: int = 1, rate: int = 48000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames * channels)


def test_on_sampler_load_allocates_and_reads_buffer(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    _write_wav(wav, frames=2400, channels=1)
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=200)
    record = BufferRecord(path=wav)

    bufnum = loader.on_sampler_load(record)

    assert bufnum == 200
    assert record.buffer_id == 200
    assert osc.calls[0] == ("/b_alloc", [200, 2400, 1])
    assert osc.calls[1] == ("/b_allocRead", [200, str(wav), 0, -1])
    assert len(osc.calls) == 2


def test_on_sampler_load_handles_stereo_wav(tmp_path: Path) -> None:
    wav = tmp_path / "stereo.wav"
    _write_wav(wav, frames=1024, channels=2)
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=50)
    record = BufferRecord(path=wav)

    loader.on_sampler_load(record)

    assert osc.calls[0] == ("/b_alloc", [50, 1024, 2])


def test_on_sampler_load_increments_bufnum_per_call(tmp_path: Path) -> None:
    wav_a = tmp_path / "a.wav"
    wav_b = tmp_path / "b.wav"
    _write_wav(wav_a, frames=100)
    _write_wav(wav_b, frames=200)
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=10)

    record_a = BufferRecord(path=wav_a)
    record_b = BufferRecord(path=wav_b)
    bufnum_a = loader.on_sampler_load(record_a)
    bufnum_b = loader.on_sampler_load(record_b)

    assert (bufnum_a, bufnum_b) == (10, 11)
    assert record_a.buffer_id == 10
    assert record_b.buffer_id == 11


def test_on_sampler_load_accepts_string_path(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    _write_wav(wav, frames=512)
    osc = _RecordingOSC()
    loader = BufferLoader(osc)
    record = BufferRecord(path=str(wav))  # type: ignore[arg-type]

    loader.on_sampler_load(record)

    assert osc.calls[1][1][1] == str(wav)


def test_on_sampler_load_raises_when_wav_missing(tmp_path: Path) -> None:
    osc = _RecordingOSC()
    loader = BufferLoader(osc)
    record = BufferRecord(path=tmp_path / "missing.wav")

    try:
        loader.on_sampler_load(record)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError for missing WAV")
    assert osc.calls == []
    assert record.buffer_id is None


def test_on_sampler_free_releases_buffer_and_clears_id(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    _write_wav(wav, frames=128)
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=300)
    record = BufferRecord(path=wav)
    loader.on_sampler_load(record)
    osc.calls.clear()

    loader.on_sampler_free(record)

    assert osc.calls == [("/b_free", [300])]
    assert record.buffer_id is None


def test_on_sampler_free_is_noop_when_buffer_id_is_none() -> None:
    osc = _RecordingOSC()
    loader = BufferLoader(osc)
    record = BufferRecord(path="unused.wav", buffer_id=None)

    loader.on_sampler_free(record)

    assert osc.calls == []
    assert record.buffer_id is None


def test_on_sampler_free_is_idempotent(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    _write_wav(wav, frames=64)
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=42)
    record = BufferRecord(path=wav)
    loader.on_sampler_load(record)

    loader.on_sampler_free(record)
    loader.on_sampler_free(record)

    free_calls = [call for call in osc.calls if call[0] == "/b_free"]
    assert free_calls == [("/b_free", [42])]
    assert record.buffer_id is None


def test_buffer_loader_requires_positive_capacity() -> None:
    try:
        BufferLoader(_RecordingOSC(), capacity=0)
    except ValueError as exc:
        assert "capacity" in str(exc)
    else:
        raise AssertionError("expected ValueError for non-positive capacity")


def test_load_evicts_least_recently_used_when_capacity_exceeded(tmp_path: Path) -> None:
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=500, capacity=2)

    records = []
    for name in ("a", "b", "c"):
        wav = tmp_path / f"{name}.wav"
        _write_wav(wav, frames=64)
        records.append(BufferRecord(path=wav))

    loader.on_sampler_load(records[0])  # bufnum 500
    loader.on_sampler_load(records[1])  # bufnum 501
    osc.calls.clear()

    loader.on_sampler_load(records[2])  # should evict records[0]

    free_calls = [call for call in osc.calls if call[0] == "/b_free"]
    assert free_calls == [("/b_free", [500])]
    assert records[0].buffer_id is None
    assert records[1].buffer_id == 501
    assert records[2].buffer_id == 502


def test_touch_promotes_record_to_most_recently_used(tmp_path: Path) -> None:
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=600, capacity=2)

    records = []
    for name in ("a", "b", "c"):
        wav = tmp_path / f"{name}.wav"
        _write_wav(wav, frames=64)
        records.append(BufferRecord(path=wav))

    loader.on_sampler_load(records[0])  # 600 (LRU)
    loader.on_sampler_load(records[1])  # 601 (MRU)
    loader.touch(records[0])             # 600 now MRU; 601 is LRU
    osc.calls.clear()

    loader.on_sampler_load(records[2])  # should evict records[1]

    free_calls = [call for call in osc.calls if call[0] == "/b_free"]
    assert free_calls == [("/b_free", [601])]
    assert records[0].buffer_id == 600
    assert records[1].buffer_id is None
    assert records[2].buffer_id == 602


def test_touch_is_noop_for_untracked_record(tmp_path: Path) -> None:
    osc = _RecordingOSC()
    loader = BufferLoader(osc, capacity=2)
    record = BufferRecord(path="unused.wav")

    loader.touch(record)

    assert osc.calls == []


def test_free_removes_from_lru_so_capacity_does_not_evict(tmp_path: Path) -> None:
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=700, capacity=2)

    records = []
    for name in ("a", "b", "c"):
        wav = tmp_path / f"{name}.wav"
        _write_wav(wav, frames=64)
        records.append(BufferRecord(path=wav))

    loader.on_sampler_load(records[0])
    loader.on_sampler_load(records[1])
    loader.on_sampler_free(records[0])
    osc.calls.clear()

    loader.on_sampler_load(records[2])

    assert [call for call in osc.calls if call[0] == "/b_free"] == []
    assert records[1].buffer_id == 701
    assert records[2].buffer_id == 702


def test_on_sampler_load_evicts_lru_via_on_sampler_free_at_default_capacity(tmp_path: Path) -> None:
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=900)
    records: list[BufferRecord] = []

    for i in range(loader.capacity):
        wav = tmp_path / f"clip_{i}.wav"
        _write_wav(wav, frames=32)
        record = BufferRecord(path=wav)
        records.append(record)
        loader.on_sampler_load(record)

    overflow_wav = tmp_path / "overflow.wav"
    _write_wav(overflow_wav, frames=32)
    overflow = BufferRecord(path=overflow_wav)
    expected_bufnum = 900 + loader.capacity
    osc.calls.clear()

    with patch.object(loader, "on_sampler_free", wraps=loader.on_sampler_free) as free_spy:
        bufnum = loader.on_sampler_load(overflow)

    free_spy.assert_called_once_with(records[0])
    assert bufnum == expected_bufnum
    assert osc.calls[0] == ("/b_free", [900])
    assert osc.calls[1] == ("/b_alloc", [expected_bufnum, 32, 1])
    assert osc.calls[2] == ("/b_allocRead", [expected_bufnum, str(overflow_wav), 0, -1])
    assert records[0].buffer_id is None
    assert overflow.buffer_id == expected_bufnum


def test_reload_below_capacity_does_not_evict(tmp_path: Path) -> None:
    osc = _RecordingOSC()
    loader = BufferLoader(osc, start_bufnum=800, capacity=64)

    records = []
    for i in range(5):
        wav = tmp_path / f"clip_{i}.wav"
        _write_wav(wav, frames=64)
        records.append(BufferRecord(path=wav))
        loader.on_sampler_load(records[-1])

    free_calls = [call for call in osc.calls if call[0] == "/b_free"]
    assert free_calls == []
    assert [r.buffer_id for r in records] == [800, 801, 802, 803, 804]
