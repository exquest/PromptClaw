"""InnerState — CypherClaw's persistent inner experience.

Persists across loop iterations. Serialized to disk every tick.
Durable copy saved every 5 minutes for cross-restart continuity.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


VOLATILE_PATH = "/tmp/inner_life_state.json"
DURABLE_PATH = "/home/user/cypherclaw-data/state/inner_life.json"


@dataclass
class InnerState:
    """Everything CypherClaw feels, thinks, and remembers."""

    # Emotional continuity (evolves slowly, -1 to 1 or 0 to 1)
    mood: float = 0.0             # -1=melancholy, 0=neutral, 1=content
    curiosity: float = 0.5        # 0=satisfied, 1=eager to explore
    social_appetite: float = 0.5  # 0=prefer solitude, 1=want company
    creative_energy: float = 0.5  # 0=depleted, 1=bursting to create

    # Narrative arc
    cycle_id: int = 0
    cycle_started_at: float = 0.0
    arc_position: float = 0.0     # 0.0 to 1.0 within current 30-min cycle
    arc_phase: str = "build"      # build / rise / climax / resolve / rest

    # Mode
    mode: str = "solitary"        # solitary / aware / engaged / performing
    mode_entered_at: float = 0.0
    presence_duration_s: float = 0.0

    # Attention
    current_focus: str | None = None
    recent_observations: list[str] = field(default_factory=list)
    pending_intentions: list[str] = field(default_factory=list)

    # Today's memory
    today_events: list[dict] = field(default_factory=list)
    things_tried: list[str] = field(default_factory=list)
    opinions_formed: list[dict] = field(default_factory=list)

    # Cooldowns (timestamps of last action per type)
    last_face_message_at: float = 0.0
    last_print_at: float = 0.0
    last_art_request_at: float = 0.0
    last_music_change_at: float = 0.0
    last_deep_think_at: float = 0.0
    last_journal_at: float = 0.0
    last_daemon_request_at: float = 0.0

    # Persistence tracking
    last_durable_save_at: float = 0.0

    def add_observation(self, text: str) -> None:
        """Record a notable observation."""
        self.recent_observations.append(text)
        if len(self.recent_observations) > 20:
            self.recent_observations = self.recent_observations[-20:]

    def add_event(self, event_type: str, detail: str = "") -> None:
        """Record a significant event for today."""
        self.today_events.append({
            "time": time.time(),
            "type": event_type,
            "detail": detail,
        })
        if len(self.today_events) > 100:
            self.today_events = self.today_events[-100:]

    def add_opinion(self, about: str, opinion: str) -> None:
        """Record an opinion about something (music, art, etc.)."""
        self.opinions_formed.append({
            "time": time.time(),
            "about": about,
            "opinion": opinion,
        })
        if len(self.opinions_formed) > 20:
            self.opinions_formed = self.opinions_formed[-20:]

    def cooldown_ok(self, key: str, min_seconds: float) -> bool:
        """Check if enough time has passed since last action of this type."""
        last = getattr(self, key, 0.0)
        return (time.time() - last) >= min_seconds

    def mark_cooldown(self, key: str) -> None:
        """Record that an action was just taken."""
        setattr(self, key, time.time())


def save_volatile(state: InnerState) -> None:
    """Write state to /tmp for other daemons to read."""
    try:
        data = asdict(state)
        tmp = VOLATILE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, VOLATILE_PATH)
    except OSError:
        pass


def save_durable(state: InnerState) -> None:
    """Write state to persistent storage for cross-restart continuity."""
    try:
        Path(DURABLE_PATH).parent.mkdir(parents=True, exist_ok=True)
        data = asdict(state)
        tmp = DURABLE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, DURABLE_PATH)
        state.last_durable_save_at = time.time()
    except OSError:
        pass


def load_state() -> InnerState:
    """Load state from durable storage, falling back to defaults."""
    for path in [DURABLE_PATH, VOLATILE_PATH]:
        try:
            if os.path.isfile(path):
                data = json.loads(Path(path).read_text())
                state = InnerState()
                # Restore persistent fields
                for key in ("mood", "curiosity", "social_appetite", "creative_energy",
                            "cycle_id", "things_tried", "opinions_formed"):
                    if key in data:
                        setattr(state, key, data[key])
                # Start fresh cycle
                state.cycle_started_at = time.time()
                state.mode_entered_at = time.time()
                return state
        except (json.JSONDecodeError, OSError):
            continue
    return InnerState(cycle_started_at=time.time(), mode_entered_at=time.time())
