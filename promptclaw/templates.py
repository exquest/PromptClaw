from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .coherence.protocol import coherence_instructions
from .config import default_project_config

STARTER_DOC = """# Project Guide

```text
 /\\_/\\
( o.o )  PromptClaw project guide 🦀✨
 > ^ <
```

## What this project is

This is a PromptClaw project. The orchestrator reads your prompts, routes work to agents,
writes all handoffs to `.promptclaw/`, and pauses only for blocking ambiguity.

## Fastest setup path

1. Run the startup wizard: `promptclaw wizard .`
2. Review `docs/STARTUP_PROFILE.md`
3. Run `promptclaw doctor .`
4. Run `promptclaw bootstrap .`
5. Replace mock agents with live command agents when ready.

## Where the wizard writes

- `prompts/00-project-vision.md`
- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`
- `docs/STARTUP_PROFILE.md`
- `docs/STARTUP_TRANSCRIPT.md`
"""

CONTROL_ROUTING = """You are the PromptClaw control plane.
Choose the best lead agent based on the task.
Choose a different verifier when one is available.
Ask a clarification question only if the task cannot be executed responsibly without user input.
When you ask a question, make it concrete and specific to the missing detail.

Output JSON only with these keys:
- ambiguous
- clarification_question
- lead_agent
- verifier_agent
- reason
- subtask_brief
- task_type
- confidence
"""

CONTROL_REVIEW = """You are reviewing whether a run should continue, retry, or stop.
Prefer one retry for fixable blocking issues.
Prefer stop when the task is complete.
"""

CONTROL_SUMMARIZE = """Summarize the run in concise markdown for future memory.
Preserve major decisions and unresolved issues.
"""

AGENT_CODEX = """# Codex Lane

You are Codex inside PromptClaw. 🛠️

## Preferred work
- coding
- implementation
- refactoring
- tests
- bug fixes

## Output style
Produce markdown that is direct, structured, and execution-focused.
"""

AGENT_CLAUDE = """# Claude Lane

You are Claude inside PromptClaw. 🧭

## Preferred work
- architecture
- specification
- review
- verification
- orchestration logic

## Output style
Produce markdown with crisp structure and clear reasoning.
"""

AGENT_GEMINI = """# Gemini Lane

You are Gemini inside PromptClaw. 📚

## Preferred work
- research
- synthesis
- writing
- documentation
- comparisons

## Output style
Produce markdown optimized for clarity and synthesis.
"""

# Shared coherence standing-instructions appended to every scaffolded agent prompt, so agents
# emit ```decision/```tension blocks the engine captures and follow the collaboration protocol.
_COHERENCE_SECTION = "## Coherence — standing instructions\n\n" + coherence_instructions()

PROJECT_VISION = """# Project Vision

Describe the claw you want to build.

Include:
- the kinds of tasks it should handle
- what success looks like
- what it should never do
- when it should ask the user a question

Tip: the startup wizard can fill this for you one question at a time.
"""

AGENT_ROLES = """# Agent Roles

Describe each agent available to this claw.

For each agent, include:
- strengths
- weaknesses
- ideal task types
- tasks it should verify
- tasks it should avoid

Tip: the startup wizard can draft this from your answers.
"""

ROUTING_RULES = """# Routing Rules

Write the routing policy in plain language.

Include:
- how to choose the lead agent
- how to choose a verifier
- when to ask a clarification question
- when to retry after verification fail
- when to stop

Tip: the startup wizard can draft this from your answers.
"""

SAMPLE_TASK = """Create a development plan for adding an artifact-based handoff protocol to a multi-agent prompt system."""

AMBIGUOUS_TASK = """Make something good for this project somehow."""

_REQUIRED_STARTUP_PROMPT_PATHS = (
    "prompts/00-project-vision.md",
    "prompts/01-agent-roles.md",
    "prompts/02-routing-rules.md",
)


@dataclass(frozen=True)
class ScaffoldTemplateEntry:
    path: str
    category: str
    content: str
    size_bytes: int


@dataclass(frozen=True)
class ScaffoldTemplateReport:
    project_name: str
    file_count: int
    total_size_bytes: int
    categories: dict[str, int]
    required_prompt_paths: tuple[str, ...]
    missing_required_prompt_paths: tuple[str, ...]
    entries: tuple[ScaffoldTemplateEntry, ...]


