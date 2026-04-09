"""Regression tests for Ollama routing through run_agent()."""

from __future__ import annotations

import sys
import threading
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import cypherclaw_daemon


class FakeObservatory:
    def __init__(self) -> None:
        self.task_results: list[dict[str, object]] = []
        self.events: list[tuple[str, dict[str, object]]] = []
        self.healing_events: list[dict[str, object]] = []

    def record_task_result(self, **kwargs: object) -> None:
        self.task_results.append(dict(kwargs))

    def record(self, event_type: str, data: dict[str, object]) -> None:
        self.events.append((event_type, data))

    def record_healing(
        self,
        failure_type: str,
        severity: int,
        action_taken: str,
        success: bool,
        context: dict[str, object],
    ) -> None:
        self.healing_events.append(
            {
                "failure_type": failure_type,
                "severity": severity,
                "action_taken": action_taken,
                "success": success,
                "context": context,
            }
        )


class FakePetManager:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def on_task_start(self, agent_name: str) -> None:
        self.calls.append(("start", agent_name))

    def on_task_end(self, agent_name: str, success: bool, duration_s: float) -> tuple[int, bool, None]:
        self.calls.append(("end", agent_name, success, duration_s))
        return 7, False, None

    def schedule_idle(self, agent_name: str) -> None:
        self.calls.append(("idle", agent_name))

    def get(self, agent_name: str) -> SimpleNamespace:
        return SimpleNamespace(get_portrait=lambda: f"{agent_name}-portrait")


def _stub_runtime(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeObservatory, FakePetManager]:
    observatory = FakeObservatory()
    pet_manager = FakePetManager()
    monkeypatch.setattr(cypherclaw_daemon, "observatory", observatory)
    monkeypatch.setattr(cypherclaw_daemon, "pet_manager", pet_manager)
    monkeypatch.setattr(cypherclaw_daemon, "_agent_semaphore", threading.Semaphore(1))
    monkeypatch.setattr(cypherclaw_daemon, "_agent_count", 0)
    monkeypatch.setattr(cypherclaw_daemon.AgentSpinner, "start", lambda self: None)
    monkeypatch.setattr(cypherclaw_daemon.AgentSpinner, "stop", lambda self: None)
    monkeypatch.setattr(cypherclaw_daemon, "tg_send", lambda message: None)
    monkeypatch.setattr(
        cypherclaw_daemon,
        "healer",
        SimpleNamespace(handle_failure=lambda failure: SimpleNamespace(resolved=False, severity=0, action_taken="noop")),
    )
    return observatory, pet_manager


def test_run_agent_ollama_uses_http_path_and_preserves_bookkeeping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observatory, pet_manager = _stub_runtime(monkeypatch)
    ollama_calls: list[dict[str, object]] = []
    time_points = iter((100.0, 102.5))

    def fake_time() -> float:
        try:
            return next(time_points)
        except StopIteration:
            return 102.5

    monkeypatch.setattr(cypherclaw_daemon.time, "time", fake_time)

    def fake_invoke_ollama(
        prompt: str,
        timeout: int = 120,
        *,
        task_category: str | None = None,
        task_label: str = "",
    ) -> str:
        ollama_calls.append(
            {
                "prompt": prompt,
                "timeout": timeout,
                "task_category": task_category,
                "task_label": task_label,
            }
        )
        return "ollama response"

    monkeypatch.setattr(cypherclaw_daemon, "_invoke_ollama", fake_invoke_ollama)
    monkeypatch.setattr(
        cypherclaw_daemon,
        "_invoke_agent_process",
        lambda *args, **kwargs: pytest.fail("run_agent('ollama', ...) should not spawn a subprocess"),
    )

    output = cypherclaw_daemon.run_agent(
        "ollama",
        "Explain the daemon bug.",
        timeout=33,
        task_label="ollama regression",
    )

    assert output == "ollama response"
    assert ollama_calls == [
        {
            "prompt": "Explain the daemon bug.",
            "timeout": 33,
            "task_category": None,
            "task_label": "ollama regression",
        }
    ]
    assert pet_manager.calls[0] == ("start", "ollama")
    assert pet_manager.calls[1][:3] == ("end", "ollama", True)
    assert isinstance(pet_manager.calls[1][3], float)
    assert pet_manager.calls[1][3] >= 0.0
    assert pet_manager.calls[2] == ("idle", "ollama")
    assert len(observatory.task_results) == 1
    result = observatory.task_results[0]
    assert result["agent"] == "ollama"
    assert result["task_id"] == "ollama regression"
    assert result["success"] is True
    assert isinstance(result["duration_ms"], int)
    assert result["duration_ms"] >= 0
    assert result["tokens"] == 0
    assert result["gate_pass"] is True
    assert [event for event, _data in observatory.events] == [
        "semaphore_acquired",
        "semaphore_released",
    ]
    assert observatory.healing_events == []


