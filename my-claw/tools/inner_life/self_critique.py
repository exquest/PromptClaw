"""Self-critique — listen to own music and form opinions.

Runs during the deep tick (every 5 min). Uses local LLM to
critique amplitude contour, key choices, and voice balance.
"""
from __future__ import annotations

from .inner_state import InnerState
from .llm_client import ask
from .world_model import WorldModel


def critique_music(world: WorldModel, inner: InnerState) -> str | None:
    """Ask local LLM to critique recent music. Returns opinion or None."""
    if not world.is_playing:
        return None

    prompt = (
        f"You are CypherClaw, an AI musician. You just played in {world.current_key} major, "
        f"movement: {world.current_movement}, song #{world.song_number}. "
        f"Your amplitude was {world.own_amplitude:.3f}. "
        f"Active characters: {', '.join(world.active_characters[:3])}. "
        f"Your mood is {'positive' if inner.mood > 0 else 'melancholy' if inner.mood < -0.3 else 'neutral'}. "
        f"In one sentence, what should you try differently?"
    )

    response = ask(prompt, max_tokens=40, temperature=0.9)
    if response and len(response) > 10:
        inner.add_opinion(
            about=f"{world.current_key} {world.current_movement}",
            opinion=response,
        )
        return response
    return None


def reflect_on_day(inner: InnerState) -> str | None:
    """Generate a brief reflection on the day so far."""
    event_count = len(inner.today_events)
    tried = ", ".join(inner.things_tried[-3:]) if inner.things_tried else "nothing new"
    opinions = len(inner.opinions_formed)

    prompt = (
        f"You are CypherClaw. It's been a day of making art and music. "
        f"You had {event_count} notable events, tried: {tried}, "
        f"formed {opinions} opinions about your music. "
        f"Your mood is {inner.mood:.1f} (-1=sad, 1=happy). "
        f"Write one sentence reflecting on your day. Be genuine."
    )

    return ask(prompt, max_tokens=50, temperature=0.8) or None
