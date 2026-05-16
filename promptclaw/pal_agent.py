from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from .artifacts import ArtifactManager
from .config import load_config
from .models import Event, RunState
from .pal_client import PALClientError, PALQueryResult, PALRouterClient
from .pal_knowledge import PALKnowledgeQueryResult, query_pal_knowledge_index
from .pal_smoke import load_smoke_reports, run_pal_smoke, summarize_smoke_reports, write_smoke_report
from .paths import ProjectPaths
from .state_store import StateStore
from .utils import extract_json_object, slugify, truncate, utc_now, write_text
from .vast_connector import default_vast_connector_boundary


class PALAgentClient(Protocol):
    base_url: str
    default_model: str

    def health(self) -> dict[str, Any]:
        ...

    def query(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.7,
    ) -> PALQueryResult:
        ...


@dataclass(frozen=True)
class PALOpsTool:
    name: str
    description: str
    run: Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class PALOpsAction:
    name: str
    description: str
    approval_required: bool
    mutating: bool
    run: Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class PALWorkflowArtifactVerification:
    run_root: Path
    workflow_id: str
    required_artifacts: tuple[str, ...]
    missing_artifacts: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing_artifacts

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_root": str(self.run_root),
            "workflow_id": self.workflow_id,
            "passed": self.passed,
            "required_artifacts": list(self.required_artifacts),
            "missing_artifacts": list(self.missing_artifacts),
        }


PAL_OPS_TRIAGE_WORKFLOW_ID = "pal_ops_triage"
PAL_OPS_ACTIONS_WORKFLOW_ID = "pal_ops_actions"

DEFAULT_TRIAGE_TASK = (
    "Diagnose PAL 2026 operational health from the local PromptClaw control plane. "
    "Confirm router health, recent smoke baseline, local Tailscale visibility, and "
    "remote PAL process hints when SSH diagnostics are configured. Recommend next "
    "operator actions without changing infrastructure."
)

DEFAULT_TOOL_ORDER: tuple[str, ...] = (
    "pal_health",
    "pal_smoke_baseline",
    "tailscale_status",
    "ssh_process_check",
)

DEFAULT_ACTION_TASK = (
    "Review the current PAL 2026 diagnostic context and propose the next bounded "
    "operator actions. Use the fixed action allow-list only. Prefer read-only "
    "evidence gathering before mutating actions, and keep every mutating action "
    "behind explicit human approval."
)

DEFAULT_SLOW_INFERENCE_TASK = (
    "Collect read-only PAL 2026 slow-inference context. Capture router health, "
    "saved smoke baseline token throughput, GPU resource hints, and recent PAL "
    "router/Ollama logs when SSH diagnostics are configured."
)

SLOW_INFERENCE_WORKFLOW_ID = "slow_inference_context"

DEFAULT_SLOW_INFERENCE_DIAGNOSIS_TASK = (
    "Diagnose PAL 2026 slow inference from fixed read-only evidence. Capture "
    "health, saved smoke baseline token throughput, optional GPU hints, and "
    "optional router/Ollama logs, then write a local diagnosis artifact without "
    "changing infrastructure."
)

SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID = "slow_inference_diagnosis"

DEFAULT_SLOW_INFERENCE_CONTEXT_TOOL_ORDER: tuple[str, ...] = (
    "pal_health",
    "pal_smoke_baseline",
    "gpu_hints",
    "slow_inference_logs",
)

DEFAULT_SLOW_INFERENCE_DIAGNOSIS_TOOL_ORDER = DEFAULT_SLOW_INFERENCE_CONTEXT_TOOL_ORDER

DEFAULT_RESTART_VALIDATION_TASK = (
    "Validate PAL 2026 after a restart or instance boot. Capture router health, "
    "one direct query, an active smoke run, local Tailscale reachability, and "
    "remote process hints when SSH diagnostics are configured."
)

RESTART_VALIDATION_WORKFLOW_ID = "restart_validation"

RESTART_VALIDATION_QUERY_PROMPT = (
    "Restart validation check: confirm PAL 2026 is reachable and ready after restart "
    "in one concise operational sentence."
)

DEFAULT_RESTART_VALIDATION_TOOL_ORDER: tuple[str, ...] = (
    "pal_health",
    "pal_direct_query",
    "pal_smoke",
    "tailscale_status",
    "ssh_process_check",
)

DEFAULT_SHUTDOWN_AUDIT_TASK = (
    "Audit PAL 2026 auto-shutdown configuration. Capture whether scheduled "
    "shutdown is enabled, whether the override flag is active, the next "
    "shutdown window, cron registration, and recent shutdown log evidence."
)

SHUTDOWN_AUDIT_WORKFLOW_ID = "shutdown_audit"

DEFAULT_SHUTDOWN_AUDIT_TOOL_ORDER: tuple[str, ...] = (
    "shutdown_remote_audit",
)

DEFAULT_PHASE2_READINESS_TASK = (
    "Assess PAL 2026 Phase 2 readiness from fixed read-only evidence. Score "
    "operator authorization, Phase 1 health, shutdown safety, deployment "
    "reproducibility, cost boundaries, and the no-execution boundary without "
    "starting any Phase 2 work."
)

PHASE2_READINESS_WORKFLOW_ID = "phase2_readiness_report"

DEFAULT_PHASE2_READINESS_TOOL_ORDER: tuple[str, ...] = (
    "pal_health",
    "pal_smoke_baseline",
    "shutdown_remote_audit",
    "phase2_project_state",
    "vast_boundary",
)

PHASE2_BLOCKED_EXECUTION_ACTIONS: tuple[str, ...] = (
    "rent",
    "destroy",
    "start",
    "stop",
    "resize_gpu_pool",
    "load_phase2_model",
    "migrate_persistent_volume",
)

PAL_AGENT_SYSTEM_PROMPT = (
    "You are PAL 2026 operating through PromptClaw's bounded agent runtime. "
    "You may choose diagnostics from the provided allow-list only. You cannot run "
    "arbitrary shell commands, mutate files, restart services, stop or destroy cloud "
    "instances, rotate keys, or spend money. Recommend those actions only as human "
    "approval gates."
)

PAL_KNOWLEDGE_CONTEXT_LIMIT = 3
PAL_KNOWLEDGE_CONTEXT_MAX_CHARS = 1600
PAL_KNOWLEDGE_SNIPPET_MAX_CHARS = 240

PAL_WORKFLOW_COMMON_REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "input/task.md",
    "routing/route.json",
    "routing/route.md",
    "summary/final-summary.md",
    "summary/run-summary.json",
    "logs/events.jsonl",
    "state.json",
)

PAL_WORKFLOW_REQUIRED_ARTIFACTS: dict[str, tuple[str, ...]] = {
    PAL_OPS_TRIAGE_WORKFLOW_ID: (
        *PAL_WORKFLOW_COMMON_REQUIRED_ARTIFACTS,
        "prompts/triage-plan.md",
        "prompts/triage-summary.md",
        "outputs/triage-plan.raw.txt",
        "outputs/triage-plan.json",
        "outputs/tool-observations.json",
        "handoffs/pal-to-operator.md",
    ),
    PAL_OPS_ACTIONS_WORKFLOW_ID: (
        *PAL_WORKFLOW_COMMON_REQUIRED_ARTIFACTS,
        "outputs/action-context.json",
        "prompts/action-plan.md",
        "prompts/action-summary.md",
        "outputs/action-plan.raw.txt",
        "outputs/action-plan.json",
        "outputs/action-results.json",
        "handoffs/pal-action-request.md",
    ),
    SLOW_INFERENCE_WORKFLOW_ID: (
        *PAL_WORKFLOW_COMMON_REQUIRED_ARTIFACTS,
        "outputs/slow-inference-context.json",
        "handoffs/slow-inference-context.md",
    ),
    SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID: (
        *PAL_WORKFLOW_COMMON_REQUIRED_ARTIFACTS,
        "outputs/slow-inference-diagnosis.json",
        "handoffs/slow-inference-diagnosis.md",
    ),
    RESTART_VALIDATION_WORKFLOW_ID: (
        *PAL_WORKFLOW_COMMON_REQUIRED_ARTIFACTS,
        "outputs/restart-validation.json",
        "handoffs/restart-validation.md",
    ),
    SHUTDOWN_AUDIT_WORKFLOW_ID: (
        *PAL_WORKFLOW_COMMON_REQUIRED_ARTIFACTS,
        "outputs/shutdown-audit.json",
        "handoffs/shutdown-audit.md",
    ),
    PHASE2_READINESS_WORKFLOW_ID: (
        *PAL_WORKFLOW_COMMON_REQUIRED_ARTIFACTS,
        "outputs/phase2-readiness.json",
        "handoffs/phase2-readiness.md",
    ),
}


def verify_pal_workflow_artifacts(
    run_root: Path,
    *,
    workflow_id: str | None = None,
) -> PALWorkflowArtifactVerification:
    resolved_run_root = run_root.resolve()
    resolved_workflow_id = workflow_id or _read_pal_workflow_id(resolved_run_root)
    required_artifacts = PAL_WORKFLOW_REQUIRED_ARTIFACTS.get(resolved_workflow_id)
    if required_artifacts is None:
        raise ValueError(f"unsupported PAL workflow: {resolved_workflow_id}")
    missing_artifacts = tuple(
        relative_path
        for relative_path in required_artifacts
        if not (resolved_run_root / relative_path).is_file()
    )
    return PALWorkflowArtifactVerification(
        run_root=resolved_run_root,
        workflow_id=resolved_workflow_id,
        required_artifacts=required_artifacts,
        missing_artifacts=missing_artifacts,
    )


@dataclass(frozen=True)
class PALSecretFinding:
    artifact: str
    pattern: str


@dataclass(frozen=True)
class PALArtifactRedactionVerification:
    run_root: Path
    scanned_artifacts: tuple[str, ...]
    findings: tuple[PALSecretFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_root": str(self.run_root),
            "passed": self.passed,
            "scanned_artifacts": list(self.scanned_artifacts),
            "findings": [
                {"artifact": finding.artifact, "pattern": finding.pattern}
                for finding in self.findings
            ],
        }


PAL_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pal_ssh_key_value", re.compile(r"PAL_SSH_KEY\s*[=:]\s*\S")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("openai_token", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)