def test_available_agents_local_only_restricts_to_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    monkeypatch.setenv("LOCAL_ONLY", "true")

    def fake_get_available_agents(agents: list[str] | tuple[str, ...] | None = None) -> list[str]:
        candidate_list = list(agents or [])
        seen.append(candidate_list)
        return candidate_list

    monkeypatch.setattr(cypherclaw_daemon.quota_monitor, "get_available_agents", fake_get_available_agents)

    assert cypherclaw_daemon._available_agents(["claude", "codex", "gemini"]) == ["ollama"]
    assert seen == [["ollama"]]


def test_best_available_agent_local_only_never_falls_back_to_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_ONLY", "1")
    monkeypatch.setattr(cypherclaw_daemon.quota_monitor, "get_available_agents", lambda agents=None: [])

    assert cypherclaw_daemon._best_available_agent(["claude", "codex", "gemini"]) == "ollama"


def test_route_message_local_only_bypasses_cloud_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_ONLY", "true")
    monkeypatch.setattr(cypherclaw_daemon, "state", SimpleNamespace(conversation=deque()))
    monkeypatch.setattr(cypherclaw_daemon, "list_artifacts", lambda: [])
    monkeypatch.setattr(cypherclaw_daemon, "pet_manager", FakePetManager())
    monkeypatch.setattr(
        cypherclaw_daemon,
        "_invoke_router_agent",
        lambda *args, **kwargs: pytest.fail("LOCAL_ONLY route_message() should not invoke a cloud router"),
    )

    steps = cypherclaw_daemon.route_message("please fix the daemon bug")

    assert steps[-1]["type"] == "agent"
    assert steps[-1]["agent"] == "ollama"


