"""Self-healing diagnostics: maps exceptions to explanations, fix suggestions, and auto-recovery hints."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Diagnosis:
    error_type: str
    phase: str
    message: str
    suggestions: list[str] = field(default_factory=list)
    auto_recoverable: bool = False
    recovery_action: str = ""


def diagnose(exc: Exception, phase: str = "", context: dict[str, Any] | None = None) -> Diagnosis:
    """Analyze an exception and return a structured diagnosis with fix suggestions."""
    context = context or {}
    exc_type = type(exc).__name__

    # --- Config / file errors ---
    if isinstance(exc, FileNotFoundError):
        path = str(exc)
        if "promptclaw.json" in path or "Missing config" in path:
            return Diagnosis(
                error_type=exc_type,
                phase=phase,
                message=f"Config file not found: {exc}",
                suggestions=[
                    "Run `promptclaw init <path>` to create a new project.",
                    "Check that you're pointing to the correct project root directory.",
                    "If the config was deleted, re-initialize with `promptclaw init --name <name> <path>`.",
                ],
            )
        if "state.json" in path:
            return Diagnosis(
                error_type=exc_type,
                phase=phase,
                message=f"Run state not found: {exc}",
                suggestions=[
                    "Verify the run-id exists with `promptclaw status <project-root>`.",
                    "The run may not have been saved — check the .promptclaw/runs/ directory.",
                ],
            )
        return Diagnosis(
            error_type=exc_type,
            phase=phase,
            message=f"File not found: {exc}",
            suggestions=[
                f"Check that the path exists: {exc}",
                "If this is an instruction file, verify `instruction_file` in promptclaw.json.",
            ],
        )

    if isinstance(exc, PermissionError):
        return Diagnosis(
            error_type=exc_type,
            phase=phase,
            message=f"Permission denied: {exc}",
            suggestions=[
                "Check file/directory permissions in the project root.",
                "Ensure the .promptclaw/ directory is writable.",
                "On macOS/Linux: `chmod -R u+rw .promptclaw/`",
            ],
        )

    # --- JSON / config parse errors ---
    if isinstance(exc, json.JSONDecodeError):
        return Diagnosis(
            error_type=exc_type,
            phase=phase,
            message=f"Invalid JSON in config: {exc}",
            suggestions=[
                "Check promptclaw.json for syntax errors (trailing commas, missing quotes).",
                "Run `python -m json.tool promptclaw.json` to validate the JSON.",
                "Re-initialize the config with `promptclaw init`.",
            ],
        )

    # --- Key errors (missing agent, missing config section) ---
    if isinstance(exc, KeyError):
        key = str(exc).strip("'\"")
        agent_name = context.get("agent_name", key)
        return Diagnosis(
            error_type=exc_type,
            phase=phase,
            message=f"Missing key: {key}",
            suggestions=[
                f"Agent '{agent_name}' is not defined in promptclaw.json.",
                "Check `promptclaw show-config <project-root>` to see available agents.",
                "Add the missing agent to the `agents` section of promptclaw.json.",
                "Run `promptclaw doctor <project-root>` to validate the full config.",
            ],
            auto_recoverable=phase in ("lead", "verify", "retry"),
            recovery_action=f"fallback_agent",
        )

    if isinstance(exc, ValueError):
        msg = str(exc)
        if "awaiting_user" in msg or "not awaiting" in msg:
            return Diagnosis(
                error_type=exc_type,
                phase=phase,
                message=msg,
                suggestions=[
                    "This run is not in a resumable state.",
                    "Use `promptclaw status <project-root> --run-id <id>` to check current status.",
                ],
            )
        if "control_plane" in msg or "control plane" in msg:
            return Diagnosis(
                error_type=exc_type,
                phase=phase,
                message=msg,
                suggestions=[
                    "The control plane agent is misconfigured.",
                    "Set `control_plane.allow_fallback: true` in promptclaw.json to auto-fallback to heuristic routing.",
                    "Or fix `control_plane.agent` to point to a valid agent name.",
                ],
                auto_recoverable=True,
                recovery_action="fallback_heuristic",
            )
        return Diagnosis(
            error_type=exc_type,
            phase=phase,
            message=msg,
            suggestions=[
                "Run `promptclaw doctor <project-root>` to validate your configuration.",
            ],
        )

    # --- Subprocess / command errors ---
    if isinstance(exc, subprocess.TimeoutExpired):
        agent_name = context.get("agent_name", "unknown")
        return Diagnosis(
            error_type=exc_type,
            phase=phase,
            message=f"Agent '{agent_name}' timed out after {exc.timeout}s",
            suggestions=[
                f"The command for agent '{agent_name}' took too long.",
                "Check if the agent process is hanging or waiting for input.",
                "Consider increasing the timeout or simplifying the task.",
            ],
            auto_recoverable=True,
            recovery_action="fallback_mock",
        )

    if isinstance(exc, OSError) and "No such file or directory" in str(exc):
        agent_name = context.get("agent_name", "unknown")
        return Diagnosis(
            error_type=exc_type,
            phase=phase,
            message=f"Agent command executable not found: {exc}",
            suggestions=[
                f"The command for agent '{agent_name}' could not be found.",
                "Run `promptclaw doctor <project-root>` to check agent executables.",
                "Ensure the program is installed and on your PATH.",
                "Or switch the agent to `kind: mock` for testing.",
            ],
            auto_recoverable=True,
            recovery_action="fallback_mock",
        )

    # --- Type errors (bad config shape) ---
    if isinstance(exc, TypeError):
        return Diagnosis(
            error_type=exc_type,
            phase=phase,
            message=f"Config shape error: {exc}",
            suggestions=[
                "Your promptclaw.json may have unexpected fields or wrong types.",
                "Run `promptclaw doctor <project-root>` to validate.",
                "Compare your config against the defaults with `promptclaw init --help`.",
            ],
        )

    if isinstance(exc, (RuntimeError, subprocess.CalledProcessError)):
        msg = str(exc)
        if "GEMINI_API_KEY" in msg and "not set" in msg:
            return Diagnosis(
                error_type="MissingEnvVar",
                phase=phase,
                message=f"GEMINI_API_KEY environment variable not set.",
                suggestions=[
                    "Export the key: `export GEMINI_API_KEY=<your-key>`",
                    "Or add it to your shell's .zshrc or .bash_profile.",
                    "Get a key from https://ai.google.dev",
                ],
                auto_recoverable=True,
                recovery_action="fallback_mock",
            )
        if "API_KEY" in msg and ("not set" in msg or "missing" in msg):
            return Diagnosis(
                error_type="MissingEnvVar",
                phase=phase,
                message=f"Required API key not found in environment.",
                suggestions=[
                    "Verify the required environment variables for this agent.",
                    "Check the agent's documentation or tool script for details.",
                ],
                auto_recoverable=True,
                recovery_action="fallback_mock",
            )

    # --- Catch-all ---
    return Diagnosis(
        error_type=exc_type,
        phase=phase,
        message=str(exc),
        suggestions=[
            "Run `promptclaw doctor <project-root>` to check for configuration issues.",
            f"Unexpected {exc_type} during {phase or 'execution'}: {exc}",
        ],
    )


def format_diagnosis(diag: Diagnosis) -> str:
    """Format a diagnosis into a human-readable error message with suggestions."""
    lines = []
    phase_label = f" [{diag.phase}]" if diag.phase else ""
    lines.append(f"Error{phase_label}: {diag.message}")
    lines.append("")
    if diag.auto_recoverable:
        lines.append(f"  Auto-recovery: {_describe_recovery(diag.recovery_action)}")
        lines.append("")
    if diag.suggestions:
        lines.append("  Suggestions:")
        for suggestion in diag.suggestions:
            lines.append(f"    - {suggestion}")
    return "\n".join(lines)


def _describe_recovery(action: str) -> str:
    descriptions = {
        "fallback_agent": "Falling back to an available agent.",
        "fallback_mock": "Falling back to mock mode for this agent.",
        "fallback_heuristic": "Falling back to heuristic routing.",
    }
    return descriptions.get(action, action)
