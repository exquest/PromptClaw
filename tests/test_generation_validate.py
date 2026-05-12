"""Tests for generated-audio validation."""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.validate import (  # noqa: E402
    SILENCE_DBFS_LIMIT,
    ValidationReport,
    validate_audio,
)


SR = 44100


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int = SR) -> Path:
    sf.write(str(path), samples, sample_rate, subtype="FLOAT")
    return path


def _tone(seconds: float, amplitude: float, freq: float = 440.0) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(SR * seconds), endpoint=False)
    return (amplitude * np.sin(2.0 * np.pi * freq * t)).astype(np.float64)


def test_valid_stereo_wav_passes(tmp_path: Path) -> None:
    left = _tone(0.5, 0.5, 440.0)
    right = _tone(0.5, 0.5, 660.0)
    stereo = np.stack([left, right], axis=1)

    report = validate_audio(_write_wav(tmp_path / "ok.wav", stereo))

    assert isinstance(report, ValidationReport)
    assert report.valid is True
    assert report.reason == "ok"
    assert report.format == "WAV"
    assert report.nan_count == 0
    assert report.peak_dbfs <= 0.0
    assert report.rms_dbfs > SILENCE_DBFS_LIMIT


def test_silent_wav_rejected(tmp_path: Path) -> None:
    silent = np.zeros(SR // 2, dtype=np.float64)

    report = validate_audio(_write_wav(tmp_path / "silent.wav", silent))

    assert report.valid is False
    assert "silence" in report.reason.lower() or report.rms_dbfs == -math.inf
    assert report.nan_count == 0


def test_clipped_wav_rejected(tmp_path: Path) -> None:
    clipped = _tone(0.25, 1.5)

    report = validate_audio(_write_wav(tmp_path / "clipped.wav", clipped))

    assert report.valid is False
    assert "clipping" in report.reason.lower()
    assert report.peak_dbfs > 0.0


def test_nan_laden_wav_rejected(tmp_path: Path) -> None:
    samples = _tone(0.25, 0.5)
    samples[100:110] = np.nan

    report = validate_audio(_write_wav(tmp_path / "nan.wav", samples))

    assert report.valid is False
    assert report.nan_count == 10
    assert "nan" in report.reason.lower()


def test_unsupported_format_rejected(tmp_path: Path) -> None:
    samples = _tone(0.25, 0.5)
    ogg_path = tmp_path / "weird.ogg"
    sf.write(str(ogg_path), samples, SR, format="OGG", subtype="VORBIS")

    report = validate_audio(ogg_path)

    assert report.valid is False
    assert "format" in report.reason.lower()
    assert report.format != "WAV"
    assert report.format != "FLAC"


def test_low_sample_rate_rejected(tmp_path: Path) -> None:
    sample_rate = 16000
    t = np.linspace(0.0, 0.5, sample_rate // 2, endpoint=False)
    samples = (0.5 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float64)

    path = tmp_path / "lowrate.wav"
    sf.write(str(path), samples, sample_rate, subtype="FLOAT")

    report = validate_audio(path)

    assert report.valid is False
    assert "sample rate" in report.reason.lower()


def test_flac_accepted(tmp_path: Path) -> None:
    samples = _tone(0.25, 0.5)
    path = tmp_path / "ok.flac"
    sf.write(str(path), samples, SR, format="FLAC")

    report = validate_audio(path)

    assert report.valid is True
    assert report.format == "FLAC"
