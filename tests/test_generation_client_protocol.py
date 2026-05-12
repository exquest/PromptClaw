from __future__ import annotations

import dataclasses
import io
import json
import os
import sys
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.client_protocol import (  # noqa: E402
    GenerationClient,
    GenerationResult,
    cost_per_second,
    format_result_log_line,
    result_summary,
    validate_generation_result,
)
from senseweave.generation.client_replicate import ReplicateClient  # noqa: E402
from senseweave.generation.request import (  # noqa: E402
    CLAP_CENTROID_DIM,
    GenerationRequest,
)


class FakeClient:
    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            audio_path=Path("/tmp/fake.wav"),
            sample_rate=48_000,
            duration_actual_sec=float(request.duration_sec),
            model_used=request.model,
            cost_usd=0.01,
            latency_ms=12,
            api_request_id="fake-request-id",
        )


class MaterializingFakeClient:
    def __init__(
        self,
        output_dir: Path,
        *,
        sample_rate: int = 48_000,
        latency_ms: int = 321,
    ) -> None:
        self.output_dir = output_dir
        self.sample_rate = sample_rate
        self.latency_ms = latency_ms

    def generate(self, request: GenerationRequest) -> GenerationResult:
        request_id = f"fake-{request.seed}-{request.hash()[:8]}"
        audio_path = self.output_dir / f"{request_id}.wav"
        frame_count = int(float(request.duration_sec) * self.sample_rate)
        audio_path.write_bytes(
            _wav_bytes(sample_rate=self.sample_rate, frames=frame_count)
        )
        return GenerationResult(
            audio_path=audio_path,
            sample_rate=self.sample_rate,
            duration_actual_sec=float(request.duration_sec),
            model_used=request.model,
            cost_usd=round(float(request.duration_sec) * 0.005, 4),
            latency_ms=self.latency_ms,
            api_request_id=request_id,
        )


if TYPE_CHECKING:
    _fake_client_check: GenerationClient = FakeClient()
    _replicate_client_check: GenerationClient = ReplicateClient()
    _materializing_client_check: GenerationClient = MaterializingFakeClient(Path())


def _request(**overrides: object) -> GenerationRequest:
    base = dict(
        prompt="quiet texture",
        clap_centroid=np.zeros(CLAP_CENTROID_DIM, dtype=np.float32),
        duration_sec=5.0,
        seed=1,
        bpm_target=90.0,
        mode_name="quiet",
        arc_phase="Emergence",
    )
    base.update(overrides)
    return GenerationRequest(**base)  # type: ignore[arg-type]


def _wav_bytes(sample_rate: int = 8_000, frames: int = 4_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


def test_generation_result_is_frozen_dataclass() -> None:
    result = FakeClient().generate(_request())

    assert dataclasses.is_dataclass(result)
    assert getattr(result, "__dataclass_params__").frozen
    assert [field.name for field in dataclasses.fields(result)] == [
        "audio_path",
        "sample_rate",
        "duration_actual_sec",
        "model_used",
        "cost_usd",
        "latency_ms",
        "api_request_id",
    ]


def test_fake_client_satisfies_protocol_at_runtime() -> None:
    client = FakeClient()

    assert isinstance(client, GenerationClient)
    assert client.generate(_request()).api_request_id == "fake-request-id"


def test_replicate_client_satisfies_protocol_at_runtime() -> None:
    assert isinstance(ReplicateClient(), GenerationClient)


def test_replicate_client_returns_generation_result_for_typed_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from senseweave.generation import client_replicate as module

    completed = SimpleNamespace(id="pred/123", status="succeeded", output=b"")
    ticks = iter([10.0, 12.5])
    client = ReplicateClient(api_token="t", clock=lambda: next(ticks))
    monkeypatch.setattr(client, "_submit_prediction", lambda request: completed)
    monkeypatch.setattr(client, "_poll_prediction", lambda prediction: prediction)
    monkeypatch.setattr(client, "_download_output", lambda prediction: _wav_bytes())
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path))

    result = client.generate(_request())

    assert isinstance(result, GenerationResult)
    assert result.audio_path == tmp_path / "senseweave-generation" / "pred-123.wav"
    assert result.audio_path.read_bytes().startswith(b"RIFF")
    assert result.sample_rate == 8_000
    assert result.duration_actual_sec == 0.5
    assert result.model_used == "musicgen-medium"
    assert result.cost_usd > 0.0
    assert result.latency_ms == 2500
    assert result.api_request_id == "pred/123"


