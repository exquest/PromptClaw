"""Persistent Tamagotchi pets for CypherClaw agents."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from glyphweave.pet_sprites import get_frames, get_portrait

PETS_FILE = Path(
    os.environ.get("PROMPTCLAW_PETS_FILE", str(Path.home() / ".promptclaw" / "pets.json"))
).expanduser()

STAGE_THRESHOLDS = {0: 0, 1: 0, 2: 50, 3: 200, 4: 500, 5: 1000}
STAGE_NAMES = {
    0: "Egg",
    1: "Baby",
    2: "Teen",
    3: "Adult",
    4: "Elite",
    5: "Master",
}
TERMINAL_STATES = {"success", "error", "communicating"}
TRANSIENT_STATES = TERMINAL_STATES | {"thinking"}
VALID_STATES = {
    "idle",
    "thinking",
    "success",
    "error",
    "sleeping",
    "communicating",
}
ACTIVE_STATES = {"thinking", "communicating"}
DECAY_STEP_S = 600

_STATE_EMOJI = {
    "idle": "💤",
    "thinking": "🧠",
    "success": "✨",
    "error": "💢",
    "sleeping": "🌙",
    "communicating": "🔀",
    "hungry": "🍖",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stage_for_xp(xp: int) -> int:
    for stage in sorted(STAGE_THRESHOLDS, reverse=True):
        if xp >= STAGE_THRESHOLDS[stage]:
            return stage
    return 1


def _clamp(value: int, lower: int = 0, upper: int = 100) -> int:
    return max(lower, min(upper, int(value)))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _render_bar(value: int, *, max_value: int = 100, width: int = 5) -> str:
    scaled = 0 if max_value <= 0 else round((_clamp(value, 0, max_value) / max_value) * width)
    return ("▓" * scaled) + ("░" * (width - scaled))


class Pet:
    """Single agent's pet."""

    def __init__(self, agent: str, data: dict | None = None):
        self.agent = agent
        self.xp = 0
        self.stage = 1
        self.state = "idle"
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.total_uptime_s = 0.0
        self.last_active: str | None = None
        self.last_decay: str | None = None
        self.created: str | None = None
        self.mood = 80
        self.hunger = 50
        self.energy = 100
        self.incarnation: int = 1
        self.critical_since: str | None = None
        self._task_started = False
        if data:
            self.__dict__.update(data)
        self.xp = max(int(self.xp), 0)
        self.stage = _stage_for_xp(self.xp)
        self.tasks_completed = max(int(self.tasks_completed), 0)
        self.tasks_failed = max(int(self.tasks_failed), 0)
        self.total_uptime_s = max(float(self.total_uptime_s), 0.0)
        self.mood = _clamp(int(self.mood))
        self.hunger = _clamp(int(self.hunger))
        self.energy = _clamp(int(self.energy))
        self.incarnation = max(int(self.incarnation), 1)
        if self.state not in VALID_STATES:
            self.state = "idle"
        if not self.created:
            self.created = _now_iso()
        if not self.last_decay:
            self.last_decay = self.last_active or self.created

    def add_xp(self, amount: int) -> bool:
        """Add XP and report whether the pet evolved."""
        if amount <= 0:
            return False
        self.xp += amount
        old_stage = self.stage
        self.stage = _stage_for_xp(int(self.xp))
        return self.stage > old_stage

    def decay(self, seconds_since_last_active: float) -> None:
        """Decay or recover stats for an idle pet."""
        if seconds_since_last_active <= 0:
            return
        elapsed = int(seconds_since_last_active)
        self.mood = _clamp(self.mood - (elapsed // 1800))
        self.hunger = _clamp(self.hunger + (elapsed // 1200))
        self.energy = _clamp(self.energy + (elapsed // 600))

    def feed(self) -> None:
        """Reset hunger and nudge mood upward."""
        self.hunger = 0
        self.mood = _clamp(self.mood + 5)

    def play(self) -> None:
        """Boost mood and drain a bit of energy."""
        self.mood = _clamp(self.mood + 15)
        self.energy = _clamp(self.energy - 10)

    def tire(self, duration_s: float) -> None:
        """Drain energy from extended work."""
        if duration_s <= 0:
            return
        self.energy = _clamp(self.energy - int(duration_s // 60))

    def effective_state(self) -> str:
        """Choose the best display state based on pet stats."""
        if self.energy < 20:
            return "sleeping"
        if self.mood < 30:
            return "error"
        if self.hunger > 80 and self.state == "idle":
            return "hungry"
        return self.state

    def record_task(self, success: bool) -> tuple[int, bool]:
        """Record a task outcome. Returns (xp_gained, evolved)."""
        if not self._task_started:
            self.feed()
        self._task_started = False
        if success:
            self.tasks_completed += 1
            xp = 10
            self.mood = _clamp(self.mood + 10)
        else:
            self.tasks_failed += 1
            xp = 2
            self.mood = _clamp(self.mood - 5)
        now = _now_iso()
        self.last_active = now
        self.last_decay = now
        evolved = self.add_xp(xp)
        return xp, evolved

    def record_uptime(self, seconds: float) -> tuple[int, bool]:
        """Add active processing time. 1 XP per 60 seconds."""
        if seconds <= 0:
            return 0, False
        self.total_uptime_s += seconds
        self.tire(seconds)
        xp = int(seconds / 60)
        if xp <= 0:
            return 0, False
        return xp, self.add_xp(xp)

    def get_frames(self) -> list[str]:
        """Get current animation frames for this pet's state and stage."""
        return get_frames(self.agent, self.stage, self.effective_state())

    def get_portrait(self) -> str:
        """Get static portrait for status display."""
        return get_portrait(self.agent, self.stage)

    def status_line(self) -> str:
        """Return a compact one-line status summary."""
        state = self.effective_state()
        return (
            f"{self.agent:<11} {STAGE_NAMES[self.stage]:<10} "
            f"XP {self.xp:>4} {_STATE_EMOJI.get(state, '❔')} "
            f"😊{_render_bar(self.mood)} "
            f"🍖{_render_bar(self.hunger)} "
            f"⚡{_render_bar(self.energy)}"
        )

    def to_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if not key.startswith("_")}


class PetManager:
    """Manages all agent pets + persistence."""

    AGENTS = ["claude", "codex", "gemini", "cypherclaw"]

    def __init__(self):
        self._lock = threading.Lock()
        self.pets: dict[str, Pet] = {}
        self._load()

    def _load(self) -> None:
        data: dict = {}
        try:
            if PETS_FILE.exists():
                data = json.loads(PETS_FILE.read_text())
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            data = {}

        for agent, pet_data in data.get("pets", {}).items():
            if agent in self.AGENTS and isinstance(pet_data, dict):
                pet = Pet(agent, pet_data)
                if pet.state in TRANSIENT_STATES:
                    pet.state = "idle"
                self.pets[agent] = pet

        for agent in self.AGENTS:
            if agent not in self.pets:
                self.pets[agent] = Pet(agent)

        self.decay_all()
        self._save()

    def _save(self) -> None:
        PETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 2,
            "pets": {agent: pet.to_dict() for agent, pet in self.pets.items()},
        }
        PETS_FILE.write_text(json.dumps(data, indent=2, sort_keys=True))

    def get(self, agent: str) -> Pet:
        return self.pets.get(agent) or self.pets["cypherclaw"]

    def _decay_all_locked(self) -> bool:
        now = datetime.now(timezone.utc)
        changed = False
        for pet in self.pets.values():
            if pet.state in ACTIVE_STATES:
                continue
            anchor = _parse_iso(pet.last_decay or pet.last_active or pet.created)
            if anchor is None:
                pet.last_decay = now.isoformat()
                changed = True
                continue
            elapsed = max((now - anchor).total_seconds(), 0.0)
            steps = int(elapsed // DECAY_STEP_S)
            if steps <= 0:
                continue
            pet.decay(steps * DECAY_STEP_S)
            remainder = elapsed - (steps * DECAY_STEP_S)
            pet.last_decay = (now - timedelta(seconds=remainder)).isoformat()
            changed = True
        return changed

    def decay_all(self) -> bool:
        """Apply idle stat decay across all pets."""
        with self._lock:
            return self._decay_all_locked()

    def tick(self) -> None:
        """Advance pet stats and persist the shared state file."""
        with self._lock:
            changed = self._decay_all_locked()
            if changed:
                self._save()

    def on_task_start(self, agent: str) -> None:
        """Set an agent pet to thinking."""
        with self._lock:
            pet = self.get(agent)
            pet.feed()
            pet._task_started = True
            pet.state = "thinking"
            now = _now_iso()
            pet.last_active = now
            pet.last_decay = now
            self._save()

    def on_task_end(self, agent: str, success: bool, duration_s: float = 0) -> tuple[int, bool, Pet]:
        """Record outcome, award XP, and set success or error state."""
        with self._lock:
            pet = self.get(agent)
            task_xp, evolved_task = pet.record_task(success)
            uptime_xp, evolved_uptime = pet.record_uptime(duration_s)
            pet.state = "success" if success else "error"
            self._save()
            return task_xp + uptime_xp, evolved_task or evolved_uptime, pet

    def on_idle(self, agent: str, only_if: set[str] | None = None) -> None:
        """Return a pet to idle when appropriate."""
        with self._lock:
            pet = self.get(agent)
            if only_if is not None and pet.state not in only_if:
                return
            pet.state = "idle"
            self._save()

    def schedule_idle(self, agent: str, delay_s: float = 3.0) -> None:
        """Reset a finished pet to idle after a short display window.

        Reuses one timer per agent — cancels any previous pending timer
        so threads don't accumulate.
        """
        if not hasattr(self, "_idle_timers"):
            self._idle_timers: dict[str, threading.Timer] = {}

        # Cancel any existing timer for this agent
        old = self._idle_timers.pop(agent, None)
        if old is not None:
            old.cancel()

        def _finish_idle_window() -> None:
            self.on_idle(agent, only_if=set(TERMINAL_STATES))
            self._idle_timers.pop(agent, None)

        timer = threading.Timer(
            delay_s,
            _finish_idle_window,
        )
        timer.daemon = True
        timer.start()
        self._idle_timers[agent] = timer

    def wake_all(self) -> None:
        """Wake sleeping pets without disturbing active ones."""
        with self._lock:
            changed = False
            for pet in self.pets.values():
                if pet.state == "sleeping":
                    pet.state = "idle"
                    changed = True
            if changed:
                self._save()

    def on_communicate(self, agents: list[str]) -> None:
        """Set multiple pets to communicating for parallel dispatch."""
        with self._lock:
            now = _now_iso()
            for agent in agents:
                pet = self.get(agent)
                pet.state = "communicating"
                pet.last_active = now
                pet.last_decay = now
            self._save()

    def on_sleep(self) -> None:
        """Set all pets to sleeping."""
        with self._lock:
            changed = False
            for pet in self.pets.values():
                if pet.state in ACTIVE_STATES:
                    continue
                if pet.state == "sleeping":
                    continue
                pet.state = "sleeping"
                changed = True
            if changed:
                self._save()

    def status_summary(self) -> str:
        """Generate the `/pets` display."""
        from glyphweave.scenes import CypherClawArt

        self.tick()
        return CypherClawArt.pet_status_display(self.pets)

    def interaction_scene(self, agents: list[str]) -> str:
        """Generate a collaboration scene for active pets."""
        from glyphweave.scenes import CypherClawArt

        return CypherClawArt.pet_interaction_scene(agents, self.pets)

    def evolution_announcement(self, pet: Pet) -> str:
        """Generate an evolution celebration message."""
        portrait = pet.get_portrait()
        return (
            "✨🎉 EVOLUTION! 🎉✨\n\n"
            f"{pet.agent.upper()}'s pet evolved to Stage {pet.stage} "
            f"({STAGE_NAMES[pet.stage]})!\n\n"
            f"```\n{portrait}\n```\n\n"
            f"Total XP: {pet.xp}"
        )
