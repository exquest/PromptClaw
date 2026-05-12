"""Regression tests for direct Ollama HTTP invocation in the daemon."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import cypherclaw_daemon


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_invoke_ollama_posts_routed_generate_request(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        cypherclaw_daemon,
        "get_ollama_route",
        lambda category: {"model": "qwen3.5:122b", "port": 11435} if category == "review" else {"model": "default", "port": 11434},
    )

    def fake_urlopen(req: object, timeout: int) -> _FakeResponse:
        request = req
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["headers"] = dict(request.headers)
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"response": "review complete"})

    monkeypatch.setattr(cypherclaw_daemon.urllib.request, "urlopen", fake_urlopen)

    result = cypherclaw_daemon._invoke_ollama(
        "Please review this patch.",
        task_category="review",
    )

    assert result == "review complete"
    assert seen["url"] == "http://localhost:11435/api/generate"
    assert seen["timeout"] == 120
    assert seen["headers"]["Content-type"] == "application/json"
    assert seen["payload"] == {
        "model": "qwen3.5:122b",
        "prompt": "Please review this patch.",
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }


def test_invoke_ollama_detects_category_and_honors_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        cypherclaw_daemon.agent_selector,
        "detect_category",
        lambda task: "netops" if "firewall" in task else "coding",
    )
    monkeypatch.setattr(
        cypherclaw_daemon,
        "get_ollama_route",
        lambda category: {"model": "qwen3:30b-a3b", "port": 11435} if category == "netops" else {"model": "default", "port": 11434},
    )

    def fake_urlopen(req: object, timeout: int) -> _FakeResponse:
        request = req
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"response": "netops ready"})

    monkeypatch.setattr(cypherclaw_daemon.urllib.request, "urlopen", fake_urlopen)

    result = cypherclaw_daemon._invoke_ollama(
        "Investigate the firewall routing issue.",
        timeout=45,
    )

    assert result == "netops ready"
    assert seen["url"] == "http://localhost:11435/api/generate"
    assert seen["timeout"] == 45
    assert seen["payload"]["model"] == "qwen3:30b-a3b"


def test_invoke_ollama_returns_bracketed_error_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cypherclaw_daemon,
        "get_ollama_route",
        lambda category: {"model": "qwen3-coder:30b", "port": 11434},
    )

    def fake_urlopen(req: object, timeout: int) -> _FakeResponse:
        raise urllib.error.URLError("connection refused")

    import urllib.error

    monkeypatch.setattr(cypherclaw_daemon.urllib.request, "urlopen", fake_urlopen)

    result = cypherclaw_daemon._invoke_ollama(
        "Implement the fix.",
        task_category="coding",
    )

    assert result.startswith("[ollama error:")
    assert result.endswith("]")
    assert "connection refused" in result
