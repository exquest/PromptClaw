from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from promptclaw import cli as promptclaw_cli
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


def test_default_pal_action_registry_excludes_vast_lifecycle_actions(tmp_path: Path) -> None:
    from promptclaw.pal_agent import build_default_action_registry, _parse_action_plan

    actions = build_default_action_registry(tmp_path, FakePALClient([]))
    blocked_actions = ("rent", "destroy", "start", "stop")

    for action_id in blocked_actions:
        assert action_id not in actions
        assert f"vast_{action_id}" not in actions

    plan = _parse_action_plan(
        json.dumps({
            "actions": [
                "rent",
                "destroy",
                "start",
                "stop",
                "vast_rent",
                "vast_destroy",
                "vast_start",
                "vast_stop",
                "restart_router",
            ],
            "rationale": "Restart the router, but do not manage the Vast instance.",
        }),
        actions=actions,
    )

    assert plan["actions"] == ["restart_router"]
    assert plan["ignored_actions"] == [
        "rent",
        "destroy",
        "start",
        "stop",
        "vast_rent",
        "vast_destroy",
        "vast_start",
        "vast_stop",
    ]


def test_pal_ops_actions_prompt_includes_vast_stub_boundary(tmp_path: Path) -> None:
    config = default_project_config("PAL Vast Boundary")
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
    }
    client = FakePALClient([
        json.dumps({
            "actions": ["inspect_logs_deep", "rent", "destroy", "start", "stop"],
            "rationale": "Inspect logs; cloud instance lifecycle is not available.",
        }),
        "PAL action summary.",
    ])

    result = run_pal_ops_actions(
        tmp_path,
        task="Inspect PAL and describe any Vast boundary.",
        client=client,
        tool_registry=tool_registry,
        action_registry=action_registry,
        default_tools=("pal_health",),
        now=_fake_now(),
    )

    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    plan_prompt = (run_root / "prompts" / "action-plan.md").read_text(encoding="utf-8")

    assert "## Provider Action Boundaries" in plan_prompt
    assert "Vast connector" in plan_prompt
    assert "callable_actions=[]" in plan_prompt
    assert "blocked_actions=[rent, destroy, start, stop]" in plan_prompt
    for action_id in ("rent", "destroy", "start", "stop"):
        assert f"- {action_id}:" not in plan_prompt
        assert f"- vast_{action_id}:" not in plan_prompt
    assert result["ignored_actions"] == ["rent", "destroy", "start", "stop"]
    assert result["pending_approval"] == ["inspect_logs_deep"]


def test_pal_slow_inference_context_captures_health_baseline_gpu_and_logs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from promptclaw.pal_agent import run_pal_slow_inference_context

    config = default_project_config("PAL Slow Inference Context")
    save_config(tmp_path, config)
    reports_dir = tmp_path / ".promptclaw" / "pal-smoke"
    reports_dir.mkdir(parents=True)
    (reports_dir / "pal-smoke-20260515T180000Z.json").write_text(json.dumps({
        "status": "pass",
        "started_at": "2026-05-15T18:00:00+00:00",
        "summary": {"passed": 3, "failed": 0, "total_latency_s": 30.0},
        "checks": [
            {"id": "reachability", "status": "pass", "latency_s": 10.0, "tokens_per_second": 8.0},
            {"id": "configuration", "status": "pass", "latency_s": 9.0, "tokens_per_second": 12.0},
            {"id": "operational_triage", "status": "pass", "latency_s": 11.0, "tokens_per_second": 16.0},
        ],
    }))
    runner = FakeSSHRunner(
        [
            {
                "exit_code": 0,
                "stdout": "NVIDIA RTX A6000, 12000, 49140, 97\npython, 4321",
                "stderr": "",
            },
            {
                "exit_code": 0,
                "stdout": "router total_duration=9000000000\nollama eval_count=12 eval_duration=6000000000",
                "stderr": "",
            },
        ]
    )
    monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)

    result = run_pal_slow_inference_context(
        tmp_path,
        task="Diagnose PAL slow inference at 2 tokens per second.",
        client=FakePALClient([]),
        now=_fake_now(),
    )

    assert result["status"] == "complete"
    assert result["workflow_id"] == "slow_inference_context"
    assert result["executed_tools"] == [
        "pal_health",
        "pal_smoke_baseline",
        "gpu_hints",
        "slow_inference_logs",
    ]
    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    context = json.loads((run_root / "outputs" / "slow-inference-context.json").read_text())
    observations = {row["tool"]: row for row in context["observations"]}
    assert context["workflow_id"] == "slow_inference_context"
    assert context["baseline_tokens_per_second"] == 12.0
    assert observations["pal_health"]["health"]["status"] == "green"
    assert observations["pal_smoke_baseline"]["baseline_tokens_per_second"] == 12.0
    assert "NVIDIA RTX A6000" in observations["gpu_hints"]["command"]["stdout"]
    assert "ollama eval_count=12" in observations["slow_inference_logs"]["command"]["stdout"]
    assert "nvidia-smi --query-gpu" in runner.calls[0]["remote_command"]
    assert "/opt/pal/logs/router.log" in runner.calls[1]["remote_command"]
    assert (run_root / "handoffs" / "slow-inference-context.md").exists()


