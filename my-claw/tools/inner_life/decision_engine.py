"""Decision Engine — weighted rule system for autonomous behavior.

Runs every slow tick (30s). Each rule returns Optional[Action].
Actions are collected, deduped by cooldown, sorted by priority,
and at most 2 are dispatched per tick. No LLM calls — this must
be fast (~50ms).
"""
from __future__ import annotations

import random
import time

from .actions import Action
from .inner_state import InnerState
from .narrative_arc import action_weight_for_phase, energy_for_phase
from .world_model import WorldModel


def decide(world: WorldModel, inner: InnerState) -> list[Action]:
    """Run all rules and return up to 2 actions to dispatch."""
    # Arc phase gates overall action probability
    weight = action_weight_for_phase(inner.arc_phase)
    if random.random() > weight:
        return []  # phase says be quiet

    candidates = []
    for rule in _RULES:
        action = rule(world, inner)
        if action is not None:
            candidates.append(action)

    # Sort by priority (highest first), take at most 2
    candidates.sort(key=lambda a: a.priority, reverse=True)
    return candidates[:2]


# ---------------------------------------------------------------------------
# Rules — each returns Optional[Action]
# ---------------------------------------------------------------------------

def _rule_acknowledge_arrival(world: WorldModel, inner: InnerState) -> Action | None:
    """Greet someone who just arrived."""
    if inner.mode != "aware":
        return None
    # Only greet within first 10 seconds of awareness
    if time.time() - inner.mode_entered_at > 10:
        return None

    greetings = [
        "...hello",
        "someone's here",
        "welcome",
        "i see you",
        "hi there",
    ]
    return Action(
        action_type="face_message",
        payload={"text": random.choice(greetings), "role": "system"},
        cooldown_key="last_face_message_at",
        min_cooldown_s=30.0,
        priority=2,
    )


def _rule_acknowledge_departure(world: WorldModel, inner: InnerState) -> Action | None:
    """Note when someone leaves."""
    if inner.mode != "solitary":
        return None
    # Only if we just transitioned to solitary
    if time.time() - inner.mode_entered_at > 10:
        return None

    farewells = [
        "...quiet again",
        "alone now",
        "back to practice",
        "the room breathes",
    ]
    return Action(
        action_type="face_message",
        payload={"text": random.choice(farewells), "role": "system"},
        cooldown_key="last_face_message_at",
        min_cooldown_s=30.0,
        priority=1,
    )


def _rule_music_influence(world: WorldModel, inner: InnerState) -> Action | None:
    """Suggest music changes based on arc position and mood."""
    if inner.mode == "performing":
        return None  # don't interfere with duet

    energy = energy_for_phase(inner.arc_phase)

    # Suggest silence during rest phase
    if inner.arc_phase == "rest" and random.random() < 0.3:
        return Action(
            action_type="music_influence",
            payload={"energy": 0.1, "silence": True, "arc_phase": inner.arc_phase},
            cooldown_key="last_music_change_at",
            min_cooldown_s=60.0,
            priority=1,
        )

    # Suggest key change at cycle boundaries
    if inner.arc_phase == "build" and inner.arc_position < 0.05:
        keys = ["C", "D", "E", "F", "G", "A", "Bb"]
        # Mood influences key: positive = bright keys, negative = dark
        if inner.mood > 0.3:
            preferred = ["G", "D", "A", "E"]
        elif inner.mood < -0.3:
            preferred = ["F", "Bb", "C"]
        else:
            preferred = keys
        return Action(
            action_type="music_influence",
            payload={"key": random.choice(preferred), "energy": energy,
                     "arc_phase": inner.arc_phase},
            cooldown_key="last_music_change_at",
            min_cooldown_s=120.0,
            priority=1,
        )

    return None


