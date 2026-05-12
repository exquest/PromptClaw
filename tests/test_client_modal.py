"""Tests for Modal generation client parity and behavior."""

from __future__ import annotations

import inspect
import os
import sys
from unittest.mock import MagicMock, patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.client_modal import ModalClient  # noqa: E402
from senseweave.generation.client_replicate import ReplicateClient  # noqa: E402


def test_modal_client_satisfies_protocol() -> None:
    """ModalClient should have the same signature as ReplicateClient.generate."""
    modal_sig = inspect.signature(ModalClient.generate)
    rep_sig = inspect.signature(ReplicateClient.generate)
    
    assert modal_sig == rep_sig


@patch("senseweave.generation.client_modal.modal")
def test_modal_client_computes_cost(mock_modal: MagicMock) -> None:
    """ModalClient should calculate cost using prediction metadata."""
    mock_func = MagicMock()
    mock_modal.Function.lookup.return_value = mock_func
    
    mock_func.remote.return_value = {"predict_time_sec": 10.0, "audio_bytes": b"test"}

    client = ModalClient()
    req = {"model": "musicgen-medium", "prompt": "test prompt", "duration_sec": 5.0}
    result = client.generate(req)
    
    assert result.get("cost_usd") is not None
    assert result["cost_usd"] > 0.0
