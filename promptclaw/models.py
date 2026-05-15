from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass
class ProjectConfig:
    name: str
    description: str = ""

@dataclass
class ArtifactConfig:
    root: str = ".promptclaw"

@dataclass
class ControlPlaneConfig:
    mode: str = "heuristic"
    agent: str | None = None
    allow_fallback: bool = True

@dataclass
class RoutingConfig:
    verification_enabled: bool = True
    max_retries: int = 1
    ask_user_on_ambiguity: bool = True
    default_task_type: str = "general"

@dataclass
class PALConfig:
    enabled: bool = False
    base_url: str = "http://pal-cloud-a6000:8000"
    default_model: str = "llama3.3:70b-instruct-q4_K_M"
    timeout_s: float = 300.0
    health_timeout_s: float = 10.0

@dataclass
class AgentConfig:
    name: str
    enabled: bool = True
    kind: str = "mock"
    shell_command: str = ""
    command: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    instruction_file: str = ""

@dataclass
class PromptClawConfig:
    project: ProjectConfig
    artifacts: ArtifactConfig
    control_plane: ControlPlaneConfig
    routing: RoutingConfig
    pal: PALConfig = field(default_factory=PALConfig)
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    coherence: Any = None  # CoherenceConfig, typed as Any to avoid circular import

@dataclass(frozen=True)
class ConfigModelReport:
    project_name: str
    artifact_root: str
    control_plane_mode: str
    verification_enabled: bool
    max_retries: int
    agent_count: int
    enabled_agent_count: int
    disabled_agent_count: int
    command_agent_count: int

@dataclass
class RouteDecision:
    ambiguous: bool
    clarification_question: str | None
    lead_agent: str
    verifier_agent: str | None
    reason: str
    subtask_brief: str
    task_type: str
    confidence: float = 0.5

@dataclass
class AgentResult:
    agent_name: str
    phase: str
    role: str
    output_text: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    output_path: str = ""
    prompt_path: str = ""

@dataclass
class Event:
    timestamp: str
    event_type: str
    message: str
    phase: str = ""
    agent: str = ""
    role: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class RunState:
    run_id: str
    title: str
    status: str
    current_phase: str
    created_at: str
    updated_at: str
    task_text: str
    lead_agent: str = ""
    verifier_agent: str = ""
    route_decision: dict[str, Any] = field(default_factory=dict)
    clarification_question: str | None = None
    final_summary_path: str = ""
    retries_used: int = 0
    events: list[Event] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    recovery_actions: list[str] = field(default_factory=list)
    coherence_violations: list[dict[str, Any]] = field(default_factory=list)
    enforcement_mode: str = "monitor"


def sorted_agents(config: PromptClawConfig) -> tuple[AgentConfig, ...]:
    """Return configured agents in deterministic name order."""
    agents: list[AgentConfig] = []
    for agent in config.agents.values():
        agents.append(agent)
    return tuple(sorted(agents, key=lambda item: item.name))


def summarize_agent(agent: AgentConfig) -> dict[str, Any]:
    """Return a JSON-safe diagnostic row for one agent configuration."""
    command_configured = False
    if agent.shell_command or agent.command:
        command_configured = True
    return {
        "name": agent.name,
        "enabled": agent.enabled,
        "kind": agent.kind,
        "command_configured": command_configured,
        "capability_count": len(agent.capabilities),
        "capabilities": list(agent.capabilities),
        "instruction_file": agent.instruction_file,
    }


def config_model_report(config: PromptClawConfig) -> ConfigModelReport:
    """Build aggregate model diagnostics for a PromptClaw config."""
    agent_count = 0
    enabled_agent_count = 0
    command_agent_count = 0
    for agent in sorted_agents(config):
        agent_count += 1
        if agent.enabled:
            enabled_agent_count += 1
        if agent.kind == "command" and (agent.shell_command or agent.command):
            command_agent_count += 1
    return ConfigModelReport(
        project_name=config.project.name,
        artifact_root=config.artifacts.root,
        control_plane_mode=config.control_plane.mode,
        verification_enabled=config.routing.verification_enabled,
        max_retries=config.routing.max_retries,
        agent_count=agent_count,
        enabled_agent_count=enabled_agent_count,
        disabled_agent_count=agent_count - enabled_agent_count,
        command_agent_count=command_agent_count,
    )


def summarize_config_model(config: PromptClawConfig) -> dict[str, Any]:
    """Return a JSON-safe operator summary for config and agent models."""
    report = config_model_report(config)
    agents: list[dict[str, Any]] = []
    for agent in sorted_agents(config):
        agents.append(summarize_agent(agent))
    return {
        "project_name": report.project_name,
        "artifact_root": report.artifact_root,
        "control_plane_mode": report.control_plane_mode,
        "verification_enabled": report.verification_enabled,
        "max_retries": report.max_retries,
        "agent_count": report.agent_count,
        "enabled_agent_count": report.enabled_agent_count,
        "disabled_agent_count": report.disabled_agent_count,
        "command_agent_count": report.command_agent_count,
        "agents": agents,
    }


def summarize_route_decision(decision: RouteDecision) -> dict[str, Any]:
    """Return a JSON-safe summary of a routing decision."""
    return {
        "ambiguous": decision.ambiguous,
        "has_clarification_question": decision.clarification_question is not None,
        "lead_agent": decision.lead_agent,
        "verifier_agent": decision.verifier_agent or "",
        "has_verifier": decision.verifier_agent is not None,
        "task_type": decision.task_type,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "subtask_brief": decision.subtask_brief,
    }


def summarize_run_state(state: RunState) -> dict[str, Any]:
    """Return a JSON-safe summary for an end-to-end run state."""
    route_task_type = ""
    if state.route_decision:
        route_task_type = str(state.route_decision.get("task_type", ""))
    return {
        "run_id": state.run_id,
        "title": state.title,
        "status": state.status,
        "phase": state.current_phase,
        "lead_agent": state.lead_agent,
        "verifier_agent": state.verifier_agent,
        "route_task_type": route_task_type,
        "retries_used": state.retries_used,
        "event_count": len(state.events),
        "error_count": len(state.errors),
        "recovery_action_count": len(state.recovery_actions),
        "coherence_violation_count": len(state.coherence_violations),
        "has_final_summary": bool(state.final_summary_path),
        "enforcement_mode": state.enforcement_mode,
    }
