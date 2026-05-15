from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from promptclaw.cli import cmd_pal_agent_actions, cmd_pal_agent_triage
from promptclaw.config import default_project_config, save_config
from promptclaw.pal_agent import PALOpsAction, PALOpsTool, run_pal_ops_actions, run_pal_ops_triage
from promptclaw.pal_client import PALQueryResult
from promptclaw.pal_knowledge import write_pal_knowledge_index


class FakePALClient:
    base_url = "http://pal-cloud-a6000:8000"
    default_model = "llama3.3:70b-instruct-q4_K_M"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def health(self) -> dict[str, Any]:
        return {"status": "green", "phase": "phase-1-a6000"}

    def query(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.7,
    ) -> PALQueryResult:
        self.prompts.append(prompt)
        text = self.responses.pop(0)
        return PALQueryResult(text=text, raw={"response": text, "model": self.default_model})


def test_pal_ops_triage_executes_only_allowlisted_tools_and_writes_artifacts(tmp_path: Path) -> None:
    config = default_project_config("PAL Agent Test")
    save_config(tmp_path, config)
    executed: list[str] = []
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL router health.",
            run=lambda: _recorded_tool_result(executed, "pal_health"),
        ),
        "pal_smoke_baseline": PALOpsTool(
            name="pal_smoke_baseline",
            description="Summarize PAL smoke baselines.",
            run=lambda: _recorded_tool_result(executed, "pal_smoke_baseline"),
        ),
    }
    client = FakePALClient([
        json.dumps({
            "tools": ["pal_health", "destroy_instance", "pal_smoke_baseline"],
            "rationale": "Check health before any operator action.",
        }),
        "PAL triage summary: health is green and smoke baseline is stable.",
    ])

    result = run_pal_ops_triage(
        tmp_path,
        task="Diagnose PAL health.",
        client=client,
        tool_registry=tool_registry,
        now=_fake_now(),
    )

    assert result["status"] == "complete"
    assert executed == ["pal_health", "pal_smoke_baseline"]
    assert result["ignored_tools"] == ["destroy_instance"]
    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    assert (run_root / "input" / "task.md").exists()
    assert (run_root / "routing" / "route.json").exists()
    assert json.loads((run_root / "outputs" / "tool-observations.json").read_text())["ignored_tools"] == [
        "destroy_instance"
    ]
    assert "health is green" in (run_root / "summary" / "final-summary.md").read_text()
    state = json.loads((run_root / "state.json").read_text())
    assert state["status"] == "complete"
    assert state["lead_agent"] == "pal"
    assert state["verifier_agent"] == "local-allowlist"


def test_pal_ops_triage_falls_back_to_default_plan_when_pal_plan_is_invalid(tmp_path: Path) -> None:
    config = default_project_config("PAL Agent Invalid Plan")
    save_config(tmp_path, config)
    executed: list[str] = []
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL router health.",
            run=lambda: _recorded_tool_result(executed, "pal_health"),
        ),
        "pal_smoke_baseline": PALOpsTool(
            name="pal_smoke_baseline",
            description="Summarize PAL smoke baselines.",
            run=lambda: _recorded_tool_result(executed, "pal_smoke_baseline"),
        ),
    }
    client = FakePALClient([
        "not json",
        "Fallback summary.",
    ])

    result = run_pal_ops_triage(
        tmp_path,
        client=client,
        tool_registry=tool_registry,
        default_tools=("pal_health", "pal_smoke_baseline"),
        now=_fake_now(),
    )

    assert result["status"] == "complete"
    assert executed == ["pal_health", "pal_smoke_baseline"]
    assert result["plan_source"] == "fallback"
    assert result["ignored_tools"] == []