def test_pal_slow_inference_context_skips_optional_remote_hints_without_ssh(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from promptclaw.pal_agent import run_pal_slow_inference_context

    config = default_project_config("PAL Slow Inference No SSH")
    save_config(tmp_path, config)
    for key in ("PAL_SSH_HOST", "PAL_SSH_PORT", "PAL_SSH_KEY"):
        monkeypatch.delenv(key, raising=False)

    result = run_pal_slow_inference_context(
        tmp_path,
        client=FakePALClient([]),
        now=_fake_now(),
    )

    assert result["status"] == "complete"
    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    context = json.loads((run_root / "outputs" / "slow-inference-context.json").read_text())
    observations = {row["tool"]: row for row in context["observations"]}
    assert context["baseline_tokens_per_second"] is None
    assert observations["pal_smoke_baseline"]["status"] == "skipped"
    assert observations["gpu_hints"]["status"] == "skipped"
    assert observations["slow_inference_logs"]["status"] == "skipped"
    assert "SSH diagnostics skipped" in observations["gpu_hints"]["summary"]
    assert "SSH diagnostics skipped" in observations["slow_inference_logs"]["summary"]


def test_pal_slow_inference_diagnosis_writes_artifact_and_declares_no_mutation(
    tmp_path: Path,
) -> None:
    from promptclaw.pal_agent import run_pal_slow_inference_diagnosis

    config = default_project_config("PAL Slow Inference Diagnosis")
    save_config(tmp_path, config)
    executed: list[str] = []
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL router health.",
            run=lambda: _slow_tool_result(
                executed,
                "pal_health",
                {"health": {"status": "green"}},
            ),
        ),
        "pal_smoke_baseline": PALOpsTool(
            name="pal_smoke_baseline",
            description="Summarize PAL smoke baselines.",
            run=lambda: _slow_tool_result(
                executed,
                "pal_smoke_baseline",
                {"baseline_tokens_per_second": 12.0},
            ),
        ),
        "gpu_hints": PALOpsTool(
            name="gpu_hints",
            description="Collect read-only GPU hints.",
            run=lambda: _slow_tool_result(executed, "gpu_hints", {}),
        ),
        "slow_inference_logs": PALOpsTool(
            name="slow_inference_logs",
            description="Collect read-only PAL logs.",
            run=lambda: _slow_tool_result(executed, "slow_inference_logs", {}),
        ),
    }

    result = run_pal_slow_inference_diagnosis(
        tmp_path,
        task="Diagnose PAL slow inference without changing services.",
        client=FakePALClient([]),
        tool_registry=tool_registry,
        now=_fake_now(),
    )

    assert result["status"] == "complete"
    assert result["workflow_id"] == "slow_inference_diagnosis"
    assert result["mutating_actions"] == []
    assert result["executed_tools"] == [
        "pal_health",
        "pal_smoke_baseline",
        "gpu_hints",
        "slow_inference_logs",
    ]
    assert executed == result["executed_tools"]
    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    payload = json.loads((run_root / "outputs" / "slow-inference-diagnosis.json").read_text())
    route = json.loads((run_root / "routing" / "route.json").read_text())
    state = json.loads((run_root / "state.json").read_text())
    events = (run_root / "logs" / "events.jsonl").read_text()
    assert payload["workflow_id"] == "slow_inference_diagnosis"
    assert payload["mutating_actions"] == []
    assert payload["diagnosis"]["baseline_tokens_per_second"] == 12.0
    assert route["workflow_id"] == "slow_inference_diagnosis"
    assert route["mutating_actions"] == []
    assert "Mutating actions: none" in (run_root / "routing" / "route.md").read_text()
    assert "PAL Slow-Inference Diagnosis" in (run_root / "summary" / "final-summary.md").read_text()
    assert (run_root / "handoffs" / "slow-inference-diagnosis.md").exists()
    assert "slow_inference_diagnosis_started" in events
    assert "slow_inference_diagnosis_completed" in events
    assert state["status"] == "complete"
    assert state["lead_agent"] == "local-allowlist"
    assert state["verifier_agent"] == "local-allowlist"