def test_execute_plan_local_only_coerces_cloud_agent_step_to_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_ONLY", "true")
    observatory, pet_manager = _stub_runtime(monkeypatch)
    sent: list[str] = []
    ollama_calls: list[dict[str, object]] = []

    monkeypatch.setattr(cypherclaw_daemon, "tg_send", sent.append)
    monkeypatch.setattr(cypherclaw_daemon, "tg_send_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(cypherclaw_daemon, "save_artifact", lambda name, content: Path("/tmp") / name)
    monkeypatch.setattr(cypherclaw_daemon, "state", SimpleNamespace(add_message=lambda *args, **kwargs: None))
    monkeypatch.setattr(cypherclaw_daemon, "agent_selector", SimpleNamespace(record_outcome=lambda *args, **kwargs: None))

    def fake_invoke_ollama(
        prompt: str,
        timeout: int = 120,
        *,
        task_category: str | None = None,
        task_label: str = "",
    ) -> str:
        ollama_calls.append(
            {
                "prompt": prompt,
                "timeout": timeout,
                "task_category": task_category,
                "task_label": task_label,
            }
        )
        return "ollama handled explicit cloud step"

    monkeypatch.setattr(cypherclaw_daemon, "_invoke_ollama", fake_invoke_ollama)
    monkeypatch.setattr(
        cypherclaw_daemon,
        "_invoke_agent_process",
        lambda *args, **kwargs: pytest.fail("LOCAL_ONLY execute_plan() should not invoke a cloud agent process"),
    )

    cypherclaw_daemon.execute_plan(
        [{"type": "agent", "agent": "claude", "prompt": "Apply the fix.", "label": "local only step"}]
    )

    assert ollama_calls == [
        {
            "prompt": "Apply the fix.",
            "timeout": cypherclaw_daemon.MAX_AGENT_TIMEOUT,
            "task_category": None,
            "task_label": "local only step",
        }
    ]
    assert observatory.task_results[-1]["agent"] == "ollama"
    assert pet_manager.calls[0] == ("start", "ollama")
    assert pet_manager.calls[1][:3] == ("end", "ollama", True)
    assert pet_manager.calls[2] == ("idle", "ollama")
    assert any("ollama handled explicit cloud step" in message for message in sent)


def test_run_agent_local_only_coerces_explicit_cloud_agent_to_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_ONLY", "true")
    observatory, pet_manager = _stub_runtime(monkeypatch)
    ollama_calls: list[dict[str, object]] = []

    def fake_invoke_ollama(
        prompt: str,
        timeout: int = 120,
        *,
        task_category: str | None = None,
        task_label: str = "",
    ) -> str:
        ollama_calls.append(
            {
                "prompt": prompt,
                "timeout": timeout,
                "task_category": task_category,
                "task_label": task_label,
            }
        )
        return "ollama local-only response"

    monkeypatch.setattr(cypherclaw_daemon, "_invoke_ollama", fake_invoke_ollama)
    monkeypatch.setattr(
        cypherclaw_daemon,
        "_invoke_agent_process",
        lambda *args, **kwargs: pytest.fail("LOCAL_ONLY run_agent() should not invoke a cloud subprocess"),
    )

    output = cypherclaw_daemon.run_agent(
        "claude",
        "Explain the change.",
        timeout=17,
        task_label="local-only direct run",
    )

    assert output == "ollama local-only response"
    assert ollama_calls == [
        {
            "prompt": "Explain the change.",
            "timeout": 17,
            "task_category": None,
            "task_label": "local-only direct run",
        }
    ]
    assert observatory.task_results[-1]["agent"] == "ollama"
    assert pet_manager.calls[0] == ("start", "ollama")
    assert pet_manager.calls[1][:3] == ("end", "ollama", True)
    assert pet_manager.calls[2] == ("idle", "ollama")


def test_run_agent_cloud_path_unchanged_when_local_only_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCAL_ONLY", raising=False)
    observatory, pet_manager = _stub_runtime(monkeypatch)
    cloud_calls: list[tuple[str, str, int]] = []

    monkeypatch.setattr(
        cypherclaw_daemon,
        "_invoke_agent_process",
        lambda agent, prompt, timeout: (
            cloud_calls.append((agent, prompt, timeout))
            or cypherclaw_daemon.AgentCommandResult(stdout="cloud response", stderr="", returncode=0)
        ),
    )
    monkeypatch.setattr(
        cypherclaw_daemon,
        "_invoke_ollama",
        lambda *args, **kwargs: pytest.fail("cloud path should not invoke ollama when LOCAL_ONLY is disabled"),
    )

    output = cypherclaw_daemon.run_agent(
        "claude",
        "Explain the change.",
        timeout=19,
        task_label="cloud path",
    )

    assert output == "cloud response"
    assert cloud_calls == [("claude", "Explain the change.", 19)]
    assert observatory.task_results[-1]["agent"] == "claude"
    assert pet_manager.calls[0] == ("start", "claude")
    assert pet_manager.calls[1][:3] == ("end", "claude", True)
    assert pet_manager.calls[2] == ("idle", "claude")