def test_pal_ops_triage_prompt_artifacts_include_bounded_knowledge_context(tmp_path: Path) -> None:
    config = default_project_config("PAL Triage Knowledge Context")
    save_config(tmp_path, config)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a-router.md").write_text(
        "# A Router\nrouter restart health runbook alpha marker.\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "b-router.md").write_text(
        "# B Router\nrouter restart health smoke beta marker.\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "c-router.md").write_text(
        "# C Router\nrouter restart health process gamma marker.\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "z-router.md").write_text(
        "# Z Router\nrouter restart health overflow zeta marker.\n",
        encoding="utf-8",
    )
    write_pal_knowledge_index(tmp_path, max_chars=400)

    executed: list[str] = []
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL router health.",
            run=lambda: _recorded_tool_result(executed, "pal_health"),
        )
    }
    client = FakePALClient([
        json.dumps({"tools": ["pal_health"], "rationale": "Check router health."}),
        "PAL triage summary with local KB context.",
    ])

    result = run_pal_ops_triage(
        tmp_path,
        task="Diagnose router restart health.",
        client=client,
        tool_registry=tool_registry,
        default_tools=("pal_health",),
        now=_fake_now(),
    )

    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    plan_prompt = (run_root / "prompts" / "triage-plan.md").read_text(encoding="utf-8")
    summary_prompt = (run_root / "prompts" / "triage-summary.md").read_text(encoding="utf-8")
    for prompt, next_marker in (
        (plan_prompt, "Available diagnostic tools:"),
        (summary_prompt, "Tool observations JSON:"),
    ):
        section = _knowledge_context_section(prompt, next_marker)
        assert section.startswith("## Knowledge Context")
        assert section.count("\n- ") == 3
        assert len(section) <= 1600
        assert "docs/a-router.md:1-2" in section
        assert "docs/b-router.md:1-2" in section
        assert "docs/c-router.md:1-2" in section
        assert "zeta marker" not in section
        assert "chunk=pal-kb:" in section


def test_pal_ops_triage_prompt_artifacts_include_knowledge_context_when_index_is_missing(
    tmp_path: Path,
) -> None:
    config = default_project_config("PAL Missing Knowledge Context")
    save_config(tmp_path, config)
    executed: list[str] = []
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL router health.",
            run=lambda: _recorded_tool_result(executed, "pal_health"),
        )
    }
    client = FakePALClient([
        json.dumps({"tools": ["pal_health"], "rationale": "Check router health."}),
        "PAL triage summary without local KB index.",
    ])

    result = run_pal_ops_triage(
        tmp_path,
        task="Diagnose router restart health.",
        client=client,
        tool_registry=tool_registry,
        default_tools=("pal_health",),
        now=_fake_now(),
    )

    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    plan_prompt = (run_root / "prompts" / "triage-plan.md").read_text(encoding="utf-8")
    section = _knowledge_context_section(plan_prompt, "Available diagnostic tools:")
    assert section.startswith("## Knowledge Context")
    assert section.count("\n- ") == 0
    assert len(section) <= 1600
    assert "No local PAL KB index is available" in section
    assert result["status"] == "complete"
    assert executed == ["pal_health"]


def test_pal_agent_cli_triage_prints_run_summary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("promptclaw.cli.run_pal_ops_triage", lambda project_root, task: {
        "run_id": "20260515t190000z-pal-ops-triage",
        "status": "complete",
        "summary_path": ".promptclaw/runs/20260515t190000z-pal-ops-triage/summary/final-summary.md",
        "executed_tools": ["pal_health"],
        "ignored_tools": [],
        "plan_source": "pal",
    })

    output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Diagnose PAL.", json=False)
    with redirect_stdout(output):
        rc = cmd_pal_agent_triage(args)

    assert rc == 0
    rendered = output.getvalue()
    assert "PAL agent triage: COMPLETE" in rendered
    assert "run_id=20260515t190000z-pal-ops-triage" in rendered
    assert "executed_tools=pal_health" in rendered