def test_pal_slow_inference_diagnosis_derives_findings_from_context(
    tmp_path: Path,
) -> None:
    from promptclaw.pal_agent import run_pal_slow_inference_diagnosis

    config = default_project_config("PAL Slow Inference Diagnosis Findings")
    save_config(tmp_path, config)
    executed: list[str] = []
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL router health.",
            run=lambda: _slow_tool_result(
                executed,
                "pal_health",
                {"health": {"status": "green"}},
            ),
        ),
        "pal_smoke_baseline": PALOpsTool(
            name="pal_smoke_baseline",
            description="Summarize PAL smoke baselines.",
            run=lambda: _slow_tool_result(
                executed,
                "pal_smoke_baseline",
                {
                    "baseline_tokens_per_second": 4.0,
                    "baseline": {"report_count": 2, "pass_rate": 1.0},
                },
            ),
        ),
        "gpu_hints": PALOpsTool(
            name="gpu_hints",
            description="Collect read-only GPU hints.",
            run=lambda: _slow_tool_result(
                executed,
                "gpu_hints",
                {
                    "command": {
                        "stdout": "NVIDIA RTX A6000, 12000, 49140, 97, 70, 280\npython, 4321",
                        "stderr": "",
                    }
                },
            ),
        ),
        "slow_inference_logs": PALOpsTool(
            name="slow_inference_logs",
            description="Collect read-only PAL logs.",
            run=lambda: _slow_tool_result(
                executed,
                "slow_inference_logs",
                {
                    "command": {
                        "stdout": "ollama eval_count=12 eval_duration=6000000000",
                        "stderr": "",
                    }
                },
            ),
        ),
    }

    result = run_pal_slow_inference_diagnosis(
        tmp_path,
        task="PAL is answering at roughly two tokens per second.",
        client=FakePALClient([]),
        tool_registry=tool_registry,
        now=_fake_now(),
    )

    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    payload = json.loads((run_root / "outputs" / "slow-inference-diagnosis.json").read_text())
    diagnosis = payload["diagnosis"]
    finding_codes = {finding["code"] for finding in diagnosis["findings"]}
    assert diagnosis["severity"] == "critical"
    assert diagnosis["baseline_tokens_per_second"] == 4.0
    assert diagnosis["observed_tokens_per_second"] == 2.0
    assert diagnosis["gpu_utilization_percent"] == 97
    assert {
        "low_baseline_tokens_per_second",
        "log_throughput_regression",
        "gpu_saturation",
    } <= finding_codes
    assert diagnosis["recommendations"]


def test_pal_diagnose_slow_inference_cli_prints_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    parser = promptclaw_cli.build_parser()
    parsed = parser.parse_args([
        "pal",
        "diagnose",
        "slow-inference",
        str(tmp_path),
        "--task",
        "Diagnose slow PAL.",
        "--json",
    ])
    assert parsed.pal_command == "diagnose"
    assert parsed.pal_diagnose_command == "slow-inference"
    assert parsed.project_root == tmp_path
    assert parsed.task == "Diagnose slow PAL."
    assert parsed.json is True

    result = {
        "run_id": "20260515t191500z-pal-slow-inference-diagnosis",
        "workflow_id": "slow_inference_diagnosis",
        "status": "complete",
        "summary_path": ".promptclaw/runs/20260515t191500z-pal-slow-inference-diagnosis/summary/final-summary.md",
        "diagnosis_path": ".promptclaw/runs/20260515t191500z-pal-slow-inference-diagnosis/outputs/slow-inference-diagnosis.json",
        "executed_tools": ["pal_health", "pal_smoke_baseline"],
        "severity": "critical",
        "finding_count": 2,
        "mutating_actions": [],
    }
    calls: list[dict[str, Any]] = []

    def fake_run(project_root: Path, *, task: str) -> dict[str, Any]:
        calls.append({"project_root": project_root, "task": task})
        return dict(result)

    monkeypatch.setattr("promptclaw.cli.run_pal_slow_inference_diagnosis", fake_run)

    text_output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Diagnose slow PAL.", json=False)
    with redirect_stdout(text_output):
        rc = promptclaw_cli.cmd_pal_diagnose_slow_inference(args)

    assert rc == 0
    rendered = text_output.getvalue()
    assert "PAL slow-inference diagnosis: COMPLETE" in rendered
    assert "severity=critical" in rendered
    assert "executed_tools=pal_health,pal_smoke_baseline" in rendered
    assert "mutating_actions=none" in rendered
    assert calls == [{"project_root": tmp_path, "task": "Diagnose slow PAL."}]

    json_output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Diagnose slow PAL.", json=True)
    with redirect_stdout(json_output):
        rc = promptclaw_cli.cmd_pal_diagnose_slow_inference(args)

    assert rc == 0
    payload = json.loads(json_output.getvalue())
    assert payload["workflow_id"] == "slow_inference_diagnosis"
    assert payload["severity"] == "critical"
    assert payload["mutating_actions"] == []