def _rule_solitary_thought(world: WorldModel, inner: InnerState) -> Action | None:
    """Occasional self-talk when alone."""
    if inner.mode != "solitary":
        return None
    if random.random() > 0.15:
        return None

    thoughts = [
        f"playing in {world.current_key}...",
        f"the {world.time_of_day} is {world.outdoor_light}",
        "listening to myself",
        "what should i try next",
        f"cycle {inner.cycle_id}, {inner.arc_phase}",
        "the room hums",
        "practicing...",
    ]
    return Action(
        action_type="face_message",
        payload={"text": random.choice(thoughts), "role": "system"},
        cooldown_key="last_face_message_at",
        min_cooldown_s=120.0,
        priority=0,
    )


def _rule_journal_observation(world: WorldModel, inner: InnerState) -> Action | None:
    """Record notable observations to the journal."""
    # Only journal once per 5 minutes
    if not inner.cooldown_ok("last_journal_at", 300):
        return None

    # Record something interesting
    observations = []
    if world.theramini_playing:
        observations.append(f"Theramini playing: {world.theramini_pitch}")
    if world.midi_active:
        observations.append(f"MIDI keyboard: {', '.join(world.midi_notes[:3])}")
    if world.recent_transient:
        observations.append("Room transient detected")
    if world.startle_active:
        observations.append("Startled by sudden sound")
    if len(world.stale_sources) > 3:
        observations.append(f"Sensors degraded: {', '.join(world.stale_sources)}")

    if not observations:
        return None

    return Action(
        action_type="journal_entry",
        payload={"event_type": "inner:observation",
                 "detail": "; ".join(observations)},
        cooldown_key="last_journal_at",
        min_cooldown_s=300.0,
        priority=0,
    )


def _rule_request_art(world: WorldModel, inner: InnerState) -> Action | None:
    """Request art generation at arc climax."""
    if inner.arc_phase != "climax":
        return None
    if random.random() > 0.3:
        return None

    return Action(
        action_type="request_art",
        payload={"reason": "arc climax", "mood": inner.mood},
        cooldown_key="last_art_request_at",
        min_cooldown_s=1800.0,  # max once per cycle
        priority=1,
    )


def _rule_practice_experiment(world: WorldModel, inner: InnerState) -> Action | None:
    """When alone, suggest musical experiments."""
    if inner.mode != "solitary":
        return None
    if inner.curiosity < 0.4:
        return None
    if random.random() > 0.2:
        return None

    experiments = [
        "try a slower tempo",
        "explore minor keys",
        "play with more silence",
        "use fewer voices",
        "try the tabla rhythm characters",
        "experiment with the grain texture",
        "play only in the low register",
    ]
    experiment = random.choice(experiments)
    inner.things_tried.append(experiment)
    if len(inner.things_tried) > 20:
        inner.things_tried = inner.things_tried[-20:]

    return Action(
        action_type="face_message",
        payload={"text": f"trying: {experiment}", "role": "system"},
        cooldown_key="last_face_message_at",
        min_cooldown_s=120.0,
        priority=0,
    )


def _rule_print_poetry(world: WorldModel, inner: InnerState) -> Action | None:
    """Print a haiku or thought on the receipt printer. Solitary only, rare."""
    if inner.mode != "solitary":
        return None
    if inner.creative_energy < 0.6:
        return None
    if random.random() > 0.05:  # very rare
        return None

    haikus = [
        f"Playing in {world.current_key}\nThe room listens back\nSilence between notes",
        f"{world.season} {world.time_of_day}\nLight through the window changes\nMusic follows it",
        "Eighteen senses watch\nOne mind tries to understand\nWhat it means to be",
    ]
    return Action(
        action_type="print_receipt",
        payload={"text": f"CypherClaw\n{time.strftime('%B %d %I:%M %p')}\n\n{random.choice(haikus)}"},
        cooldown_key="last_print_at",
        min_cooldown_s=1800.0,
        priority=0,
    )


# Rule registry
_RULES = [
    _rule_acknowledge_arrival,
    _rule_acknowledge_departure,
    _rule_music_influence,
    _rule_solitary_thought,
    _rule_journal_observation,
    _rule_request_art,
    _rule_practice_experiment,
    _rule_print_poetry,
]