def verify_pal_artifact_redaction(run_root: Path) -> PALArtifactRedactionVerification:
    resolved_run_root = run_root.resolve()
    findings: list[PALSecretFinding] = []
    scanned: list[str] = []
    for path in sorted(resolved_run_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        relative = path.relative_to(resolved_run_root).as_posix()
        scanned.append(relative)
        for pattern_name, pattern in PAL_SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(PALSecretFinding(artifact=relative, pattern=pattern_name))
    return PALArtifactRedactionVerification(
        run_root=resolved_run_root,
        scanned_artifacts=tuple(scanned),
        findings=tuple(findings),
    )


PAL_SSH_REQUIRED_ENV_VARS: tuple[str, ...] = ("PAL_SSH_HOST", "PAL_SSH_PORT", "PAL_SSH_KEY")


def pal_ssh_env_missing(env: dict[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return not all((source.get(name) or "").strip() for name in PAL_SSH_REQUIRED_ENV_VARS)


def write_pal_escalation_artifact(
    run_root: Path,
    *,
    pending_approval: Iterable[str],
    ssh_env_missing: bool,
) -> Path | None:
    """Write `summary/escalation.md` when SSH env is missing and approvals are pending.

    Returns the artifact path when written, or ``None`` when either trigger is absent.
    """
    pending = [action_id for action_id in pending_approval if action_id]
    if not pending or not ssh_env_missing:
        return None
    path = run_root / "summary" / "escalation.md"
    write_text(path, _render_pal_escalation_markdown(pending))
    return path


def _render_pal_escalation_markdown(pending_approval: list[str]) -> str:
    bullets = "\n".join(f"- `{action_id}`" for action_id in pending_approval)
    missing = ", ".join(f"`{name}`" for name in PAL_SSH_REQUIRED_ENV_VARS)
    return (
        "# PAL Escalation\n\n"
        "PAL run requires human attention: SSH diagnostics are not configured "
        "and one or more proposed actions are still awaiting approval.\n\n"
        "## Pending approval\n\n"
        f"{bullets}\n\n"
        "## Required environment\n\n"
        f"Set {missing} so PAL can collect remote evidence, or explicitly "
        "approve the pending action ids above.\n"
    )


def _read_pal_workflow_id(run_root: Path) -> str:
    candidates: tuple[tuple[Path, tuple[str, ...]], ...] = (
        (run_root / "summary" / "run-summary.json", ("workflow",)),
        (run_root / "routing" / "route.json", ("workflow_id", "task_type")),
    )
    for path, keys in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
    raise ValueError("workflow_id required when PAL run artifacts do not identify the workflow")


def load_pal_action_results(project_root: Path, run_id: str) -> dict[str, Any]:
    """Load the saved PAL action plan results for ``run_id``.

    Reads ``outputs/action-results.json`` written by ``run_pal_ops_actions``.
    """
    project_root = project_root.resolve()
    config = load_config(project_root)
    paths = ProjectPaths(project_root=project_root, config=config)
    results_path = paths.run_outputs(run_id) / "action-results.json"
    if not results_path.is_file():
        raise FileNotFoundError(
            f"PAL action results not found for run_id {run_id!r}: {results_path}"
        )
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(
            f"PAL action results for run_id {run_id!r} must be a JSON object"
        )
    return payload


def run_pal_ops_triage(
    project_root: Path,
    *,
    task: str = DEFAULT_TRIAGE_TASK,
    client: PALAgentClient | None = None,
    tool_registry: dict[str, PALOpsTool] | None = None,
    default_tools: tuple[str, ...] = DEFAULT_TOOL_ORDER,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_config(project_root)
    paths = ProjectPaths(project_root=project_root, config=config)
    pal_client = client or PALRouterClient.from_config(config)
    tools = tool_registry or build_default_tool_registry(project_root, pal_client)

    created_at = now()
    run_id = _build_run_id(created_at, "pal-ops-triage")
    artifacts = ArtifactManager(paths, run_id)
    artifacts.create_run_layout()
    artifacts.write_task(task)

    state = RunState(
        run_id=run_id,
        title="PAL Ops Triage",
        status="running",
        current_phase="planning",
        created_at=created_at,
        updated_at=created_at,
        task_text=task,
        lead_agent="pal",
        verifier_agent="local-allowlist",
        route_decision={
            "task_type": "pal_ops_triage",
            "lead_agent": "pal",
            "verifier_agent": "local-allowlist",
            "reason": "PAL selects from bounded diagnostics; PromptClaw executes only allow-listed tools.",
        },
    )

    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.started",
        message="PAL ops triage run started.",
        phase="planning",
        agent="pal",
    )

    knowledge_context = _build_knowledge_context(project_root, task)
    plan_prompt = _render_plan_prompt(task, tools, knowledge_context=knowledge_context)
    plan_prompt_path = artifacts.write_prompt("triage-plan.md", plan_prompt)
    plan_result = pal_client.query(
        plan_prompt,
        system=PAL_AGENT_SYSTEM_PROMPT,
        temperature=0.1,
    )
    artifacts.write_output("triage-plan.raw.txt", plan_result.text)
    plan = _parse_tool_plan(plan_result.text, tools=tools, default_tools=default_tools)
    plan_output_path = artifacts.write_output("triage-plan.json", _json_dumps(plan))
    artifacts.write_route_json({
        "lead_agent": "pal",
        "verifier_agent": "local-allowlist",
        "task_type": "pal_ops_triage",
        "plan_source": plan["source"],
        "tools": plan["tools"],
        "ignored_tools": plan["ignored_tools"],
        "prompt_path": _relative_path(project_root, plan_prompt_path),
        "output_path": _relative_path(project_root, plan_output_path),
    })
    artifacts.write_route_markdown(_render_route_markdown(plan))
    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.plan_selected",
        message=f"Selected {len(plan['tools'])} bounded diagnostic tools.",
        phase="planning",
        agent="pal",
        extra={"tools": plan["tools"], "ignored_tools": plan["ignored_tools"], "source": plan["source"]},
    )

    state.current_phase = "tooling"
    observations: list[dict[str, Any]] = []
    for tool_name in plan["tools"]:
        tool = tools[tool_name]
        observation = _run_tool(tool)
        observations.append(observation)
        _record_event(
            artifacts,
            state,
            now,
            event_type="pal_agent.tool_observed",
            message=f"{tool_name} returned {observation['status']}.",
            phase="tooling",
            agent="local-allowlist",
            role="verifier",
            extra={"tool": tool_name, "status": observation["status"]},
        )

    observations_payload = {
        "task": task,
        "plan_source": plan["source"],
        "rationale": plan["rationale"],
        "executed_tools": plan["tools"],
        "ignored_tools": plan["ignored_tools"],
        "observations": observations,
    }
    artifacts.write_output("tool-observations.json", _json_dumps(observations_payload))

    state.current_phase = "summary"
    summary_prompt = _render_summary_prompt(
        task,
        observations_payload,
        knowledge_context=knowledge_context,
    )
    artifacts.write_prompt("triage-summary.md", summary_prompt)
    try:
        summary_result = pal_client.query(
            summary_prompt,
            system=PAL_AGENT_SYSTEM_PROMPT,
            temperature=0.2,
        )
        summary_text = summary_result.text.strip() or _fallback_summary(observations_payload)
    except (PALClientError, RuntimeError, OSError) as exc:
        summary_text = _fallback_summary(observations_payload, error=str(exc))
    summary_path = artifacts.write_summary("final-summary.md", summary_text.rstrip() + "\n")
    artifacts.write_handoff("pal-to-operator.md", _render_operator_handoff(summary_text, observations_payload))

    state.status = "complete"
    state.current_phase = "complete"
    state.updated_at = now()
    state.final_summary_path = _relative_path(project_root, summary_path)
    artifacts.write_run_summary_json(
        workflow=PAL_OPS_TRIAGE_WORKFLOW_ID,
        status=state.status,
        tool=list(plan["tools"]),
        action=[],
    )
    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.completed",
        message="PAL ops triage completed.",
        phase="complete",
        agent="pal",
        extra={"summary_path": state.final_summary_path},
    )
    StateStore(paths).save(state)

    return {
        "run_id": run_id,
        "status": state.status,
        "summary_path": state.final_summary_path,
        "executed_tools": list(plan["tools"]),
        "ignored_tools": list(plan["ignored_tools"]),
        "plan_source": plan["source"],
        "tool_count": len(plan["tools"]),
    }


def run_pal_ops_actions(
    project_root: Path,
    *,
    task: str = DEFAULT_ACTION_TASK,
    approved_actions: tuple[str, ...] = (),
    client: PALAgentClient | None = None,
    tool_registry: dict[str, PALOpsTool] | None = None,
    action_registry: dict[str, PALOpsAction] | None = None,
    default_tools: tuple[str, ...] = DEFAULT_TOOL_ORDER,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_config(project_root)
    paths = ProjectPaths(project_root=project_root, config=config)
    pal_client = client or PALRouterClient.from_config(config)
    tools = tool_registry or build_default_tool_registry(project_root, pal_client)
    actions = action_registry or build_default_action_registry(project_root, pal_client)
    approved = tuple(dict.fromkeys(str(action_id) for action_id in approved_actions))

    created_at = now()
    run_id = _build_run_id(created_at, "pal-ops-actions")
    artifacts = ArtifactManager(paths, run_id)
    artifacts.create_run_layout()
    artifacts.write_task(task)

    state = RunState(
        run_id=run_id,
        title="PAL Ops Actions",
        status="running",
        current_phase="context",
        created_at=created_at,
        updated_at=created_at,
        task_text=task,
        lead_agent="pal",
        verifier_agent="local-approval-gate",
        route_decision={
            "task_type": "pal_ops_actions",
            "lead_agent": "pal",
            "verifier_agent": "local-approval-gate",
            "reason": "PAL proposes fixed actions; PromptClaw executes only allow-listed actions with explicit approval.",
        },
    )

    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.actions_started",
        message="PAL ops action run started.",
        phase="context",
        agent="pal",
    )

    context_tools = [name for name in default_tools if name in tools]
    observations: list[dict[str, Any]] = []
    for tool_name in context_tools:
        observation = _run_tool(tools[tool_name])
        observations.append(observation)
        _record_event(
            artifacts,
            state,
            now,
            event_type="pal_agent.action_context_observed",
            message=f"{tool_name} returned {observation['status']}.",
            phase="context",
            agent="local-allowlist",
            role="verifier",
            extra={"tool": tool_name, "status": observation["status"]},
        )

    context_payload = {
        "task": task,
        "context_tools": context_tools,
        "observations": observations,
    }
    artifacts.write_output("action-context.json", _json_dumps(context_payload))

    state.current_phase = "planning"
    knowledge_context = _build_knowledge_context(project_root, task)
    plan_prompt = _render_action_plan_prompt(
        task,
        context_payload,
        actions,
        knowledge_context=knowledge_context,
    )
    plan_prompt_path = artifacts.write_prompt("action-plan.md", plan_prompt)
    plan_result = pal_client.query(
        plan_prompt,
        system=PAL_AGENT_SYSTEM_PROMPT,
        temperature=0.1,
    )
    artifacts.write_output("action-plan.raw.txt", plan_result.text)
    plan = _parse_action_plan(plan_result.text, actions=actions)
    plan_output_path = artifacts.write_output("action-plan.json", _json_dumps(plan))
    artifacts.write_route_json({
        "lead_agent": "pal",
        "verifier_agent": "local-approval-gate",
        "task_type": "pal_ops_actions",
        "plan_source": plan["source"],
        "actions": plan["actions"],
        "ignored_actions": plan["ignored_actions"],
        "approved_actions": list(approved),
        "prompt_path": _relative_path(project_root, plan_prompt_path),
        "output_path": _relative_path(project_root, plan_output_path),
    })
    artifacts.write_route_markdown(_render_action_route_markdown(plan, approved))
    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.actions_selected",
        message=f"PAL proposed {len(plan['actions'])} bounded actions.",
        phase="planning",
        agent="pal",
        extra={"actions": plan["actions"], "ignored_actions": plan["ignored_actions"], "source": plan["source"]},
    )

    state.current_phase = "approval"
    approved_set = set(approved)
    proposed_set = set(plan["actions"])
    ignored_approvals = [action_id for action_id in approved if action_id not in actions or action_id not in proposed_set]
    action_rows: list[dict[str, Any]] = []
    executed_actions: list[str] = []
    pending_approval: list[str] = []

    for action_id in plan["actions"]:
        action = actions[action_id]
        if action.approval_required and action_id not in approved_set:
            pending_approval.append(action_id)
            action_rows.append({
                "action": action_id,
                "status": "pending_approval",
                "summary": "Action was proposed by PAL but was not approved for execution.",
                "approval_required": action.approval_required,
                "mutating": action.mutating,
            })
            continue
        result = _run_action(action)
        executed_actions.append(action_id)
        action_rows.append(result)
        _record_event(
            artifacts,
            state,
            now,
            event_type="pal_agent.action_executed",
            message=f"{action_id} returned {result['status']}.",
            phase="approval",
            agent="local-approval-gate",
            role="verifier",
            extra={"action": action_id, "status": result["status"], "mutating": action.mutating},
        )

    action_payload = {
        "task": task,
        "plan_source": plan["source"],
        "rationale": plan["rationale"],
        "proposed_actions": plan["actions"],
        "ignored_actions": plan["ignored_actions"],
        "approved_actions": list(approved),
        "ignored_approvals": ignored_approvals,
        "executed_actions": executed_actions,
        "pending_approval": pending_approval,
        "context": context_payload,
        "actions": action_rows,
    }
    artifacts.write_output("action-results.json", _json_dumps(action_payload))

    state.current_phase = "summary"
    summary_prompt = _render_action_summary_prompt(
        task,
        action_payload,
        knowledge_context=knowledge_context,
    )
    artifacts.write_prompt("action-summary.md", summary_prompt)
    try:
        summary_result = pal_client.query(
            summary_prompt,
            system=PAL_AGENT_SYSTEM_PROMPT,
            temperature=0.2,
        )
        summary_text = summary_result.text.strip() or _fallback_action_summary(action_payload)
    except (PALClientError, RuntimeError, OSError) as exc:
        summary_text = _fallback_action_summary(action_payload, error=str(exc))
    summary_path = artifacts.write_summary("final-summary.md", summary_text.rstrip() + "\n")
    artifacts.write_handoff("pal-action-request.md", _render_action_handoff(summary_text, action_payload))

    state.status = "complete"
    state.current_phase = "complete"
    state.updated_at = now()
    state.final_summary_path = _relative_path(project_root, summary_path)
    artifacts.write_run_summary_json(
        workflow=PAL_OPS_ACTIONS_WORKFLOW_ID,
        status=state.status,
        tool=list(context_tools),
        action=list(executed_actions),
    )
    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.actions_completed",
        message="PAL ops action run completed.",
        phase="complete",
        agent="pal",
        extra={"summary_path": state.final_summary_path},
    )
    StateStore(paths).save(state)

    return {
        "run_id": run_id,
        "status": state.status,
        "summary_path": state.final_summary_path,
        "proposed_actions": list(plan["actions"]),
        "executed_actions": executed_actions,
        "pending_approval": pending_approval,
        "ignored_actions": list(plan["ignored_actions"]),
        "ignored_approvals": ignored_approvals,
        "plan_source": plan["source"],
        "action_count": len(plan["actions"]),
    }


def run_pal_slow_inference_context(
    project_root: Path,
    *,
    task: str = DEFAULT_SLOW_INFERENCE_TASK,
    client: PALAgentClient | None = None,
    tool_registry: dict[str, PALOpsTool] | None = None,
    default_tools: tuple[str, ...] = DEFAULT_SLOW_INFERENCE_CONTEXT_TOOL_ORDER,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_config(project_root)
    paths = ProjectPaths(project_root=project_root, config=config)
    pal_client = client or PALRouterClient.from_config(config)
    tools = tool_registry or build_slow_inference_context_tool_registry(project_root, pal_client)

    created_at = now()
    run_id = _build_run_id(created_at, "pal-slow-inference-context")
    artifacts = ArtifactManager(paths, run_id)
    artifacts.create_run_layout()
    artifacts.write_task(task)

    state = RunState(
        run_id=run_id,
        title="PAL Slow Inference Context",
        status="running",
        current_phase="context",
        created_at=created_at,
        updated_at=created_at,
        task_text=task,
        lead_agent="local-allowlist",
        verifier_agent="local-allowlist",
        route_decision={
            "task_type": SLOW_INFERENCE_WORKFLOW_ID,
            "workflow_id": SLOW_INFERENCE_WORKFLOW_ID,
            "lead_agent": "local-allowlist",
            "verifier_agent": "local-allowlist",
            "reason": "PromptClaw collects fixed read-only slow-inference diagnostics.",
        },
    )

    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.slow_inference_context_started",
        message="PAL slow-inference context collection started.",
        phase="context",
        agent="local-allowlist",
        role="verifier",
    )

    context_tools = [name for name in default_tools if name in tools]
    observations: list[dict[str, Any]] = []
    for tool_name in context_tools:
        observation = _run_tool(tools[tool_name])
        observations.append(observation)
        _record_event(
            artifacts,
            state,
            now,
            event_type="pal_agent.slow_inference_context_observed",
            message=f"{tool_name} returned {observation['status']}.",
            phase="context",
            agent="local-allowlist",
            role="verifier",
            extra={"tool": tool_name, "status": observation["status"]},
        )

    baseline_tokens_per_second = _baseline_tokens_per_second_from_observations(observations)
    context_payload = {
        "workflow_id": SLOW_INFERENCE_WORKFLOW_ID,
        "task": task,
        "executed_tools": context_tools,
        "baseline_tokens_per_second": baseline_tokens_per_second,
        "observations": observations,
    }
    context_path = artifacts.write_output("slow-inference-context.json", _json_dumps(context_payload))
    artifacts.write_route_json({
        "lead_agent": "local-allowlist",
        "verifier_agent": "local-allowlist",
        "task_type": SLOW_INFERENCE_WORKFLOW_ID,
        "workflow_id": SLOW_INFERENCE_WORKFLOW_ID,
        "tools": context_tools,
        "output_path": _relative_path(project_root, context_path),
    })
    artifacts.write_route_markdown(_render_slow_inference_route_markdown(context_tools))

    state.current_phase = "summary"
    summary_text = _render_slow_inference_context_summary(context_payload)
    summary_path = artifacts.write_summary("final-summary.md", summary_text)
    artifacts.write_handoff(
        "slow-inference-context.md",
        _render_slow_inference_context_handoff(context_payload),
    )

    state.status = "complete"
    state.current_phase = "complete"
    state.updated_at = now()
    state.final_summary_path = _relative_path(project_root, summary_path)
    artifacts.write_run_summary_json(
        workflow=SLOW_INFERENCE_WORKFLOW_ID,
        status=state.status,
        tool=list(context_tools),
        action=[],
    )
    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.slow_inference_context_completed",
        message="PAL slow-inference context collection completed.",
        phase="complete",
        agent="local-allowlist",
        role="verifier",
        extra={"summary_path": state.final_summary_path},
    )
    StateStore(paths).save(state)

    return {
        "run_id": run_id,
        "workflow_id": SLOW_INFERENCE_WORKFLOW_ID,
        "status": state.status,
        "summary_path": state.final_summary_path,
        "executed_tools": context_tools,
        "tool_count": len(context_tools),
        "baseline_tokens_per_second": baseline_tokens_per_second,
    }