def test_pal_restart_validation_runs_health_query_smoke_tailscale_and_process_checks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from promptclaw.pal_agent import run_pal_restart_validation

    config = default_project_config("PAL Restart Validation")
    save_config(tmp_path, config)
    calls: list[str] = []

    class RestartFakePALClient:
        base_url = "http://pal-cloud-a6000:8000"
        default_model = "llama3.3:70b-instruct-q4_K_M"

        def health(self) -> dict[str, Any]:
            calls.append("pal_health")
            return {"status": "green", "phase": "phase-1-a6000"}

        def query(
            self,
            prompt: str,
            *,
            system: str | None = None,
            model: str | None = None,
            temperature: float | None = 0.7,
        ) -> PALQueryResult:
            calls.append("pal_direct_query")
            assert "restart validation" in prompt.lower()
            return PALQueryResult(
                text="PAL restart validation query succeeded.",
                raw={
                    "response": "PAL restart validation query succeeded.",
                    "model": self.default_model,
                },
            )

    fake_client = RestartFakePALClient()

    def fake_run_pal_smoke(client: Any) -> dict[str, Any]:
        calls.append("pal_smoke")
        assert client is fake_client
        return {
            "status": "pass",
            "started_at": "2026-05-15T20:00:00+00:00",
            "summary": {"passed": 3, "failed": 0, "total_latency_s": 12.5},
            "checks": [],
        }

    def fake_write_smoke_report(
        project_root: Path,
        report: dict[str, Any],
        output: Path | None = None,
    ) -> Path:
        report_path = project_root / ".promptclaw" / "pal-smoke" / "pal-smoke-restart.json"
        report_path.parent.mkdir(parents=True)
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report_path

    def fake_tailscale_status() -> dict[str, Any]:
        calls.append("tailscale_status")
        return {
            "status": "ok",
            "summary": "pal-cloud-a6000 is visible in local Tailscale status.",
            "node_visible": True,
        }

    def fake_process_check() -> dict[str, Any]:
        calls.append("ssh_process_check")
        return {
            "status": "ok",
            "summary": "Read-only SSH process/log diagnostic completed.",
            "command": {
                "stdout": "tailscaled\nollama serve\nuvicorn app:app --host 0.0.0.0 --port 8000",
                "stderr": "",
                "exit_code": 0,
            },
        }

    monkeypatch.setattr("promptclaw.pal_agent.run_pal_smoke", fake_run_pal_smoke)
    monkeypatch.setattr("promptclaw.pal_agent.write_smoke_report", fake_write_smoke_report)
    monkeypatch.setattr("promptclaw.pal_agent._tailscale_status_tool", fake_tailscale_status)
    monkeypatch.setattr("promptclaw.pal_agent._ssh_process_check_tool", fake_process_check)

    result = run_pal_restart_validation(
        tmp_path,
        task="Validate PAL after restart.",
        client=fake_client,
        now=_fake_now(),
    )

    expected_tools = [
        "pal_health",
        "pal_direct_query",
        "pal_smoke",
        "tailscale_status",
        "ssh_process_check",
    ]
    assert calls == expected_tools
    assert result["status"] == "complete"
    assert result["workflow_id"] == "restart_validation"
    assert result["validation_status"] == "pass"
    assert result["mutating_actions"] == []
    assert result["executed_tools"] == expected_tools

    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    payload = json.loads((run_root / "outputs" / "restart-validation.json").read_text())
    route = json.loads((run_root / "routing" / "route.json").read_text())
    state = json.loads((run_root / "state.json").read_text())
    events = (run_root / "logs" / "events.jsonl").read_text()
    observations = {row["tool"]: row for row in payload["observations"]}

    assert payload["workflow_id"] == "restart_validation"
    assert payload["validation_status"] == "pass"
    assert payload["mutating_actions"] == []
    assert payload["executed_tools"] == expected_tools
    assert observations["pal_health"]["health"]["status"] == "green"
    assert observations["pal_direct_query"]["query"]["response"] == "PAL restart validation query succeeded."
    assert observations["pal_smoke"]["report"]["status"] == "pass"
    assert observations["pal_smoke"]["report_path"].endswith(".promptclaw/pal-smoke/pal-smoke-restart.json")
    assert observations["tailscale_status"]["node_visible"] is True
    assert "ollama serve" in observations["ssh_process_check"]["command"]["stdout"]
    assert route["workflow_id"] == "restart_validation"
    assert route["mutating_actions"] == []
    assert "Mutating actions: none" in (run_root / "routing" / "route.md").read_text()
    assert "PAL Restart Validation" in (run_root / "summary" / "final-summary.md").read_text()
    assert (run_root / "handoffs" / "restart-validation.md").exists()
    assert "restart_validation_started" in events
    assert "restart_validation_completed" in events
    assert state["status"] == "complete"
    assert state["lead_agent"] == "local-allowlist"
    assert state["verifier_agent"] == "local-allowlist"


