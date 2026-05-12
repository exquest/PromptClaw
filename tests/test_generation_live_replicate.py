"""Live Replicate integration smoke test for generation client (T-005).

This test is gated behind both the ``--run-live-replicate`` pytest flag
and a non-empty ``REPLICATE_API_TOKEN`` environment variable, so the
default ``pytest tests/`` run never touches the real Replicate API.

Each opted-in run costs approximately ~$0.10 against the live
Replicate API (one MusicGen submission + 30 second WAV download). Use
sparingly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.client_replicate import ReplicateClient  # noqa: E402


def _result_field(result: Any, field: str) -> Any:
    """Normalize result lookup across dict-shaped and dataclass-shaped returns."""
    if isinstance(result, dict):
        return result.get(field)
    return getattr(result, field, None)


def _payload_size_bytes(result: Any) -> int:
    """Compute the WAV payload size from either inline bytes or a file path."""
    audio_bytes = _result_field(result, "audio_bytes")
    if isinstance(audio_bytes, (bytes, bytearray)):
        return len(audio_bytes)
    audio_path = _result_field(result, "audio_path") or _result_field(result, "wav_path")
    if audio_path is not None:
        return Path(str(audio_path)).stat().st_size
    raise AssertionError(
        "live Replicate result exposed neither 'audio_bytes' nor an audio path"
    )


@pytest.mark.live_replicate
def test_replicate_client_live_generation() -> None:
    """End-to-end smoke test invoking the real Replicate MusicGen endpoint.

    Cost: approximately ~$0.10 per run against the live Replicate API.
    """
    if not os.environ.get("REPLICATE_API_TOKEN"):
        pytest.skip("REPLICATE_API_TOKEN not set; live Replicate test cannot run")

    client = ReplicateClient(api_token=os.environ["REPLICATE_API_TOKEN"])

    request_data = {
        "model": "musicgen-medium",
        "prompt": "ambient pad, slow, sparse, 30 seconds",
        "duration_sec": 30.0,
        "seed": 42,
    }

    result = client.generate(request_data)

    payload_size = _payload_size_bytes(result)
    assert payload_size > 100 * 1024, (
        f"expected WAV payload > 100 KB, got {payload_size} bytes"
    )

    cost_usd = _result_field(result, "cost_usd")
    assert cost_usd is not None, "live Replicate result missing 'cost_usd'"
    assert cost_usd > 0.01 and cost_usd < 0.50, (
        f"cost_usd outside sanity bound [$0.01, $0.50]: {cost_usd}"
    )

    latency_ms = _result_field(result, "latency_ms")
    assert latency_ms is not None, "live Replicate result missing 'latency_ms'"
    assert latency_ms < 60000, f"latency_ms exceeded 60s budget: {latency_ms}"