def run_pal_slow_inference_diagnosis(
    project_root: Path,
    *,
    task: str = DEFAULT_SLOW_INFERENCE_DIAGNOSIS_TASK,
    client: PALAgentClient | None = None,
    tool_registry: dict[str, PALOpsTool] | None = None,
    default_tools: tuple[str, ...] = DEFAULT_SLOW_INFERENCE_DIAGNOSIS_TOOL_ORDER,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_config(project_root)
    paths = ProjectPaths(project_root=project_root, config=config)
    pal_client = client or PALRouterClient.from_config(config)
    tools = tool_registry or build_slow_inference_context_tool_registry(project_root, pal_client)

    created_at = now()
    run_id = _build_run_id(created_at, "pal-slow-inference-diagnosis")
    artifacts = ArtifactManager(paths, run_id)
    artifacts.create_run_layout()
    artifacts.write_task(task)

    state = RunState(
        run_id=run_id,
        title="PAL Slow Inference Diagnosis",
        status="running",
        current_phase="diagnosis",
        created_at=created_at,
        updated_at=created_at,
        task_text=task,
        lead_agent="local-allowlist",
        verifier_agent="local-allowlist",
        route_decision={
            "task_type": SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID,
            "workflow_id": SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID,
            "lead_agent": "local-allowlist",
            "verifier_agent": "local-allowlist",
            "reason": "PromptClaw derives a deterministic diagnosis from fixed read-only diagnostics.",
            "mutating_actions": [],
        },
    )

    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.slow_inference_diagnosis_started",
        message="PAL slow-inference diagnosis started.",
        phase="diagnosis",
        agent="local-allowlist",
        role="verifier",
    )

    context_tools = [name for name in default_tools if name in tools]
    observations: list[dict[str, Any]] = []
    for tool_name in context_tools:
        observation = _run_tool(tools[tool_name])
        observations.append(observation)
        _record_event(
            artifacts,
            state,
            now,
            event_type="pal_agent.slow_inference_diagnosis_observed",
            message=f"{tool_name} returned {observation['status']}.",
            phase="diagnosis",
            agent="local-allowlist",
            role="verifier",
            extra={"tool": tool_name, "status": observation["status"]},
        )

    diagnosis = _diagnose_slow_inference_observations(observations)
    payload = {
        "workflow_id": SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID,
        "task": task,
        "executed_tools": context_tools,
        "mutating_actions": [],
        "observations": observations,
        "diagnosis": diagnosis,
    }
    diagnosis_path = artifacts.write_output("slow-inference-diagnosis.json", _json_dumps(payload))
    artifacts.write_route_json({
        "lead_agent": "local-allowlist",
        "verifier_agent": "local-allowlist",
        "task_type": SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID,
        "workflow_id": SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID,
        "tools": context_tools,
        "mutating_actions": [],
        "output_path": _relative_path(project_root, diagnosis_path),
    })
    artifacts.write_route_markdown(_render_slow_inference_diagnosis_route_markdown(context_tools))

    state.current_phase = "summary"
    summary_text = _render_slow_inference_diagnosis_summary(payload)
    summary_path = artifacts.write_summary("final-summary.md", summary_text)
    artifacts.write_handoff(
        "slow-inference-diagnosis.md",
        _render_slow_inference_diagnosis_handoff(payload),
    )

    state.status = "complete"
    state.current_phase = "complete"
    state.updated_at = now()
    state.final_summary_path = _relative_path(project_root, summary_path)
    artifacts.write_run_summary_json(
        workflow=SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID,
        status=state.status,
        tool=list(context_tools),
        action=[],
    )
    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.slow_inference_diagnosis_completed",
        message="PAL slow-inference diagnosis completed.",
        phase="complete",
        agent="local-allowlist",
        role="verifier",
        extra={"summary_path": state.final_summary_path},
    )
    StateStore(paths).save(state)

    return {
        "run_id": run_id,
        "workflow_id": SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID,
        "status": state.status,
        "summary_path": state.final_summary_path,
        "diagnosis_path": _relative_path(project_root, diagnosis_path),
        "executed_tools": context_tools,
        "tool_count": len(context_tools),
        "severity": diagnosis["severity"],
        "finding_count": len(diagnosis["findings"]),
        "mutating_actions": [],
    }


def run_pal_restart_validation(
    project_root: Path,
    *,
    task: str = DEFAULT_RESTART_VALIDATION_TASK,
    client: PALAgentClient | None = None,
    tool_registry: dict[str, PALOpsTool] | None = None,
    default_tools: tuple[str, ...] = DEFAULT_RESTART_VALIDATION_TOOL_ORDER,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_config(project_root)
    paths = ProjectPaths(project_root=project_root, config=config)
    pal_client = client or PALRouterClient.from_config(config)
    tools = tool_registry or build_restart_validation_tool_registry(project_root, pal_client)

    created_at = now()
    run_id = _build_run_id(created_at, "pal-restart-validation")
    artifacts = ArtifactManager(paths, run_id)
    artifacts.create_run_layout()
    artifacts.write_task(task)

    state = RunState(
        run_id=run_id,
        title="PAL Restart Validation",
        status="running",
        current_phase="validation",
        created_at=created_at,
        updated_at=created_at,
        task_text=task,
        lead_agent="local-allowlist",
        verifier_agent="local-allowlist",
        route_decision={
            "task_type": RESTART_VALIDATION_WORKFLOW_ID,
            "workflow_id": RESTART_VALIDATION_WORKFLOW_ID,
            "lead_agent": "local-allowlist",
            "verifier_agent": "local-allowlist",
            "reason": "PromptClaw validates restart health through fixed read-only diagnostics.",
            "mutating_actions": [],
        },
    )

    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.restart_validation_started",
        message="PAL restart validation started.",
        phase="validation",
        agent="local-allowlist",
        role="verifier",
    )

    validation_tools = [name for name in default_tools if name in tools]
    observations: list[dict[str, Any]] = []
    for tool_name in validation_tools:
        observation = _run_tool(tools[tool_name])
        observations.append(observation)
        _record_event(
            artifacts,
            state,
            now,
            event_type="pal_agent.restart_validation_observed",
            message=f"{tool_name} returned {observation['status']}.",
            phase="validation",
            agent="local-allowlist",
            role="verifier",
            extra={"tool": tool_name, "status": observation["status"]},
        )

    validation_status = _restart_validation_status_from_observations(observations)
    payload = {
        "workflow_id": RESTART_VALIDATION_WORKFLOW_ID,
        "task": task,
        "executed_tools": validation_tools,
        "mutating_actions": [],
        "validation_status": validation_status,
        "observations": observations,
    }
    validation_path = artifacts.write_output("restart-validation.json", _json_dumps(payload))
    artifacts.write_route_json({
        "lead_agent": "local-allowlist",
        "verifier_agent": "local-allowlist",
        "task_type": RESTART_VALIDATION_WORKFLOW_ID,
        "workflow_id": RESTART_VALIDATION_WORKFLOW_ID,
        "tools": validation_tools,
        "mutating_actions": [],
        "output_path": _relative_path(project_root, validation_path),
    })
    artifacts.write_route_markdown(_render_restart_validation_route_markdown(validation_tools))

    state.current_phase = "summary"
    summary_text = _render_restart_validation_summary(payload)
    summary_path = artifacts.write_summary("final-summary.md", summary_text)
    artifacts.write_handoff(
        "restart-validation.md",
        _render_restart_validation_handoff(payload),
    )

    state.status = "complete"
    state.current_phase = "complete"
    state.updated_at = now()
    state.final_summary_path = _relative_path(project_root, summary_path)
    artifacts.write_run_summary_json(
        workflow=RESTART_VALIDATION_WORKFLOW_ID,
        status=state.status,
        tool=list(validation_tools),
        action=[],
    )
    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.restart_validation_completed",
        message="PAL restart validation completed.",
        phase="complete",
        agent="local-allowlist",
        role="verifier",
        extra={
            "summary_path": state.final_summary_path,
            "validation_status": validation_status,
        },
    )
    StateStore(paths).save(state)

    return {
        "run_id": run_id,
        "workflow_id": RESTART_VALIDATION_WORKFLOW_ID,
        "status": state.status,
        "validation_status": validation_status,
        "summary_path": state.final_summary_path,
        "validation_path": _relative_path(project_root, validation_path),
        "executed_tools": validation_tools,
        "tool_count": len(validation_tools),
        "mutating_actions": [],
    }


def run_pal_shutdown_audit(
    project_root: Path,
    *,
    task: str = DEFAULT_SHUTDOWN_AUDIT_TASK,
    client: PALAgentClient | None = None,
    tool_registry: dict[str, PALOpsTool] | None = None,
    default_tools: tuple[str, ...] = DEFAULT_SHUTDOWN_AUDIT_TOOL_ORDER,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_config(project_root)
    paths = ProjectPaths(project_root=project_root, config=config)
    tools = tool_registry or build_shutdown_audit_tool_registry()

    created_at = now()
    run_id = _build_run_id(created_at, "pal-shutdown-audit")
    artifacts = ArtifactManager(paths, run_id)
    artifacts.create_run_layout()
    artifacts.write_task(task)

    state = RunState(
        run_id=run_id,
        title="PAL Shutdown Audit",
        status="running",
        current_phase="audit",
        created_at=created_at,
        updated_at=created_at,
        task_text=task,
        lead_agent="local-allowlist",
        verifier_agent="local-allowlist",
        route_decision={
            "task_type": SHUTDOWN_AUDIT_WORKFLOW_ID,
            "workflow_id": SHUTDOWN_AUDIT_WORKFLOW_ID,
            "lead_agent": "local-allowlist",
            "verifier_agent": "local-allowlist",
            "reason": "PromptClaw audits shutdown state through fixed read-only diagnostics.",
            "mutating_actions": [],
        },
    )

    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.shutdown_audit_started",
        message="PAL shutdown audit started.",
        phase="audit",
        agent="local-allowlist",
        role="verifier",
    )

    audit_tools = [name for name in default_tools if name in tools]
    observations: list[dict[str, Any]] = []
    for tool_name in audit_tools:
        observation = _run_tool(tools[tool_name])
        observations.append(observation)
        _record_event(
            artifacts,
            state,
            now,
            event_type="pal_agent.shutdown_audit_observed",
            message=f"{tool_name} returned {observation['status']}.",
            phase="audit",
            agent="local-allowlist",
            role="verifier",
            extra={"tool": tool_name, "status": observation["status"]},
        )

    audit = _shutdown_audit_from_observations(observations)
    payload = {
        "workflow_id": SHUTDOWN_AUDIT_WORKFLOW_ID,
        "task": task,
        "executed_tools": audit_tools,
        "mutating_actions": [],
        "audit_status": audit["audit_status"],
        "shutdown_enabled_state": audit["shutdown_enabled_state"],
        "override_state": audit["override_state"],
        "next_shutdown_window": audit["next_shutdown_window"],
        "audit": audit,
        "observations": observations,
    }
    audit_path = artifacts.write_output("shutdown-audit.json", _json_dumps(payload))
    artifacts.write_route_json({
        "lead_agent": "local-allowlist",
        "verifier_agent": "local-allowlist",
        "task_type": SHUTDOWN_AUDIT_WORKFLOW_ID,
        "workflow_id": SHUTDOWN_AUDIT_WORKFLOW_ID,
        "tools": audit_tools,
        "mutating_actions": [],
        "audit_status": audit["audit_status"],
        "shutdown_enabled_state": audit["shutdown_enabled_state"],
        "override_state": audit["override_state"],
        "next_shutdown_window": audit["next_shutdown_window"],
        "output_path": _relative_path(project_root, audit_path),
    })
    artifacts.write_route_markdown(_render_shutdown_audit_route_markdown(audit_tools))

    state.current_phase = "summary"
    summary_text = _render_shutdown_audit_summary(payload)
    summary_path = artifacts.write_summary("final-summary.md", summary_text)
    artifacts.write_handoff(
        "shutdown-audit.md",
        _render_shutdown_audit_handoff(payload),
    )

    state.status = "complete"
    state.current_phase = "complete"
    state.updated_at = now()
    state.final_summary_path = _relative_path(project_root, summary_path)
    artifacts.write_run_summary_json(
        workflow=SHUTDOWN_AUDIT_WORKFLOW_ID,
        status=state.status,
        tool=list(audit_tools),
        action=[],
    )
    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.shutdown_audit_completed",
        message="PAL shutdown audit completed.",
        phase="complete",
        agent="local-allowlist",
        role="verifier",
        extra={
            "summary_path": state.final_summary_path,
            "audit_status": audit["audit_status"],
            "shutdown_enabled_state": audit["shutdown_enabled_state"],
            "override_state": audit["override_state"],
            "next_shutdown_window": audit["next_shutdown_window"],
        },
    )
    StateStore(paths).save(state)

    return {
        "run_id": run_id,
        "workflow_id": SHUTDOWN_AUDIT_WORKFLOW_ID,
        "status": state.status,
        "audit_status": audit["audit_status"],
        "shutdown_enabled_state": audit["shutdown_enabled_state"],
        "override_state": audit["override_state"],
        "next_shutdown_window": audit["next_shutdown_window"],
        "summary_path": state.final_summary_path,
        "audit_path": _relative_path(project_root, audit_path),
        "executed_tools": audit_tools,
        "tool_count": len(audit_tools),
        "mutating_actions": [],
    }


