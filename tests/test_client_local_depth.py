"""Depth-2 local generation client tests - locked surface for frac-0011."""

from __future__ import annotations

import os
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.client_local import (  # noqa: E402
    LocalAdaClient,
    local_request_id,
    local_request_summary,
)
from senseweave.generation.client_protocol import GenerationResult  # noqa: E402
from senseweave.generation.request import (  # noqa: E402
    CLAP_CENTROID_DIM,
    GenerationRequest,
)


def _request(**overrides: object) -> GenerationRequest:
    base = dict(
        prompt="glass bell, quiet room",
        clap_centroid=np.zeros(CLAP_CENTROID_DIM, dtype=np.float32),
        duration_sec=5.0,
        seed=23,
        bpm_target=72.0,
        mode_name="companion",
        arc_phase="Emergence",
        model="musicgen-medium",
    )
    base.update(overrides)
    return GenerationRequest(**base)  # type: ignore[arg-type]


def _wav_stats(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav_file:
        first_frames = wav_file.readframes(1024)
        return {
            "channels": wav_file.getnchannels(),
            "sample_rate": wav_file.getframerate(),
            "frames": wav_file.getnframes(),
            "first_frames": first_frames,
        }


def test_local_request_summary_is_stable_and_meaningful() -> None:
    request = _request()
    mapping_request = {
        "request_hash": "local-mapping-request",
        "prompt": "soft local preview",
        "duration_sec": 0.25,
        "seed": 7,
        "model": "musicgen-medium",
    }

    summary = local_request_summary(request)
    mapping_summary = local_request_summary(mapping_request)

    assert summary == local_request_summary(request)
    assert summary["request_id"] == local_request_id(request)
    assert summary["model"] == "musicgen-medium"
    assert summary["duration_sec"] == pytest.approx(5.0)
    assert summary["seed"] == 23
    assert summary["prompt_chars"] == len("glass bell, quiet room")
    assert 160.0 <= summary["frequency_hz"] <= 880.0

    assert mapping_summary["request_id"] == "local-local-mapping-request"
    assert mapping_summary["duration_sec"] == pytest.approx(0.25)
    assert mapping_summary["prompt_chars"] == len("soft local preview")


def test_local_ada_client_generates_typed_wav_result(tmp_path: Path) -> None:
    ticks = iter([100.0, 100.25])
    client = LocalAdaClient(
        output_dir=tmp_path,
        sample_rate=8_000,
        clock=lambda: next(ticks),
    )
    request = _request()

    result = client.generate(request)

    assert isinstance(result, GenerationResult)
    assert result.audio_path == tmp_path / f"{local_request_id(request)}.wav"
    assert result.audio_path.exists()
    assert result.sample_rate == 8_000
    assert result.duration_actual_sec == pytest.approx(5.0)
    assert result.model_used == "musicgen-medium"
    assert result.cost_usd == 0.0
    assert result.latency_ms == 250
    assert result.api_request_id == local_request_id(request)

    stats = _wav_stats(result.audio_path)
    assert stats["channels"] == 1
    assert stats["sample_rate"] == 8_000
    assert stats["frames"] == 40_000
    assert any(byte != 0 for byte in stats["first_frames"])


def test_local_ada_client_mapping_request_returns_end_to_end_payload(
    tmp_path: Path,
) -> None:
    client = LocalAdaClient(output_dir=tmp_path, sample_rate=8_000)
    request = {
        "request_hash": "abc123",
        "prompt": "short local texture",
        "duration_sec": 0.25,
        "seed": 7,
        "model": "musicgen-medium",
    }

    result = client.generate(request)

    assert result["prediction_id"] == local_request_id(request)
    assert result["api_request_id"] == local_request_id(request)
    assert result["audio_path"] == str(tmp_path / f"{local_request_id(request)}.wav")
    assert Path(result["audio_path"]).exists()
    assert result["sample_rate"] == 8_000
    assert result["duration_actual_sec"] == pytest.approx(0.25)
    assert result["model_used"] == "musicgen-medium"
    assert result["cost_usd"] == 0.0
    assert result["latency_ms"] >= 0


def test_local_generation_is_deterministic_for_same_request(tmp_path: Path) -> None:
    client = LocalAdaClient(output_dir=tmp_path, sample_rate=8_000)
    request = {
        "request_hash": "repeatable",
        "prompt": "repeatable local tone",
        "duration_sec": 0.25,
        "seed": 99,
        "model": "musicgen-medium",
    }

    first = client.generate(request)
    first_bytes = Path(first["audio_path"]).read_bytes()
    second = client.generate(dict(request))
    second_bytes = Path(second["audio_path"]).read_bytes()

    assert first["prediction_id"] == second["prediction_id"]
    assert first["audio_path"] == second["audio_path"]
    assert first_bytes == second_bytes


def test_client_local_reaches_depth_two() -> None:
    sdp_src = "/Users/anthony/Programming/sdp-cli/src"
    if sdp_src not in sys.path:
        sys.path.insert(0, sdp_src)
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/generation/client_local.py")
    assert result.depth >= 2, result.reason
