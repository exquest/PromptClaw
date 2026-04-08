"""WorldModel — unified picture of what is happening right now.

Rebuilt every fast tick (2s) from all sensor state files.
Pure data — no decisions, no side effects.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime


# State file paths
STATE_FILES = {
    "organism": "/tmp/organism_state.json",
    "composer": "/tmp/composer_state.json",
    "characters": "/tmp/active_characters.json",
    "theramini": "/tmp/theramini_state.json",
    "midi": "/tmp/midi_keyboard_state.json",
    "room_activity": "/tmp/room_activity.json",
    "room_presence": "/tmp/room_presence.json",
    "observer": "/tmp/observer_state.json",
    "porch": "/tmp/porch_eye_state.json",
    "side": "/tmp/side_eye_state.json",
    "garden": "/tmp/garden_state.json",
    "startle": "/tmp/startle_state.json",
    "self_listen": "/tmp/self_listen.json",
    "input_levels": "/tmp/input_levels.json",
}

MAX_STALE_S = 60.0  # state older than this is considered stale


def _read_state(path: str, max_age: float = MAX_STALE_S) -> dict:
    """Read a JSON state file. Returns empty dict if missing, corrupt, or stale."""
    try:
        if not os.path.isfile(path):
            return {}
        age = time.time() - os.path.getmtime(path)
        if age > max_age:
            return {}
        with open(path) as f:
            return json.loads(f.read())
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


@dataclass
class WorldModel:
    """Everything CypherClaw can perceive right now."""

    timestamp: float = 0.0

    # Organism vitals
    energy: float = 0.5
    valence: float = 0.5
    arousal: float = 0.3

    # Presence
    someone_here: bool = False
    room_brightness: float = 0.0
    observer_someone: bool = False

    # Music
    current_key: str = "C"
    current_movement: str = ""
    song_number: int = 0

    # Room
    room_activity: str = "quiet"
    recent_transient: bool = False
    window_mic_amp: float = 0.0
    cypherclaw_mic_amp: float = 0.0

    # Instruments
    theramini_playing: bool = False
    theramini_pitch: str | None = None
    midi_active: bool = False
    midi_notes: list[str] = field(default_factory=list)

    # Environment
    outdoor_brightness: float = 0.5
    outdoor_weather: str = "unknown"
    outdoor_light: str = "moderate"
    season: str = "spring"
    time_of_day: str = "day"

    # Self-monitoring
    own_amplitude: float = 0.0
    is_playing: bool = False
    startle_active: bool = False
    startle_count: int = 0

    # Characters
    active_characters: list[str] = field(default_factory=list)

    # Observer
    observer_lighting: str = "moderate"
    observer_description: str = ""

    # Staleness tracking
    stale_sources: list[str] = field(default_factory=list)


def read_world() -> WorldModel:
    """Read all sensor state files and build a WorldModel."""
    w = WorldModel(timestamp=time.time())
    stale = []

    # Organism
    org = _read_state(STATE_FILES["organism"])
    if org:
        mood = org.get("organism_mood", org.get("collective_mood", org.get("mood", {})))
        w.energy = mood.get("energy", 0.5)
        w.valence = mood.get("valence", 0.5)
        w.arousal = mood.get("arousal", 0.3)
    else:
        stale.append("organism")

    # Composer
    comp = _read_state(STATE_FILES["composer"])
    if comp:
        w.current_key = comp.get("key", "C")
        w.current_movement = comp.get("movement", "")
        w.song_number = comp.get("song", 0)
    else:
        stale.append("composer")

    # Characters
    chars = _read_state(STATE_FILES["characters"], max_age=300)
    w.active_characters = chars.get("active_characters", [])

    # Theramini
    ther = _read_state(STATE_FILES["theramini"])
    if ther:
        w.theramini_playing = ther.get("is_playing", False)
        w.theramini_pitch = ther.get("pitch_note")
    else:
        stale.append("theramini")

    # MIDI
    midi = _read_state(STATE_FILES["midi"])
    if midi:
        w.midi_active = midi.get("playing", False)
        w.midi_notes = midi.get("notes", [])
    else:
        stale.append("midi")

    # Room activity
    room = _read_state(STATE_FILES["room_activity"])
    if room:
        w.room_activity = room.get("activity_level", "quiet")
        w.recent_transient = room.get("recent_transient", False)
        w.window_mic_amp = room.get("window_mic_amp", 0.0)
        w.cypherclaw_mic_amp = room.get("cypherclaw_mic_amp", 0.0)
    else:
        stale.append("room_activity")

    # Room presence (camera)
    pres = _read_state(STATE_FILES["room_presence"])
    if pres:
        w.someone_here = pres.get("someone_here", False)
        w.room_brightness = pres.get("brightness", 0.0)
    else:
        stale.append("room_presence")

    # Observer
    obs = _read_state(STATE_FILES["observer"])
    if obs and obs.get("ok"):
        w.observer_someone = obs.get("someone_here", False)
        w.observer_lighting = obs.get("lighting", "moderate")
        w.observer_description = obs.get("description", "")
    else:
        stale.append("observer")

    # Combine presence signals
    w.someone_here = w.someone_here or w.observer_someone

    # Outdoor
    porch = _read_state(STATE_FILES["porch"])
    side = _read_state(STATE_FILES["side"])
    outdoor = porch or side
    if outdoor:
        w.outdoor_brightness = outdoor.get("brightness", 0.5)
        w.outdoor_weather = outdoor.get("weather", "unknown")
    else:
        stale.append("porch")

    # Garden
    garden = _read_state(STATE_FILES["garden"], max_age=120)
    if garden:
        w.outdoor_light = garden.get("light", "moderate")
        w.season = garden.get("season", "spring")

    # Time of day
    hour = datetime.now().hour
    if hour < 6:
        w.time_of_day = "night"
    elif hour < 9:
        w.time_of_day = "dawn"
    elif hour < 12:
        w.time_of_day = "morning"
    elif hour < 17:
        w.time_of_day = "afternoon"
    elif hour < 20:
        w.time_of_day = "evening"
    else:
        w.time_of_day = "night"

    # Self-listen
    sl = _read_state(STATE_FILES["self_listen"])
    if sl:
        w.own_amplitude = sl.get("amplitude", 0.0)
        w.is_playing = sl.get("is_playing", False)
    else:
        stale.append("self_listen")

    # Startle
    st = _read_state(STATE_FILES["startle"])
    if st:
        w.startle_active = st.get("startled", False)
        w.startle_count = st.get("startle_count", 0)

    # Input levels
    inp = _read_state(STATE_FILES["input_levels"])
    if not inp:
        stale.append("input_levels")

    w.stale_sources = stale
    return w
