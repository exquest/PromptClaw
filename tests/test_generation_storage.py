"""Tests for generated-audio storage and SampleRecord registration."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation import storage as storage_module  # noqa: E402
from senseweave.generation.storage import GenerationStorage  # noqa: E402
from senseweave.sample_library import SampleRecord  # noqa: E402


REQUEST_HASH = "a" * 64


def _write_wav(
    path: Path,
    data: np.ndarray,
    *,
    sample_rate: int = 48_000,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data, sample_rate, subtype="PCM_16")
    return path


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        hash=lambda: REQUEST_HASH,
        model="musicgen-medium",
        mode_name="solitary",
        arc_phase="Emergence",
        mood=0.25,
    )


def test_save_writes_date_partitioned_request_hash_path_and_registers_record(
    tmp_path: Path,
) -> None:
    source = _write_wav(tmp_path / "input.wav", np.array([[0.25, -0.5], [0.5, -0.25]]))
    library = Mock()

    record = GenerationStorage(library, tmp_path / "samples").save(
        SimpleNamespace(audio_path=source, model_used="musicgen-medium"),
        _request(),
    )

    day = datetime.now(timezone.utc).date().isoformat()
    expected_path = tmp_path / "samples" / "generated" / day / f"{REQUEST_HASH}.wav"
    assert record.path == expected_path
    assert expected_path.exists()
    assert record.source == "generated"
    assert record.sample_id == REQUEST_HASH
    assert record.arc_phase == "Emergence"
    assert record.mood == 0.25
    assert record.extras["tags"].split() == [
        "generated",
        "musicgen-medium",
        "solitary",
    ]
    library.add.assert_called_once_with(record)


def test_save_computes_peak_rms_and_duration_from_saved_wav(tmp_path: Path) -> None:
    data = np.array([[0.25, -0.25], [0.5, -0.5], [0.0, 0.0]], dtype=np.float32)
    source = _write_wav(tmp_path / "source.wav", data)
    library = Mock()

    record = GenerationStorage(library, tmp_path / "samples").save(
        SimpleNamespace(audio_path=source),
        _request(),
    )

    assert record.duration == 3 / 48_000
    assert record.peak == np.max(np.abs(sf.read(record.path, always_2d=True)[0]))
    assert record.rms == np.sqrt(np.mean(np.square(sf.read(record.path)[0])))


def test_save_transcodes_mp3_to_wav_with_ffmpeg(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp3"
    source.write_bytes(b"fake mp3")
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], *, check: bool) -> None:
        commands.append(cmd)
        assert check is True
        _write_wav(Path(cmd[-1]), np.array([[0.1, -0.1]], dtype=np.float32))

    monkeypatch.setattr(storage_module.subprocess, "run", fake_run)

    record = GenerationStorage(Mock(), tmp_path / "samples").save(
        {"audio_path": source, "audio_format": "mp3"},
        _request(),
    )

    assert commands == [
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ar",
            "48000",
            "-ac",
            "2",
            str(record.path),
        ]
    ]
    assert record.path.suffix == ".wav"


def test_save_resamples_and_upmixes_non_48khz_mono_wav(tmp_path: Path) -> None:
    source = _write_wav(
        tmp_path / "mono.wav",
        np.array([0.1, -0.1, 0.2], dtype=np.float32),
        sample_rate=24_000,
    )

    record = GenerationStorage(Mock(), tmp_path / "samples").save(
        SimpleNamespace(audio_path=source),
        _request(),
    )

    info = sf.info(record.path)
    data, _ = sf.read(record.path, always_2d=True)
    assert info.samplerate == 48_000
    assert info.channels == 2
    assert data.shape[1] == 2
    assert isinstance(record, SampleRecord)
