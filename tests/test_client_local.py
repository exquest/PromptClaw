"""Tests for the local Ada generation client."""

from __future__ import annotations

import inspect
import json
import os
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.client_local import (  # noqa: E402
    GenerationClient,
    GenerationResult,
    LocalAdaClient,
    local_request_id,
    local_request_summary,
)
from senseweave.generation.client_protocol import (  # noqa: E402
    result_summary,
    validate_generation_result,
)
from senseweave.generation.client_replicate import ReplicateClient  # noqa: E402
from senseweave.generation.request import (  # noqa: E402
    CLAP_CENTROID_DIM,
    GenerationRequest,
)


def test_local_ada_client_satisfies_generation_client_protocol() -> None:
    client: GenerationClient = LocalAdaClient()

    local_sig = inspect.signature(LocalAdaClient.generate)
    rep_sig = inspect.signature(ReplicateClient.generate)

    assert client is not None
    assert local_sig == rep_sig


def test_local_ada_client_generates_local_preview_payload(tmp_path: Path) -> None:
    client = LocalAdaClient(output_dir=tmp_path, sample_rate=8_000)

    result = client.generate(
        {
            "request_hash": "existing-local-test",
            "prompt": "test",
            "duration_sec": 0.25,
            "seed": 1,
            "model": "musicgen-medium",
        }
    )

    assert result["model_used"] == "musicgen-medium"
    assert result["cost_usd"] == 0.0
    assert Path(result["audio_path"]).exists()