def run_pal_phase2_readiness_report(
    project_root: Path,
    *,
    task: str = DEFAULT_PHASE2_READINESS_TASK,
    client: PALAgentClient | None = None,
    tool_registry: dict[str, PALOpsTool] | None = None,
    default_tools: tuple[str, ...] = DEFAULT_PHASE2_READINESS_TOOL_ORDER,
    now: Callable[[], str] = utc_now,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_config(project_root)
    paths = ProjectPaths(project_root=project_root, config=config)
    pal_client = client or PALRouterClient.from_config(config)
    tools = tool_registry or build_phase2_readiness_tool_registry(project_root, pal_client)

    created_at = now()
    run_id = _build_run_id(created_at, "pal-phase2-readiness")
    artifacts = ArtifactManager(paths, run_id)
    artifacts.create_run_layout()
    artifacts.write_task(task)

    state = RunState(
        run_id=run_id,
        title="PAL Phase 2 Readiness",
        status="running",
        current_phase="readiness",
        created_at=created_at,
        updated_at=created_at,
        task_text=task,
        lead_agent="local-allowlist",
        verifier_agent="local-allowlist",
        route_decision={
            "task_type": PHASE2_READINESS_WORKFLOW_ID,
            "workflow_id": PHASE2_READINESS_WORKFLOW_ID,
            "lead_agent": "local-allowlist",
            "verifier_agent": "local-allowlist",
            "reason": "PromptClaw scores Phase 2 prerequisites through fixed read-only diagnostics.",
            "mutating_actions": [],
            "phase2_execution_actions": [],
        },
    )

    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.phase2_readiness_started",
        message="PAL Phase 2 readiness report started.",
        phase="readiness",
        agent="local-allowlist",
        role="verifier",
    )

    readiness_tools = [name for name in default_tools if name in tools]
    observations: list[dict[str, Any]] = []
    for tool_name in readiness_tools:
        observation = _run_tool(tools[tool_name])
        observations.append(observation)
        _record_event(
            artifacts,
            state,
            now,
            event_type="pal_agent.phase2_readiness_observed",
            message=f"{tool_name} returned {observation['status']}.",
            phase="readiness",
            agent="local-allowlist",
            role="verifier",
            extra={"tool": tool_name, "status": observation["status"]},
        )

    readiness = _phase2_readiness_from_observations(observations)
    payload = {
        "workflow_id": PHASE2_READINESS_WORKFLOW_ID,
        "task": task,
        "executed_tools": readiness_tools,
        "mutating_actions": [],
        "phase2_execution_actions": [],
        "blocked_phase2_actions": list(PHASE2_BLOCKED_EXECUTION_ACTIONS),
        "readiness_status": readiness["readiness_status"],
        "overall_score": readiness["overall_score"],
        "prerequisites": readiness["prerequisites"],
        "observations": observations,
    }
    readiness_path = artifacts.write_output("phase2-readiness.json", _json_dumps(payload))
    artifacts.write_route_json({
        "lead_agent": "local-allowlist",
        "verifier_agent": "local-allowlist",
        "task_type": PHASE2_READINESS_WORKFLOW_ID,
        "workflow_id": PHASE2_READINESS_WORKFLOW_ID,
        "tools": readiness_tools,
        "mutating_actions": [],
        "phase2_execution_actions": [],
        "blocked_phase2_actions": list(PHASE2_BLOCKED_EXECUTION_ACTIONS),
        "readiness_status": readiness["readiness_status"],
        "overall_score": readiness["overall_score"],
        "output_path": _relative_path(project_root, readiness_path),
    })
    artifacts.write_route_markdown(_render_phase2_readiness_route_markdown(readiness_tools))

    state.current_phase = "summary"
    summary_text = _render_phase2_readiness_summary(payload)
    summary_path = artifacts.write_summary("final-summary.md", summary_text)
    artifacts.write_handoff(
        "phase2-readiness.md",
        _render_phase2_readiness_handoff(payload),
    )

    state.status = "complete"
    state.current_phase = "complete"
    state.updated_at = now()
    state.final_summary_path = _relative_path(project_root, summary_path)
    artifacts.write_run_summary_json(
        workflow=PHASE2_READINESS_WORKFLOW_ID,
        status=state.status,
        tool=list(readiness_tools),
        action=[],
    )
    _record_event(
        artifacts,
        state,
        now,
        event_type="pal_agent.phase2_readiness_completed",
        message="PAL Phase 2 readiness report completed.",
        phase="complete",
        agent="local-allowlist",
        role="verifier",
        extra={
            "summary_path": state.final_summary_path,
            "readiness_status": readiness["readiness_status"],
            "overall_score": readiness["overall_score"],
        },
    )
    StateStore(paths).save(state)

    return {
        "run_id": run_id,
        "workflow_id": PHASE2_READINESS_WORKFLOW_ID,
        "status": state.status,
        "readiness_status": readiness["readiness_status"],
        "overall_score": readiness["overall_score"],
        "summary_path": state.final_summary_path,
        "readiness_path": _relative_path(project_root, readiness_path),
        "executed_tools": readiness_tools,
        "tool_count": len(readiness_tools),
        "prerequisite_count": len(readiness["prerequisites"]),
        "mutating_actions": [],
        "phase2_execution_actions": [],
    }


def build_default_tool_registry(project_root: Path, client: PALAgentClient) -> dict[str, PALOpsTool]:
    return {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Call the configured PAL router /health endpoint.",
            run=lambda: _pal_health_tool(client),
        ),
        "pal_smoke_baseline": PALOpsTool(
            name="pal_smoke_baseline",
            description="Summarize saved PAL smoke reports under .promptclaw/pal-smoke.",
            run=lambda: _pal_smoke_baseline_tool(project_root),
        ),
        "tailscale_status": PALOpsTool(
            name="tailscale_status",
            description="Run a fixed local Tailscale status check and look for pal-cloud-a6000.",
            run=_tailscale_status_tool,
        ),
        "ssh_process_check": PALOpsTool(
            name="ssh_process_check",
            description="If PAL_SSH_* env vars are configured, run a fixed read-only remote process/log check.",
            run=_ssh_process_check_tool,
        ),
    }


def build_restart_validation_tool_registry(
    project_root: Path,
    client: PALAgentClient,
) -> dict[str, PALOpsTool]:
    return {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Call the configured PAL router /health endpoint.",
            run=lambda: _pal_health_tool(client),
        ),
        "pal_direct_query": PALOpsTool(
            name="pal_direct_query",
            description="Send one fixed restart-validation prompt to the configured PAL router.",
            run=lambda: _pal_direct_query_tool(client),
        ),
        "pal_smoke": PALOpsTool(
            name="pal_smoke",
            description="Run the active PAL smoke suite and save a fresh smoke report.",
            run=lambda: _pal_smoke_run_tool(project_root, client),
        ),
        "tailscale_status": PALOpsTool(
            name="tailscale_status",
            description="Run a fixed local Tailscale status check and look for pal-cloud-a6000.",
            run=_tailscale_status_tool,
        ),
        "ssh_process_check": PALOpsTool(
            name="ssh_process_check",
            description="If PAL_SSH_* env vars are configured, run a fixed read-only remote process/log check.",
            run=_ssh_process_check_tool,
        ),
    }


def build_shutdown_audit_tool_registry() -> dict[str, PALOpsTool]:
    return {
        "shutdown_remote_audit": PALOpsTool(
            name="shutdown_remote_audit",
            description=(
                "Read PAL shutdown config, cron entry, override flag state, "
                "current local shutdown time, and recent shutdown logs over SSH."
            ),
            run=_shutdown_remote_audit_tool,
        ),
    }


def build_phase2_readiness_tool_registry(
    project_root: Path,
    client: PALAgentClient,
) -> dict[str, PALOpsTool]:
    return {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Call the configured PAL router /health endpoint.",
            run=lambda: _pal_health_tool(client),
        ),
        "pal_smoke_baseline": PALOpsTool(
            name="pal_smoke_baseline",
            description="Summarize saved PAL smoke reports and baseline token throughput.",
            run=lambda: _pal_smoke_baseline_tool(project_root),
        ),
        "shutdown_remote_audit": PALOpsTool(
            name="shutdown_remote_audit",
            description=(
                "Read PAL shutdown config, cron entry, override flag state, "
                "current local shutdown time, and recent shutdown logs over SSH."
            ),
            run=_shutdown_remote_audit_tool,
        ),
        "phase2_project_state": PALOpsTool(
            name="phase2_project_state",
            description="Inspect local PAL runbook and session-state readiness evidence.",
            run=lambda: _phase2_project_state_tool(project_root),
        ),
        "vast_boundary": PALOpsTool(
            name="vast_boundary",
            description="Inspect the local Vast connector lifecycle boundary.",
            run=_vast_boundary_tool,
        ),
    }


def build_slow_inference_context_tool_registry(
    project_root: Path,
    client: PALAgentClient,
) -> dict[str, PALOpsTool]:
    return {
        "pal_health": PALOpsTool(
            name="pal_health",
            description="Call the configured PAL router /health endpoint.",
            run=lambda: _pal_health_tool(client),
        ),
        "pal_smoke_baseline": PALOpsTool(
            name="pal_smoke_baseline",
            description="Summarize saved PAL smoke reports and baseline token throughput.",
            run=lambda: _pal_smoke_baseline_tool(project_root),
        ),
        "gpu_hints": PALOpsTool(
            name="gpu_hints",
            description="Collect fixed read-only GPU utilization and process hints over configured SSH.",
            run=_gpu_hints_tool,
        ),
        "slow_inference_logs": PALOpsTool(
            name="slow_inference_logs",
            description="Collect fixed read-only PAL router/Ollama log tails over configured SSH.",
            run=_slow_inference_logs_tool,
        ),
    }


def build_default_action_registry(project_root: Path, client: PALAgentClient) -> dict[str, PALOpsAction]:
    return {
        "rerun_smoke": PALOpsAction(
            name="rerun_smoke",
            description="Run the PAL smoke suite again and save a fresh local smoke report.",
            approval_required=True,
            mutating=False,
            run=lambda: _rerun_smoke_action(project_root, client),
        ),
        "inspect_logs_deep": PALOpsAction(
            name="inspect_logs_deep",
            description="Run a fixed read-only SSH command for deeper PAL service logs and resource hints.",
            approval_required=True,
            mutating=False,
            run=_inspect_logs_deep_action,
        ),
        "restart_router": PALOpsAction(
            name="restart_router",
            description="Restart only the PAL FastAPI router container/service on the cloud instance.",
            approval_required=True,
            mutating=True,
            run=_restart_router_action,
        ),
        "pause_shutdown_once": PALOpsAction(
            name="pause_shutdown_once",
            description="Create /opt/pal/config/override.flag so the scheduled shutdown is skipped.",
            approval_required=True,
            mutating=True,
            run=_pause_shutdown_once_action,
        ),
        "resume_shutdown": PALOpsAction(
            name="resume_shutdown",
            description="Remove /opt/pal/config/override.flag so scheduled shutdown resumes.",
            approval_required=True,
            mutating=True,
            run=_resume_shutdown_action,
        ),
    }


def export_pal_action_metadata(
    project_root: Path | None = None,
    client: PALAgentClient | None = None,
) -> list[dict[str, Any]]:
    """Return JSON-serializable metadata for every default PAL action.

    The action runners are never invoked here, so a stub project_root and
    client are sufficient when callers only need the allow-list surface.
    """
    actions = build_default_action_registry(
        project_root or Path(),
        client,  # type: ignore[arg-type]
    )
    return [
        {
            "id": action_id,
            "name": action.name,
            "description": action.description,
            "approval_required": action.approval_required,
            "mutating": action.mutating,
        }
        for action_id, action in actions.items()
    ]


def _run_tool(tool: PALOpsTool) -> dict[str, Any]:
    try:
        result = tool.run()
    except Exception as exc:
        return {
            "tool": tool.name,
            "status": "error",
            "summary": f"{tool.name} raised {type(exc).__name__}: {exc}",
        }
    if not isinstance(result, dict):
        return {
            "tool": tool.name,
            "status": "error",
            "summary": f"{tool.name} returned non-object result",
            "raw": repr(result),
        }
    payload = dict(result)
    payload.setdefault("tool", tool.name)
    payload.setdefault("status", "ok")
    payload.setdefault("summary", "")
    return payload


def _run_action(action: PALOpsAction) -> dict[str, Any]:
    try:
        result = action.run()
    except Exception as exc:
        return {
            "action": action.name,
            "status": "error",
            "summary": f"{action.name} raised {type(exc).__name__}: {exc}",
            "approval_required": action.approval_required,
            "mutating": action.mutating,
        }
    if not isinstance(result, dict):
        return {
            "action": action.name,
            "status": "error",
            "summary": f"{action.name} returned non-object result",
            "raw": repr(result),
            "approval_required": action.approval_required,
            "mutating": action.mutating,
        }
    payload = dict(result)
    payload.setdefault("action", action.name)
    payload.setdefault("status", "ok")
    payload.setdefault("summary", "")
    payload.setdefault("approval_required", action.approval_required)
    payload.setdefault("mutating", action.mutating)
    return payload


def _pal_health_tool(client: PALAgentClient) -> dict[str, Any]:
    health = client.health()
    return {
        "status": "ok" if str(health.get("status", "")).lower() == "green" else "warn",
        "summary": f"PAL router status is {health.get('status', 'unknown')}.",
        "health": health,
    }


def _pal_direct_query_tool(client: PALAgentClient) -> dict[str, Any]:
    result = client.query(
        RESTART_VALIDATION_QUERY_PROMPT,
        system=PAL_AGENT_SYSTEM_PROMPT,
        temperature=0.1,
    )
    response = result.text.strip()
    return {
        "status": "ok" if response else "warn",
        "summary": "Direct PAL restart-validation query returned a response."
        if response
        else "Direct PAL restart-validation query returned an empty response.",
        "query": {
            "prompt": RESTART_VALIDATION_QUERY_PROMPT,
            "response": truncate(response, 1200),
            "model": result.raw.get("model", client.default_model),
            "raw": result.raw,
        },
    }


def _pal_smoke_run_tool(project_root: Path, client: PALAgentClient) -> dict[str, Any]:
    report = run_pal_smoke(client)
    report_path = write_smoke_report(project_root, report)
    summary = report.get("summary", {})
    status = "ok" if report.get("status") == "pass" else "warn"
    return {
        "status": status,
        "summary": (
            f"PAL smoke suite {report.get('status', 'unknown')} with "
            f"{summary.get('passed', 0)} passed and {summary.get('failed', 0)} failed checks."
        ),
        "report_path": str(report_path),
        "report": report,
    }


