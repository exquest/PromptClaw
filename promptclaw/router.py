from __future__ import annotations

import json

from .models import AgentConfig, PromptClawConfig, RouteDecision
from .utils import extract_json_object, truthy

TASK_KEYWORDS = {
    "code": ["code", "implement", "refactor", "bug", "function", "script", "python", "typescript", "test", "build"],
    "architecture": ["architecture", "design", "system", "workflow", "protocol", "orchestrator", "state", "handoff", "integration"],
    "research": ["research", "compare", "analyze", "summary", "synthesize", "market", "literature", "document"],
    "docs": ["manual", "docs", "documentation", "guide", "writeup", "instruction"],
    "image": ["image", "generate", "picture", "visual", "drawing", "illustration", "art", "photo"],
}

AMBIGUITY_MARKERS = [
    "something",
    "somehow",
    "maybe",
    "not sure",
    "unclear",
    "figure out",
    "whatever",
    "tbd",
    "???",
    "make it better",
    "make it good",
]


def agent_catalog_markdown(config: PromptClawConfig) -> str:
    lines: list[str] = []
    for name, agent in config.agents.items():
        status = "enabled" if agent.enabled else "disabled"
        lines.append(f"- {name}: {status}; capabilities = {', '.join(agent.capabilities) or 'none'}")
    return "\n".join(lines)


def detect_ambiguity(task_text: str) -> tuple[bool, str | None]:
    lowered = task_text.lower()
    if "# clarification answer" in lowered:
        answer = lowered.split("# clarification answer", 1)[1].strip()
        if answer:
            return False, None

    task_type = infer_task_type(task_text)
    if len(task_text.strip()) < 25:
        return True, generate_clarification_question(task_text, task_type, reason="too_short")

    for marker in AMBIGUITY_MARKERS:
        if marker in lowered:
            return True, generate_clarification_question(task_text, task_type, reason="vague")

    if task_type == "code" and not any(token in lowered for token in ["python", "typescript", "javascript", "go", "rust", "java", "language"]):
        if any(token in lowered for token in ["module", "script", "function", "feature"]):
            return True, "Which language or stack should PromptClaw target, and should it return code only or code plus tests?"

    if task_type in {"research", "docs"} and not any(token in lowered for token in ["summary", "guide", "manual", "report", "brief", "plan"]):
        return True, "What deliverable do you want here: a summary, a guide, a report, a plan, or something else?"

    return False, None


def generate_clarification_question(task_text: str, task_type: str, reason: str = "vague") -> str:
    lowered = task_text.lower()
    if task_type == "code":
        return "Should PromptClaw produce implementation code, a plan, tests, or some combination of those?"
    if task_type == "architecture":
        return "What outcome do you want from this architecture task: a design doc, a task plan, a state machine, or another artifact?"
    if task_type == "research":
        return "What should the research focus on, and do you want a quick summary, a comparison, or a deeper report?"
    if task_type == "docs":
        return "What doc format do you want: README, setup guide, instruction manual, or something else?"
    if "improve" in lowered or "better" in lowered:
        return "What specific part should be improved, and what finished output should PromptClaw return?"
    if reason == "too_short":
        return "What outcome, format, and key constraints should PromptClaw target for this task?"
    return "What specific output should PromptClaw produce here, and what does success look like?"


def infer_task_type(task_text: str, default_task_type: str = "general") -> str:
    lowered = task_text.lower()
    scores = {name: 0 for name in TASK_KEYWORDS}
    for family, keywords in TASK_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                scores[family] += 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return default_task_type
    return best


def score_agent_for_task(agent: AgentConfig, task_text: str, task_type: str, trust_score: float = 1.0) -> float:
    score = 0
    lowered = task_text.lower()
    for capability in agent.capabilities:
        if capability.lower() == task_type:
            score += 3
        if capability.lower() in lowered:
            score += 1
    if task_type == "code" and "implementation" in [cap.lower() for cap in agent.capabilities]:
        score += 2
    if task_type == "architecture" and "verification" in [cap.lower() for cap in agent.capabilities]:
        score += 1
    if task_type == "research" and "docs" in [cap.lower() for cap in agent.capabilities]:
        score += 1
    return score * trust_score