def _request(**overrides: object) -> GenerationRequest:
    base = dict(
        prompt="glass bell, quiet room",
        clap_centroid=np.zeros(CLAP_CENTROID_DIM, dtype=np.float32),
        duration_sec=5.0,
        seed=23,
        bpm_target=72.0,
        mode_name="companion",
        arc_phase="Emergence",
        backend="local",
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


class TestLocalAdaClientEndToEnd:
    """End-to-end checks for the public local generation client surface."""

    def test_typed_requests_generate_wavs_and_protocol_summaries(
        self,
        tmp_path: Path,
    ) -> None:
        ticks = iter([10.0, 10.125, 20.0, 20.25, 30.0, 30.5])
        client = LocalAdaClient(
            output_dir=tmp_path / "typed",
            sample_rate=8_000,
            clock=lambda: next(ticks),
        )
        cases = [
            (_request(prompt="glass bell, quiet room", seed=23), 125),
            (_request(prompt="soft bowed texture", seed=24), 250),
            (_request(prompt="low drone with bright grains", seed=25), 500),
        ]

        seen_ids: set[str] = set()
        for request, expected_latency_ms in cases:
            result = client.generate(request)
            assert isinstance(result, GenerationResult)
            assert result.audio_path == (
                tmp_path / "typed" / f"{local_request_id(request)}.wav"
            )
            assert result.audio_path.exists()
            assert result.sample_rate == 8_000
            assert result.duration_actual_sec == pytest.approx(request.duration_sec)
            assert result.model_used == request.model
            assert result.cost_usd == 0.0
            assert result.latency_ms == expected_latency_ms
            assert result.api_request_id == local_request_id(request)

            stats = _wav_stats(result.audio_path)
            assert stats["channels"] == 1
            assert stats["sample_rate"] == 8_000
            assert stats["frames"] == 40_000
            assert any(byte != 0 for byte in stats["first_frames"])

            summary = result_summary(result)
            assert summary["request_id"] == local_request_id(request)
            assert summary["model"] == request.model
            assert summary["audio_path"] == str(result.audio_path)
            assert summary["duration_sec"] == pytest.approx(request.duration_sec)
            assert summary["cost_usd"] == 0.0
            assert summary["cost_per_second_usd"] == 0.0

            outcome = validate_generation_result(
                result,
                request,
                sample_rate_floor=8_000,
                duration_tolerance_sec=0.0,
            )
            assert outcome.passed is True
            assert outcome.reasons == ()
            seen_ids.add(result.api_request_id)

        assert len(seen_ids) == len(cases)

    def test_mapping_requests_return_queue_ready_payloads(
        self,
        tmp_path: Path,
    ) -> None:
        client = LocalAdaClient(output_dir=tmp_path / "mapping", sample_rate=8_000)
        requests = [
            {
                "request_hash": "local-map-a",
                "prompt": "short local texture",
                "duration_sec": 0.25,
                "seed": 7,
                "model": "musicgen-medium",
            },
            {
                "request_hash": "local-map-b",
                "prompt": "another preview",
                "duration_sec": 0.5,
                "seed": 8,
                "model": "stable-audio-open",
            },
        ]

        for request in requests:
            result = client.generate(request)
            expected_id = local_request_id(request)
            audio_path = tmp_path / "mapping" / f"{expected_id}.wav"

            assert result["prediction_id"] == expected_id
            assert result["api_request_id"] == expected_id
            assert result["request_id"] == expected_id
            assert result["audio_path"] == str(audio_path)
            assert Path(result["audio_path"]).exists()
            assert result["sample_rate"] == 8_000
            assert result["duration_actual_sec"] == pytest.approx(
                request["duration_sec"]
            )
            assert result["duration_sec"] == pytest.approx(request["duration_sec"])
            assert result["model_used"] == request["model"]
            assert result["model"] == request["model"]
            assert result["cost_usd"] == 0.0
            assert result["cost_per_second_usd"] == 0.0
            assert result["latency_ms"] >= 0

            stats = _wav_stats(Path(result["audio_path"]))
            assert stats["frames"] == int(request["duration_sec"] * 8_000)
            assert any(byte != 0 for byte in stats["first_frames"])

    def test_request_summaries_and_payloads_are_json_safe(
        self,
        tmp_path: Path,
    ) -> None:
        client = LocalAdaClient(output_dir=tmp_path / "json", sample_rate=8_000)
        typed_request = _request(prompt="json-safe local request", seed=31)
        mapping_request = {
            "request_hash": "json-map",
            "prompt": "json mapping preview",
            "duration_sec": 0.25,
            "seed": 32,
            "model": "musicgen-medium",
        }

        summaries = [
            local_request_summary(typed_request),
            local_request_summary(mapping_request),
        ]
        for summary in summaries:
            rendered = json.dumps(summary, sort_keys=True)
            decoded = json.loads(rendered)
            assert decoded == summary
            assert decoded["request_id"].startswith("local-")
            assert decoded["prompt_chars"] > 0
            assert 160.0 <= decoded["frequency_hz"] <= 880.0

        payload = client.generate(mapping_request)
        diagnostic = {
            "summary": local_request_summary(mapping_request),
            "payload": payload,
        }
        decoded_diagnostic = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert decoded_diagnostic["summary"]["request_id"] == payload["request_id"]
        assert decoded_diagnostic["payload"]["audio_path"] == payload["audio_path"]
        assert decoded_diagnostic["payload"]["prediction_id"] == payload["prediction_id"]

    def test_repeated_mapping_generation_reuses_deterministic_path_and_bytes(
        self,
        tmp_path: Path,
    ) -> None:
        client = LocalAdaClient(output_dir=tmp_path / "repeat", sample_rate=8_000)
        request = {
            "request_hash": "repeatable-local",
            "prompt": "repeatable local tone",
            "duration_sec": 0.25,
            "seed": 99,
            "model": "musicgen-medium",
        }

        results = [client.generate(dict(request)) for _ in range(3)]
        payloads = [Path(result["audio_path"]).read_bytes() for result in results]

        assert {result["prediction_id"] for result in results} == {
            local_request_id(request)
        }
        assert {result["audio_path"] for result in results} == {
            str(tmp_path / "repeat" / f"{local_request_id(request)}.wav")
        }
        assert payloads[0] == payloads[1] == payloads[2]
