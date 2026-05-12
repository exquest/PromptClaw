"""Tests for the CypherClaw self-healing engine."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import healer


def _failure(
    failure_type: str,
    *,
    error_message: str = "boom",
    context: dict | None = None,
    timestamp: float | None = None,
) -> healer.Failure:
    return healer.Failure(
        type=failure_type,
        error_message=error_message,
        context=context or {},
        timestamp=time.time() if timestamp is None else timestamp,
    )


def test_handle_failure_notifies_after_resolved_agent_error(monkeypatch: pytest.MonkeyPatch) -> None:
    notifications: list[str] = []
    engine = healer.Healer(notify_fn=notifications.append, ask_fn=lambda _: "yes")

    monkeypatch.setattr(engine, "_try_run_agent", lambda agent, command, task_id: agent == "codex")

    result = engine.handle_failure(
        _failure(
            "agent_error",
            context={"agent": "claude", "task_id": "T-123", "command": "run", "retry_count": 3},
        )
    )

    assert result.resolved is True
    assert result.severity == healer.NOTIFY
    assert "codex" in result.action_taken
    assert notifications and "resolved" in notifications[0]


def test_handle_failure_respects_user_denial_for_ask_severity() -> None:
    notifications: list[str] = []
    prompts: list[str] = []
    engine = healer.Healer(
        notify_fn=notifications.append,
        ask_fn=lambda message: prompts.append(message) or "no",
    )

    result = engine.handle_failure(
        _failure(
            "gate_failure",
            error_message="gate failed",
            context={"agent": "codex", "task_id": "T-456", "retry_count": 3},
        )
    )

    assert result.resolved is False
    assert result.action_taken == "user declined auto-fix"
    assert result.severity == healer.ASK
    assert prompts and "Should I attempt auto-fix?" in prompts[0]
    assert notifications == []


def test_gate_failure_tries_alternate_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []
    engine = healer.Healer(notify_fn=lambda _: None, ask_fn=lambda _: "yes")

    def fake_try_run_agent(agent: str, command: str, task_id: str) -> bool:
        attempts.append(agent)
        return agent == "codex"

    monkeypatch.setattr(engine, "_try_run_agent", fake_try_run_agent)

    result = engine.handle_failure(
        _failure(
            "gate_failure",
            error_message="lint failed",
            context={"agent": "claude", "task_id": "T-789", "retry_count": 1},
        )
    )

    assert result.resolved is True
    assert attempts == ["claude", "codex"]
    assert "codex" in result.action_taken


def test_classify_process_crash_escalates_after_crash_loop() -> None:
    engine = healer.Healer(notify_fn=lambda _: None, ask_fn=lambda _: "yes")
    now = time.time()
    engine._crash_history["daemon"] = [now - 10, now - 20, now - 30]

    severity = engine.classify_severity(
        _failure(
            "process_crash",
            context={"process": "daemon"},
            timestamp=now,
        )
    )

    assert severity == healer.ASK


def test_parse_package_name_handles_import_and_command_failures() -> None:
    engine = healer.Healer(notify_fn=lambda _: None, ask_fn=lambda _: "yes")

    assert engine._parse_package_name("ModuleNotFoundError: No module named 'yaml'") == "yaml"
    assert engine._parse_package_name("ImportError: cannot import name 'x' from 'requests.sessions'") == "requests"
    assert engine._parse_package_name("rg: command not found") == "rg"
