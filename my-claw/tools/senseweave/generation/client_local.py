"""Deterministic local preview generation client."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import tempfile
import time
import wave
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .client_protocol import GenerationClient, GenerationResult, result_summary
from .request import GenerationRequest


DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "senseweave-local-generation"
DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_DURATION_SEC = 5.0
DEFAULT_MODEL = "local-ada-preview"
_MIN_FREQUENCY_HZ = 160.0
_FREQUENCY_RANGE_HZ = 720
_AMPLITUDE = 0.18
_SAMPLE_WIDTH_BYTES = 2
_CHANNELS = 1


class LocalAdaClient:
    """Local deterministic preview backend for offline generation tests."""

    def __init__(
        self,
        output_dir: str | Path | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.output_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
        self.sample_rate = int(sample_rate)
        self._clock = clock

    def generate(self, request: Any) -> Any:
        """Generate a deterministic local WAV preview for ``request``."""
        start = self._clock()
        result = _generate_local_result(
            request,
            output_dir=self.output_dir,
            sample_rate=self.sample_rate,
            latency_ms=0,
        )
        latency_ms = max(0, int((self._clock() - start) * 1000))
        result = replace(result, latency_ms=latency_ms)
        if isinstance(request, GenerationRequest):
            return result
        return _legacy_payload(result)


def local_request_id(request: Any) -> str:
    """Return the stable local generation id for ``request``."""
    source = _identity_source(request)
    return f"local-{_safe_token(source)}"


def local_request_summary(request: Any) -> dict[str, Any]:
    """Return operator-readable local request metadata."""
    prompt = _request_prompt(request)
    seed = _request_seed(request)
    duration_sec = _request_duration_sec(request)
    return {
        "request_id": local_request_id(request),
        "model": _request_model(request),
        "duration_sec": round(duration_sec, 3),
        "seed": seed,
        "prompt_chars": len(prompt),
        "frequency_hz": round(_frequency_hz(seed, prompt), 3),
    }


def _generate_local_result(
    request: Any,
    *,
    output_dir: Path,
    sample_rate: int,
    latency_ms: int,
) -> GenerationResult:
    request_id = local_request_id(request)
    duration_sec = _request_duration_sec(request)
    prompt = _request_prompt(request)
    seed = _request_seed(request)
    audio_path = output_dir / f"{request_id}.wav"
    _write_preview_wav(
        audio_path,
        duration_sec=duration_sec,
        sample_rate=sample_rate,
        frequency_hz=_frequency_hz(seed, prompt),
    )
    return GenerationResult(
        audio_path=audio_path,
        sample_rate=sample_rate,
        duration_actual_sec=duration_sec,
        model_used=_request_model(request),
        cost_usd=0.0,
        latency_ms=latency_ms,
        api_request_id=request_id,
    )


def _legacy_payload(result: GenerationResult) -> dict[str, Any]:
    payload = result_summary(result)
    payload.update(
        {
            "audio_path": str(result.audio_path),
            "sample_rate": result.sample_rate,
            "duration_actual_sec": result.duration_actual_sec,
            "model_used": result.model_used,
            "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
            "api_request_id": result.api_request_id,
            "prediction_id": result.api_request_id,
        }
    )
    return payload


def _write_preview_wav(
    audio_path: Path,
    *,
    duration_sec: float,
    sample_rate: int,
    frequency_hz: float,
) -> None:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, int(round(duration_sec * sample_rate)))
    fade_in_frames = max(1, int(sample_rate * 0.01))
    fade_out_frames = max(1, int(sample_rate * 0.02))
    frames = bytearray()
    for index in range(frame_count):
        position = index / float(sample_rate)
        fade = min(
            1.0,
            index / fade_in_frames,
            (frame_count - index) / fade_out_frames,
        )
        tone = math.sin(math.tau * frequency_hz * position)
        overtone = 0.35 * math.sin(math.tau * frequency_hz * 1.5 * position)
        sample = max(-1.0, min(1.0, (tone + overtone) * _AMPLITUDE * fade))
        frames.extend(struct.pack("<h", int(sample * 32767)))

    with wave.open(str(audio_path), "wb") as wav_file:
        wav_file.setnchannels(_CHANNELS)
        wav_file.setsampwidth(_SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(frames))


def _identity_source(request: Any) -> str:
    value = _field(request, "hash", "request_hash")
    if callable(value):
        value = value()
    if value not in (None, ""):
        return str(value)
    payload = {
        "prompt": _request_prompt(request),
        "duration_sec": _request_duration_sec(request),
        "seed": _request_seed(request),
        "model": _request_model(request),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _safe_token(value: str) -> str:
    text = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in str(value).strip()
    )
    return text or "request"


def _request_prompt(request: Any) -> str:
    value = _field(request, "prompt")
    return "" if value is None else str(value)


def _request_duration_sec(request: Any) -> float:
    value = _field(request, "duration_sec", "duration")
    if value is None:
        return DEFAULT_DURATION_SEC
    return float(value)


def _request_seed(request: Any) -> int:
    value = _field(request, "seed")
    if value is None:
        return 0
    return int(value)


def _request_model(request: Any) -> str:
    value = _field(request, "model", "model_name")
    if value in (None, ""):
        return DEFAULT_MODEL
    return str(value)


def _frequency_hz(seed: int, prompt: str) -> float:
    material = f"{seed}:{prompt}".encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(material).digest()[:2], "big")
    return _MIN_FREQUENCY_HZ + float(bucket % _FREQUENCY_RANGE_HZ)


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


if TYPE_CHECKING:
    _protocol_check: GenerationClient = LocalAdaClient()


__all__ = [
    "GenerationClient",
    "GenerationResult",
    "LocalAdaClient",
    "local_request_id",
    "local_request_summary",
]
