"""Tests for daemon fallback when agent providers degrade."""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import cypherclaw_daemon


class FakeQuotaMonitor:
    def __init__(self, available: list[str], status: dict[str, dict[str, object]] | None = None) -> None:
        self.available = list(available)
        self.status = status or {
            "anthropic": {"status": "healthy", "headroom": 0.80, "confidence": "observed"},
            "openai": {"status": "healthy", "headroom": 0.70, "confidence": "observed"},
            "google": {"status": "healthy", "headroom": 0.60, "confidence": "observed"},
        }
        self.forced: list[tuple[str, str]] = []

    def get_available_agents(self, agents: list[str] | tuple[str, ...] | None = None) -> list[str]:
        candidates = list(agents) if agents is not None else ["claude", "codex", "gemini"]
        filtered = [agent for agent in self.available if agent in candidates]
        if filtered:
            return filtered
        return [candidates[0]]

    def get_provider_status(self) -> dict[str, dict[str, object]]:
        return self.status

    def get_agent_headroom(self, agent_name: str) -> float:
        provider = cypherclaw_daemon.PROVIDERS[agent_name]
        return float(self.status[provider]["headroom"])

    def force_status(self, provider: str, status: str, **_: object) -> None:
        self.status.setdefault(provider, {})
        self.status[provider]["status"] = status
        self.forced.append((provider, status))


class FakeObservatory:
    def __init__(self) -> None:
        self.task_results: list[dict[str, object]] = []
        self.healing_events: list[dict[str, object]] = []
        self.events: list[tuple[str, dict[str, object]]] = []

    def record_task_result(self, **kwargs: object) -> None:
        self.task_results.append(dict(kwargs))

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

    def record(self, event_type: str, data: dict[str, object]) -> None:
        self.events.append((event_type, data))


class FakePetManager:
    def on_task_start(self, agent_name: str) -> None:
        return None

    def on_task_end(self, agent_name: str, success: bool, duration_s: float) -> tuple[None, bool, None]:
        return None, False, None

    def schedule_idle(self, agent_name: str) -> None:
        return None


@pytest.fixture
def daemon_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    obs = FakeObservatory()
    quota = FakeQuotaMonitor(["claude", "codex", "gemini"])
    sent_messages: list[str] = []

    monkeypatch.setattr(cypherclaw_daemon, "observatory", obs)
    monkeypatch.setattr(cypherclaw_daemon, "quota_monitor", quota)
    monkeypatch.setattr(cypherclaw_daemon, "pet_manager", FakePetManager())
    monkeypatch.setattr(cypherclaw_daemon.AgentSpinner, "start", lambda self: None)
    monkeypatch.setattr(cypherclaw_daemon.AgentSpinner, "stop", lambda self: None)
    monkeypatch.setattr(cypherclaw_daemon, "tg_send", sent_messages.append)
    monkeypatch.setattr(
        cypherclaw_daemon,
        "healer",
        SimpleNamespace(handle_failure=lambda failure: SimpleNamespace(resolved=False, severity=0, action_taken="noop")),
    )
    monkeypatch.setattr(
        cypherclaw_daemon,
        "state",
        SimpleNamespace(
            conversation=deque(),
            tasks={},
            schedules=[],
            pending_confirm=None,
            add_message=lambda *args, **kwargs: None,
        ),
    )
    monkeypatch.setattr(cypherclaw_daemon, "list_artifacts", lambda: [])
    monkeypatch.setattr(cypherclaw_daemon, "fast_route", lambda text: None)

    return {"observatory": obs, "quota_monitor": quota, "sent_messages": sent_messages}


class TestDaemonFallback:
    def test_cli_quota_error_triggers_retry_with_different_agent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        daemon_env: dict[str, object],
    ) -> None:
        calls: list[str] = []

        def fake_invoke(agent_name: str, prompt: str, timeout: int) -> cypherclaw_daemon.AgentCommandResult:
            calls.append(agent_name)
            if agent_name == "claude":
                return cypherclaw_daemon.AgentCommandResult(
                    stdout="",
                    stderr="rate limit exceeded",
                    returncode=1,
                )
            return cypherclaw_daemon.AgentCommandResult(
                stdout="codex saved the day",
                stderr="",
                returncode=0,
            )

        monkeypatch.setattr(cypherclaw_daemon, "_invoke_agent_process", fake_invoke)

        output = cypherclaw_daemon.run_agent("claude", "fix the bug", task_label="quota-test")

        assert output == "codex saved the day"
        assert calls == ["claude", "codex"]

    def test_routing_fallback_uses_available_agents(
        self,
        monkeypatch: pytest.MonkeyPatch,
        daemon_env: dict[str, object],
    ) -> None:
        daemon_env["quota_monitor"].available = ["codex", "gemini"]  # type: ignore[index]
        monkeypatch.setattr(
            cypherclaw_daemon,
            "agent_selector",
            SimpleNamespace(select=lambda *args, **kwargs: "codex"),
        )

        def fake_router(agent_name: str, route_prompt: str, route_env: dict[str, str], timeout: int) -> object:
            raise cypherclaw_daemon.subprocess.TimeoutExpired(cmd=agent_name, timeout=timeout)

        monkeypatch.setattr(cypherclaw_daemon, "_invoke_router_agent", fake_router)

        steps = cypherclaw_daemon.route_message("please handle this")

        assert steps[-1]["type"] == "agent"
        assert steps[-1]["agent"] == "codex"

    def test_quota_error_updates_monitor_status(
        self,
        monkeypatch: pytest.MonkeyPatch,
        daemon_env: dict[str, object],
    ) -> None:
        monkeypatch.setattr(
            cypherclaw_daemon,
            "_invoke_agent_process",
            lambda agent_name, prompt, timeout: cypherclaw_daemon.AgentCommandResult(
                stdout="",
                stderr="billing quota exhausted",
                returncode=1,
            ),
        )

        cypherclaw_daemon.run_agent("claude", "fix the bug", task_label="quota-status-test")

        assert ("anthropic", "paused") in daemon_env["quota_monitor"].forced  # type: ignore[index]

    def test_quota_command_returns_status(
        self,
        monkeypatch: pytest.MonkeyPatch,
        daemon_env: dict[str, object],
    ) -> None:
        daemon_env["quota_monitor"].status = {  # type: ignore[index]
            "anthropic": {"status": "paused", "headroom": 0.03, "confidence": "observed"},
            "openai": {"status": "warn", "headroom": 0.22, "confidence": "observed"},
            "google": {"status": "healthy", "headroom": 0.85, "confidence": "observed"},
        }

        handled = cypherclaw_daemon.handle_builtin("/quota")

        assert handled is True
        assert daemon_env["sent_messages"]  # type: ignore[index]
        assert "Provider Quota" in daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "openai" in daemon_env["sent_messages"][-1]  # type: ignore[index]

    def test_non_quota_error_does_not_trigger_fallback(
        self,
        monkeypatch: pytest.MonkeyPatch,
        daemon_env: dict[str, object],
    ) -> None:
        calls: list[str] = []

        def fake_invoke(agent_name: str, prompt: str, timeout: int) -> cypherclaw_daemon.AgentCommandResult:
            calls.append(agent_name)
            return cypherclaw_daemon.AgentCommandResult(
                stdout="",
                stderr="SyntaxError: invalid syntax",
                returncode=1,
            )

        monkeypatch.setattr(cypherclaw_daemon, "_invoke_agent_process", fake_invoke)

        output = cypherclaw_daemon.run_agent("claude", "fix the bug", task_label="non-quota-test")

        assert calls == ["claude"]
        assert "SyntaxError" in output