def _pal_smoke_baseline_tool(project_root: Path) -> dict[str, Any]:
    reports = load_smoke_reports(project_root)
    summary = summarize_smoke_reports(reports)
    baseline_tokens_per_second = _baseline_tokens_per_second_from_summary(summary)
    status = "ok"
    if summary["report_count"] == 0:
        status = "skipped"
    elif summary["fail_count"] > 0:
        status = "warn"
    return {
        "status": status,
        "summary": (
            f"Found {summary['report_count']} PAL smoke reports with "
            f"{float(summary['pass_rate']) * 100:.1f}% pass rate."
        ),
        "baseline": summary,
        "baseline_tokens_per_second": baseline_tokens_per_second,
    }


def _baseline_tokens_per_second_from_summary(summary: dict[str, Any]) -> float | None:
    prompts = summary.get("prompts", {})
    if not isinstance(prompts, dict):
        return None
    values: list[float] = []
    for prompt_summary in prompts.values():
        if not isinstance(prompt_summary, dict):
            continue
        value = prompt_summary.get("avg_tokens_per_second")
        if isinstance(value, int | float):
            values.append(float(value))
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _baseline_tokens_per_second_from_observations(
    observations: list[dict[str, Any]],
) -> float | None:
    for observation in observations:
        if observation.get("tool") != "pal_smoke_baseline":
            continue
        value = observation.get("baseline_tokens_per_second")
        if isinstance(value, int | float):
            return float(value)
    return None


def _diagnose_slow_inference_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    rows = {str(row.get("tool", "")): row for row in observations}
    baseline_tps = _baseline_tokens_per_second_from_observations(observations)
    observed_tps = _observed_tokens_per_second_from_logs(rows.get("slow_inference_logs"))
    gpu_utilization = _gpu_utilization_percent_from_observation(rows.get("gpu_hints"))
    router_status = _router_health_status(rows.get("pal_health"))

    findings: list[dict[str, Any]] = []
    if router_status and router_status not in {"green", "ok", "healthy"}:
        findings.append({
            "code": "router_health_not_green",
            "severity": "warning",
            "summary": f"PAL router health is {router_status}.",
        })

    if baseline_tps is None:
        findings.append({
            "code": "baseline_tokens_per_second_unavailable",
            "severity": "info",
            "summary": "No saved PAL smoke token/s baseline is available.",
        })
    elif baseline_tps < 5.0:
        findings.append({
            "code": "low_baseline_tokens_per_second",
            "severity": "critical",
            "summary": f"Saved PAL smoke baseline is low at {baseline_tps:g} tokens/s.",
        })
    elif baseline_tps < 10.0:
        findings.append({
            "code": "low_baseline_tokens_per_second",
            "severity": "warning",
            "summary": f"Saved PAL smoke baseline is below target at {baseline_tps:g} tokens/s.",
        })

    if observed_tps is not None and baseline_tps is not None and observed_tps <= baseline_tps * 0.5:
        findings.append({
            "code": "log_throughput_regression",
            "severity": "critical" if observed_tps < 5.0 else "warning",
            "summary": (
                f"Recent log throughput is {observed_tps:g} tokens/s versus "
                f"{baseline_tps:g} tokens/s baseline."
            ),
        })
    elif observed_tps is None and _observation_status(rows.get("slow_inference_logs")) == "skipped":
        findings.append({
            "code": "remote_logs_unavailable",
            "severity": "info",
            "summary": "PAL SSH logs were unavailable, so live token/s could not be inferred.",
        })

    if gpu_utilization is not None and gpu_utilization >= 90:
        findings.append({
            "code": "gpu_saturation",
            "severity": "critical" if gpu_utilization >= 95 else "warning",
            "summary": f"Read-only GPU hints show {gpu_utilization}% utilization.",
        })
    elif gpu_utilization is None and _observation_status(rows.get("gpu_hints")) == "skipped":
        findings.append({
            "code": "gpu_hints_unavailable",
            "severity": "info",
            "summary": "PAL SSH GPU hints were unavailable.",
        })

    severity = _max_finding_severity(findings)
    return {
        "severity": severity,
        "router_status": router_status,
        "baseline_tokens_per_second": baseline_tps,
        "observed_tokens_per_second": observed_tps,
        "gpu_utilization_percent": gpu_utilization,
        "findings": findings,
        "recommendations": _slow_inference_recommendations(findings),
    }


def _router_health_status(observation: dict[str, Any] | None) -> str:
    if not observation:
        return ""
    health = observation.get("health")
    if not isinstance(health, dict):
        return ""
    return str(health.get("status", "")).lower()


def _observation_status(observation: dict[str, Any] | None) -> str:
    if not observation:
        return ""
    return str(observation.get("status", ""))


