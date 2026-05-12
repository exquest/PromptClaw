"""Tests for daemon fallback when agent providers degrade."""

from __future__ import annotations

import json
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
    def test_child_process_env_strips_systemd_watchdog_vars(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("NOTIFY_SOCKET", "/tmp/notify.sock")
        monkeypatch.setenv("WATCHDOG_PID", "123")
        monkeypatch.setenv("WATCHDOG_USEC", "1000000")
        monkeypatch.setenv("KEEP_ME", "yes")

        env = cypherclaw_daemon._child_process_env({"EXTRA": "1"})

        assert "NOTIFY_SOCKET" not in env
        assert "WATCHDOG_PID" not in env
        assert "WATCHDOG_USEC" not in env
        assert env["KEEP_ME"] == "yes"
        assert env["EXTRA"] == "1"

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
        sdp_dir = project_root / "sdp"
        sdp_dir.mkdir()

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
                ("T-001@20260402T175501Z", "clone install", "T1", "pending", None),
                ("T-001@20260402T175502Z", "identity", "T1", "pending", None),
                ("T-001@20260401T195527Z", "studio", "T1", "running", None),
                ("T-002@20260401T195527Z", "studio split parent", "T1", "split", None),
                ("T-002@20260401T195527Za", "studio child a", "T1", "pending", "T-002@20260401T195527Z"),
                ("T-002@20260401T195527Zb", "studio child b", "T1", "complete", "T-002@20260401T195527Z"),
                ("T-010@20260327T172236Z", "glyph", "T2", "pending", None),
                ("T-001@20260402T175504Z-2", "embodiment core", "T1", "pending", None),
                ("T-001@20260327T221957Z", "pet", "T2", "pending", None),
                ("T-001@20260329T183119Z", "narrative", "T1", "pending", None),
                ("T-001@20260331T210000Z", "sense", "T1", "pending", None),
                ("T-001@20260402T175503Z-2", "publication", "T1", "pending", None),
                ("T-001@20260402T175502Z-2", "federation read", "T1", "pending", None),
                ("T-001@20260402T175503Z", "proposal writes", "T1", "pending", None),
                ("T-001@20260402T175504Z", "bundle exchange", "T1", "pending", None),
                ("T-001@20260402T175505Z", "interaction loops", "T1", "pending", None),
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
            con.execute(
                """
                UPDATE tasks
                SET frozen = 1,
                    frozen_reason = 'superseded',
                    frozen_at = '2026-04-02T00:00:00+00:00',
                    frozen_by = 'pytest'
                WHERE task_id = 'T-001@20260328T142659Z'
                """
            )

        (sdp_dir / "execution-roadmap.md").write_text(
            "\n".join(
                [
                    "# CypherClaw Execution Roadmap",
                    "",
                    "## Execution Spine",
                    "",
                    "| Stage | PRD | Why it is here | Unlocks |",
                    "|---|---|---|---|",
                    "| 1 | [prd-home-resilience.md](./prd-home-resilience.md) | x | y |",
                    "| 2 | [prd-restructure.md](./prd-restructure.md) | x | y |",
                    "| 3 | [prd-clone-and-home-creation.md](./prd-clone-and-home-creation.md) | x | y |",
                    "| 4 | [prd-instance-identity-and-lineage.md](./prd-instance-identity-and-lineage.md) | x | y |",
                    "| 5 | [prd-glyphweave-studio-loop.md](./prd-glyphweave-studio-loop.md) | x | y |",
                    "| 6 | [prd-embodiment-core.md](./prd-embodiment-core.md) | x | y |",
                    "| 7 | [prd-embodiment-interaction-loops.md](./prd-embodiment-interaction-loops.md) | x | y |",
                    "| 8 | [prd-glyphweave-art-studio.md](./prd-glyphweave-art-studio.md) | x | y |",
                    "| 9 | [prd-narrative-engine.md](./prd-narrative-engine.md) | x | y |",
                    "| 10 | [prd-pet-system-v2.md](./prd-pet-system-v2.md) | x | y |",
                    "| 11 | [prd-publication-and-gallery-surfaces.md](./prd-publication-and-gallery-surfaces.md) | x | y |",
                    "| 12 | [prd-federation-read-model.md](./prd-federation-read-model.md) | x | y |",
                    "| 13 | [prd-federation-proposal-writes.md](./prd-federation-proposal-writes.md) | x | y |",
                    "| 14 | [prd-bundle-exchange.md](./prd-bundle-exchange.md) | x | y |",
                ]
            ),
            encoding="utf-8",
        )
        (sdp_dir / "execution-roadmap.queue-map.json").write_text(
            json.dumps(
                {
                    "stages": {
                        "prd-home-resilience.md": ["20260331T232739Z"],
                        "prd-restructure.md": ["20260328T142659Z"],
                        "prd-clone-and-home-creation.md": ["20260402T175501Z"],
                        "prd-instance-identity-and-lineage.md": ["20260402T175502Z"],
                        "prd-glyphweave-studio-loop.md": ["20260401T195527Z"],
                        "prd-embodiment-core.md": ["20260331T210000Z", "20260402T175504Z-2"],
                        "prd-embodiment-interaction-loops.md": ["20260402T175505Z"],
                        "prd-glyphweave-art-studio.md": ["20260327T172236Z"],
                        "prd-narrative-engine.md": ["20260329T183119Z"],
                        "prd-pet-system-v2.md": ["20260327T221957Z"],
                        "prd-publication-and-gallery-surfaces.md": ["20260402T175503Z-2"],
                        "prd-federation-read-model.md": ["20260402T175502Z-2"],
                        "prd-federation-proposal-writes.md": ["20260402T175503Z"],
                        "prd-bundle-exchange.md": ["20260402T175504Z"],
                    },
                    "completed_earlier": [
                        {"label": "Model Awareness", "batches": ["20260327T154047Z"]}
                    ],
                }
            ),
            encoding="utf-8",
        )
        for filename, heading in {
            "prd-home-resilience.md": "# PRD: Home Resilience\n",
            "prd-restructure.md": "# PRD: Restructure\n",
            "prd-clone-and-home-creation.md": "# PRD: Clone and Home Creation\n",
            "prd-instance-identity-and-lineage.md": "# PRD: Instance Identity and Lineage\n",
            "prd-glyphweave-studio-loop.md": "# PRD: GlyphWeave Studio Loop\n",
            "prd-embodiment-core.md": "# PRD: Embodiment Core\n",
            "prd-embodiment-interaction-loops.md": "# PRD: Embodiment Interaction Loops\n",
            "prd-glyphweave-art-studio.md": "# PRD: GlyphWeave Art Studio\n",
            "prd-narrative-engine.md": "# PRD: Narrative Engine\n",
            "prd-pet-system-v2.md": "# PRD: Pet System v2\n",
            "prd-publication-and-gallery-surfaces.md": "# PRD: Publication and Gallery Surfaces\n",
            "prd-federation-read-model.md": "# PRD: Federation Read Model\n",
            "prd-federation-proposal-writes.md": "# PRD: Federation Proposal Writes\n",
            "prd-bundle-exchange.md": "# PRD: Bundle Exchange\n",
        }.items():
            (sdp_dir / filename).write_text(heading, encoding="utf-8")

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)

        handled = cypherclaw_daemon.handle_builtin("/prd")

        assert handled is True
        text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "PRD Roadmap" in text
        labels = [
            "Home Resilience",
            "Restructure",
            "Clone and Home Creation",
            "Instance Identity and Lineage",
            "GlyphWeave Studio Loop",
            "Embodiment Core",
            "Embodiment Interaction Loops",
            "GlyphWeave Art Studio",
            "Narrative Engine",
            "Pet System v2",
            "Publication and Gallery Surfaces",
            "Federation Read Model",
            "Federation Proposal Writes",
            "Bundle Exchange",
        ]
        positions = [text.index(label) for label in labels]
        assert positions == sorted(positions)
        assert "running" in text.lower()
        assert "Restructure — frozen [1 frozen]" in text
        assert "GlyphWeave Studio Loop — running [1/3] (1 running, 1 pending, 1 skipped)" in text
        assert "Federation — " not in text
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
            con.execute(
                """
                CREATE TABLE completion_gate_reports (
                    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_run_id TEXT,
                    project_name TEXT,
                    status TEXT,
                    waiver_reason TEXT,
                    report_path TEXT,
                    summary TEXT,
                    created_at TEXT
                )
                """
            )
            task_rows = [
                ("T-home", "home", "T1", "needs_split", None),
                ("T-artist", "artist", "T1", "running", None),
                ("T-blocked", "blocked", "T1", "blocked", None),
                ("T-split", "split parent", "T1", "split", None),
                ("T-splita", "split child a", "T1", "pending", "T-split"),
                ("T-splitb", "split child b", "T1", "complete", "T-split"),
                ("T-frozen", "superseded", "T1", "pending", None),
            ]
            for task_id, description, tier, status, parent_task_id in task_rows:
                frozen = 1 if task_id == "T-frozen" else 0
                frozen_reason = "superseded" if task_id == "T-frozen" else ""
                con.execute(
                    """
                    INSERT INTO tasks (
                        task_id, description, tier, status, lead_agent, verify_agent, priority,
                        complexity_score, source, criteria, rollback_count, parent_task_id,
                        status_reason, status_changed_at, status_changed_by, frozen,
                        frozen_reason, frozen_at, frozen_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, NULL, 0, 0, 'prd', '', 0, ?, '', '', '', ?, ?, '', '', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
                    """,
                    (task_id, description, tier, status, parent_task_id, frozen, frozen_reason),
                )
            con.execute(
                """
                INSERT INTO task_runs (
                    task_id, lead_agent, verify_agent, started_at, completed_at, verdict, gate_passed, work_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("T-artist", "codex", "gemini", "2026-04-01T00:00:00+00:00", None, "", 0, "no_work"),
            )
            con.execute(
                """
                INSERT INTO task_runs (
                    task_id, lead_agent, verify_agent, started_at, completed_at, verdict, gate_passed, work_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("T-done", "claude", "codex", "2026-03-31T23:40:00+00:00", "2026-03-31T23:50:00+00:00", "PASS", 1, "work"),
            )
            con.execute(
                """
                INSERT INTO completion_gate_reports (
                    pipeline_run_id, project_name, status, waiver_reason, report_path, summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("run-1", "cypherclaw", "pass", "", "verification_reports/completion-gate.json", "Local completion gate passed.", "2026-04-01T00:05:00+00:00"),
            )

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cypherclaw_daemon, "_runner_service_state", lambda: "active")
        monkeypatch.setattr(cypherclaw_daemon, "_sdp_monitor_last_snapshot", lambda: None)

        handled = cypherclaw_daemon.handle_builtin("/monitor")

        assert handled is True
        text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "SDP Monitor" in text
        assert "Progress: 1/5 complete (20%)" in text
        assert "Queue: 1 pending, 1 needs split, 1 blocked, 1 running, 1 skipped, 1 frozen" in text
        assert "Runner: active" in text
        assert "Current: T-artist" in text
        assert "Pair: codex → gemini" in text
        assert "Gate: pass · Local completion gate passed." in text
        assert "Recent: T-done · PASS · claude→codex" in text
        assert "Providers: claude 80% healthy · codex 70% healthy · gemini 60% healthy" in text
        assert "Available: claude, codex, gemini" in text

    def test_monitor_command_respects_selector_disabled_agents(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        daemon_env: dict[str, object],
    ) -> None:
        project_root = tmp_path / "cypherclaw"
        state_dir = project_root / ".sdp"
        state_dir.mkdir(parents=True)
        db_path = state_dir / "state.db"
        (project_root / "sdp.toml").write_text(
            'selector_claude_remaining_tokens = "0.0"\n'
            'selector_codex_remaining_tokens = "10000000.0"\n'
            'selector_gemini_remaining_tokens = "10000000.0"\n',
            encoding="utf-8",
        )

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

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cypherclaw_daemon, "_runner_service_state", lambda: "inactive")
        monkeypatch.setattr(cypherclaw_daemon, "_sdp_monitor_last_snapshot", lambda: None)

        handled = cypherclaw_daemon.handle_builtin("/monitor")

        assert handled is True
        text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "Available: codex, gemini | Excluded: claude (selector)" in text

    def test_monitor_command_prefers_sdp_cli_monitor_snapshot(
        self,
        monkeypatch: pytest.MonkeyPatch,
        daemon_env: dict[str, object],
    ) -> None:
        monitor_snapshot = (
            "SDP Status\n\n"
            "Progress: [██] 52%  195 / 378 tasks complete\n"
            "  completed: 195, in-progress: 1, pending: 180, needs_split: 2, blocked: 0\n\n"
            "╭──────────────────────────────── SDP Monitor ────────────────────────────────╮\n"
            "│ Project:  promptclaw                                                         │\n"
            "│ Run:      run-t-005@20260327t233208zb-1775194225  active                     │\n"
            "│ Phase:    develop | active codex/gpt-5.4 (xhigh)                             │\n"
            "│ Lead:     codex | codex/gpt-5.4 (xhigh)                                      │\n"
            "│ Verify:   gemini | gemini/3-flash-preview (standard)                         │\n"
            "│ Task:     T-005@20260327T233208Zb (T3) Wire `/api/chat/send` ... [running]   │\n"
            "│ Timing:   task 2m 51s / est 21m 41s | ETC 70h 5m 40s | ETA 2026-04-05 20:36 PDT │\n"
            "│ Quota                                                                        │\n"
            "│   anthropic  5h: 0.0% │ 7d: 98.0% (reset 1d 12h) │ 7d-sonnet: 3.0% (reset 4d 19h) │\n"
            "│   openai     short: 21.0% (reset 9m) │ long: 74.0% (reset 5d 3h)             │\n"
            "│   google     1d: ~100.0% (reset 1h 26m)                                      │\n"
            "│   risk       likely pause: google 1d ~100.0% | reset 1h 26m | ETA crosses reset │\n"
            "╰──────────────────────────────────────────────────────────────────────────────╯"
        )
        monkeypatch.setattr(
            cypherclaw_daemon,
            "_sdp_monitor_last_snapshot",
            lambda: monitor_snapshot,
        )

        handled = cypherclaw_daemon.handle_builtin("/monitor")

        assert handled is True
        text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert text == monitor_snapshot

    def test_tasks_command_returns_actionable_queue_sections(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        daemon_env: dict[str, object],
    ) -> None:
        project_root = tmp_path / "cypherclaw"
        state_dir = project_root / ".sdp"
        state_dir.mkdir(parents=True)
        db_path = state_dir / "state.db"

        with sqlite3.connect(db_path) as con:
            con.executescript(
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
                    source TEXT NOT NULL DEFAULT 'prd',
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
                );
                """
            )
            rows = [
                ("T-run", "render the current scene", "T1", "running", "", 0, ""),
                ("T-root", "build install manifest", "T1", "pending", "", 5, ""),
                ("T-split", "decompose old stage", "T1", "split", "", 0, ""),
                ("T-child", "implement child slice", "T1", "pending", "T-split", 4, ""),
                ("T-needs", "rewrite embodiment contract", "T1", "needs_split", "", 3, "too broad for one run"),
                ("T-blocked", "repair camera ingest", "T1", "blocked", "", 2, "waiting on device"),
                ("T-review", "resolve verifier mismatch", "T1", "needs_review", "", 1, "manual review required"),
                ("T-frozen", "obsolete federation batch", "T1", "pending", "", 0, ""),
            ]
            for task_id, description, tier, status, parent_task_id, priority, status_reason in rows:
                frozen = 1 if task_id == "T-frozen" else 0
                frozen_reason = "superseded by clone roadmap" if task_id == "T-frozen" else ""
                con.execute(
                    """
                    INSERT INTO tasks (
                        task_id, description, tier, status, lead_agent, verify_agent, priority,
                        complexity_score, source, criteria, rollback_count, parent_task_id,
                        status_reason, status_changed_at, status_changed_by, frozen,
                        frozen_reason, frozen_at, frozen_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, NULL, ?, 0, 'prd', '', 0, ?, ?, '', '', ?, ?, '', '', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
                    """,
                    (
                        task_id,
                        description,
                        tier,
                        status,
                        priority,
                        parent_task_id or None,
                        status_reason,
                        frozen,
                        frozen_reason,
                    ),
                )

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)

        handled = cypherclaw_daemon.handle_builtin("/tasks")

        assert handled is True
        text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "Queue Tasks" in text
        assert "Summary: 1 running · 2 pending · 1 needs split · 1 blocked · 1 needs attention · 1 decomposed · 1 frozen" in text
        assert "Running:" in text
        assert "Next Root Tasks:" in text
        assert "Needs Split:" in text
        assert "Blocked:" in text
        assert "Needs Attention:" in text
        assert "Background: 1 frozen · 1 decomposed parents" in text
        assert "`T-root`" in text
        assert "`T-child`" not in text
        assert "Use: `/tasks pending 10`" in text

    def test_tasks_command_supports_filtered_views(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        daemon_env: dict[str, object],
    ) -> None:
        project_root = tmp_path / "cypherclaw"
        state_dir = project_root / ".sdp"
        state_dir.mkdir(parents=True)
        db_path = state_dir / "state.db"

        with sqlite3.connect(db_path) as con:
            con.executescript(
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
                    source TEXT NOT NULL DEFAULT 'prd',
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
                );
                """
            )
            rows = [
                ("T-needs", "split the embodiment slice", "T1", "needs_split", 0, "", "too broad"),
                ("T-frozen", "retired publication draft", "T1", "pending", 1, "superseded", ""),
                ("T-blocked", "wait for operator input", "T1", "blocked", 0, "", "missing device"),
            ]
            for task_id, description, tier, status, frozen, frozen_reason, status_reason in rows:
                con.execute(
                    """
                    INSERT INTO tasks (
                        task_id, description, tier, status, lead_agent, verify_agent, priority,
                        complexity_score, source, criteria, rollback_count, parent_task_id,
                        status_reason, status_changed_at, status_changed_by, frozen,
                        frozen_reason, frozen_at, frozen_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, NULL, 0, 0, 'prd', '', 0, NULL, ?, '', '', ?, ?, '', '', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
                    """,
                    (task_id, description, tier, status, status_reason, frozen, frozen_reason),
                )

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)

        handled = cypherclaw_daemon.handle_builtin("/tasks frozen 10")

        assert handled is True
        frozen_text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "Tasks · Frozen" in frozen_text
        assert "Showing 1 of 1" in frozen_text
        assert "`T-frozen`" in frozen_text
        assert "`T-blocked`" not in frozen_text

        handled = cypherclaw_daemon.handle_builtin("/tasks needs split 10")

        assert handled is True
        split_text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "Tasks · Needs Split" in split_text
        assert "Showing 1 of 1" in split_text
        assert "`T-needs`" in split_text
        assert "`T-blocked`" not in split_text

    def test_tasks_command_supports_prd_and_stage_views(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        daemon_env: dict[str, object],
    ) -> None:
        project_root = tmp_path / "cypherclaw"
        state_dir = project_root / ".sdp"
        state_dir.mkdir(parents=True)
        sdp_dir = project_root / "sdp"
        sdp_dir.mkdir()
        db_path = state_dir / "state.db"

        with sqlite3.connect(db_path) as con:
            con.executescript(
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
                    source TEXT NOT NULL DEFAULT 'prd',
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
                );
                """
            )
            rows = [
                ("T-001@20260402T175501Z", "create clone installer", "T1", "running", "", 4, "", 0, ""),
                ("T-002@20260402T175501Z", "write unattended bootstrap", "T1", "pending", "", 3, "", 0, ""),
                ("T-003@20260402T175501Z", "split clone publication followup", "T1", "needs_split", "", 2, "too broad", 0, ""),
                ("T-001@20260402T175502Z", "assign instance name", "T1", "pending", "", 2, "", 0, ""),
                ("T-002@20260402T175502Z", "obsolete lineage cleanup", "T1", "pending", "", 1, "", 1, "superseded"),
            ]
            for task_id, description, tier, status, parent_task_id, priority, status_reason, frozen, frozen_reason in rows:
                con.execute(
                    """
                    INSERT INTO tasks (
                        task_id, description, tier, status, lead_agent, verify_agent, priority,
                        complexity_score, source, criteria, rollback_count, parent_task_id,
                        status_reason, status_changed_at, status_changed_by, frozen,
                        frozen_reason, frozen_at, frozen_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, NULL, ?, 0, 'prd', '', 0, ?, ?, '', '', ?, ?, '', '', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
                    """,
                    (
                        task_id,
                        description,
                        tier,
                        status,
                        priority,
                        parent_task_id or None,
                        status_reason,
                        frozen,
                        frozen_reason,
                    ),
                )

        (sdp_dir / "execution-roadmap.md").write_text(
            "\n".join(
                [
                    "# CypherClaw Execution Roadmap",
                    "",
                    "## Execution Spine",
                    "",
                    "| Stage | PRD | Why it is here | Unlocks |",
                    "|---|---|---|---|",
                    "| 1 | [prd-clone-and-home-creation.md](./prd-clone-and-home-creation.md) | x | y |",
                    "| 2 | [prd-instance-identity-and-lineage.md](./prd-instance-identity-and-lineage.md) | x | y |",
                ]
            ),
            encoding="utf-8",
        )
        (sdp_dir / "execution-roadmap.queue-map.json").write_text(
            json.dumps(
                {
                    "stages": {
                        "prd-clone-and-home-creation.md": ["20260402T175501Z"],
                        "prd-instance-identity-and-lineage.md": ["20260402T175502Z"],
                    }
                }
            ),
            encoding="utf-8",
        )
        (sdp_dir / "prd-clone-and-home-creation.md").write_text(
            "# PRD: Clone and Home Creation\n",
            encoding="utf-8",
        )
        (sdp_dir / "prd-instance-identity-and-lineage.md").write_text(
            "# PRD: Instance Identity and Lineage\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)

        handled = cypherclaw_daemon.handle_builtin("/tasks prd 1 5")

        assert handled is True
        prd_text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "Tasks · PRD 1 · Clone and Home Creation" in prd_text
        assert "Summary: 1 running · 1 pending · 1 needs split" in prd_text
        assert "Batches: 20260402T175501Z" in prd_text
        assert "`T-001@20260402T175501Z`" in prd_text
        assert "`T-001@20260402T175502Z`" not in prd_text

        handled = cypherclaw_daemon.handle_builtin("/tasks stage instance identity 5")

        assert handled is True
        stage_text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "Tasks · PRD 2 · Instance Identity and Lineage" in stage_text
        assert "Summary: 0 running · 1 pending · 1 frozen" in stage_text
        assert "Background: 1 frozen" in stage_text
        assert "`T-001@20260402T175502Z`" in stage_text
        assert "`T-001@20260402T175501Z`" not in stage_text

    def test_monitor_command_reports_open_run_drift(
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
            con.execute(
                """
                INSERT INTO tasks (
                    task_id, description, tier, status, lead_agent, verify_agent, priority,
                    complexity_score, source, criteria, rollback_count, parent_task_id,
                    status_reason, status_changed_at, status_changed_by, frozen,
                    frozen_reason, frozen_at, frozen_by, created_at, updated_at
                ) VALUES ('T-run', 'run', 'T1', 'running', NULL, NULL, 0, 0, 'prd', '', 0, NULL, '', '', '', 0, '', '', '', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
                """
            )
            con.execute(
                """
                INSERT INTO tasks (
                    task_id, description, tier, status, lead_agent, verify_agent, priority,
                    complexity_score, source, criteria, rollback_count, parent_task_id,
                    status_reason, status_changed_at, status_changed_by, frozen,
                    frozen_reason, frozen_at, frozen_by, created_at, updated_at
                ) VALUES ('T-blocked', 'blocked', 'T1', 'blocked', NULL, NULL, 0, 0, 'prd', '', 0, NULL, '', '', '', 0, '', '', '', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
                """
            )
            con.execute(
                """
                INSERT INTO task_runs (
                    task_id, lead_agent, verify_agent, started_at, completed_at, verdict, gate_passed, work_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("T-run", "codex", "gemini", "2026-04-01T00:00:00+00:00", "", "", 0, "no_work"),
            )
            con.execute(
                """
                INSERT INTO task_runs (
                    task_id, lead_agent, verify_agent, started_at, completed_at, verdict, gate_passed, work_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("T-blocked", "codex", "gemini", "2026-04-01T00:00:01+00:00", "", "", 0, "no_work"),
            )

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cypherclaw_daemon, "_runner_service_state", lambda: "active")
        monkeypatch.setattr(cypherclaw_daemon, "_sdp_monitor_last_snapshot", lambda: None)

        handled = cypherclaw_daemon.handle_builtin("/monitor")

        assert handled is True
        text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "State: drift — 1 stale open runs" in text

    def test_monitor_command_hides_stale_child_when_runner_inactive(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        daemon_env: dict[str, object],
    ) -> None:
        project_root = tmp_path / "cypherclaw"
        state_dir = project_root / ".sdp"
        state_dir.mkdir(parents=True)
        db_path = state_dir / "state.db"

        with sqlite3.connect(db_path) as con:
            con.executescript(
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
                    source TEXT NOT NULL DEFAULT 'prd',
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
                );
                CREATE TABLE task_runs (
                    task_id TEXT NOT NULL,
                    lead_agent TEXT,
                    verify_agent TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    verdict TEXT,
                    gate_passed INTEGER,
                    work_result TEXT
                );
                """
            )
            con.execute(
                """
                INSERT INTO tasks (
                    task_id, description, tier, status, lead_agent, verify_agent, priority,
                    complexity_score, source, criteria, rollback_count, parent_task_id,
                    status_reason, status_changed_at, status_changed_by, frozen,
                    frozen_reason, frozen_at, frozen_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, 0, 0, 'prd', '', 0, ?, '', '', '', 0, '', '', '', '2026-04-01T00:00:00+00:00', '2026-04-01T00:00:00+00:00')
                """,
                ("T-stale-child", "stale child", "T1", "running", "T-root"),
            )
            con.execute(
                """
                INSERT INTO task_runs (
                    task_id, lead_agent, verify_agent, started_at, completed_at, verdict, gate_passed, work_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("T-stale-child", "codex", "gemini", "2026-04-01T00:00:00+00:00", None, "", 0, "no_work"),
            )

        monkeypatch.setattr(cypherclaw_daemon, "PROJECT_ROOT", project_root)
        monkeypatch.setattr(cypherclaw_daemon, "_runner_service_state", lambda: "inactive")
        monkeypatch.setattr(cypherclaw_daemon, "_sdp_monitor_last_snapshot", lambda: None)

        handled = cypherclaw_daemon.handle_builtin("/monitor")

        assert handled is True
        text = daemon_env["sent_messages"][-1]  # type: ignore[index]
        assert "Runner: inactive" in text
        assert "Current: T-stale-child" not in text
        assert "Current: idle" in text

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
