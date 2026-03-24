from __future__ import annotations

import json

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


def project_scaffold(project_name: str) -> dict[str, str]:
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
        "prompts/agents/codex.md": AGENT_CODEX + "\n",
        "prompts/agents/claude.md": AGENT_CLAUDE + "\n",
        "prompts/agents/gemini.md": AGENT_GEMINI + "\n",
        "prompts/00-project-vision.md": PROJECT_VISION + "\n",
        "prompts/01-agent-roles.md": AGENT_ROLES + "\n",
        "prompts/02-routing-rules.md": ROUTING_RULES + "\n",
        ".promptclaw/memory/project-memory.md": "# Project memory\n",
        "examples/tasks/sample-task.md": SAMPLE_TASK + "\n",
        "examples/tasks/ambiguous-task.md": AMBIGUOUS_TASK + "\n",
    }
