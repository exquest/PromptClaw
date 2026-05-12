"""Helpers for checking Ollama instance health and loaded models."""

from __future__ import annotations

import json
import urllib.request
from typing import Any


DEFAULT_TIMEOUT_S = 5


def _ps_url(port: int) -> str:
    return f"http://localhost:{port}/api/ps"


def _read_ps(port: int, timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(_ps_url(port), timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None

    return payload if isinstance(payload, dict) else None


def check_health(port: int) -> bool:
    """Return whether Ollama responds on the provided port within 5 seconds."""
    return _read_ps(port) is not None


def check_models(port: int) -> list[str]:
    """Return the names of models currently loaded on the Ollama instance."""
    payload = _read_ps(port)
    if payload is None:
        return []

    models = payload.get("models")
    if not isinstance(models, list):
        return []

    names = [model.get("name") for model in models if isinstance(model, dict)]
    return [name for name in names if isinstance(name, str)]
