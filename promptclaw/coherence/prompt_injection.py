"""Prompt injection — format decision context and constitutional rules for inclusion in prompts."""

from __future__ import annotations

from typing import Any

from .decision_store import Decision


def format_decision_context(decisions: list[Decision]) -> str:
    """Format relevant decisions as a markdown block for prompt injection.

    Returns an empty string if no decisions are provided.
    """
    if not decisions:
        return ""

    lines: list[str] = ["## Active Decisions (DO NOT VIOLATE)"]
    for d in decisions:
        lines.append(f"\n### ADR: {d.title}")
        lines.append(f"- **Decision:** {d.decision_text}")
        lines.append(f"- **Rationale:** {d.rationale}")
        if d.file_paths:
            lines.append(f"- **Affects:** {', '.join(d.file_paths)}")
        if d.tags:
            lines.append(f"- **Tags:** {', '.join(d.tags)}")

    return "\n".join(lines) + "\n"


def format_constitutional_context(rules: list[Any] | None = None, mode: Any = None) -> str:
    """Format active constitutional rules as a markdown section agents can read.

    Args:
        rules: List of Rule objects from the Constitution.
        mode: The current EnforcementMode.

    Returns a markdown block describing the active rules, or empty string if none.
    """
    if not rules:
        return ""

    from .models import EnforcementMode, ViolationSeverity

    mode_label = mode.value if isinstance(mode, EnforcementMode) else str(mode or "unknown")

    lines: list[str] = [f"## Constitutional Rules (enforcement: {mode_label})"]
    for r in rules:
        severity_label = r.severity.value.upper() if isinstance(r.severity, ViolationSeverity) else str(r.severity)
        lines.append(f"\n- **[{severity_label}] {r.rule_id}**: {r.description}")
        if r.message and r.message != r.description:
            lines.append(f"  - {r.message}")

    return "\n".join(lines) + "\n"
