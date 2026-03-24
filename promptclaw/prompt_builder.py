from __future__ import annotations

from pathlib import Path

from .models import AgentConfig, RouteDecision
from .utils import read_text, truncate

def load_instruction(project_root: Path, instruction_file: str, default_text: str) -> str:
    if not instruction_file:
        return default_text
    path = project_root / instruction_file
    if not path.exists():
        return default_text
    return read_text(path)

def build_routing_prompt(
    control_instruction: str,
    task_text: str,
    memory_text: str,
    agent_catalog: str,
) -> str:
    return (
        f"{control_instruction.strip()}\n\n"
        "# Task\n"
        f"{task_text.strip()}\n\n"
        "# Project Memory\n"
        f"{truncate(memory_text or '(no project memory yet)', 4000)}\n\n"
        "# Available Agents\n"
        f"{agent_catalog.strip()}\n\n"
        "# Output\n"
        "Return JSON with these exact keys: "
        "ambiguous, clarification_question, lead_agent, verifier_agent, reason, subtask_brief, task_type, confidence."
    )

def build_lead_prompt(
    agent_instruction: str,
    task_text: str,
    decision: RouteDecision,
    memory_text: str,
) -> str:
    return (
        f"{agent_instruction.strip()}\n\n"
        "# Assigned Role\n"
        "Lead\n\n"
        "# Task\n"
        f"{task_text.strip()}\n\n"
        "# Task Type\n"
        f"{decision.task_type}\n\n"
        "# Handoff Brief\n"
        f"{decision.subtask_brief.strip()}\n\n"
        "# Project Memory\n"
        f"{truncate(memory_text or '(no project memory yet)', 4000)}\n\n"
        "# Required Output\n"
        "Produce markdown. Be explicit, structured, and implementation-oriented."
    )

def build_verify_prompt(
    agent_instruction: str,
    task_text: str,
    decision: RouteDecision,
    lead_output: str,
    memory_text: str,
) -> str:
    return (
        f"{agent_instruction.strip()}\n\n"
        "# Assigned Role\n"
        "Verifier\n\n"
        "# Original Task\n"
        f"{task_text.strip()}\n\n"
        "# Lead Output To Review\n"
        f"{truncate(lead_output, 12000)}\n\n"
        "# Route Context\n"
        f"Task type: {decision.task_type}\nReason: {decision.reason}\n\n"
        "# Project Memory\n"
        f"{truncate(memory_text or '(no project memory yet)', 3000)}\n\n"
        "# Required Output\n"
        "Produce markdown and include one explicit verdict line: "
        "VERDICT: PASS, VERDICT: PASS_WITH_NOTES, or VERDICT: FAIL."
    )

def build_retry_prompt(
    agent_instruction: str,
    task_text: str,
    verifier_output: str,
    prior_output: str,
    decision: RouteDecision,
) -> str:
    return (
        f"{agent_instruction.strip()}\n\n"
        "# Assigned Role\n"
        "Lead retry\n\n"
        "# Original Task\n"
        f"{task_text.strip()}\n\n"
        "# Previous Output\n"
        f"{truncate(prior_output, 10000)}\n\n"
        "# Verifier Feedback\n"
        f"{truncate(verifier_output, 10000)}\n\n"
        "# Required Output\n"
        "Produce a corrected markdown output that addresses the verifier's blocking issues."
    )
