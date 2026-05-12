"""Modal-backed generation client (CCG-012 / T-003)."""

from __future__ import annotations

import time
from typing import Any

try:
    import modal  # type: ignore
except ImportError:
    modal = None  # type: ignore

from .client_replicate import GenerationError


# Modal A10G price: ~$1.10 per hour = ~$0.000305 per second
PER_SECOND_A10G_USD = 1.10 / 3600.0


class ModalClient:
    """Modal-backed generation client parallel to ReplicateClient."""

    def __init__(self, timeout_sec: float = 120.0) -> None:
        self._timeout_sec = timeout_sec
        # We lookup the CypherClaw generation function lazily to avoid
        # requiring Modal credentials just to import this module.
        self._app_name = "cypherclaw-musicgen"
        self._function_name = "generate"

    def generate(self, request: Any) -> Any:
        """Submit a generation request through Modal."""
        if modal is None:
            raise GenerationError("Modal SDK not installed")

        try:
            func = modal.Function.lookup(self._app_name, self._function_name)
            
            # Record local latency
            start_time = time.monotonic()
            
            # Call the function synchronously
            result = func.remote(request)
            
            latency_ms = int((time.monotonic() - start_time) * 1000)
            
            if not isinstance(result, dict):
                # If it doesn't return a dict, wrap it
                result = {"audio_bytes": result}
            
            # Cost computed from prediction metadata if present, else fallback to latency
            predict_time_sec = result.get("predict_time_sec", latency_ms / 1000.0)
            cost_usd = predict_time_sec * PER_SECOND_A10G_USD
            
            result["cost_usd"] = cost_usd
            result["latency_ms"] = latency_ms
            
            return result
            
        except Exception as exc:
            raise GenerationError(f"Modal generation failed: {exc}") from exc
