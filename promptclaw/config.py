from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import (
    AgentConfig,
    ArtifactConfig,
    ControlPlaneConfig,
    ProjectConfig,
    PromptClawConfig,
    RoutingConfig,
)
from .utils import read_json, write_json

CONFIG_FILENAME = "promptclaw.json"

def default_project_config(project_name: str = "New PromptClaw") -> PromptClawConfig:
    return PromptClawConfig(
        project=ProjectConfig(name=project_name, description="Orchestrated multi-agent claw."),
        artifacts=ArtifactConfig(root=".promptclaw"),
        control_plane=ControlPlaneConfig(mode="heuristic", agent="claude", allow_fallback=True),
        routing=RoutingConfig(
            verification_enabled=True,
            max_retries=1,
            ask_user_on_ambiguity=True,
            default_task_type="general",
        ),
        agents={
            "codex": AgentConfig(
                name="codex",
                enabled=True,
                kind="mock",
                capabilities=["coding", "implementation", "testing", "refactoring"],
                instruction_file="prompts/agents/codex.md",
            ),
            "claude": AgentConfig(
                name="claude",
                enabled=True,
                kind="mock",
                capabilities=["architecture", "specification", "verification", "analysis"],
                instruction_file="prompts/agents/claude.md",
            ),
            "gemini": AgentConfig(
                name="gemini",
                enabled=True,
                kind="mock",
                capabilities=["research", "writing", "docs", "synthesis"],
                instruction_file="prompts/agents/gemini.md",
            ),
        },
    )

def config_path(project_root: Path) -> Path:
    return project_root / CONFIG_FILENAME

def load_config(project_root: Path) -> PromptClawConfig:
    raw = read_json(config_path(project_root))
    if raw is None:
        raise FileNotFoundError(f"Missing config: {config_path(project_root)}")
    agents = {
        name: AgentConfig(name=name, **{k: v for k, v in agent.items() if k != "name"})
        for name, agent in raw.get("agents", {}).items()
    }
    return PromptClawConfig(
        project=ProjectConfig(**raw["project"]),
        artifacts=ArtifactConfig(**raw.get("artifacts", {})),
        control_plane=ControlPlaneConfig(**raw.get("control_plane", {})),
        routing=RoutingConfig(**raw.get("routing", {})),
        agents=agents,
    )

def save_config(project_root: Path, config: PromptClawConfig) -> None:
    raw = asdict(config)
    write_json(config_path(project_root), raw)

def validate_config(config: PromptClawConfig) -> list[str]:
    issues: list[str] = []
    if not config.project.name.strip():
        issues.append("project.name must not be empty")
    if config.control_plane.mode not in {"heuristic", "agent"}:
        issues.append("control_plane.mode must be 'heuristic' or 'agent'")
    if config.routing.max_retries < 0:
        issues.append("routing.max_retries must be >= 0")
    if not config.agents:
        issues.append("at least one agent must be defined")
    enabled_agents = [agent for agent in config.agents.values() if agent.enabled]
    if not enabled_agents:
        issues.append("at least one agent must be enabled")
    if config.control_plane.mode == "agent":
        if not config.control_plane.agent:
            issues.append("control_plane.agent is required when mode='agent'")
        elif config.control_plane.agent not in config.agents:
            issues.append("control_plane.agent must refer to a defined agent")
    for name, agent in config.agents.items():
        if agent.kind not in {"mock", "echo", "command"}:
            issues.append(f"agent '{name}' has unsupported kind '{agent.kind}'")
        if agent.kind == "command" and not (agent.shell_command or agent.command):
            issues.append(f"agent '{name}' is command mode but has no command")
    return issues