def test_pal_validate_restart_cli_prints_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    parser = promptclaw_cli.build_parser()
    parsed = parser.parse_args([
        "pal",
        "validate",
        "restart",
        str(tmp_path),
        "--task",
        "Validate restart.",
        "--json",
    ])
    assert parsed.pal_command == "validate"
    assert parsed.pal_validate_command == "restart"
    assert parsed.project_root == tmp_path
    assert parsed.task == "Validate restart."
    assert parsed.json is True

    result = {
        "run_id": "20260515t200000z-pal-restart-validation",
        "workflow_id": "restart_validation",
        "status": "complete",
        "validation_status": "pass",
        "summary_path": ".promptclaw/runs/20260515t200000z-pal-restart-validation/summary/final-summary.md",
        "validation_path": ".promptclaw/runs/20260515t200000z-pal-restart-validation/outputs/restart-validation.json",
        "executed_tools": ["pal_health", "pal_direct_query", "pal_smoke"],
        "tool_count": 3,
        "mutating_actions": [],
    }
    calls: list[dict[str, Any]] = []

    def fake_run(project_root: Path, *, task: str) -> dict[str, Any]:
        calls.append({"project_root": project_root, "task": task})
        return dict(result)

    monkeypatch.setattr("promptclaw.cli.run_pal_restart_validation", fake_run)

    text_output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Validate restart.", json=False)
    with redirect_stdout(text_output):
        rc = promptclaw_cli.cmd_pal_validate_restart(args)

    assert rc == 0
    rendered = text_output.getvalue()
    assert "PAL restart validation: COMPLETE" in rendered
    assert "validation_status=pass" in rendered
    assert "executed_tools=pal_health,pal_direct_query,pal_smoke" in rendered
    assert "mutating_actions=none" in rendered
    assert calls == [{"project_root": tmp_path, "task": "Validate restart."}]

    json_output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Validate restart.", json=True)
    with redirect_stdout(json_output):
        rc = promptclaw_cli.cmd_pal_validate_restart(args)

    assert rc == 0
    payload = json.loads(json_output.getvalue())
    assert payload["workflow_id"] == "restart_validation"
    assert payload["validation_status"] == "pass"
    assert payload["mutating_actions"] == []