def test_pal_ops_actions_requires_explicit_approval_before_executing_actions(tmp_path: Path) -> None:
    config = default_project_config("PAL Actions Proposal")
    save_config(tmp_path, config)
    executed: list[str] = []
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL router health.",
            run=lambda: _recorded_tool_result(executed, "pal_health"),
        ),
    }
    action_registry = {
        "inspect_logs_deep": PALOpsAction(
            name="inspect_logs_deep",
            description="Inspect PAL logs.",
            approval_required=True,
            mutating=False,
            run=lambda: _recorded_tool_result(executed, "inspect_logs_deep"),
        ),
        "restart_router": PALOpsAction(
            name="restart_router",
            description="Restart the PAL router.",
            approval_required=True,
            mutating=True,
            run=lambda: _recorded_tool_result(executed, "restart_router"),
        ),
    }
    client = FakePALClient([
        json.dumps({
            "actions": ["inspect_logs_deep", "restart_router", "destroy_instance"],
            "rationale": "Gather deeper evidence before restarting anything.",
        }),
        "Proposal only: no actions were approved.",
    ])

    result = run_pal_ops_actions(
        tmp_path,
        client=client,
        tool_registry=tool_registry,
        action_registry=action_registry,
        default_tools=("pal_health",),
        now=_fake_now(),
    )

    assert result["status"] == "complete"
    assert executed == ["pal_health"]
    assert result["pending_approval"] == ["inspect_logs_deep", "restart_router"]
    assert result["executed_actions"] == []
    assert result["ignored_actions"] == ["destroy_instance"]
    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    action_results = json.loads((run_root / "outputs" / "action-results.json").read_text())
    assert action_results["actions"][0]["status"] == "pending_approval"
    assert action_results["actions"][1]["status"] == "pending_approval"
    assert "no actions were approved" in (run_root / "summary" / "final-summary.md").read_text()


def test_pal_ops_actions_executes_only_approved_allowlisted_actions(tmp_path: Path) -> None:
    config = default_project_config("PAL Actions Approved")
    save_config(tmp_path, config)
    executed: list[str] = []
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL router health.",
            run=lambda: _recorded_tool_result(executed, "pal_health"),
        ),
    }
    action_registry = {
        "inspect_logs_deep": PALOpsAction(
            name="inspect_logs_deep",
            description="Inspect PAL logs.",
            approval_required=True,
            mutating=False,
            run=lambda: _recorded_tool_result(executed, "inspect_logs_deep"),
        ),
        "restart_router": PALOpsAction(
            name="restart_router",
            description="Restart the PAL router.",
            approval_required=True,
            mutating=True,
            run=lambda: _recorded_tool_result(executed, "restart_router"),
        ),
    }
    client = FakePALClient([
        json.dumps({
            "actions": ["inspect_logs_deep", "restart_router"],
            "rationale": "Inspect logs first.",
        }),
        "Executed approved log inspection; restart still needs approval.",
    ])

    result = run_pal_ops_actions(
        tmp_path,
        client=client,
        tool_registry=tool_registry,
        action_registry=action_registry,
        approved_actions=("inspect_logs_deep", "destroy_instance"),
        default_tools=("pal_health",),
        now=_fake_now(),
    )

    assert executed == ["pal_health", "inspect_logs_deep"]
    assert result["executed_actions"] == ["inspect_logs_deep"]
    assert result["pending_approval"] == ["restart_router"]
    assert result["ignored_approvals"] == ["destroy_instance"]


