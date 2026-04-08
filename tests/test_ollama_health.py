"""Tests for the Ollama health helper."""

from __future__ import annotations

import json
import socket
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import ollama_health


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_check_health_returns_true_with_default_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(url: str, timeout: int) -> _FakeResponse:
        seen["url"] = url
        seen["timeout"] = timeout
        return _FakeResponse({"models": [{"name": "qwen3:30b-a3b"}]})

    monkeypatch.setattr(ollama_health.urllib.request, "urlopen", fake_urlopen)

    assert ollama_health.check_health(11435) is True
    assert seen == {
        "url": "http://localhost:11435/api/ps",
        "timeout": 5,
    }


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("connection refused"),
        socket.timeout("timed out"),
    ],
)
def test_check_health_returns_false_on_connection_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fake_urlopen(url: str, timeout: int) -> _FakeResponse:
        raise error

    monkeypatch.setattr(ollama_health.urllib.request, "urlopen", fake_urlopen)

    assert ollama_health.check_health(11434) is False


def test_check_models_returns_loaded_model_names(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str, timeout: int) -> _FakeResponse:
        return _FakeResponse(
            {
                "models": [
                    {"name": "qwen3-coder:30b"},
                    {"name": "qwen3.5:122b"},
                    {"size": 123},
                ]
            }
        )

    monkeypatch.setattr(ollama_health.urllib.request, "urlopen", fake_urlopen)

    assert ollama_health.check_models(11434) == [
        "qwen3-coder:30b",
        "qwen3.5:122b",
    ]


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("connection refused"),
        socket.timeout("timed out"),
    ],
)
def test_check_models_returns_empty_list_on_connection_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fake_urlopen(url: str, timeout: int) -> _FakeResponse:
        raise error

    monkeypatch.setattr(ollama_health.urllib.request, "urlopen", fake_urlopen)

    assert ollama_health.check_models(11434) == []
