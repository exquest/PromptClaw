"""CypherClaw Inner Life — the mind behind the senses.

A persistent process that reads all sensors, forms a coherent picture
of the world, makes autonomous decisions, and takes initiative.

Four-speed loop:
  Fast (2s)   — read sensors, detect events
  Slow (30s)  — decide and act
  Deep (5min) — reflect with local LLM
  Cycle (30m) — complete narrative arc
"""
from __future__ import annotations

import logging
import time

from .actions import Action, dispatch
from .decision_engine import decide
from .inner_state import InnerState, load_state, save_durable, save_volatile
from .mood import evolve_mood
from .narrative_arc import complete_cycle, start_new_cycle, update_arc
from .presence import update_presence
from .self_critique import critique_music, reflect_on_day
from .world_model import WorldModel, read_world

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [inner_life] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("inner_life")

FAST_INTERVAL = 2.0
SLOW_INTERVAL = 30.0
DEEP_INTERVAL = 300.0
DURABLE_SAVE_INTERVAL = 300.0


def _detect_events(world: WorldModel, inner: InnerState) -> list[str]:
    """Detect immediate events from sensor changes."""
    events = []
    if world.startle_active:
        events.append("startle")
    if world.theramini_playing and inner.mode != "performing":
        events.append("theramini_start")
    if world.midi_active and inner.mode != "performing":
        events.append("midi_start")
    if world.recent_transient:
        events.append("room_transient")
    return events


def run():
    """Main inner life loop. Never exits."""
    inner = load_state()
    world = WorldModel()

    last_fast = 0.0
    last_slow = 0.0
    last_deep = 0.0

    log.info("Inner life started — mode=%s, mood=%.2f, cycle=%d",
             inner.mode, inner.mood, inner.cycle_id)

    while True:
        now = time.time()

        try:
            # === FAST TICK (2s): senses ===
            if now - last_fast >= FAST_INTERVAL:
                world = read_world()

                # Presence state machine
                transition = update_presence(world, inner)
                if transition:
                    inner.add_event("mode_change", transition)
                    log.info("Mode: %s", transition)

                # Detect immediate events
                events = _detect_events(world, inner)
                for event in events:
                    inner.add_observation(event)

                last_fast = now

            # === SLOW TICK (30s): decisions ===
            if now - last_slow >= SLOW_INTERVAL:
                # Update narrative arc
                cycle_done = update_arc(inner)
                if cycle_done:
                    summary = complete_cycle(inner)
                    inner.add_event("cycle_complete", str(summary))
                    log.info("Cycle %d complete", inner.cycle_id)
                    start_new_cycle(inner)

                # Evolve mood
                evolve_mood(world, inner)

                # Make decisions
                actions = decide(world, inner)
                for action in actions:
                    ok = dispatch(action, inner)
                    if ok:
                        log.info("Action: %s", action.action_type)

                last_slow = now

            # === DEEP TICK (5min): reflection ===
            if now - last_deep >= DEEP_INTERVAL:
                if inner.mode == "solitary":
                    # Self-critique
                    critique = critique_music(world, inner)
                    if critique:
                        log.info("Critique: %s", critique[:60])

                    # Occasional reflection
                    if inner.arc_phase in ("resolve", "rest"):
                        reflection = reflect_on_day(inner)
                        if reflection:
                            inner.add_observation(f"reflection: {reflection}")
                            log.info("Reflection: %s", reflection[:60])

                last_deep = now

            # === PERSIST STATE ===
            save_volatile(inner)
            if now - inner.last_durable_save_at >= DURABLE_SAVE_INTERVAL:
                save_durable(inner)

        except Exception:
            log.exception("Tick failed")

        time.sleep(0.5)


def main():
    """Entry point."""
    run()


if __name__ == "__main__":
    main()
