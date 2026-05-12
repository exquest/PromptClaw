"""Persist generated audio into the sample library."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf

from senseweave.sample_library import SampleRecord


TARGET_SAMPLE_RATE = 48_000
TARGET_CHANNELS = 2


class GenerationStorage:
    """Write generation results under ``samples/generated`` and index them."""

    def __init__(self, library: Any, samples_root: Path | str) -> None:
        self.library = library
        self.samples_root = Path(samples_root)

    def save(self, result: Any, req: Any) -> SampleRecord:
        """Store ``result`` audio as normalized WAV and register a SampleRecord."""
        request_hash = _request_hash(req)
        day = datetime.now(timezone.utc).date().isoformat()
        target_dir = self.samples_root / "generated" / day
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{request_hash}.wav"

        source_path = _audio_path(result)
        _write_wav(source_path, target_path, result)

        analysis = _analyze_audio(target_path)
        model = _optional_string(req, "model", "model_name") or _optional_string(
            result, "model_used"
        )
        mode = _mode_name(req)
        tags = ["generated"]
        if model:
            tags.append(model)
        if mode:
            tags.append(mode)

        extras = {
            "tags": " ".join(tags),
            "tags_json": json.dumps(tags),
        }
        if model:
            extras["model"] = model
        if mode:
            extras["mode"] = mode
        api_request_id = _optional_string(result, "api_request_id")
        if api_request_id:
            extras["api_request_id"] = api_request_id

        record = SampleRecord(
            character_tags=frozenset(),
            sample_id=request_hash,
            path=target_path,
            source="generated",
            arc_phase=_optional_string(req, "arc_phase"),
            mood=_optional_float(_field(req, "mood")),
            captured_at=datetime.now(timezone.utc),
            duration=analysis["duration"],
            rms=analysis["rms"],
            peak=analysis["peak"],
            extras=extras,
        )
        self.library.add(record)
        return record


def _write_wav(source_path: Path, target_path: Path, result: Any) -> None:
    audio_format = _audio_format(source_path, result)
    if audio_format == "mp3":
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source_path),
                "-ar",
                str(TARGET_SAMPLE_RATE),
                "-ac",
                str(TARGET_CHANNELS),
                str(target_path),
            ],
            check=True,
        )
        return

    if audio_format != "wav":
        raise ValueError(f"unsupported generated audio format: {audio_format}")

    info = sf.info(source_path)
    if info.samplerate == TARGET_SAMPLE_RATE and info.channels == TARGET_CHANNELS:
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(source_path, target_path)
        return

    data, sample_rate = sf.read(source_path, always_2d=True)
    normalized = _normalize_channels(data)
    if sample_rate != TARGET_SAMPLE_RATE:
        resampled = librosa.resample(
            normalized.T,
            orig_sr=sample_rate,
            target_sr=TARGET_SAMPLE_RATE,
        )
        normalized = resampled.T
    sf.write(target_path, normalized, TARGET_SAMPLE_RATE, subtype="PCM_16")


def _normalize_channels(data: np.ndarray) -> np.ndarray:
    if data.shape[1] == TARGET_CHANNELS:
        return data
    if data.shape[1] == 1:
        return np.repeat(data, TARGET_CHANNELS, axis=1)
    mono = np.mean(data, axis=1, keepdims=True)
    return np.repeat(mono, TARGET_CHANNELS, axis=1)


def _analyze_audio(path: Path) -> dict[str, float]:
    data, sample_rate = sf.read(path, always_2d=False)
    values = np.asarray(data, dtype=np.float64)
    if values.size == 0:
        return {"duration": 0.0, "rms": 0.0, "peak": 0.0}
    peak = float(np.max(np.abs(values)))
    rms = float(np.sqrt(np.mean(np.square(values))))
    frames = values.shape[0] if values.ndim > 1 else values.size
    return {
        "duration": float(frames / sample_rate),
        "rms": rms,
        "peak": peak,
    }


def _audio_path(result: Any) -> Path:
    value = _field(result, "audio_path", "wav_path", "path")
    if value is None:
        raise ValueError("generation result must expose audio_path, wav_path, or path")
    path = Path(value)
    if not path.exists():
        raise FileNotFoundError(f"generated audio file missing: {path}")
    return path


def _audio_format(source_path: Path, result: Any) -> str:
    explicit = _optional_string(result, "format", "audio_format")
    if explicit:
        return explicit.lower().lstrip(".")
    suffix = source_path.suffix.lower().lstrip(".")
    if suffix:
        return suffix
    return sf.info(source_path).format.lower()


def _request_hash(req: Any) -> str:
    value = _field(req, "hash", "request_hash")
    if callable(value):
        value = value()
    if value is None:
        raise ValueError("generation request must expose hash() or request_hash")
    text = str(value).strip()
    if not text:
        raise ValueError("generation request hash must be non-empty")
    return text


def _mode_name(req: Any) -> str | None:
    value = _field(req, "mode_name", "mode")
    if hasattr(value, "name"):
        value = value.name
    return str(value) if value not in (None, "") else None


def _optional_string(obj: Any, *names: str) -> str | None:
    value = _field(obj, *names)
    if value in (None, ""):
        return None
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _field(obj: Any, *names: str) -> Any:
    if isinstance(obj, Mapping):
        for name in names:
            if name in obj:
                return obj[name]
        return None
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None
