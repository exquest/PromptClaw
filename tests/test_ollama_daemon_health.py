"""Unit tests for daemon-level Ollama health summaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import cypherclaw_daemon


def test_ollama_health_reports_both_ports_models_and_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    health_calls: list[int] = []
    model_calls: list[int] = []
    ticks = iter([10.0, 10.012, 20.0, 20.034])

    monkeypatch.setattr(
        cypherclaw_daemon.ollama_probe,
        "check_health",
        lambda port: health_calls.append(port) or True,
    )
    monkeypatch.setattr(
        cypherclaw_daemon.ollama_probe,
        "check_models",
        lambda port: model_calls.append(port) or {
            11434: ["qwen3-coder:30b"],
            11435: ["qwen3.5:122b", "qwen3:30b-a3b"],
        }[port],
    )
    monkeypatch.setattr(cypherclaw_daemon.time, "perf_counter", lambda: next(ticks))

    result = cypherclaw_daemon.ollama_health()

    assert json.loads(json.dumps(result)) == result
    assert result == {
        "healthy": True,
        "instances": [
            {
                "socket": "socket0",
                "port": 11434,
                "healthy": True,
                "status": "healthy",
                "models": ["qwen3-coder:30b"],
                "latency_ms": 12,
            },
            {
                "socket": "socket1",
                "port": 11435,
                "healthy": True,
                "status": "healthy",
                "models": ["qwen3.5:122b", "qwen3:30b-a3b"],
                "latency_ms": 34,
            },
        ],
    }
    assert health_calls == [11434, 11435]
    assert model_calls == [11434, 11435]


def test_ollama_health_marks_unreachable_socket_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_calls: list[int] = []
    ticks = iter([1.0, 1.005, 2.0, 2.009])

    monkeypatch.setattr(
        cypherclaw_daemon.ollama_probe,
        "check_health",
        lambda port: port == 11434,
    )
    monkeypatch.setattr(
        cypherclaw_daemon.ollama_probe,
        "check_models",
        lambda port: model_calls.append(port) or ["qwen3-coder:30b"],
    )
    monkeypatch.setattr(cypherclaw_daemon.time, "perf_counter", lambda: next(ticks))

    result = cypherclaw_daemon.ollama_health()

    assert result == {
        "healthy": True,
        "instances": [
            {
                "socket": "socket0",
                "port": 11434,
                "healthy": True,
                "status": "healthy",
                "models": ["qwen3-coder:30b"],
                "latency_ms": 5,
            },
            {
                "socket": "socket1",
                "port": 11435,
                "healthy": False,
                "status": "unreachable",
                "models": [],
                "latency_ms": None,
            },
        ],
    }
    assert model_calls == [11434]


def test_ollama_health_returns_dual_unhealthy_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter([30.0, 30.003, 40.0, 40.004])

    monkeypatch.setattr(cypherclaw_daemon.ollama_probe, "check_health", lambda port: False)
    monkeypatch.setattr(
        cypherclaw_daemon.ollama_probe,
        "check_models",
        lambda port: pytest.fail("check_models should not be called when the probe is unhealthy"),
    )
    monkeypatch.setattr(cypherclaw_daemon.time, "perf_counter", lambda: next(ticks))

    result = cypherclaw_daemon.ollama_health()

    assert result["healthy"] is False
    assert result["instances"] == [
        {
            "socket": "socket0",
            "port": 11434,
            "healthy": False,
            "status": "unreachable",
            "models": [],
            "latency_ms": None,
        },
        {
            "socket": "socket1",
            "port": 11435,
            "healthy": False,
            "status": "unreachable",
            "models": [],
            "latency_ms": None,
        },
    ]