def choose_lead_agent(config: PromptClawConfig, task_text: str, task_type: str,
                      trust_scores: dict[str, float] | None = None) -> str:
    candidates = [agent for agent in config.agents.values() if agent.enabled]
    # Filter out agents with trust < 0.2
    if trust_scores:
        trusted = [a for a in candidates if trust_scores.get(a.name, 1.0) >= 0.2]
        if trusted:
            candidates = trusted
    if not candidates:
        raise ValueError("No enabled agents available")
    ranked = sorted(
        candidates,
        key=lambda agent: (
            score_agent_for_task(agent, task_text, task_type,
                                trust_score=trust_scores.get(agent.name, 1.0) if trust_scores else 1.0),
            len(agent.capabilities),
        ),
        reverse=True,
    )
    return ranked[0].name


def choose_verifier_agent(config: PromptClawConfig, lead_agent: str, task_text: str, task_type: str,
                          trust_scores: dict[str, float] | None = None) -> str | None:
    candidates = [agent for agent in config.agents.values() if agent.enabled and agent.name != lead_agent]
    # Filter out agents with trust < 0.2
    if trust_scores:
        trusted = [a for a in candidates if trust_scores.get(a.name, 1.0) >= 0.2]
        if trusted:
            candidates = trusted
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda agent: (
            ("verification" in [cap.lower() for cap in agent.capabilities]),
            score_agent_for_task(agent, task_text, task_type,
                                trust_score=trust_scores.get(agent.name, 1.0) if trust_scores else 1.0),
            len(agent.capabilities),
        ),
        reverse=True,
    )
    return ranked[0].name


def heuristic_route(config: PromptClawConfig, task_text: str,
                    trust_scores: dict[str, float] | None = None) -> RouteDecision:
    ambiguous, question = detect_ambiguity(task_text)
    task_type = infer_task_type(task_text, config.routing.default_task_type)
    lead = choose_lead_agent(config, task_text, task_type, trust_scores=trust_scores)
    verifier = choose_verifier_agent(config, lead, task_text, task_type, trust_scores=trust_scores) if config.routing.verification_enabled else None
    confidence = 0.35 if ambiguous else 0.72
    return RouteDecision(
        ambiguous=ambiguous,
        clarification_question=question,
        lead_agent=lead,
        verifier_agent=verifier,
        reason=f"Heuristic routing selected {lead} for task type '{task_type}'.",
        subtask_brief=f"Handle the task as a {task_type} task and produce a high-signal markdown artifact.",
        task_type=task_type,
        confidence=confidence,
    )


def parse_route_decision(text: str) -> RouteDecision | None:
    raw_json = extract_json_object(text)
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    required = {"lead_agent", "reason", "subtask_brief", "task_type"}
    if not required.issubset(data.keys()):
        return None
    return RouteDecision(
        ambiguous=truthy(data.get("ambiguous", False)),
        clarification_question=data.get("clarification_question"),
        lead_agent=str(data["lead_agent"]),
        verifier_agent=data.get("verifier_agent"),
        reason=str(data["reason"]),
        subtask_brief=str(data["subtask_brief"]),
        task_type=str(data["task_type"]),
        confidence=float(data.get("confidence", 0.5)),
    )


def route_markdown(decision: RouteDecision) -> str:
    return (
        "# Route Decision\n\n"
        f"- Ambiguous: {'yes' if decision.ambiguous else 'no'}\n"
        f"- Lead agent: {decision.lead_agent}\n"
        f"- Verifier agent: {decision.verifier_agent or 'none'}\n"
        f"- Task type: {decision.task_type}\n"
        f"- Confidence: {decision.confidence:.2f}\n\n"
        "## Reason\n"
        f"{decision.reason}\n\n"
        "## Handoff brief\n"
        f"{decision.subtask_brief}\n\n"
        + (
            "## Clarification question\n"
            f"{decision.clarification_question}\n"
            if decision.ambiguous and decision.clarification_question
            else ""
        )
    )
