"""Contextual animation system for CypherClaw's Tamagotchi pets.

Provides personality-driven narration lines, activity decorations, and
frame builders that reflect what an agent is *actually doing* rather than
showing generic spinners.
"""

from __future__ import annotations

import re
from typing import Final

# ---------------------------------------------------------------------------
# Contextual narration lines per agent / task category
# ---------------------------------------------------------------------------

NARRATIONS: Final[dict[str, dict[str, list[str]]]] = {
    "claude": {
        "architecture": [
            "contemplating the design...",
            "sketching blueprints in the mind...",
            "weighing trade-offs carefully...",
            "envisioning the structure...",
            "reasoning through layers...",
        ],
        "review": [
            "reading every line with care...",
            "checking for hidden bugs...",
            "cross-referencing the spec...",
            "pondering edge cases...",
            "composing thoughtful feedback...",
        ],
        "coding": [
            "writing elegant solutions...",
            "thinking in abstractions...",
            "considering the architecture...",
            "crafting clean code...",
        ],
        "research": [
            "diving into the docs...",
            "connecting the dots...",
            "building a mental model...",
            "synthesizing findings...",
        ],
        "default": [
            "deep in thought...",
            "processing carefully...",
            "reasoning step by step...",
            "almost there...",
        ],
    },
    "codex": {
        "coding": [
            "fingers flying across the keys...",
            "refactoring with precision...",
            "writing tests first...",
            "optimizing the hot path...",
            "squashing bugs like a pro...",
        ],
        "testing": [
            "running the test suite...",
            "checking edge cases...",
            "watching green checkmarks appear...",
            "hunting for regressions...",
        ],
        "deploy": [
            "syncing to the server...",
            "running migrations...",
            "watching the health check...",
            "crossing fingers...",
        ],
        "default": [
            "hacking away...",
            "in the zone...",
            "building something cool...",
            "shipping code...",
        ],
    },
    "gemini": {
        "research": [
            "searching the web...",
            "reading multiple sources...",
            "cross-referencing claims...",
            "fact-checking everything...",
            "assembling the puzzle...",
        ],
        "writing": [
            "drafting prose...",
            "finding the right words...",
            "polishing the narrative...",
            "weaving ideas together...",
        ],
        "image": [
            "painting pixels...",
            "composing the scene...",
            "adding final touches...",
            "bringing it to life...",
        ],
        "default": [
            "exploring possibilities...",
            "gathering information...",
            "synthesizing knowledge...",
            "connecting ideas...",
        ],
    },
    "cypherclaw": {
        "routing": [
            "deciding who's best for this...",
            "analyzing the request...",
            "consulting the skill scores...",
            "picking the right agent...",
        ],
        "default": [
            "orchestrating the team...",
            "keeping things running...",
            "monitoring all systems...",
            "ready for anything...",
        ],
    },
}

# ---------------------------------------------------------------------------
# Activity decorations  (small ASCII additions that cycle per frame)
# ---------------------------------------------------------------------------

ACTIVITY_DECORATIONS: Final[dict[str, list[str]]] = {
    "coding": ["  \u2328\ufe0f \u00b7\u00b7\u00b7", "  \u2328\ufe0f \u00b7\u00b7\u2022", "  \u2328\ufe0f \u00b7\u2022\u2022", "  \u2328\ufe0f \u2022\u2022\u2022", "  \u2328\ufe0f \u00b7\u00b7\u2022", "  \u2328\ufe0f \u00b7\u00b7\u00b7"],
    "thinking": ["  \U0001f4ad .", "  \U0001f4ad ..", "  \U0001f4ad ...", "  \U0001f4ad ....", "  \U0001f4ad ...", "  \U0001f4ad .."],
    "research": ["  \U0001f50d .", "  \U0001f50d .o", "  \U0001f50d .oO", "  \U0001f50d oO\u00b0", "  \U0001f50d O\u00b0\u00b7", "  \U0001f50d \u00b0\u00b7\u00b7"],
    "writing": ["  \u270d\ufe0f _", "  \u270d\ufe0f __", "  \u270d\ufe0f ___", "  \u270d\ufe0f ____", "  \u270d\ufe0f ___", "  \u270d\ufe0f __"],
    "deploy": ["  \U0001f680 \u25ab\u25ab\u25ab", "  \U0001f680 \u25aa\u25ab\u25ab", "  \U0001f680 \u25aa\u25aa\u25ab", "  \U0001f680 \u25aa\u25aa\u25aa", "  \U0001f680 \u25ab\u25aa\u25aa", "  \U0001f680 \u25ab\u25ab\u25aa"],
    "image": ["  \U0001f3a8 ~", "  \U0001f3a8 ~~", "  \U0001f3a8 ~~~", "  \U0001f3a8 ~~~~", "  \U0001f3a8 ~~~", "  \U0001f3a8 ~~"],
    "default": ["  \u26a1 \u2219", "  \u26a1 \u2219\u2219", "  \u26a1 \u2219\u2219\u2219", "  \u26a1 \u2219\u2219", "  \u26a1 \u2219", "  \u26a1"],
}