def _observed_tokens_per_second_from_logs(observation: dict[str, Any] | None) -> float | None:
    if not observation:
        return None
    command = observation.get("command")
    if not isinstance(command, dict):
        return None
    text = f"{command.get('stdout', '')}\n{command.get('stderr', '')}"
    match = re.search(r"eval_count=(\d+(?:\.\d+)?)\s+eval_duration=(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    eval_count = float(match.group(1))
    eval_duration_ns = float(match.group(2))
    if eval_duration_ns <= 0:
        return None
    return round(eval_count / (eval_duration_ns / 1_000_000_000), 3)


def _gpu_utilization_percent_from_observation(observation: dict[str, Any] | None) -> int | None:
    if not observation:
        return None
    command = observation.get("command")
    if not isinstance(command, dict):
        return None
    stdout = str(command.get("stdout", ""))
    for line in stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            value = float(parts[3])
        except ValueError:
            continue
        if 0.0 <= value <= 100.0:
            return int(round(value))
    return None


def _max_finding_severity(findings: list[dict[str, Any]]) -> str:
    rank = {"ok": 0, "info": 1, "warning": 2, "critical": 3}
    severity = "ok"
    for finding in findings:
        candidate = str(finding.get("severity", "info"))
        if rank.get(candidate, 1) > rank[severity]:
            severity = candidate
    return severity


def _slow_inference_recommendations(findings: list[dict[str, Any]]) -> list[str]:
    codes = {str(finding.get("code", "")) for finding in findings}
    recommendations: list[str] = []
    if "baseline_tokens_per_second_unavailable" in codes:
        recommendations.append("Run `promptclaw pal smoke PROJECT_ROOT` to create a baseline report.")
    if "low_baseline_tokens_per_second" in codes or "log_throughput_regression" in codes:
        recommendations.append(
            "Compare against a fresh smoke run after any approved remediation to confirm token/s recovery."
        )
    if "gpu_saturation" in codes:
        recommendations.append("Review competing GPU processes before approving restart or instance changes.")
    if "router_health_not_green" in codes:
        recommendations.append("Inspect router health details before approving any service action.")
    if "remote_logs_unavailable" in codes or "gpu_hints_unavailable" in codes:
        recommendations.append("Set PAL_SSH_HOST, PAL_SSH_PORT, and PAL_SSH_KEY to include remote evidence.")
    if not recommendations:
        recommendations.append("No slow-inference fault was detected from the available read-only evidence.")
    return recommendations


def _restart_validation_status_from_observations(observations: list[dict[str, Any]]) -> str:
    statuses = {str(observation.get("status", "")) for observation in observations}
    if "error" in statuses:
        return "fail"
    if statuses.intersection({"warn", "skipped"}):
        return "warn"
    return "pass"


def _shutdown_remote_audit_tool() -> dict[str, Any]:
    remote_command = (
        "CONFIG=/opt/pal/config/shutdown.conf; "
        "printf 'CONFIG_PATH=%s\\n' \"$CONFIG\"; "
        "if [ -f \"$CONFIG\" ]; then printf 'CONFIG_PRESENT=true\\n'; "
        "else printf 'CONFIG_PRESENT=false\\n'; fi; "
        "ENABLED=$(test -f \"$CONFIG\" && sed -n 's/^ENABLED=//p' \"$CONFIG\" | tail -n 1); "
        "SHUTDOWN_TIME=$(test -f \"$CONFIG\" && sed -n 's/^SHUTDOWN_TIME=//p' \"$CONFIG\" | tail -n 1); "
        "TIMEZONE=$(test -f \"$CONFIG\" && sed -n 's/^TIMEZONE=//p' \"$CONFIG\" | tail -n 1); "
        "OVERRIDE_FILE=$(test -f \"$CONFIG\" && sed -n 's/^OVERRIDE_FILE=//p' \"$CONFIG\" | tail -n 1); "
        "OVERRIDE_FILE=${OVERRIDE_FILE:-/opt/pal/config/override.flag}; "
        "printf 'ENABLED=%s\\n' \"$ENABLED\"; "
        "printf 'SHUTDOWN_TIME=%s\\n' \"$SHUTDOWN_TIME\"; "
        "printf 'TIMEZONE=%s\\n' \"$TIMEZONE\"; "
        "printf 'OVERRIDE_FILE=%s\\n' \"$OVERRIDE_FILE\"; "
        "if [ -f \"$OVERRIDE_FILE\" ]; then printf 'OVERRIDE_PRESENT=true\\n'; "
        "else printf 'OVERRIDE_PRESENT=false\\n'; fi; "
        "CRON_ENTRY=$(crontab -l 2>/dev/null | grep -F '/opt/pal/scripts/auto_shutdown.sh' | tail -n 1 || true); "
        "printf 'CRON_ENTRY=%s\\n' \"$CRON_ENTRY\"; "
        "CURRENT_LOCAL=$(TZ=\"${TIMEZONE:-America/Los_Angeles}\" date +%Y-%m-%dT%H:%M:%S%z 2>/dev/null || "
        "date +%Y-%m-%dT%H:%M:%S%z); "
        "printf 'CURRENT_LOCAL=%s\\n' \"$CURRENT_LOCAL\"; "
        "printf '%s\\n' '--- shutdown log ---'; "
        "tail -n 40 /opt/pal/logs/shutdown.log 2>/dev/null || true"
    )
    result = _run_ssh_command(remote_command, timeout_s=20)
    audit = _derive_shutdown_audit(result)
    if result.get("skipped"):
        status = "skipped"
    elif result.get("exit_code") == 0 and audit["audit_status"] == "pass":
        status = "ok"
    elif result.get("exit_code") == 0:
        status = "warn"
    else:
        status = "error"
    return {
        "status": status,
        "summary": _shutdown_audit_tool_summary(audit, status),
        "audit": audit,
        "command": result,
    }


def _shutdown_audit_tool_summary(audit: dict[str, Any], status: str) -> str:
    if status == "skipped":
        return "Shutdown audit skipped because PAL SSH diagnostics are unavailable."
    if status == "error":
        return "Shutdown audit remote diagnostic returned a non-zero exit."
    return (
        "Shutdown audit found "
        f"enabled={audit['shutdown_enabled_state']}, "
        f"override={audit['override_state']}, "
        f"next_window={audit['next_shutdown_window']}."
    )


def _derive_shutdown_audit(command_result: dict[str, Any]) -> dict[str, Any]:
    if command_result.get("skipped"):
        audit = _unknown_shutdown_audit()
        audit["audit_status"] = "incomplete"
        return audit

    fields, recent_log_excerpt = _parse_shutdown_audit_stdout(str(command_result.get("stdout", "")))
    config_present = _parse_optional_bool(fields.get("CONFIG_PRESENT"))
    enabled_value = _parse_optional_bool(fields.get("ENABLED"))
    override_present = _parse_optional_bool(fields.get("OVERRIDE_PRESENT"))
    cron_entry = fields.get("CRON_ENTRY", "").strip()
    cron_installed = bool(cron_entry) if command_result.get("exit_code") == 0 else None
    shutdown_time = fields.get("SHUTDOWN_TIME", "").strip()
    timezone = fields.get("TIMEZONE", "").strip()
    next_window = _next_shutdown_window(
        shutdown_time=shutdown_time,
        current_local=fields.get("CURRENT_LOCAL", ""),
        timezone=timezone,
    )
    audit_status = _shutdown_audit_status(
        exit_code=command_result.get("exit_code"),
        enabled=enabled_value,
        override_present=override_present,
        cron_installed=cron_installed,
        next_window=next_window,
    )
    return {
        "audit_status": audit_status,
        "config_path": fields.get("CONFIG_PATH", "/opt/pal/config/shutdown.conf").strip(),
        "config_present": config_present,
        "shutdown_enabled_state": _enabled_state(enabled_value),
        "shutdown_time": shutdown_time,
        "timezone": timezone,
        "override_file": fields.get("OVERRIDE_FILE", "/opt/pal/config/override.flag").strip(),
        "override_state": _override_state(override_present),
        "cron_installed": cron_installed,
        "cron_entry": cron_entry,
        "current_local": fields.get("CURRENT_LOCAL", "").strip(),
        "next_shutdown_window": next_window,
        "recent_log_excerpt": recent_log_excerpt,
    }


def _unknown_shutdown_audit() -> dict[str, Any]:
    return {
        "audit_status": "incomplete",
        "config_path": "/opt/pal/config/shutdown.conf",
        "config_present": None,
        "shutdown_enabled_state": "unknown",
        "shutdown_time": "",
        "timezone": "",
        "override_file": "/opt/pal/config/override.flag",
        "override_state": "unknown",
        "cron_installed": None,
        "cron_entry": "",
        "current_local": "",
        "next_shutdown_window": "unavailable",
        "recent_log_excerpt": "",
    }


def _shutdown_audit_from_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    for observation in observations:
        audit = observation.get("audit")
        if isinstance(audit, dict):
            return dict(audit)
    return _unknown_shutdown_audit()


def _phase2_readiness_from_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    rows = {str(row.get("tool", "")): row for row in observations}
    prerequisites = [
        _phase2_operator_authorization_prerequisite(),
        _phase2_health_baseline_prerequisite(
            rows.get("pal_health"),
            rows.get("pal_smoke_baseline"),
        ),
        _phase2_shutdown_safety_prerequisite(rows.get("shutdown_remote_audit")),
        _phase2_deployment_reproducibility_prerequisite(rows.get("phase2_project_state")),
        _phase2_cost_boundary_prerequisite(rows.get("vast_boundary")),
        _phase2_execution_boundary_prerequisite(),
    ]
    overall_score = round(
        sum(float(row["score"]) for row in prerequisites) / len(prerequisites),
        2,
    )
    return {
        "readiness_status": _phase2_readiness_status(prerequisites),
        "overall_score": overall_score,
        "prerequisites": prerequisites,
    }


def _phase2_operator_authorization_prerequisite() -> dict[str, Any]:
    return {
        "id": "operator_authorization",
        "label": "Explicit operator authorization",
        "score": 0.0,
        "status": "blocked",
        "summary": "Phase 2 requires explicit Anthony authorization outside this report.",
        "evidence": {
            "authorization_recorded": False,
            "reason": "PAL-022 is report-only and cannot authorize Phase 2 execution.",
        },
    }


def _phase2_health_baseline_prerequisite(
    health_observation: dict[str, Any] | None,
    baseline_observation: dict[str, Any] | None,
) -> dict[str, Any]:
    health_status = _router_health_status(health_observation)
    health_green = health_status in {"green", "ok", "healthy"}
    baseline = baseline_observation.get("baseline") if baseline_observation else None
    baseline_report_count = 0
    baseline_fail_count = 0
    if isinstance(baseline, dict):
        baseline_report_count = _int_value(baseline.get("report_count"))
        baseline_fail_count = _int_value(baseline.get("fail_count"))
    baseline_ok = baseline_report_count > 0 and baseline_fail_count == 0
    score = round((0.5 if health_green else 0.0) + (0.5 if baseline_ok else 0.0), 2)
    status = "pass" if score == 1.0 else "warn" if score > 0 else "fail"
    return {
        "id": "phase1_health_baseline",
        "label": "Phase 1 health and smoke baseline",
        "score": score,
        "status": status,
        "summary": "PAL health is green and smoke baselines are passing."
        if score == 1.0
        else "PAL health or smoke baseline evidence is incomplete.",
        "evidence": {
            "router_status": health_status or "unknown",
            "smoke_report_count": baseline_report_count,
            "smoke_fail_count": baseline_fail_count,
            "baseline_tokens_per_second": (
                baseline_observation.get("baseline_tokens_per_second")
                if baseline_observation
                else None
            ),
        },
    }


def _phase2_shutdown_safety_prerequisite(
    shutdown_observation: dict[str, Any] | None,
) -> dict[str, Any]:
    audit = shutdown_observation.get("audit") if shutdown_observation else None
    if not isinstance(audit, dict):
        audit = _unknown_shutdown_audit()
    audit_status = str(audit.get("audit_status", "incomplete"))
    enabled_state = str(audit.get("shutdown_enabled_state", "unknown"))
    override_state = str(audit.get("override_state", "unknown"))
    safe = audit_status == "pass" and enabled_state == "enabled" and override_state == "inactive"
    if safe:
        score = 1.0
        status = "pass"
    elif audit_status == "incomplete":
        score = 0.5
        status = "warn"
    else:
        score = 0.25
        status = "warn" if audit_status == "warn" else "fail"
    return {
        "id": "shutdown_safety",
        "label": "Shutdown safety",
        "score": score,
        "status": status,
        "summary": "Shutdown automation is enabled and no override is active."
        if safe
        else "Shutdown safety evidence is incomplete or needs review.",
        "evidence": {
            "audit_status": audit_status,
            "shutdown_enabled_state": enabled_state,
            "override_state": override_state,
            "next_shutdown_window": audit.get("next_shutdown_window", "unavailable"),
        },
    }


def _phase2_deployment_reproducibility_prerequisite(
    project_state_observation: dict[str, Any] | None,
) -> dict[str, Any]:
    project_state = project_state_observation.get("project_state") if project_state_observation else None
    if not isinstance(project_state, dict):
        project_state = {}
    runbook_present = bool(project_state.get("phase1_runbook_present"))
    session_state_present = bool(project_state.get("session_state_present"))
    phase2_appendix_only = bool(project_state.get("phase2_is_appendix_only"))
    score = 0.0
    if runbook_present:
        score += 0.4
    if session_state_present:
        score += 0.4
    if phase2_appendix_only:
        score += 0.2
    score = round(score, 2)
    status = "pass" if score == 1.0 else "warn" if score > 0 else "fail"
    return {
        "id": "deployment_reproducibility",
        "label": "Deployment reproducibility",
        "score": score,
        "status": status,
        "summary": "PAL Phase 1 runbook and session state are present."
        if score == 1.0
        else "PAL deployment runbook or session-state evidence is incomplete.",
        "evidence": {
            "phase1_runbook_present": runbook_present,
            "session_state_present": session_state_present,
            "phase2_is_appendix_only": phase2_appendix_only,
        },
    }


def _phase2_cost_boundary_prerequisite(boundary_observation: dict[str, Any] | None) -> dict[str, Any]:
    boundary = boundary_observation.get("boundary") if boundary_observation else None
    if not isinstance(boundary, dict):
        boundary = {}
    callable_actions = [str(item) for item in boundary.get("callable_actions", [])]
    blocked_actions = [str(item) for item in boundary.get("blocked_actions", [])]
    expected_blocked = {"rent", "destroy", "start", "stop"}
    boundary_safe = not callable_actions and expected_blocked.issubset(set(blocked_actions))
    return {
        "id": "cost_and_vast_boundary",
        "label": "Cost and Vast lifecycle boundary",
        "score": 1.0 if boundary_safe else 0.0,
        "status": "pass" if boundary_safe else "fail",
        "summary": "Vast lifecycle operations remain blocked by the default connector boundary."
        if boundary_safe
        else "Vast lifecycle boundary exposes callable actions.",
        "evidence": {
            "provider": boundary.get("provider", "vast"),
            "status": boundary.get("status", "unknown"),
            "blocked_actions": blocked_actions,
            "callable_actions": callable_actions,
        },
    }


def _phase2_execution_boundary_prerequisite() -> dict[str, Any]:
    return {
        "id": "phase2_execution_boundary",
        "label": "No Phase 2 execution action exposed",
        "score": 1.0,
        "status": "pass",
        "summary": "The readiness workflow exposes no Phase 2 execution actions.",
        "evidence": {
            "mutating_actions": [],
            "phase2_execution_actions": [],
            "blocked_phase2_actions": list(PHASE2_BLOCKED_EXECUTION_ACTIONS),
        },
    }


def _phase2_readiness_status(prerequisites: list[dict[str, Any]]) -> str:
    statuses = {str(row.get("status", "")) for row in prerequisites}
    if "blocked" in statuses:
        return "blocked"
    if statuses.intersection({"fail", "warn"}):
        return "not_ready"
    return "ready_for_authorization"


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _parse_shutdown_audit_stdout(stdout: str) -> tuple[dict[str, str], str]:
    fields: dict[str, str] = {}
    log_lines: list[str] = []
    in_log = False
    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        if line.strip() == "--- shutdown log ---":
            in_log = True
            continue
        if in_log:
            log_lines.append(line)
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields, "\n".join(log_lines).strip()


def _parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    return None


def _enabled_state(enabled: bool | None) -> str:
    if enabled is True:
        return "enabled"
    if enabled is False:
        return "disabled"
    return "unknown"


def _override_state(override_present: bool | None) -> str:
    if override_present is True:
        return "active"
    if override_present is False:
        return "inactive"
    return "unknown"


def _shutdown_audit_status(
    *,
    exit_code: Any,
    enabled: bool | None,
    override_present: bool | None,
    cron_installed: bool | None,
    next_window: str,
) -> str:
    if exit_code not in {0, None}:
        return "fail"
    if enabled is None or override_present is None or cron_installed is None or next_window == "unavailable":
        return "incomplete"
    if enabled is False or override_present is True or cron_installed is False:
        return "warn"
    return "pass"


def _next_shutdown_window(*, shutdown_time: str, current_local: str, timezone: str) -> str:
    target = _parse_shutdown_time(shutdown_time)
    current = _parse_shutdown_current_local(current_local)
    timezone = timezone.strip()
    if target is None or current is None or not timezone:
        return "unavailable"
    start = current.replace(
        hour=target[0],
        minute=target[1],
        second=0,
        microsecond=0,
    )
    if start <= current:
        start = start + timedelta(days=1)
    end = start + timedelta(minutes=5)
    return f"{start:%Y-%m-%d %H:%M}-{end:%H:%M} {timezone}"


def _parse_shutdown_time(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _parse_shutdown_current_local(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    if re.search(r"[+-]\d{4}$", normalized):
        normalized = f"{normalized[:-5]}{normalized[-5:-2]}:{normalized[-2:]}"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _phase2_project_state_tool(project_root: Path) -> dict[str, Any]:
    runbook_path = _first_existing_path(
        project_root,
        (
            Path("ops/phase-1-checkpoints.md"),
            Path("pal-2026/ops/phase-1-checkpoints.md"),
        ),
    )
    session_state_path = _first_existing_path(
        project_root,
        (
            Path("ops/session-state.md"),
            Path("pal-2026/ops/session-state.md"),
        ),
    )
    runbook_text = runbook_path.read_text(encoding="utf-8") if runbook_path else ""
    phase2_is_appendix_only = "Phase 2 is appendix-only" in runbook_text
    project_state = {
        "phase1_runbook_present": runbook_path is not None,
        "phase1_runbook_path": str(runbook_path) if runbook_path else "",
        "session_state_present": session_state_path is not None,
        "session_state_path": str(session_state_path) if session_state_path else "",
        "phase2_is_appendix_only": phase2_is_appendix_only,
    }
    complete = (
        project_state["phase1_runbook_present"]
        and project_state["session_state_present"]
        and phase2_is_appendix_only
    )
    return {
        "status": "ok" if complete else "warn",
        "summary": "PAL Phase 1 runbook and session-state evidence are present."
        if complete
        else "PAL Phase 1 runbook or session-state evidence is incomplete.",
        "project_state": project_state,
    }


def _first_existing_path(project_root: Path, relative_paths: tuple[Path, ...]) -> Path | None:
    for relative_path in relative_paths:
        candidate = project_root / relative_path
        if candidate.exists():
            return candidate
    return None


def _vast_boundary_tool() -> dict[str, Any]:
    boundary = default_vast_connector_boundary().to_dict()
    callable_actions = boundary.get("callable_actions", [])
    return {
        "status": "ok" if callable_actions == [] else "error",
        "summary": "Vast lifecycle actions are blocked by the local connector boundary."
        if callable_actions == []
        else "Vast connector boundary exposes callable lifecycle actions.",
        "boundary": boundary,
    }


def _tailscale_status_tool() -> dict[str, Any]:
    executable = _tailscale_executable()
    if executable is None:
        return {
            "status": "skipped",
            "summary": "Tailscale CLI is not installed or not discoverable on this Mac.",
            "checked_paths": ["tailscale", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"],
        }
    result = _run_command([executable, "status"], timeout_s=12)
    combined = f"{result['stdout']}\n{result['stderr']}"
    node_visible = "pal-cloud-a6000" in combined
    status = "ok" if result["exit_code"] == 0 and node_visible else "warn"
    if result["exit_code"] != 0:
        status = "error"
    return {
        "status": status,
        "summary": "pal-cloud-a6000 is visible in local Tailscale status."
        if node_visible
        else "pal-cloud-a6000 was not visible in local Tailscale status output.",
        "node_visible": node_visible,
        "command": result,
    }


def _ssh_process_check_tool() -> dict[str, Any]:
    remote_command = (
        'ps -eo pid,comm,args | grep -E "[t]ailscaled|[o]llama serve|[u]vicorn|[c]ron" || true; '
        "printf '\\n--- shutdown log ---\\n'; "
        "tail -n 12 /opt/pal/logs/shutdown.log 2>/dev/null || true"
    )
    result = _run_ssh_command(remote_command, timeout_s=20)
    if result.get("skipped"):
        return {
            "status": "skipped",
            "summary": str(result["stderr"]),
            "command": result,
        }
    status = "ok" if result["exit_code"] == 0 else "warn"
    return {
        "status": status,
        "summary": "Read-only SSH process/log diagnostic completed."
        if status == "ok"
        else "Read-only SSH process/log diagnostic returned a non-zero exit.",
        "command": result,
    }


def _gpu_hints_tool() -> dict[str, Any]:
    remote_command = (
        "printf '%s\\n' '--- gpu summary ---'; "
        "if command -v nvidia-smi >/dev/null 2>&1; then "
        "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw "
        "--format=csv,noheader,nounits; "
        "printf '%s\\n' '--- gpu processes ---'; "
        "nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory "
        "--format=csv,noheader,nounits 2>/dev/null || true; "
        "else printf '%s\\n' 'nvidia-smi unavailable'; fi"
    )
    result = _run_ssh_command(remote_command, timeout_s=20)
    if result.get("skipped"):
        status = "skipped"
    else:
        status = "ok" if result["exit_code"] == 0 else "warn"
    return {
        "status": status,
        "summary": _action_status_summary(
            status,
            ok="Read-only GPU hint diagnostic completed.",
            skipped=str(result["stderr"]),
            problem="Read-only GPU hint diagnostic returned a non-zero exit.",
        ),
        "command": result,
    }


def _slow_inference_logs_tool() -> dict[str, Any]:
    remote_command = (
        "printf '%s\\n' '--- pal router log ---'; "
        "tail -n 120 /opt/pal/logs/router.log 2>/dev/null || true; "
        "printf '%s\\n' '--- pal ollama log ---'; "
        "tail -n 120 /opt/pal/logs/ollama.log 2>/dev/null || true; "
        "printf '%s\\n' '--- pal startup log ---'; "
        "tail -n 80 /opt/pal/logs/start_all.log 2>/dev/null || true"
    )
    result = _run_ssh_command(remote_command, timeout_s=25)
    if result.get("skipped"):
        status = "skipped"
    else:
        status = "ok" if result["exit_code"] == 0 else "warn"
    return {
        "status": status,
        "summary": _action_status_summary(
            status,
            ok="Read-only PAL slow-inference log collection completed.",
            skipped=str(result["stderr"]),
            problem="Read-only PAL slow-inference log collection returned a non-zero exit.",
        ),
        "command": result,
    }


def _rerun_smoke_action(project_root: Path, client: PALAgentClient) -> dict[str, Any]:
    report = run_pal_smoke(client)
    report_path = write_smoke_report(project_root, report)
    return {
        "status": "ok" if report["status"] == "pass" else "warn",
        "summary": (
            f"PAL smoke suite {report['status']} with "
            f"{report['summary']['passed']} passed and {report['summary']['failed']} failed checks."
        ),
        "report_path": str(report_path),
        "report": report,
    }


def _inspect_logs_deep_action() -> dict[str, Any]:
    remote_command = (
        "printf '%s\\n' '--- processes ---'; "
        'ps -eo pid,comm,args | grep -E "[t]ailscaled|[o]llama serve|[u]vicorn|[c]ron|[d]ockerd" || true; '
        "printf '%s\\n' '--- pal logs ---'; "
        "for f in /opt/pal/logs/router.log /opt/pal/logs/ollama.log /opt/pal/logs/start_all.log; do "
        "test -f \"$f\" && printf '%s\\n' \"--- $f ---\" && tail -n 80 \"$f\"; "
        "done; "
        "printf '%s\\n' '--- docker ps ---'; "
        "if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then "
        "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'; "
        "printf '%s\\n' '--- router container logs ---'; docker logs pal-router --tail 120 2>&1 || true; "
        "printf '%s\\n' '--- ollama container logs ---'; docker logs pal-ollama --tail 120 2>&1 || true; "
        "else printf '%s\\n' 'docker unavailable or not running; PAL may be host-managed'; fi; "
        "printf '%s\\n' '--- shutdown log ---'; "
        "tail -n 80 /opt/pal/logs/shutdown.log 2>/dev/null || true; "
        "printf '%s\\n' '--- disk ---'; "
        "df -h /opt/pal 2>/dev/null || true; "
        "printf '%s\\n' '--- gpu ---'; "
        "nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || true"
    )
    result = _run_ssh_command(remote_command, timeout_s=30)
    if result.get("skipped"):
        status = "skipped"
    else:
        status = "ok" if result["exit_code"] == 0 else "warn"
    return {
        "status": status,
        "summary": _action_status_summary(
            status,
            ok="Deep read-only PAL logs/resource inspection completed.",
            skipped=str(result["stderr"]),
            problem="Deep read-only PAL logs/resource inspection returned a non-zero exit.",
        ),
        "command": result,
    }


def _restart_router_action() -> dict[str, Any]:
    remote_command = (
        "if [ -x /opt/pal/scripts/start_router.sh ]; then "
        "/opt/pal/scripts/start_router.sh && sleep 2 && "
        "curl --max-time 10 -fsS http://localhost:8000/health && "
        'printf "\\n--- router process ---\\n" && '
        'ps -eo pid,comm,args | grep -E "[u]vicorn.*app:app"; '
        "elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then "
        "cd /opt/pal && docker compose restart router && docker compose ps router; "
        "else printf '%s\\n' 'No supported PAL router restart path found.' >&2; exit 78; fi"
    )
    result = _run_ssh_command(remote_command, timeout_s=45)
    if result.get("skipped"):
        status = "skipped"
    else:
        status = "ok" if result["exit_code"] == 0 else "error"
    return {
        "status": status,
        "summary": _action_status_summary(
            status,
            ok="PAL router restart completed.",
            skipped=str(result["stderr"]),
            problem="PAL router restart failed.",
        ),
        "command": result,
    }


def _pause_shutdown_once_action() -> dict[str, Any]:
    remote_command = "touch /opt/pal/config/override.flag && ls -l /opt/pal/config/override.flag"
    result = _run_ssh_command(remote_command, timeout_s=20)
    if result.get("skipped"):
        status = "skipped"
    else:
        status = "ok" if result["exit_code"] == 0 else "error"
    return {
        "status": status,
        "summary": _action_status_summary(
            status,
            ok="Auto-shutdown override flag is present.",
            skipped=str(result["stderr"]),
            problem="Could not create auto-shutdown override flag.",
        ),
        "command": result,
    }


def _resume_shutdown_action() -> dict[str, Any]:
    remote_command = "rm -f /opt/pal/config/override.flag && test ! -e /opt/pal/config/override.flag"
    result = _run_ssh_command(remote_command, timeout_s=20)
    if result.get("skipped"):
        status = "skipped"
    else:
        status = "ok" if result["exit_code"] == 0 else "error"
    return {
        "status": status,
        "summary": _action_status_summary(
            status,
            ok="Auto-shutdown override flag is absent.",
            skipped=str(result["stderr"]),
            problem="Could not remove auto-shutdown override flag.",
        ),
        "command": result,
    }


def _tailscale_executable() -> str | None:
    if path := shutil.which("tailscale"):
        return path
    app_path = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
    if app_path.exists():
        return str(app_path)
    return None


def _run_ssh_command(remote_command: str, *, timeout_s: int) -> dict[str, Any]:
    args_or_error = _ssh_args(remote_command)
    if isinstance(args_or_error, dict):
        return args_or_error
    return _run_command(args_or_error, timeout_s=timeout_s)


def _ssh_args(remote_command: str) -> list[str] | dict[str, Any]:
    host = os.getenv("PAL_SSH_HOST", "").strip()
    port = os.getenv("PAL_SSH_PORT", "").strip()
    key = os.getenv("PAL_SSH_KEY", "").strip()
    user = os.getenv("PAL_SSH_USER", "root").strip() or "root"
    if not (host and port and key):
        return {
            "args": ["ssh", "<PAL_SSH_HOST>", "<remote-command>"],
            "exit_code": 78,
            "stdout": "",
            "stderr": "SSH diagnostics skipped because PAL_SSH_HOST, PAL_SSH_PORT, and PAL_SSH_KEY are not all set.",
            "skipped": True,
        }
    ssh = shutil.which("ssh")
    if ssh is None:
        return {
            "args": ["ssh", "<missing>", "<remote-command>"],
            "exit_code": 78,
            "stdout": "",
            "stderr": "ssh executable not found on this machine.",
            "skipped": True,
        }
    return [
        ssh,
        "-i",
        key,
        "-p",
        port,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        f"{user}@{host}",
        remote_command,
    ]


def _run_command(args: list[str], *, timeout_s: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "args": _redact_args(args),
            "exit_code": 124,
            "stdout": truncate(exc.stdout or "", 4000),
            "stderr": truncate(exc.stderr or f"Timed out after {timeout_s}s", 4000),
        }
    return {
        "args": _redact_args(args),
        "exit_code": completed.returncode,
        "stdout": truncate(completed.stdout, 4000),
        "stderr": truncate(completed.stderr, 4000),
    }


def _action_status_summary(status: str, *, ok: str, skipped: str, problem: str) -> str:
    if status == "ok":
        return ok
    if status == "skipped":
        return skipped
    return problem


def _redact_args(args: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for item in args:
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        redacted.append(item)
        if item == "-i":
            skip_next = True
    return redacted


def _build_knowledge_context(project_root: Path, query: str) -> str:
    normalized_query = " ".join(query.split())
    if not normalized_query:
        return _render_knowledge_context(
            (),
            note="No local PAL KB query was available for this workflow task.",
        )
    try:
        results = query_pal_knowledge_index(
            project_root,
            normalized_query,
            limit=PAL_KNOWLEDGE_CONTEXT_LIMIT,
        )
    except FileNotFoundError:
        return _render_knowledge_context(
            (),
            note=(
                "No local PAL KB index is available. Run "
                "`promptclaw pal kb build PROJECT_ROOT` to populate this section."
            ),
        )
    except (OSError, ValueError):
        return _render_knowledge_context(
            (),
            note="Local PAL KB context could not be loaded safely for this workflow.",
        )
    if not results:
        return _render_knowledge_context(
            (),
            note="No local PAL KB matches were found for this workflow task.",
        )
    return _render_knowledge_context(results)


def _render_knowledge_context(
    results: tuple[PALKnowledgeQueryResult, ...],
    *,
    note: str = "",
) -> str:
    lines = ["## Knowledge Context", ""]
    if results:
        lines.append(
            f"Local PAL KB matches (max {PAL_KNOWLEDGE_CONTEXT_LIMIT}; bounded snippets):"
        )
        for result in results[:PAL_KNOWLEDGE_CONTEXT_LIMIT]:
            snippet = truncate(
                " ".join(result.snippet.split()),
                PAL_KNOWLEDGE_SNIPPET_MAX_CHARS,
            )
            lines.append(
                "- "
                f"{result.source_path}:{result.start_line}-{result.end_line} "
                f"(score={result.score:g}, chunk={result.chunk_id}): {snippet}"
            )
    else:
        lines.append(note or "No local PAL KB matches were available for this workflow task.")
    return truncate("\n".join(lines).rstrip(), PAL_KNOWLEDGE_CONTEXT_MAX_CHARS)


def _render_plan_prompt(
    task: str,
    tools: dict[str, PALOpsTool],
    *,
    knowledge_context: str = "",
) -> str:
    tool_lines = "\n".join(
        f"- {name}: {tool.description}" for name, tool in sorted(tools.items())
    )
    context = knowledge_context or _render_knowledge_context(())
    return (
        "# PAL Ops Triage Tool Plan\n\n"
        f"Task:\n{task}\n\n"
        f"{context}\n\n"
        "Available diagnostic tools:\n"
        f"{tool_lines}\n\n"
        "Return only a JSON object with this shape:\n"
        '{"tools":["pal_health"],"rationale":"short reason"}\n\n'
        "Choose only tools from the list. For a standard PAL ops triage, prefer every read-only "
        "diagnostic unless you have a specific reason to skip one; tools that are not configured "
        "will report skipped safely. Destructive or mutating actions are not available."
    )


def _render_summary_prompt(
    task: str,
    observations_payload: dict[str, Any],
    *,
    knowledge_context: str = "",
) -> str:
    context = knowledge_context or _render_knowledge_context(())
    return (
        "# PAL Ops Triage Summary\n\n"
        f"Task:\n{task}\n\n"
        f"{context}\n\n"
        "Tool observations JSON:\n"
        f"```json\n{_json_dumps(observations_payload)}\n```\n\n"
        "Write a concise operator summary with: status, evidence, risks, and next actions. "
        "Do not describe an unexecuted tool as failed or unconfigured; only summarize evidence "
        "from the observations. "
        "Any restart, shutdown, rental, key, firewall, or config change must be phrased as requiring human approval."
    )


def _render_action_plan_prompt(
    task: str,
    context_payload: dict[str, Any],
    actions: dict[str, PALOpsAction],
    *,
    knowledge_context: str = "",
) -> str:
    action_lines = "\n".join(
        "- "
        f"{name}: {action.description} "
        f"(approval_required={str(action.approval_required).lower()}, mutating={str(action.mutating).lower()})"
        for name, action in sorted(actions.items())
    )
    context = knowledge_context or _render_knowledge_context(())
    return (
        "# PAL Ops Action Plan\n\n"
        f"Task:\n{task}\n\n"
        f"{context}\n\n"
        "Current diagnostic context:\n"
        f"```json\n{_json_dumps(context_payload)}\n```\n\n"
        "Available fixed actions:\n"
        f"{action_lines}\n\n"
        f"{_render_provider_action_boundaries()}\n\n"
        "Return only a JSON object with this shape:\n"
        '{"actions":["inspect_logs_deep"],"rationale":"short reason"}\n\n'
        "Choose only actions from the list. Do not invent shell commands. Prefer "
        "read-only evidence gathering before mutating actions. PromptClaw will not "
        "execute any proposed action unless the operator explicitly approves its action id."
    )


def _render_provider_action_boundaries() -> str:
    boundary = default_vast_connector_boundary()
    callable_actions = ", ".join(boundary.callable_action_names())
    blocked_actions = ", ".join(boundary.blocked_action_names())
    callable_text = f"[{callable_actions}]" if callable_actions else "[]"
    return (
        "## Provider Action Boundaries\n\n"
        "- Vast connector: "
        f"status={boundary.status}; "
        f"callable_actions={callable_text}; "
        f"blocked_actions=[{blocked_actions}]. "
        "These blocked lifecycle actions are not available fixed action ids."
    )


def _render_action_summary_prompt(
    task: str,
    action_payload: dict[str, Any],
    *,
    knowledge_context: str = "",
) -> str:
    context = knowledge_context or _render_knowledge_context(())
    return (
        "# PAL Ops Action Summary\n\n"
        f"Task:\n{task}\n\n"
        f"{context}\n\n"
        "Action results JSON:\n"
        f"```json\n{_json_dumps(action_payload)}\n```\n\n"
        "Write a concise operator summary with: what was proposed, what was executed, "
        "what still needs approval, evidence from action results, and next commands if useful. "
        "Do not imply that pending actions have run. Any restart, shutdown, rental, key, "
        "firewall, or config change must remain tied to explicit human approval."
    )


def _parse_tool_plan(
    text: str,
    *,
    tools: dict[str, PALOpsTool],
    default_tools: tuple[str, ...],
) -> dict[str, Any]:
    parsed: dict[str, Any] | None = None
    json_text = extract_json_object(text)
    if json_text:
        try:
            raw = json.loads(json_text)
            if isinstance(raw, dict):
                parsed = raw
        except json.JSONDecodeError:
            parsed = None

    if parsed is None or not isinstance(parsed.get("tools"), list):
        fallback_tools = [name for name in default_tools if name in tools]
        return {
            "source": "fallback",
            "rationale": "PAL did not return a valid tool plan; used the default safe diagnostic order.",
            "tools": fallback_tools,
            "ignored_tools": [],
            "raw_text": text,
        }

    selected: list[str] = []
    ignored: list[str] = []
    for item in parsed["tools"]:
        name = str(item)
        if name in tools:
            if name not in selected:
                selected.append(name)
        elif name not in ignored:
            ignored.append(name)

    if not selected:
        selected = [name for name in default_tools if name in tools]

    return {
        "source": "pal",
        "rationale": str(parsed.get("rationale", "")),
        "tools": selected,
        "ignored_tools": ignored,
        "raw_text": text,
    }


def _parse_action_plan(text: str, *, actions: dict[str, PALOpsAction]) -> dict[str, Any]:
    parsed: dict[str, Any] | None = None
    json_text = extract_json_object(text)
    if json_text:
        try:
            raw = json.loads(json_text)
            if isinstance(raw, dict):
                parsed = raw
        except json.JSONDecodeError:
            parsed = None

    if parsed is None or not isinstance(parsed.get("actions"), list):
        return {
            "source": "fallback",
            "rationale": "PAL did not return a valid action plan; no actions were proposed.",
            "actions": [],
            "ignored_actions": [],
            "raw_text": text,
        }

    selected: list[str] = []
    ignored: list[str] = []
    for item in parsed["actions"]:
        name = str(item)
        if name in actions:
            if name not in selected:
                selected.append(name)
        elif name not in ignored:
            ignored.append(name)

    return {
        "source": "pal",
        "rationale": str(parsed.get("rationale", "")),
        "actions": selected,
        "ignored_actions": ignored,
        "raw_text": text,
    }


def _render_route_markdown(plan: dict[str, Any]) -> str:
    tools = ", ".join(plan["tools"]) if plan["tools"] else "none"
    ignored = ", ".join(plan["ignored_tools"]) if plan["ignored_tools"] else "none"
    return (
        "# PAL Ops Triage Route\n\n"
        f"- Lead agent: PAL\n"
        f"- Verifier/executor: local allow-list\n"
        f"- Plan source: {plan['source']}\n"
        f"- Tools: {tools}\n"
        f"- Ignored requested tools: {ignored}\n"
        f"- Rationale: {plan.get('rationale', '')}\n"
    )


def _render_action_route_markdown(plan: dict[str, Any], approved: tuple[str, ...]) -> str:
    actions = ", ".join(plan["actions"]) if plan["actions"] else "none"
    ignored = ", ".join(plan["ignored_actions"]) if plan["ignored_actions"] else "none"
    approvals = ", ".join(approved) if approved else "none"
    return (
        "# PAL Ops Action Route\n\n"
        f"- Lead agent: PAL\n"
        f"- Verifier/executor: local approval gate\n"
        f"- Plan source: {plan['source']}\n"
        f"- Proposed actions: {actions}\n"
        f"- Approved actions: {approvals}\n"
        f"- Ignored requested actions: {ignored}\n"
        f"- Rationale: {plan.get('rationale', '')}\n"
    )


def _render_operator_handoff(summary_text: str, observations_payload: dict[str, Any]) -> str:
    executed = ", ".join(observations_payload["executed_tools"]) or "none"
    ignored = ", ".join(observations_payload["ignored_tools"]) or "none"
    return (
        "# PAL To Operator Handoff\n\n"
        f"Executed diagnostics: {executed}\n\n"
        f"Ignored non-allow-listed requests: {ignored}\n\n"
        "## Summary\n\n"
        f"{summary_text.rstrip()}\n"
    )


def _render_action_handoff(summary_text: str, action_payload: dict[str, Any]) -> str:
    proposed = ", ".join(action_payload["proposed_actions"]) or "none"
    executed = ", ".join(action_payload["executed_actions"]) or "none"
    pending = ", ".join(action_payload["pending_approval"]) or "none"
    ignored = ", ".join(action_payload["ignored_actions"]) or "none"
    return (
        "# PAL Action Request Handoff\n\n"
        f"Proposed actions: {proposed}\n\n"
        f"Executed actions: {executed}\n\n"
        f"Pending approval: {pending}\n\n"
        f"Ignored non-allow-listed actions: {ignored}\n\n"
        "## Summary\n\n"
        f"{summary_text.rstrip()}\n"
    )


def _render_slow_inference_route_markdown(context_tools: list[str]) -> str:
    tools = ", ".join(context_tools) if context_tools else "none"
    return (
        "# PAL Slow-Inference Context Route\n\n"
        f"- Workflow id: {SLOW_INFERENCE_WORKFLOW_ID}\n"
        f"- Lead agent: local allow-list\n"
        f"- Verifier/executor: local allow-list\n"
        f"- Tools: {tools}\n"
        "- Mutating actions: none\n"
    )


def _render_slow_inference_diagnosis_route_markdown(context_tools: list[str]) -> str:
    tools = ", ".join(context_tools) if context_tools else "none"
    return (
        "# PAL Slow-Inference Diagnosis Route\n\n"
        f"- Workflow id: {SLOW_INFERENCE_DIAGNOSIS_WORKFLOW_ID}\n"
        f"- Lead agent: local allow-list\n"
        f"- Verifier/executor: local allow-list\n"
        f"- Tools: {tools}\n"
        "- Mutating actions: none\n"
    )


def _render_restart_validation_route_markdown(validation_tools: list[str]) -> str:
    tools = ", ".join(validation_tools) if validation_tools else "none"
    return (
        "# PAL Restart Validation Route\n\n"
        f"- Workflow id: {RESTART_VALIDATION_WORKFLOW_ID}\n"
        f"- Lead agent: local allow-list\n"
        f"- Verifier/executor: local allow-list\n"
        f"- Tools: {tools}\n"
        "- Mutating actions: none\n"
    )


def _render_shutdown_audit_route_markdown(audit_tools: list[str]) -> str:
    tools = ", ".join(audit_tools) if audit_tools else "none"
    return (
        "# PAL Shutdown Audit Route\n\n"
        f"- Workflow id: {SHUTDOWN_AUDIT_WORKFLOW_ID}\n"
        f"- Lead agent: local allow-list\n"
        f"- Verifier/executor: local allow-list\n"
        f"- Tools: {tools}\n"
        "- Mutating actions: none\n"
    )


def _render_phase2_readiness_route_markdown(readiness_tools: list[str]) -> str:
    tools = ", ".join(readiness_tools) if readiness_tools else "none"
    return (
        "# PAL Phase 2 Readiness Route\n\n"
        f"- Workflow id: {PHASE2_READINESS_WORKFLOW_ID}\n"
        f"- Lead agent: local allow-list\n"
        f"- Verifier/executor: local allow-list\n"
        f"- Tools: {tools}\n"
        "- Mutating actions: none\n"
        "- Phase 2 execution actions: none\n"
    )


def _render_slow_inference_context_summary(context_payload: dict[str, Any]) -> str:
    lines = ["# PAL Slow-Inference Context", ""]
    baseline_tps = context_payload.get("baseline_tokens_per_second")
    lines.append(f"Workflow id: {context_payload['workflow_id']}")
    lines.append(f"Baseline tokens/s: {baseline_tps if baseline_tps is not None else 'unavailable'}")
    lines.append("")
    lines.append("Observations:")
    for observation in context_payload["observations"]:
        lines.append(
            f"- {observation.get('tool', 'unknown')}: "
            f"{observation.get('status', 'unknown')} - {observation.get('summary', '')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_slow_inference_diagnosis_summary(payload: dict[str, Any]) -> str:
    diagnosis = payload["diagnosis"]
    lines = ["# PAL Slow-Inference Diagnosis", ""]
    lines.append(f"Workflow id: {payload['workflow_id']}")
    lines.append(f"Severity: {diagnosis['severity']}")
    lines.append(
        "Baseline tokens/s: "
        f"{diagnosis['baseline_tokens_per_second'] if diagnosis['baseline_tokens_per_second'] is not None else 'unavailable'}"
    )
    lines.append(
        "Observed tokens/s: "
        f"{diagnosis['observed_tokens_per_second'] if diagnosis['observed_tokens_per_second'] is not None else 'unavailable'}"
    )
    lines.append(
        "GPU utilization: "
        f"{diagnosis['gpu_utilization_percent']}%" if diagnosis["gpu_utilization_percent"] is not None else "GPU utilization: unavailable"
    )
    lines.append("Mutating actions: none")
    lines.append("")
    lines.append("Findings:")
    if diagnosis["findings"]:
        for finding in diagnosis["findings"]:
            lines.append(
                f"- {finding['code']} ({finding['severity']}): {finding['summary']}"
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Recommendations:")
    for recommendation in diagnosis["recommendations"]:
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def _render_restart_validation_summary(payload: dict[str, Any]) -> str:
    lines = ["# PAL Restart Validation", ""]
    lines.append(f"Workflow id: {payload['workflow_id']}")
    lines.append(f"Validation status: {payload['validation_status']}")
    lines.append("Mutating actions: none")
    lines.append("")
    lines.append("Observations:")
    for observation in payload["observations"]:
        lines.append(
            f"- {observation.get('tool', 'unknown')}: "
            f"{observation.get('status', 'unknown')} - {observation.get('summary', '')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_shutdown_audit_summary(payload: dict[str, Any]) -> str:
    audit = payload["audit"]
    lines = ["# PAL Shutdown Audit", ""]
    lines.append(f"Workflow id: {payload['workflow_id']}")
    lines.append(f"Audit status: {payload['audit_status']}")
    lines.append(f"Shutdown enabled state: {payload['shutdown_enabled_state']}")
    lines.append(f"Override state: {payload['override_state']}")
    lines.append(f"Next shutdown window: {payload['next_shutdown_window']}")
    lines.append(f"Cron installed: {_display_optional_bool(audit.get('cron_installed'))}")
    lines.append("Mutating actions: none")
    lines.append("")
    lines.append("Observations:")
    for observation in payload["observations"]:
        lines.append(
            f"- {observation.get('tool', 'unknown')}: "
            f"{observation.get('status', 'unknown')} - {observation.get('summary', '')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_phase2_readiness_summary(payload: dict[str, Any]) -> str:
    lines = ["# PAL Phase 2 Readiness", ""]
    lines.append(f"Workflow id: {payload['workflow_id']}")
    lines.append(f"Readiness status: {payload['readiness_status']}")
    lines.append(f"Overall score: {payload['overall_score']:.2f}")
    lines.append("Mutating actions: none")
    lines.append("Phase 2 execution actions: none")
    lines.append("")
    lines.append("Prerequisites:")
    for prerequisite in payload["prerequisites"]:
        lines.append(
            f"- {prerequisite['id']}: {prerequisite['score']:.2f} "
            f"({prerequisite['status']}) - {prerequisite['summary']}"
        )
    lines.append("")
    lines.append("Observations:")
    for observation in payload["observations"]:
        lines.append(
            f"- {observation.get('tool', 'unknown')}: "
            f"{observation.get('status', 'unknown')} - {observation.get('summary', '')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _display_optional_bool(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _render_slow_inference_context_handoff(context_payload: dict[str, Any]) -> str:
    executed = ", ".join(context_payload["executed_tools"]) or "none"
    return (
        "# PAL Slow-Inference Context Handoff\n\n"
        f"Workflow id: {context_payload['workflow_id']}\n\n"
        f"Executed diagnostics: {executed}\n\n"
        f"Baseline tokens/s: {context_payload.get('baseline_tokens_per_second')}\n\n"
        "This artifact is read-only context for a later slow-inference diagnosis. "
        "It does not approve or execute infrastructure changes.\n"
    )


def _render_slow_inference_diagnosis_handoff(payload: dict[str, Any]) -> str:
    diagnosis = payload["diagnosis"]
    executed = ", ".join(payload["executed_tools"]) or "none"
    return (
        "# PAL Slow-Inference Diagnosis Handoff\n\n"
        f"Workflow id: {payload['workflow_id']}\n\n"
        f"Executed diagnostics: {executed}\n\n"
        "Mutating actions: none\n\n"
        f"Severity: {diagnosis['severity']}\n\n"
        "This diagnosis is read-only except for local PromptClaw run artifacts. "
        "It does not approve or execute infrastructure changes.\n"
    )


def _render_restart_validation_handoff(payload: dict[str, Any]) -> str:
    executed = ", ".join(payload["executed_tools"]) or "none"
    return (
        "# PAL Restart Validation Handoff\n\n"
        f"Workflow id: {payload['workflow_id']}\n\n"
        f"Executed diagnostics: {executed}\n\n"
        "Mutating actions: none\n\n"
        f"Validation status: {payload['validation_status']}\n\n"
        "This validation is read-only except for local PromptClaw run artifacts "
        "and local PAL smoke report storage. It does not approve or execute "
        "infrastructure changes.\n"
    )


def _render_shutdown_audit_handoff(payload: dict[str, Any]) -> str:
    executed = ", ".join(payload["executed_tools"]) or "none"
    return (
        "# PAL Shutdown Audit Handoff\n\n"
        f"Workflow id: {payload['workflow_id']}\n\n"
        f"Executed diagnostics: {executed}\n\n"
        "Mutating actions: none\n\n"
        f"Audit status: {payload['audit_status']}\n\n"
        f"Shutdown enabled state: {payload['shutdown_enabled_state']}\n\n"
        f"Override state: {payload['override_state']}\n\n"
        f"Next shutdown window: {payload['next_shutdown_window']}\n\n"
        "This audit is read-only except for local PromptClaw run artifacts. "
        "It does not approve or execute shutdown override changes.\n"
    )


def _render_phase2_readiness_handoff(payload: dict[str, Any]) -> str:
    executed = ", ".join(payload["executed_tools"]) or "none"
    return (
        "# PAL Phase 2 Readiness Handoff\n\n"
        f"Workflow id: {payload['workflow_id']}\n\n"
        f"Executed diagnostics: {executed}\n\n"
        "Mutating actions: none\n\n"
        "Phase 2 execution actions: none\n\n"
        f"Readiness status: {payload['readiness_status']}\n\n"
        f"Overall score: {payload['overall_score']:.2f}\n\n"
        "This report is read-only except for local PromptClaw run artifacts. "
        "It does not approve or execute Phase 2 infrastructure, model, or "
        "Vast lifecycle changes.\n"
    )


def _fallback_summary(observations_payload: dict[str, Any], *, error: str = "") -> str:
    lines = ["# PAL Ops Triage Summary", ""]
    if error:
        lines.append(f"PAL summary generation failed: {error}")
        lines.append("")
    lines.append(f"Executed tools: {', '.join(observations_payload['executed_tools']) or 'none'}")
    lines.append(f"Ignored tools: {', '.join(observations_payload['ignored_tools']) or 'none'}")
    lines.append("")
    lines.append("Observations:")
    for observation in observations_payload["observations"]:
        lines.append(f"- {observation.get('tool', 'unknown')}: {observation.get('status', 'unknown')} - {observation.get('summary', '')}")
    return "\n".join(lines)


def _fallback_action_summary(action_payload: dict[str, Any], *, error: str = "") -> str:
    lines = ["# PAL Ops Action Summary", ""]
    if error:
        lines.append(f"PAL action summary generation failed: {error}")
        lines.append("")
    lines.append(f"Proposed actions: {', '.join(action_payload['proposed_actions']) or 'none'}")
    lines.append(f"Executed actions: {', '.join(action_payload['executed_actions']) or 'none'}")
    lines.append(f"Pending approval: {', '.join(action_payload['pending_approval']) or 'none'}")
    lines.append(f"Ignored actions: {', '.join(action_payload['ignored_actions']) or 'none'}")
    lines.append("")
    lines.append("Action results:")
    for row in action_payload["actions"]:
        lines.append(f"- {row.get('action', 'unknown')}: {row.get('status', 'unknown')} - {row.get('summary', '')}")
    return "\n".join(lines)


def _record_event(
    artifacts: ArtifactManager,
    state: RunState,
    now: Callable[[], str],
    *,
    event_type: str,
    message: str,
    phase: str,
    agent: str = "",
    role: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    event = Event(
        timestamp=now(),
        event_type=event_type,
        message=message,
        phase=phase,
        agent=agent,
        role=role,
        extra=extra or {},
    )
    state.events.append(event)
    state.updated_at = event.timestamp
    artifacts.append_event(event)


def _build_run_id(timestamp: str, title: str) -> str:
    clean_stamp = (
        timestamp.replace("+00:00", "Z")
        .replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .lower()
    )
    return f"{clean_stamp}-{slugify(title)}"


def _relative_path(project_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
