"""Audio validation for generated samples."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


PEAK_DBFS_LIMIT = 0.0
SILENCE_DBFS_LIMIT = -50.0
MIN_SAMPLE_RATE_HZ = 22050
ACCEPTED_FORMATS = ("WAV", "FLAC")


@dataclass
class ValidationReport:
    """Result of validating a generated audio file."""

    valid: bool
    reason: str
    peak_dbfs: float
    rms_dbfs: float
    nan_count: int
    format: str


def _amplitude_to_dbfs(amplitude: float) -> float:
    if amplitude <= 0.0:
        return -math.inf
    return 20.0 * math.log10(amplitude)


def validate_audio(path: str | Path) -> ValidationReport:
    """Validate ``path`` for clipping, silence, NaN samples, and format.

    A file is valid when it is mono or stereo WAV/FLAC at >=22050 Hz with no
    NaN samples, peak <= 0 dBFS, and RMS >= -50 dBFS.
    """
    audio_path = Path(path)
    try:
        info = sf.info(str(audio_path))
    except (RuntimeError, sf.LibsndfileError) as exc:
        return ValidationReport(
            valid=False,
            reason=f"unreadable audio file: {exc}",
            peak_dbfs=-math.inf,
            rms_dbfs=-math.inf,
            nan_count=0,
            format="",
        )

    fmt = str(info.format).upper()
    samples, sample_rate = sf.read(str(audio_path), always_2d=True, dtype="float64")
    samples = np.asarray(samples, dtype=np.float64)
    channels = samples.shape[1]

    nan_mask = np.isnan(samples)
    nan_count = int(nan_mask.sum())
    finite = samples[~nan_mask]

    if finite.size:
        peak = float(np.max(np.abs(finite)))
        rms = float(np.sqrt(np.mean(np.square(finite))))
    else:
        peak = 0.0
        rms = 0.0
    peak_dbfs = _amplitude_to_dbfs(peak)
    rms_dbfs = _amplitude_to_dbfs(rms)

    def _report(valid: bool, reason: str) -> ValidationReport:
        return ValidationReport(
            valid=valid,
            reason=reason,
            peak_dbfs=peak_dbfs,
            rms_dbfs=rms_dbfs,
            nan_count=nan_count,
            format=fmt,
        )

    if fmt not in ACCEPTED_FORMATS:
        return _report(False, f"unsupported format: {fmt or 'unknown'}")
    if channels not in (1, 2):
        return _report(False, f"unsupported channel count: {channels}")
    if sample_rate < MIN_SAMPLE_RATE_HZ:
        return _report(False, f"sample rate too low: {sample_rate} Hz")
    if nan_count > 0:
        return _report(False, f"audio contains {nan_count} NaN sample(s)")
    if peak_dbfs > PEAK_DBFS_LIMIT:
        return _report(False, f"clipping: peak {peak_dbfs:.2f} dBFS > 0 dBFS")
    if rms_dbfs < SILENCE_DBFS_LIMIT:
        return _report(False, f"silence: RMS {rms_dbfs:.2f} dBFS < -50 dBFS")
    return _report(True, "ok")


__all__ = (
    "ACCEPTED_FORMATS",
    "MIN_SAMPLE_RATE_HZ",
    "PEAK_DBFS_LIMIT",
    "SILENCE_DBFS_LIMIT",
    "ValidationReport",
    "validate_audio",
)