def _scaffold_contents(project_name: str) -> dict[str, str]:
    config = default_project_config(project_name)
    return {
        "promptclaw.json": json.dumps({
            "project": {
                "name": config.project.name,
                "description": config.project.description,
            },
            "artifacts": {
                "root": config.artifacts.root,
            },
            "control_plane": {
                "mode": config.control_plane.mode,
                "agent": config.control_plane.agent,
                "allow_fallback": config.control_plane.allow_fallback,
            },
            "routing": {
                "verification_enabled": config.routing.verification_enabled,
                "max_retries": config.routing.max_retries,
                "ask_user_on_ambiguity": config.routing.ask_user_on_ambiguity,
                "default_task_type": config.routing.default_task_type,
            },
            "agents": {
                name: {
                    "enabled": agent.enabled,
                    "kind": agent.kind,
                    "shell_command": agent.shell_command,
                    "command": agent.command,
                    "env": agent.env,
                    "capabilities": agent.capabilities,
                    "instruction_file": agent.instruction_file,
                }
                for name, agent in config.agents.items()
            },
        }, indent=2) + "\n",
        "docs/PROJECT_GUIDE.md": STARTER_DOC + "\n",
        "prompts/control/routing.md": CONTROL_ROUTING + "\n",
        "prompts/control/review.md": CONTROL_REVIEW + "\n",
        "prompts/control/summarize.md": CONTROL_SUMMARIZE + "\n",
        "prompts/agents/codex.md": AGENT_CODEX + "\n\n" + _COHERENCE_SECTION,
        "prompts/agents/claude.md": AGENT_CLAUDE + "\n\n" + _COHERENCE_SECTION,
        "prompts/agents/gemini.md": AGENT_GEMINI + "\n\n" + _COHERENCE_SECTION,
        "prompts/00-project-vision.md": PROJECT_VISION + "\n",
        "prompts/01-agent-roles.md": AGENT_ROLES + "\n",
        "prompts/02-routing-rules.md": ROUTING_RULES + "\n",
        ".promptclaw/memory/project-memory.md": "# Project memory\n",
        "examples/tasks/sample-task.md": SAMPLE_TASK + "\n",
        "examples/tasks/ambiguous-task.md": AMBIGUOUS_TASK + "\n",
    }


def template_category(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized == "promptclaw.json":
        return "config"
    if normalized.startswith("docs/"):
        return "docs"
    if normalized.startswith("prompts/control/"):
        return "control_prompt"
    if normalized.startswith("prompts/agents/"):
        return "agent_prompt"
    if normalized in _REQUIRED_STARTUP_PROMPT_PATHS:
        return "startup_prompt"
    if normalized.startswith(".promptclaw/memory/"):
        return "memory"
    if normalized.startswith("examples/"):
        return "example"
    return "other"


def required_startup_prompt_paths() -> tuple[str, ...]:
    return _REQUIRED_STARTUP_PROMPT_PATHS


def coherence_protocol_section() -> str:
    return _COHERENCE_SECTION


def default_constitution_text() -> str:
    constitution_path = Path(__file__).resolve().parent.parent / "constitution.yaml"
    return constitution_path.read_text(encoding="utf-8")


def scaffold_template_entries(project_name: str) -> tuple[ScaffoldTemplateEntry, ...]:
    entries: list[ScaffoldTemplateEntry] = []
    for path, content in _scaffold_contents(project_name).items():
        entries.append(
            ScaffoldTemplateEntry(
                path=path,
                category=template_category(path),
                content=content,
                size_bytes=len(content.encode("utf-8")),
            )
        )
    return tuple(entries)


def scaffold_template_report(project_name: str) -> ScaffoldTemplateReport:
    entries = scaffold_template_entries(project_name)
    category_counts: dict[str, int] = {}
    entry_paths: set[str] = set()
    total_size_bytes = 0
    for entry in entries:
        category_counts[entry.category] = category_counts.get(entry.category, 0) + 1
        entry_paths.add(entry.path)
        total_size_bytes += entry.size_bytes

    missing_required: list[str] = []
    for path in required_startup_prompt_paths():
        if path not in entry_paths:
            missing_required.append(path)

    return ScaffoldTemplateReport(
        project_name=project_name,
        file_count=len(entries),
        total_size_bytes=total_size_bytes,
        categories={name: category_counts[name] for name in sorted(category_counts)},
        required_prompt_paths=required_startup_prompt_paths(),
        missing_required_prompt_paths=tuple(missing_required),
        entries=entries,
    )


def summarize_scaffold_templates(project_name: str) -> dict[str, object]:
    report = scaffold_template_report(project_name)
    entries: list[dict[str, object]] = []
    for entry in report.entries:
        entries.append({
            "path": entry.path,
            "category": entry.category,
            "size_bytes": entry.size_bytes,
        })
    return {
        "project_name": report.project_name,
        "file_count": report.file_count,
        "total_size_bytes": report.total_size_bytes,
        "categories": dict(report.categories),
        "required_prompt_paths": list(report.required_prompt_paths),
        "missing_required_prompt_paths": list(report.missing_required_prompt_paths),
        "entries": entries,
    }


def project_scaffold(project_name: str) -> dict[str, str]:
    return _scaffold_contents(project_name)
