from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .artifacts import ArtifactManager
from .config import load_config
from .models import Event, RunState
from .pal_client import PALClientError, PALQueryResult, PALRouterClient
from .pal_smoke import load_smoke_reports, summarize_smoke_reports
from .paths import ProjectPaths
from .state_store import StateStore
from .utils import extract_json_object, slugify, truncate, utc_now


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

PAL_AGENT_SYSTEM_PROMPT = (
    "You are PAL 2026 operating through PromptClaw's bounded agent runtime. "
    "You may choose diagnostics from the provided allow-list only. You cannot run "
    "arbitrary shell commands, mutate files, restart services, stop or destroy cloud "
    "instances, rotate keys, or spend money. Recommend those actions only as human "
    "approval gates."
)


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

    plan_prompt = _render_plan_prompt(task, tools)
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
    summary_prompt = _render_summary_prompt(task, observations_payload)
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


def _pal_health_tool(client: PALAgentClient) -> dict[str, Any]:
    health = client.health()
    return {
        "status": "ok" if str(health.get("status", "")).lower() == "green" else "warn",
        "summary": f"PAL router status is {health.get('status', 'unknown')}.",
        "health": health,
    }


def _pal_smoke_baseline_tool(project_root: Path) -> dict[str, Any]:
    reports = load_smoke_reports(project_root)
    summary = summarize_smoke_reports(reports)
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
    host = os.getenv("PAL_SSH_HOST", "").strip()
    port = os.getenv("PAL_SSH_PORT", "").strip()
    key = os.getenv("PAL_SSH_KEY", "").strip()
    user = os.getenv("PAL_SSH_USER", "root").strip() or "root"
    if not (host and port and key):
        return {
            "status": "skipped",
            "summary": "SSH diagnostics skipped because PAL_SSH_HOST, PAL_SSH_PORT, and PAL_SSH_KEY are not all set.",
            "required_env": ["PAL_SSH_HOST", "PAL_SSH_PORT", "PAL_SSH_KEY"],
        }
    ssh = shutil.which("ssh")
    if ssh is None:
        return {"status": "skipped", "summary": "ssh executable not found on this machine."}

    remote_command = (
        'ps -eo pid,comm,args | grep -E "[t]ailscaled|[o]llama serve|[u]vicorn|[c]ron" || true; '
        "printf '\\n--- shutdown log ---\\n'; "
        "tail -n 12 /opt/pal/logs/shutdown.log 2>/dev/null || true"
    )
    result = _run_command(
        [
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
        ],
        timeout_s=20,
    )
    status = "ok" if result["exit_code"] == 0 else "warn"
    return {
        "status": status,
        "summary": "Read-only SSH process/log diagnostic completed."
        if status == "ok"
        else "Read-only SSH process/log diagnostic returned a non-zero exit.",
        "command": result,
    }


def _tailscale_executable() -> str | None:
    if path := shutil.which("tailscale"):
        return path
    app_path = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
    if app_path.exists():
        return str(app_path)
    return None


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


def _render_plan_prompt(task: str, tools: dict[str, PALOpsTool]) -> str:
    tool_lines = "\n".join(
        f"- {name}: {tool.description}" for name, tool in sorted(tools.items())
    )
    return (
        "# PAL Ops Triage Tool Plan\n\n"
        f"Task:\n{task}\n\n"
        "Available diagnostic tools:\n"
        f"{tool_lines}\n\n"
        "Return only a JSON object with this shape:\n"
        '{"tools":["pal_health"],"rationale":"short reason"}\n\n'
        "Choose only tools from the list. For a standard PAL ops triage, prefer every read-only "
        "diagnostic unless you have a specific reason to skip one; tools that are not configured "
        "will report skipped safely. Destructive or mutating actions are not available."
    )


def _render_summary_prompt(task: str, observations_payload: dict[str, Any]) -> str:
    return (
        "# PAL Ops Triage Summary\n\n"
        f"Task:\n{task}\n\n"
        "Tool observations JSON:\n"
        f"```json\n{_json_dumps(observations_payload)}\n```\n\n"
        "Write a concise operator summary with: status, evidence, risks, and next actions. "
        "Do not describe an unexecuted tool as failed or unconfigured; only summarize evidence "
        "from the observations. "
        "Any restart, shutdown, rental, key, firewall, or config change must be phrased as requiring human approval."
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
