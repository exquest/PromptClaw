"""Tests for daemon fallback when agent providers degrade."""

from __future__ import annotations

import sqlite3
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

    def test_prd_command_returns_ordered_roadmap(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        daemon_env: dict[str, object],
    ) -> None:
        project_root = tmp_path / "cypherclaw"
        state_dir = project_root / ".sdp"
        state_dir.mkdir(parents=True)
        db_path = state_dir / "state.db"

        con = sqlite3.connect(db_path)
        with con:
            con.execute(
                """
                CREATE TABLE tasks (
                    task_id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lead_agent TEXT,
                    verify_agent TEXT,
                    priority INTEGER NOT NULL DEFAULT 0,
                    complexity_score INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'manual',
                    criteria TEXT NOT NULL DEFAULT '',
                    rollback_count INTEGER NOT NULL DEFAULT 0,
                    parent_task_id TEXT,
                    status_reason TEXT NOT NULL DEFAULT '',
                    status_changed_at TEXT NOT NULL DEFAULT '',
                    status_changed_by TEXT NOT NULL DEFAULT '',
                    frozen INTEGER NOT NULL DEFAULT 0,
                    frozen_reason TEXT NOT NULL DEFAULT '',
                    frozen_at TEXT NOT NULL DEFAULT '',
                    frozen_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            rows = [
                ("T-011@20260331T232739Z", "home", "T1", "pending", None),
                ("T-001@20260328T142659Z", "restructure", "T1", "pending", None),
                ("T-001@20260401T195527Z", "studio", "T1", "running", None),
                ("T-010@20260327T172236Z", "glyph", "T2", "pending", None),
                ("T-001@20260327T221957Z", "pet", "T2", "pending", None),
                ("T-001@20260329T183119Z", "narrative", "T1", "pending", None),
                ("T-001@20260331T210000Z", "sense", "T1", "pending", None),
                ("T-001@20260327T234426Z", "proactive", "T1", "pending", None),
                ("T-001@20260327T233208Z", "web", "T1", "pending", None),
                ("T-001@20260329T205115Z", "federation", "T1", "pending", None),
                ("T-001@20260327T154047Z", "model awareness", "T1", "complete", None),
            ]
            for task_id, description, tier, status, parent_task_id in rows:
                con.execute(
                    """
                    INSERT INTO tasks (
                        task_id, description, tier, status, lead_agent, verify_agent, priority,
                        complexity_score, source, criteria, rollback_count, parent_task_id,
                        status_reason, status_changed_at, status_changed_by, frozen,
                        frozen_reason, frozen_at, frozen_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, NULL, 0, 0, 'prd', '', 0, ?, '', '', '', 0, '', '', '', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
                    """,
                    (task_id, description, tier, status, parent_task_id),
                )

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)

        handled = cypherclaw_daemon.handle_builtin("/prd")

        assert handled is True
        text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "PRD Roadmap" in text
        labels = [
            "Home Resilience",
            "Restructure",
            "GlyphWeave Studio Loop",
            "GlyphWeave Art",
            "Pet System v2",
            "Narrative Engine",
            "SenseWeave",
            "Proactive Intel",
            "Web Platform",
            "Federation",
        ]
        positions = [text.index(label) for label in labels]
        assert positions == sorted(positions)
        assert "running" in text.lower()
        assert "Completed Earlier" in text

    def test_monitor_command_returns_live_queue_state(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        daemon_env: dict[str, object],
    ) -> None:
        project_root = tmp_path / "cypherclaw"
        state_dir = project_root / ".sdp"
        state_dir.mkdir(parents=True)
        db_path = state_dir / "state.db"

        con = sqlite3.connect(db_path)
        with con:
            con.execute(
                """
                CREATE TABLE tasks (
                    task_id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lead_agent TEXT,
                    verify_agent TEXT,
                    priority INTEGER NOT NULL DEFAULT 0,
                    complexity_score INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'manual',
                    criteria TEXT NOT NULL DEFAULT '',
                    rollback_count INTEGER NOT NULL DEFAULT 0,
                    parent_task_id TEXT,
                    status_reason TEXT NOT NULL DEFAULT '',
                    status_changed_at TEXT NOT NULL DEFAULT '',
                    status_changed_by TEXT NOT NULL DEFAULT '',
                    frozen INTEGER NOT NULL DEFAULT 0,
                    frozen_reason TEXT NOT NULL DEFAULT '',
                    frozen_at TEXT NOT NULL DEFAULT '',
                    frozen_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE task_runs (
                    task_id TEXT NOT NULL,
                    lead_agent TEXT,
                    verify_agent TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    verdict TEXT,
                    gate_passed INTEGER,
                    work_result TEXT
                )
                """
            )
            task_rows = [
                ("T-home", "home", "T1", "pending", None),
                ("T-artist", "artist", "T1", "running", None),
                ("T-blocked", "blocked", "T1", "blocked", None),
                ("T-split", "split parent", "T1", "split", None),
            ]
            for task_id, description, tier, status, parent_task_id in task_rows:
                con.execute(
                    """
                    INSERT INTO tasks (
                        task_id, description, tier, status, lead_agent, verify_agent, priority,
                        complexity_score, source, criteria, rollback_count, parent_task_id,
                        status_reason, status_changed_at, status_changed_by, frozen,
                        frozen_reason, frozen_at, frozen_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, NULL, 0, 0, 'prd', '', 0, ?, '', '', '', 0, '', '', '', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
                    """,
                    (task_id, description, tier, status, parent_task_id),
                )
            con.execute(
                """
                INSERT INTO task_runs (
                    task_id, lead_agent, verify_agent, started_at, completed_at, verdict, gate_passed, work_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("T-artist", "codex", "gemini", "2026-04-01T00:00:00+00:00", None, "", 0, "no_work"),
            )

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cypherclaw_daemon, "_runner_service_state", lambda: "active")

        handled = cypherclaw_daemon.handle_builtin("/monitor")

        assert handled is True
        text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "SDP Monitor" in text
        assert "Progress: 0/4 complete (0%)" in text
        assert "Queue: 1 pending, 2 blocked, 1 running roots" in text
        assert "Runner: active" in text
        assert "Current: T-artist" in text
        assert "Pair: codex → gemini" in text

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
