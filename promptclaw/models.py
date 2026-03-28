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
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    coherence: Any = None  # CoherenceConfig, typed as Any to avoid circular import

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
