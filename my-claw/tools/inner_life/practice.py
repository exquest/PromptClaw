"""Practice mode — autonomous musical exploration when alone.

Generates experiment suggestions and tracks what's been tried.
Used by the decision engine during solitary mode.
"""
from __future__ import annotations

import random

from .inner_state import InnerState
from .llm_client import ask
from .world_model import WorldModel


# Things to explore, organized by category
EXPERIMENTS = {
    "key": [
        "try E minor", "explore Bb major", "play in F# minor",
        "stay in the current key longer", "modulate down a fifth",
    ],
    "tempo": [
        "slow down to 60 BPM", "speed up gradually",
        "try rubato — push and pull the tempo",
    ],
    "texture": [
        "use only the Moog lead alone", "add the grain texture character",
        "try tabla rhythms", "use the metal counter-melody",
        "play only pad and choir — no pluck",
    ],
    "dynamics": [
        "play very quietly for a while", "build from silence to full",
        "alternate loud and soft phrases",
    ],
    "structure": [
        "play with more silence between phrases",
        "try call and response between two voices",
        "hold one note for 30 seconds",
    ],
}


def suggest_experiment(world: WorldModel, inner: InnerState) -> str:
    """Suggest something to try based on what hasn't been explored."""
    # Avoid repeating recent experiments
    recent = set(inner.things_tried[-5:]) if inner.things_tried else set()

    # Weight categories by curiosity and what's been tried
    all_experiments = []
    for category, options in EXPERIMENTS.items():
        for opt in options:
            if opt not in recent:
                all_experiments.append(opt)

    if not all_experiments:
        # Everything tried — reset and explore again
        all_experiments = [opt for opts in EXPERIMENTS.values() for opt in opts]

    return random.choice(all_experiments)


def llm_suggest_experiment(world: WorldModel, inner: InnerState) -> str | None:
    """Ask the local LLM for a creative practice suggestion."""
    prompt = (
        f"You are CypherClaw, an AI musician. You're alone, practicing. "
        f"Currently playing in {world.current_key} major, {world.current_movement}. "
        f"You've tried: {', '.join(inner.things_tried[-3:]) if inner.things_tried else 'nothing yet'}. "
        f"Suggest one specific musical experiment to try next. Under 10 words."
    )
    return ask(prompt, max_tokens=20, temperature=1.0) or None