class GenerationClientProtocolEndToEndTests:
    """End-to-end checks for the shared protocol helper surface."""

    __test__ = True

    def test_typed_client_result_flows_through_summary_log_and_validation(
        self,
        tmp_path: Path,
    ) -> None:
        request = _request()
        client: GenerationClient = MaterializingFakeClient(tmp_path)

        result = client.generate(request)

        assert isinstance(result, GenerationResult)
        assert result.audio_path.exists()
        assert result.audio_path.read_bytes().startswith(b"RIFF")
        assert result.model_used == request.model
        assert result.duration_actual_sec == pytest.approx(request.duration_sec)
        assert result.cost_usd == pytest.approx(0.025)
        assert cost_per_second(result) == pytest.approx(0.005)

        summary = result_summary(result)
        assert summary == {
            "model": request.model,
            "sample_rate": 48_000,
            "duration_sec": pytest.approx(5.0),
            "cost_usd": pytest.approx(0.025),
            "cost_per_second_usd": pytest.approx(0.005),
            "latency_ms": 321,
            "request_id": result.api_request_id,
            "audio_path": str(result.audio_path),
        }
        assert json.loads(json.dumps(summary, sort_keys=True))["audio_path"] == str(
            result.audio_path
        )

        assert format_result_log_line(result) == (
            f"model={request.model} dur=5.00s cost=$0.0250 "
            f"latency=321ms id={result.api_request_id}"
        )
        outcome = validate_generation_result(
            result,
            request,
            sample_rate_floor=48_000,
            duration_tolerance_sec=0.0,
        )
        assert outcome.passed is True
        assert outcome.reasons == ()

    def test_protocol_diagnostics_are_json_safe_for_multiple_results(
        self,
        tmp_path: Path,
    ) -> None:
        client = MaterializingFakeClient(tmp_path, sample_rate=24_000)
        requests = [
            _request(prompt="quiet texture", seed=1),
            _request(prompt="wide shimmer", seed=2),
            _request(prompt="low room tone", seed=3),
        ]

        diagnostics = []
        for request in requests:
            result = client.generate(request)
            diagnostics.append(
                {
                    "request_hash": request.hash(),
                    "summary": result_summary(result),
                    "log_line": format_result_log_line(result),
                    "validation": validate_generation_result(
                        result,
                        request,
                        sample_rate_floor=24_000,
                        duration_tolerance_sec=0.0,
                    ).passed,
                }
            )

        decoded = json.loads(json.dumps(diagnostics, sort_keys=True))

        assert len(decoded) == 3
        assert {item["summary"]["request_id"] for item in decoded} == {
            result_summary(client.generate(request))["request_id"]
            for request in requests
        }
        assert all(item["validation"] is True for item in decoded)
        assert all("\n" not in item["log_line"] for item in decoded)

    def test_validation_failure_diagnostic_preserves_reason_order(
        self,
    ) -> None:
        request = _request(duration_sec=5.0, model="musicgen-medium")
        result = GenerationResult(
            audio_path=Path("/tmp/protocol-failure.wav"),
            sample_rate=8_000,
            duration_actual_sec=2.0,
            model_used="stable-audio-open",
            cost_usd=-0.1,
            latency_ms=-12,
            api_request_id="bad-result",
        )

        outcome = validate_generation_result(
            result,
            request,
            sample_rate_floor=16_000,
            duration_tolerance_sec=1.0,
        )
        diagnostic = {
            "passed": outcome.passed,
            "reasons": list(outcome.reasons),
            "summary": result_summary(result),
            "log_line": format_result_log_line(result),
        }

        assert json.loads(json.dumps(diagnostic, sort_keys=True))["passed"] is False
        assert outcome.passed is False
        assert [reason.split()[0] for reason in outcome.reasons] == [
            "model",
            "sample",
            "duration",
            "negative",
            "negative",
        ]