def test_pal_shutdown_audit_reports_enabled_override_and_next_window(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from promptclaw.pal_agent import run_pal_shutdown_audit

    config = default_project_config("PAL Shutdown Audit")
    save_config(tmp_path, config)
    runner = FakeSSHRunner([
        {
            "exit_code": 0,
            "stdout": "\n".join([
                "CONFIG_PATH=/opt/pal/config/shutdown.conf",
                "CONFIG_PRESENT=true",
                "ENABLED=true",
                "SHUTDOWN_TIME=01:00",
                "TIMEZONE=America/Los_Angeles",
                "OVERRIDE_FILE=/opt/pal/config/override.flag",
                "OVERRIDE_PRESENT=false",
                "CRON_ENTRY=*/5 * * * * /opt/pal/scripts/auto_shutdown.sh",
                "CURRENT_LOCAL=2026-05-15T23:30:00-0700",
                "--- shutdown log ---",
                "Fri May 15 01:00:01 PDT 2026: Shutdown window skipped during test.",
            ]),
            "stderr": "",
        }
    ])
    monkeypatch.setattr("promptclaw.pal_agent._run_ssh_command", runner)

    result = run_pal_shutdown_audit(
        tmp_path,
        task="Audit PAL shutdown configuration.",
        client=FakePALClient([]),
        now=_fake_now(),
    )

    assert result["status"] == "complete"
    assert result["workflow_id"] == "shutdown_audit"
    assert result["audit_status"] == "pass"
    assert result["shutdown_enabled_state"] == "enabled"
    assert result["override_state"] == "inactive"
    assert result["next_shutdown_window"] == "2026-05-16 01:00-01:05 America/Los_Angeles"
    assert result["mutating_actions"] == []
    assert result["executed_tools"] == ["shutdown_remote_audit"]

    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    payload = json.loads((run_root / "outputs" / "shutdown-audit.json").read_text())
    route = json.loads((run_root / "routing" / "route.json").read_text())
    state = json.loads((run_root / "state.json").read_text())
    events = (run_root / "logs" / "events.jsonl").read_text()
    summary = (run_root / "summary" / "final-summary.md").read_text()
    observation = payload["observations"][0]

    assert payload["workflow_id"] == "shutdown_audit"
    assert payload["mutating_actions"] == []
    assert payload["audit_status"] == "pass"
    assert payload["shutdown_enabled_state"] == "enabled"
    assert payload["override_state"] == "inactive"
    assert payload["next_shutdown_window"] == "2026-05-16 01:00-01:05 America/Los_Angeles"
    assert payload["audit"]["cron_installed"] is True
    assert payload["audit"]["shutdown_time"] == "01:00"
    assert payload["audit"]["timezone"] == "America/Los_Angeles"
    assert payload["audit"]["override_file"] == "/opt/pal/config/override.flag"
    assert "Shutdown window skipped during test" in payload["audit"]["recent_log_excerpt"]
    assert observation["tool"] == "shutdown_remote_audit"
    assert observation["status"] == "ok"
    assert route["workflow_id"] == "shutdown_audit"
    assert route["mutating_actions"] == []
    assert route["shutdown_enabled_state"] == "enabled"
    assert route["override_state"] == "inactive"
    assert route["next_shutdown_window"] == "2026-05-16 01:00-01:05 America/Los_Angeles"
    assert "Mutating actions: none" in (run_root / "routing" / "route.md").read_text()
    assert "Shutdown enabled state: enabled" in summary
    assert "Override state: inactive" in summary
    assert "Next shutdown window: 2026-05-16 01:00-01:05 America/Los_Angeles" in summary
    assert (run_root / "handoffs" / "shutdown-audit.md").exists()
    assert "shutdown_audit_started" in events
    assert "shutdown_audit_completed" in events
    assert state["status"] == "complete"
    assert state["lead_agent"] == "local-allowlist"
    assert state["verifier_agent"] == "local-allowlist"
    assert "/opt/pal/config/shutdown.conf" in runner.last_command
    assert "crontab -l" in runner.last_command
    assert "/opt/pal/logs/shutdown.log" in runner.last_command
    assert "touch /opt/pal/config/override.flag" not in runner.last_command
    assert "rm -f /opt/pal/config/override.flag" not in runner.last_command
    assert "shutdown -h now" not in runner.last_command


def test_pal_shutdown_audit_without_ssh_records_unknown_states(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from promptclaw.pal_agent import run_pal_shutdown_audit

    config = default_project_config("PAL Shutdown Audit No SSH")
    save_config(tmp_path, config)
    for key in ("PAL_SSH_HOST", "PAL_SSH_PORT", "PAL_SSH_KEY"):
        monkeypatch.delenv(key, raising=False)

    result = run_pal_shutdown_audit(
        tmp_path,
        client=FakePALClient([]),
        now=_fake_now(),
    )

    assert result["status"] == "complete"
    assert result["workflow_id"] == "shutdown_audit"
    assert result["audit_status"] == "incomplete"
    assert result["shutdown_enabled_state"] == "unknown"
    assert result["override_state"] == "unknown"
    assert result["next_shutdown_window"] == "unavailable"

    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    payload = json.loads((run_root / "outputs" / "shutdown-audit.json").read_text())
    observation = payload["observations"][0]
    summary = (run_root / "summary" / "final-summary.md").read_text()

    assert observation["status"] == "skipped"
    assert payload["audit"]["cron_installed"] is None
    assert payload["audit"]["config_present"] is None
    assert "Shutdown enabled state: unknown" in summary
    assert "Override state: unknown" in summary
    assert "Next shutdown window: unavailable" in summary


def test_pal_audit_shutdown_cli_prints_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    parser = promptclaw_cli.build_parser()
    parsed = parser.parse_args([
        "pal",
        "audit",
        "shutdown",
        str(tmp_path),
        "--task",
        "Audit shutdown.",
        "--json",
    ])
    assert parsed.pal_command == "audit"
    assert parsed.pal_audit_command == "shutdown"
    assert parsed.project_root == tmp_path
    assert parsed.task == "Audit shutdown."
    assert parsed.json is True

    result = {
        "run_id": "20260515t203000z-pal-shutdown-audit",
        "workflow_id": "shutdown_audit",
        "status": "complete",
        "audit_status": "pass",
        "shutdown_enabled_state": "enabled",
        "override_state": "inactive",
        "next_shutdown_window": "2026-05-16 01:00-01:05 America/Los_Angeles",
        "summary_path": ".promptclaw/runs/20260515t203000z-pal-shutdown-audit/summary/final-summary.md",
        "audit_path": ".promptclaw/runs/20260515t203000z-pal-shutdown-audit/outputs/shutdown-audit.json",
        "executed_tools": ["shutdown_remote_audit"],
        "tool_count": 1,
        "mutating_actions": [],
    }
    calls: list[dict[str, Any]] = []

    def fake_run(project_root: Path, *, task: str) -> dict[str, Any]:
        calls.append({"project_root": project_root, "task": task})
        return dict(result)

    monkeypatch.setattr("promptclaw.cli.run_pal_shutdown_audit", fake_run)

    text_output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Audit shutdown.", json=False)
    with redirect_stdout(text_output):
        rc = promptclaw_cli.cmd_pal_audit_shutdown(args)

    assert rc == 0
    rendered = text_output.getvalue()
    assert "PAL shutdown audit: COMPLETE" in rendered
    assert "audit_status=pass" in rendered
    assert "shutdown_enabled=enabled" in rendered
    assert "override=inactive" in rendered
    assert "next_shutdown_window=2026-05-16 01:00-01:05 America/Los_Angeles" in rendered
    assert "mutating_actions=none" in rendered
    assert calls == [{"project_root": tmp_path, "task": "Audit shutdown."}]

    json_output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Audit shutdown.", json=True)
    with redirect_stdout(json_output):
        rc = promptclaw_cli.cmd_pal_audit_shutdown(args)

    assert rc == 0
    payload = json.loads(json_output.getvalue())
    assert payload["workflow_id"] == "shutdown_audit"
    assert payload["shutdown_enabled_state"] == "enabled"
    assert payload["override_state"] == "inactive"
    assert payload["next_shutdown_window"] == "2026-05-16 01:00-01:05 America/Los_Angeles"
    assert payload["mutating_actions"] == []


def test_pal_phase2_readiness_report_scores_each_prerequisite_without_actions(
    tmp_path: Path,
) -> None:
    from promptclaw.pal_agent import run_pal_phase2_readiness_report

    config = default_project_config("PAL Phase 2 Readiness")
    save_config(tmp_path, config)
    executed: list[str] = []
    expected_tools = [
        "pal_health",
        "pal_smoke_baseline",
        "shutdown_remote_audit",
        "phase2_project_state",
        "vast_boundary",
    ]
    tool_registry = {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Check PAL health.",
            run=lambda: _slow_tool_result(
                executed,
                "pal_health",
                {"health": {"status": "green", "phase": "phase-1-a6000"}},
            ),
        ),
        "pal_smoke_baseline": PALOpsTool(
            name="pal_smoke_baseline",
            description="Summarize PAL smoke baselines.",
            run=lambda: _slow_tool_result(
                executed,
                "pal_smoke_baseline",
                {
                    "baseline": {
                        "report_count": 2,
                        "pass_count": 2,
                        "fail_count": 0,
                        "pass_rate": 1.0,
                    },
                    "baseline_tokens_per_second": 18.4,
                },
            ),
        ),
        "shutdown_remote_audit": PALOpsTool(
            name="shutdown_remote_audit",
            description="Audit shutdown state.",
            run=lambda: _slow_tool_result(
                executed,
                "shutdown_remote_audit",
                {
                    "audit": {
                        "audit_status": "pass",
                        "shutdown_enabled_state": "enabled",
                        "override_state": "inactive",
                        "next_shutdown_window": "2026-05-16 01:00-01:05 America/Los_Angeles",
                    }
                },
            ),
        ),
        "phase2_project_state": PALOpsTool(
            name="phase2_project_state",
            description="Inspect local PAL project state.",
            run=lambda: _slow_tool_result(
                executed,
                "phase2_project_state",
                {
                    "project_state": {
                        "phase1_runbook_present": True,
                        "session_state_present": True,
                        "phase2_is_appendix_only": True,
                    }
                },
            ),
        ),
        "vast_boundary": PALOpsTool(
            name="vast_boundary",
            description="Inspect Vast boundary.",
            run=lambda: _slow_tool_result(
                executed,
                "vast_boundary",
                {
                    "boundary": {
                        "provider": "vast",
                        "status": "stubbed",
                        "blocked_actions": ["rent", "destroy", "start", "stop"],
                        "callable_actions": [],
                    }
                },
            ),
        ),
    }

    result = run_pal_phase2_readiness_report(
        tmp_path,
        task="Assess Phase 2 readiness.",
        client=FakePALClient([]),
        tool_registry=tool_registry,
        now=_fake_now(),
    )

    assert executed == expected_tools
    assert result["status"] == "complete"
    assert result["workflow_id"] == "phase2_readiness_report"
    assert result["readiness_status"] == "blocked"
    assert result["overall_score"] == 0.83
    assert result["mutating_actions"] == []
    assert result["phase2_execution_actions"] == []
    assert result["executed_tools"] == expected_tools

    run_root = tmp_path / ".promptclaw" / "runs" / result["run_id"]
    payload = json.loads((run_root / "outputs" / "phase2-readiness.json").read_text())
    route = json.loads((run_root / "routing" / "route.json").read_text())
    state = json.loads((run_root / "state.json").read_text())
    events = (run_root / "logs" / "events.jsonl").read_text()
    summary = (run_root / "summary" / "final-summary.md").read_text()
    prerequisites = {row["id"]: row for row in payload["prerequisites"]}

    assert set(prerequisites) == {
        "operator_authorization",
        "phase1_health_baseline",
        "shutdown_safety",
        "deployment_reproducibility",
        "cost_and_vast_boundary",
        "phase2_execution_boundary",
    }
    assert prerequisites["operator_authorization"]["score"] == 0.0
    assert prerequisites["operator_authorization"]["status"] == "blocked"
    assert prerequisites["phase1_health_baseline"]["score"] == 1.0
    assert prerequisites["shutdown_safety"]["score"] == 1.0
    assert prerequisites["deployment_reproducibility"]["score"] == 1.0
    assert prerequisites["cost_and_vast_boundary"]["score"] == 1.0
    assert prerequisites["phase2_execution_boundary"]["score"] == 1.0
    assert payload["workflow_id"] == "phase2_readiness_report"
    assert payload["overall_score"] == 0.83
    assert payload["readiness_status"] == "blocked"
    assert payload["mutating_actions"] == []
    assert payload["phase2_execution_actions"] == []
    assert payload["executed_tools"] == expected_tools
    assert route["workflow_id"] == "phase2_readiness_report"
    assert route["mutating_actions"] == []
    assert route["phase2_execution_actions"] == []
    assert "Mutating actions: none" in (run_root / "routing" / "route.md").read_text()
    assert "Phase 2 execution actions: none" in summary
    assert "operator_authorization" in summary
    assert (run_root / "handoffs" / "phase2-readiness.md").exists()
    assert not (run_root / "outputs" / "action-results.json").exists()
    assert "phase2_readiness_started" in events
    assert "phase2_readiness_completed" in events
    assert state["status"] == "complete"
    assert state["lead_agent"] == "local-allowlist"
    assert state["verifier_agent"] == "local-allowlist"


def test_pal_report_phase2_readiness_cli_prints_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    parser = promptclaw_cli.build_parser()
    parsed = parser.parse_args([
        "pal",
        "report",
        "phase2-readiness",
        str(tmp_path),
        "--task",
        "Assess readiness.",
        "--json",
    ])
    assert parsed.pal_command == "report"
    assert parsed.pal_report_command == "phase2-readiness"
    assert parsed.project_root == tmp_path
    assert parsed.task == "Assess readiness."
    assert parsed.json is True
    assert not hasattr(parsed, "approve")

    result = {
        "run_id": "20260515t210000z-pal-phase2-readiness",
        "workflow_id": "phase2_readiness_report",
        "status": "complete",
        "readiness_status": "blocked",
        "overall_score": 0.83,
        "summary_path": ".promptclaw/runs/20260515t210000z-pal-phase2-readiness/summary/final-summary.md",
        "readiness_path": ".promptclaw/runs/20260515t210000z-pal-phase2-readiness/outputs/phase2-readiness.json",
        "executed_tools": ["pal_health", "pal_smoke_baseline"],
        "tool_count": 2,
        "prerequisite_count": 6,
        "mutating_actions": [],
        "phase2_execution_actions": [],
    }
    calls: list[dict[str, Any]] = []

    def fake_run(project_root: Path, *, task: str) -> dict[str, Any]:
        calls.append({"project_root": project_root, "task": task})
        return dict(result)

    monkeypatch.setattr("promptclaw.cli.run_pal_phase2_readiness_report", fake_run)

    text_output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Assess readiness.", json=False)
    with redirect_stdout(text_output):
        rc = promptclaw_cli.cmd_pal_report_phase2_readiness(args)

    assert rc == 0
    rendered = text_output.getvalue()
    assert "PAL Phase 2 readiness: COMPLETE" in rendered
    assert "readiness_status=blocked" in rendered
    assert "overall_score=0.83" in rendered
    assert "executed_tools=pal_health,pal_smoke_baseline" in rendered
    assert "mutating_actions=none" in rendered
    assert "phase2_execution_actions=none" in rendered
    assert calls == [{"project_root": tmp_path, "task": "Assess readiness."}]

    json_output = io.StringIO()
    args = argparse.Namespace(project_root=tmp_path, task="Assess readiness.", json=True)
    with redirect_stdout(json_output):
        rc = promptclaw_cli.cmd_pal_report_phase2_readiness(args)

    assert rc == 0
    payload = json.loads(json_output.getvalue())
    assert payload["workflow_id"] == "phase2_readiness_report"
    assert payload["readiness_status"] == "blocked"
    assert payload["mutating_actions"] == []
    assert payload["phase2_execution_actions"] == []


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


def _slow_tool_result(
    executed: list[str],
    name: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    executed.append(name)
    result = {"tool": name, "status": "ok", "summary": f"{name} ran"}
    result.update(extra)
    return result


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
