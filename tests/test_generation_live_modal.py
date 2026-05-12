"""Live Modal integration test for generation client."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.client_modal import ModalClient  # noqa: E402


@pytest.mark.live_modal
def test_modal_client_live_generation() -> None:
    """End-to-end smoke test invoking the real Modal MusicGen deployment."""
    client = ModalClient()
    
    request_data = {
        "model": "musicgen-medium",
        "prompt": "solitary: intimate, sparse, single voice",
        "duration_sec": 5.0,
        "seed": 42
    }
    
    result = client.generate(request_data)
    
    assert "cost_usd" in result
    assert result["cost_usd"] > 0.0
    assert "latency_ms" in result
    assert result["latency_ms"] > 0