# ---------------------------------------------------------------------------
# Category detection from task description
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: Final[list[tuple[str, list[str]]]] = [
    ("architecture", ["architect", "design", "plan", "spec", "structure"]),
    ("review", ["review", "verify", "check", "audit"]),
    ("testing", ["test", "pytest", "coverage"]),
    ("deploy", ["deploy", "staging", "production", "server"]),
    ("research", ["research", "search", "find", "investigate"]),
    ("image", ["image", "draw", "generate", "picture"]),
    ("writing", ["write", "draft", "document", "compose"]),
    ("coding", ["code", "implement", "build", "fix", "refactor"]),
    ("routing", ["route", "decide"]),
]


def detect_task_category(task_desc: str) -> str:
    """Map a task description to a narration / decoration category.

    Scans *task_desc* for keywords and returns the first matching category.
    Falls back to ``"default"`` when nothing matches.
    """
    lower = task_desc.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}", lower):
                return category
    return "default"


# ---------------------------------------------------------------------------
# Decoration category mapping (some narration categories share decorations)
# ---------------------------------------------------------------------------

_DECORATION_MAP: Final[dict[str, str]] = {
    "architecture": "thinking",
    "review": "thinking",
    "coding": "coding",
    "testing": "coding",
    "deploy": "deploy",
    "research": "research",
    "writing": "writing",
    "image": "image",
    "routing": "thinking",
    "default": "default",
}


def _get_decorations(category: str) -> list[str]:
    """Return the decoration frames for a task category."""
    deco_key = _DECORATION_MAP.get(category, "default")
    return ACTIVITY_DECORATIONS.get(deco_key, ACTIVITY_DECORATIONS["default"])


def _get_narrations(agent: str, category: str) -> list[str]:
    """Return narration lines for an agent + task category."""
    agent_key = agent.lower()
    agent_narrations = NARRATIONS.get(agent_key, NARRATIONS.get("cypherclaw", {}))
    lines = agent_narrations.get(category)
    if lines:
        return lines
    return agent_narrations.get("default", ["working..."])


# ---------------------------------------------------------------------------
# Agent icon lookup (mirrors player.py)
# ---------------------------------------------------------------------------

_AGENT_ICONS: Final[dict[str, str]] = {
    "claude": "\U0001f7e3",    # purple circle
    "codex": "\U0001f7e2",     # green circle
    "gemini": "\U0001f535",    # blue circle
    "cypherclaw": "\U0001f9e0",  # brain
}


# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------

def build_contextual_frames(
    agent: str,
    task_desc: str,
    pet_frames: list[str] | None = None,
    num_frames: int = 6,
) -> list[str]:
    """Build rich animated frames with pet sprite, contextual narration, and activity decoration.

    Each frame combines:
    - The pet's ASCII sprite (in a code block for monospace)
    - An activity decoration animation
    - A narration line that reflects what the agent is experiencing

    Parameters
    ----------
    agent:
        Agent name (``"claude"``, ``"codex"``, ``"gemini"``, ``"cypherclaw"``).
    task_desc:
        A short description of the current task, used for category detection.
    pet_frames:
        Optional list of ASCII pet sprite strings (one per animation frame).
        When *None* a simple placeholder is used.
    num_frames:
        How many frames to generate.

    Returns
    -------
    list[str]
        Ready-to-display frame strings.
    """
    category = detect_task_category(task_desc)
    narrations = _get_narrations(agent, category)
    decorations = _get_decorations(category)
    icon = _AGENT_ICONS.get(agent.lower(), "\U0001f7e3")

    frames: list[str] = []
    for i in range(num_frames):
        # Sprite
        if pet_frames:
            sprite = pet_frames[i % len(pet_frames)]
        else:
            sprite = f"  /\\_/\\\n ( o.o )  {agent}\n  > ^ <"

        narration = narrations[i % len(narrations)]
        decoration = decorations[i % len(decorations)]

        frame = (
            f"```\n"
            f"{sprite}\n"
            f"```\n"
            f"{decoration}\n"
            f"{icon} {narration}"
        )
        frames.append(frame)

    return frames


def build_thinking_frames(
    pet_portrait: str | None = None,
    num_frames: int = 6,
) -> list[str]:
    """Build frames for the CypherClaw thinking/routing phase.

    Uses cypherclaw narrations with thinking decorations.

    Parameters
    ----------
    pet_portrait:
        Optional ASCII portrait string for the CypherClaw pet.
        When *None* a simple placeholder is used.
    num_frames:
        How many frames to generate.

    Returns
    -------
    list[str]
        Ready-to-display frame strings.
    """
    narrations = _get_narrations("cypherclaw", "routing")
    decorations = _get_decorations("routing")
    icon = _AGENT_ICONS["cypherclaw"]

    frames: list[str] = []
    for i in range(num_frames):
        if pet_portrait:
            sprite = pet_portrait
        else:
            sprite = "  /\\_/\\\n ( o.o )  cypherclaw\n  > ^ <"

        narration = narrations[i % len(narrations)]
        decoration = decorations[i % len(decorations)]

        frame = (
            f"```\n"
            f"{sprite}\n"
            f"```\n"
            f"{decoration}\n"
            f"{icon} {narration}"
        )
        frames.append(frame)

    return frames
