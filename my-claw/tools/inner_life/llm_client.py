"""LLM Client — thin wrapper around Ollama with timeout and GPU awareness.

Used for deep tick reflection, self-critique, and generating face messages.
Falls back gracefully if GPU is busy.
"""
from __future__ import annotations

import json
import urllib.request


OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:4b"
TIMEOUT_S = 10


def gpu_available() -> bool:
    """Check if Ollama can serve without a long queue."""
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=3)
        data = json.loads(resp.read())
        for m in data.get("models", []):
            # Large models block the GPU
            if "27b" in m.get("name", "") or "9b" in m.get("name", ""):
                return False
        return True
    except Exception:
        return False


def ask(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 60,
        temperature: float = 0.8) -> str:
    """Ask the local LLM a question. Returns empty string on failure."""
    if not gpu_available():
        return ""

    try:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=TIMEOUT_S)
        data = json.loads(resp.read())
        return data.get("response", "").strip()
    except Exception:
        return ""