def test_pal_ops_actions_prompt_artifacts_include_bounded_knowledge_context(tmp_path: Path) -> None:
    config = default_project_config("PAL Action Knowledge Context")
    save_config(tmp_path, config)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "actions.md").write_text(
        "# Actions\nrouter restart action planning should inspect logs before mutation.\n",
        encoding="utf-8",
    )
    write_pal_knowledge_index(tmp_path, max_chars=400)

    executed: list[str] = []
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL router health.",
            run=lambda: _recorded_tool_result(executed, "pal_health"),
        ),
    }
    action_registry = {
        "inspect_logs_deep": PALOpsAction(
            name="inspect_logs_deep",
            description="Inspect PAL logs.",
            approval_required=True,
            mutating=False,
            run=lambda: _recorded_tool_result(executed, "inspect_logs_deep"),
        ),
        "restart_router": PALOpsAction(
            name="restart_router",
            description="Restart the PAL router.",
            approval_required=True,
            mutating=True,
            run=lambda: _recorded_tool_result(executed, "restart_router"),
        ),
    }
    client = FakePALClient([
        json.dumps({
            "actions": ["inspect_logs_deep", "restart_router"],
            "rationale": "Inspect logs before restart.",
        }),
        "PAL action summary with local KB context.",
    ])

    result = run_pal_ops_actions(
        tmp_path,
        task="Plan router restart action.",
        client=client,
        tool_registry=tool_registry,
        action_registry=action_registry,
        default_tools=("pal_health",),
        now=_fake_now(),
    )

    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    plan_prompt = (run_root / "prompts" / "action-plan.md").read_text(encoding="utf-8")
    summary_prompt = (run_root / "prompts" / "action-summary.md").read_text(encoding="utf-8")
    for prompt, next_marker in (
        (plan_prompt, "Current diagnostic context:"),
        (summary_prompt, "Action results JSON:"),
    ):
        section = _knowledge_context_section(prompt, next_marker)
        assert section.startswith("## Knowledge Context")
        assert section.count("\n- ") == 1
        assert len(section) <= 1600
        assert "docs/actions.md:1-2" in section
        assert "inspect logs before mutation" in section
        assert "chunk=pal-kb:" in section
    assert executed == ["pal_health"]
    assert result["pending_approval"] == ["inspect_logs_deep", "restart_router"]


def test_pal_agent_cli_actions_prints_approval_summary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("promptclaw.cli.run_pal_ops_actions", lambda project_root, task, approved_actions: {
        "run_id": "20260515t191000z-pal-ops-actions",
        "status": "complete",
        "summary_path": ".promptclaw/runs/20260515t191000z-pal-ops-actions/summary/final-summary.md",
        "proposed_actions": ["inspect_logs_deep", "restart_router"],
        "executed_actions": ["inspect_logs_deep"],
        "pending_approval": ["restart_router"],
        "ignored_actions": [],
        "ignored_approvals": [],
        "plan_source": "pal",
    })

    output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Act on PAL.", approve=["inspect_logs_deep"], json=False)
    with redirect_stdout(output):
        rc = cmd_pal_agent_actions(args)

    assert rc == 0
    rendered = output.getvalue()
    assert "PAL agent actions: COMPLETE" in rendered
    assert "executed_actions=inspect_logs_deep" in rendered
    assert "pending_approval=restart_router" in rendered


def _recorded_tool_result(executed: list[str], name: str) -> dict[str, Any]:
    executed.append(name)
    return {"status": "ok", "summary": f"{name} ran"}


def _knowledge_context_section(prompt: str, next_marker: str) -> str:
    start = prompt.index("## Knowledge Context")
    end = prompt.index(f"\n\n{next_marker}", start)
    return prompt[start:end]


def _fake_now():
    counter = {"seconds": 0}

    def now() -> str:
        seconds = counter["seconds"]
        counter["seconds"] += 1
        return f"2026-05-15T19:00:{seconds:02d}+00:00"

    return now

class FakeSSHRunner:
    """Stand-in for promptclaw.pal_agent._run_ssh_command.

    Install via ``monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)``
    to exercise remote-action code paths without opening a real SSH connection.
    Returns canned responses in order, or ``default`` once the queue is empty.
    """

    def __init__(
        self,
        responses: list[dict[str, Any]] | None = None,
        *,
        default: dict[str, Any] | None = None,
    ) -> None:
        self.responses: list[dict[str, Any]] = list(responses or [])
        self.default: dict[str, Any] = default or {"exit_code": 0, "stdout": "", "stderr": ""}
        self.calls: list[dict[str, Any]] = []

    def __call__(self, remote_command: str, *, timeout_s: int) -> dict[str, Any]:
        self.calls.append({"remote_command": remote_command, "timeout_s": timeout_s})
        if self.responses:
            return dict(self.responses.pop(0))
        return dict(self.default)

    @property
    def last_command(self) -> str:
        return self.calls[-1]["remote_command"] if self.calls else ""


def test_restart_router_action_prefers_start_router_sh(monkeypatch) -> None:
    from promptclaw.pal_agent import _restart_router_action

    runner = FakeSSHRunner()
    monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)

    result = _restart_router_action()

    assert result["status"] == "ok"
    assert "/opt/pal/scripts/start_router.sh" in runner.last_command
    assert runner.last_command.startswith(
        "if [ -x /opt/pal/scripts/start_router.sh ]; then /opt/pal/scripts/start_router.sh"
    )


def test_restart_router_action_uses_docker_only_when_host_script_absent(monkeypatch) -> None:
    from promptclaw.pal_agent import _restart_router_action

    runner = FakeSSHRunner()
    monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)
    _restart_router_action()

    captured_command = runner.last_command
    host_check = "[ -x /opt/pal/scripts/start_router.sh ]"
    docker_guard = "elif command -v docker"
    assert host_check in captured_command
    assert docker_guard in captured_command
    assert captured_command.index(host_check) < captured_command.index(docker_guard), (
        "Docker fallback must be gated behind the host-script check"
    )
    assert "docker" not in captured_command.split(docker_guard)[0], (
        "Docker must not be referenced before the host-script check"
    )


def test_inspect_logs_deep_action_runs_remote_diagnostic_via_fake_ssh(monkeypatch) -> None:
    from promptclaw.pal_agent import _inspect_logs_deep_action

    runner = FakeSSHRunner([{"exit_code": 0, "stdout": "logs ok", "stderr": ""}])
    monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)

    result = _inspect_logs_deep_action()

    assert result["status"] == "ok"
    assert runner.calls and runner.calls[0]["timeout_s"] == 30
    assert "/opt/pal/logs/router.log" in runner.last_command


def test_pause_shutdown_once_action_creates_override_flag_via_fake_ssh(monkeypatch) -> None:
    from promptclaw.pal_agent import _pause_shutdown_once_action

    runner = FakeSSHRunner()
    monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)

    result = _pause_shutdown_once_action()

    assert result["status"] == "ok"
    assert "touch /opt/pal/config/override.flag" in runner.last_command


def test_resume_shutdown_action_removes_override_flag_via_fake_ssh(monkeypatch) -> None:
    from promptclaw.pal_agent import _resume_shutdown_action

    runner = FakeSSHRunner()
    monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)

    result = _resume_shutdown_action()

    assert result["status"] == "ok"
    assert "rm -f /opt/pal/config/override.flag" in runner.last_command


def test_ssh_process_check_tool_reports_warn_on_nonzero_exit_via_fake_ssh(monkeypatch) -> None:
    from promptclaw.pal_agent import _ssh_process_check_tool

    runner = FakeSSHRunner([{"exit_code": 1, "stdout": "", "stderr": "boom"}])
    monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)

    result = _ssh_process_check_tool()

    assert result["status"] == "warn"
    assert "[t]ailscaled" in runner.last_command
    assert "/opt/pal/logs/shutdown.log" in runner.last_command


def test_action_propagates_skipped_response_from_fake_ssh(monkeypatch) -> None:
    from promptclaw.pal_agent import _restart_router_action

    runner = FakeSSHRunner(
        [
            {
                "args": ["ssh", "<PAL_SSH_HOST>", "<remote-command>"],
                "exit_code": 78,
                "stdout": "",
                "stderr": "SSH diagnostics skipped because PAL_SSH_HOST, PAL_SSH_PORT, and PAL_SSH_KEY are not all set.",
                "skipped": True,
            }
        ]
    )
    monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)

    result = _restart_router_action()

    assert result["status"] == "skipped"
    assert "skipped" in result["summary"].lower()
