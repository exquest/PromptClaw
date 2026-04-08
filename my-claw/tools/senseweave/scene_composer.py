"""Scene Composer — PARE-001: creative brain deciding WHAT to draw.

Reads house mood from organism state and garden conditions, then
assembles a SceneSpec describing characters, elements, weather, and
palette for the Pareidolia renderer to paint.

Flow: sensor_fusion -> mood_mirror -> garden_watcher -> scene_composer -> pareidolia
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime

from senseweave.mood_mirror import mood_to_art_params, mood_to_face_expression
from senseweave.garden_watcher import estimate_outdoor_light, estimate_season
from senseweave.pareidolia import (
    PALETTES,
    ColorPalette,
    SceneCharacter,
    SceneElement,
    WeatherEffects,
    render_scene,
    select_palette,
)

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    Image = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Organism character roster (21 characters, grouped by energy affinity)
# ---------------------------------------------------------------------------

ACTIVE_CHARACTERS = [
    "Instrument", "Speaker", "Messenger", "Spark", "Dancer", "Pulse", "Signal",
]

QUIET_CHARACTERS = [
    "Dreamer", "Membrane", "Heartbeat", "Listener", "Shadow", "Whisper", "Breath",
]

NATURE_CHARACTERS = [
    "Garden Eye", "Basalt", "Pebble", "Root", "Lichen", "Moss", "Dew",
]

# Characters that count as a "face" (always include at least one)
FACE_CHARACTERS = {"Basalt", "Pebble", "Garden Eye", "Dreamer", "Listener"}

ALL_CHARACTERS = ACTIVE_CHARACTERS + QUIET_CHARACTERS + NATURE_CHARACTERS

ORGANISM_STATE_PATH = "/tmp/organism_state.json"



# ---------------------------------------------------------------------------
# Camera state — real outdoor conditions from porch/side cameras
# ---------------------------------------------------------------------------

def _read_camera_state() -> dict | None:
    """Read real outdoor conditions from porch_eye camera state files."""
    import json
    best = None
    for path in ["/tmp/porch_eye_state.json", "/tmp/side_eye_state.json"]:
        try:
            data = json.loads(open(path).read())
            if data.get("error"):
                continue
            # Prefer whichever has more recent capture
            if best is None or data.get("last_capture_time", 0) > best.get("last_capture_time", 0):
                best = data
        except Exception:
            continue
    return best

# Default mood when sensor state is unavailable
_DEFAULT_MOOD: dict = {"energy": 0.4, "valence": 0.5, "arousal": 0.3}


# ---------------------------------------------------------------------------
# Season element pools
# ---------------------------------------------------------------------------

_SEASON_ELEMENTS: dict[str, list[str]] = {
    "spring": ["tree", "flower", "puddle", "bush", "butterfly"],
    "summer": ["tree", "bush", "butterfly", "rock", "flower"],
    "fall":   ["tree", "mushroom", "path", "rock", "bush"],
    "winter": ["bare_tree", "snow_drift", "path", "rock"],
}


# ---------------------------------------------------------------------------
# SceneSpec
# ---------------------------------------------------------------------------


@dataclass
class SceneSpec:
    """Complete specification for a composed scene.

    characters: list[dict] with name, expression, position (x,y), size
    elements:   list[dict] with type, position (x,y)
    weather:    dict with rain (0-1), snow (0-1), clouds (0-5), fog (bool)
    hour:       int (0-23)
    palette_name: str
    title:      str
    mood_tag:   str
    """
    characters: list[dict] = field(default_factory=list)
    elements: list[dict] = field(default_factory=list)
    weather: dict = field(default_factory=lambda: {
        "rain": 0.0, "snow": 0.0, "clouds": 0, "fog": False,
    })
    hour: int = 12
    palette_name: str = "day_calm"
    title: str = ""
    mood_tag: str = "calm"


# ---------------------------------------------------------------------------
# pick_characters
# ---------------------------------------------------------------------------


def pick_characters(mood: dict, count: int, prefer: list[str] | None = None) -> list[dict]:
    """Select organism characters that match the current mood.

    High energy -> active characters (Instrument, Speaker, Messenger).
    Low energy  -> quiet characters (Dreamer, Membrane, Heartbeat).
    Calm        -> nature characters (Garden Eye, Basalt, Pebble).
    Always includes at least one "face" character.

    Returns list of dicts with name, expression, position, size.
    """
    count = max(1, min(4, count))
    energy = mood.get("energy", 0.5)
    valence = mood.get("valence", 0.5)
    arousal = mood.get("arousal", 0.5)

    expression = mood_to_face_expression(mood)

    # Build a weighted pool and matching face set based on mood
    pool: list[str] = []
    # If music system specifies active characters, put them first
    if prefer:
        pool.extend(prefer)
    if energy >= 0.6:
        # High energy: active characters dominant, some nature
        primary = ACTIVE_CHARACTERS
        pool.extend(ACTIVE_CHARACTERS)
        pool.extend(ACTIVE_CHARACTERS)  # double-weight
        pool.extend(NATURE_CHARACTERS)
    elif energy < 0.35:
        # Low energy: quiet characters dominant, some nature
        primary = QUIET_CHARACTERS
        pool.extend(QUIET_CHARACTERS)
        pool.extend(QUIET_CHARACTERS)  # double-weight
        pool.extend(NATURE_CHARACTERS)
    else:
        # Calm / moderate: nature characters dominant
        primary = NATURE_CHARACTERS
        pool.extend(NATURE_CHARACTERS)
        pool.extend(NATURE_CHARACTERS)  # double-weight
        pool.extend(QUIET_CHARACTERS)
        pool.extend(ACTIVE_CHARACTERS)

    # Shuffle and pick
    rng = random.Random()
    rng.shuffle(pool)
    selected_names: list[str] = []
    for name in pool:
        if name not in selected_names:
            selected_names.append(name)
        if len(selected_names) >= count:
            break

    # Ensure at least one face character (prefer faces from the primary group)
    has_face = any(n in FACE_CHARACTERS for n in selected_names)
    if not has_face:
        primary_faces = [n for n in FACE_CHARACTERS
                         if n in primary and n not in selected_names]
        if not primary_faces:
            primary_faces = [n for n in FACE_CHARACTERS if n not in selected_names]
        if primary_faces:
            selected_names[-1] = rng.choice(primary_faces)

    # Ensure at least one character from the primary group
    has_primary = any(n in primary for n in selected_names)
    if not has_primary and count >= 2:
        # Replace the second-to-last with a primary character
        options = [n for n in primary if n not in selected_names]
        if options:
            selected_names[0] = rng.choice(options)

    # Assign positions spread across the scene (x: 15-85% of 1280, y: 55-75% of 1024)
    characters: list[dict] = []
    spread = max(1, len(selected_names))
    for i, name in enumerate(selected_names):
        x_frac = 0.15 + 0.70 * (i / max(1, spread - 1)) if spread > 1 else 0.5
        x = int(x_frac * 1280)
        y = int((0.58 + rng.uniform(-0.03, 0.05)) * 1024)
        size = rng.randint(55, 90)
        characters.append({
            "name": name,
            "expression": expression,
            "position": (x, y),
            "size": size,
        })

    return characters


# ---------------------------------------------------------------------------
# pick_elements
# ---------------------------------------------------------------------------


def pick_elements(season: str, weather: str, count: int = 3) -> list[dict]:
    """Select scene elements appropriate for season and weather.

    Spring: trees, flowers, puddles.
    Summer: trees, bushes, butterflies.
    Fall:   trees (falling leaves), mushrooms, paths.
    Winter: bare trees, snow drifts, paths.
    Rain always adds at least one puddle.

    Returns list of dicts with type, position.
    """
    pool = list(_SEASON_ELEMENTS.get(season, _SEASON_ELEMENTS["spring"]))

    # Rain always forces a puddle
    if weather == "rain" and "puddle" not in pool:
        pool.append("puddle")

    rng = random.Random()
    rng.shuffle(pool)

    selected: list[str] = []

    # If rain, ensure a puddle first
    if weather == "rain":
        selected.append("puddle")
        pool = [e for e in pool if e != "puddle"]

    for elem_type in pool:
        if len(selected) >= count:
            break
        selected.append(elem_type)

    # Pad to count if pool was too small
    while len(selected) < count:
        selected.append(rng.choice(pool if pool else ["rock"]))

    # Assign positions spread across scene ground area
    elements: list[dict] = []
    for i, elem_type in enumerate(selected):
        x_frac = 0.10 + 0.80 * (i / max(1, count - 1)) if count > 1 else 0.5
        x = int(x_frac * 1280)
        y = int(rng.uniform(0.62, 0.80) * 1024)
        elements.append({
            "type": elem_type,
            "position": (x, y),
        })

    return elements


# ---------------------------------------------------------------------------
# generate_title
# ---------------------------------------------------------------------------

_MOOD_WORDS: dict[str, list[str]] = {
    "happy":    ["bright", "warm", "golden", "smiling", "cheerful"],
    "sad":      ["quiet", "fading", "grey", "still", "hushed"],
    "calm":     ["gentle", "soft", "slow", "resting", "peaceful"],
    "curious":  ["watching", "wondering", "peering", "searching", "alert"],
    "excited":  ["buzzing", "dancing", "sparkling", "rushing", "alive"],
    "sleeping": ["dreaming", "silent", "deep", "drifting", "floating"],
    "anxious":  ["restless", "tense", "flickering", "shifting", "uneasy"],
}

_WEATHER_PHRASES: dict[str, list[str]] = {
    "clear": ["under open sky", "in the light", "beneath the blue"],
    "rain":  ["in the rain", "through the drizzle", "as drops fall"],
    "snow":  ["in the snow", "through the flurries", "as flakes drift"],
    "overcast": ["under grey skies", "beneath the clouds", "in soft light"],
    "fog":   ["in the mist", "through the fog", "in the haze"],
}


def generate_title(characters: list, mood_tag: str, weather: str) -> str:
    """Generate a short poetic title from characters, mood, and weather.

    Returns something like "Two rocks watch the rain" or
    "Morning light through the window".
    """
    rng = random.Random()

    mood_words = _MOOD_WORDS.get(mood_tag, _MOOD_WORDS["calm"])
    weather_phrases = _WEATHER_PHRASES.get(weather, _WEATHER_PHRASES["clear"])

    adjective = rng.choice(mood_words)
    location = rng.choice(weather_phrases)

    count = len(characters)
    if count == 0:
        return f"A {adjective} moment {location}"

    if count == 1:
        name = characters[0].get("name", "someone")
        return f"{name}, {adjective} {location}"

    # Multiple characters
    names = [c.get("name", "someone") for c in characters[:2]]
    if count == 2:
        subject = f"{names[0]} and {names[1]}"
    else:
        subject = f"{names[0]}, {names[1]} and friends"

    return f"{subject}, {adjective} {location}"


# ---------------------------------------------------------------------------
# Weather inference from mood/hour/season
# ---------------------------------------------------------------------------


def _infer_weather(mood: dict, hour: int, season: str) -> dict:
    """Infer weather from real camera data, falling back to mood-based guesses."""
    # Try real camera data first
    cam = _read_camera_state()
    if cam and cam.get("last_capture_time", 0) > 0:
        brightness = cam.get("brightness", 0.5)
        weather_label = cam.get("weather", "")
        # Map camera observations to weather dict
        if weather_label == "night" or brightness < 0.1:
            return {"rain": 0.0, "snow": 0.0, "clouds": 0, "fog": False}
        if weather_label == "overcast" or (0.1 <= brightness < 0.4 and 8 <= hour <= 17):
            return {"rain": 0.1, "snow": 0.0, "clouds": 3, "fog": False}
        if weather_label in ("dawn", "dusk"):
            return {"rain": 0.0, "snow": 0.0, "clouds": 1, "fog": brightness < 0.2}
        if brightness >= 0.6:
            return {"rain": 0.0, "snow": 0.0, "clouds": 0, "fog": False}
        # Motion could indicate wind/rain
        if cam.get("motion_detected", False) and brightness < 0.4:
            return {"rain": 0.3, "snow": 0.0, "clouds": 3, "fog": False}
    # Fallback: mood-based inference
    energy = mood.get("energy", 0.5)
    valence = mood.get("valence", 0.5)

    rain = 0.0
    snow = 0.0
    clouds = 0
    fog = False

    # Low valence + moderate energy -> rainy
    if valence < 0.35 and energy >= 0.3:
        rain = 0.3 + (0.4 * (1.0 - valence))
        clouds = 3

    # Winter + low energy -> snowy
    if season == "winter" and energy < 0.4:
        snow = 0.3 + (0.4 * (1.0 - energy))
        rain = 0.0  # snow replaces rain

    # Overcast from moderate-low valence
    if valence < 0.5 and rain == 0.0 and snow == 0.0:
        clouds = 2 + int((0.5 - valence) * 6)

    # Fog in early morning or low visibility conditions
    if (5 <= hour <= 7) and season in ("fall", "spring") and valence < 0.5:
        fog = True
        clouds = max(clouds, 2)

    # Clear skies for happy moods
    if valence >= 0.6 and rain == 0.0 and snow == 0.0:
        clouds = min(clouds, 1)

    clouds = max(0, min(5, clouds))
    rain = max(0.0, min(1.0, rain))
    snow = max(0.0, min(1.0, snow))

    return {"rain": rain, "snow": snow, "clouds": clouds, "fog": fog}


def _weather_label(weather: dict) -> str:
    """Classify weather dict into a simple label."""
    if weather.get("rain", 0) > 0.1:
        return "rain"
    if weather.get("snow", 0) > 0.1:
        return "snow"
    if weather.get("fog", False):
        return "fog"
    if weather.get("clouds", 0) >= 3:
        return "overcast"
    return "clear"


# ---------------------------------------------------------------------------
# Palette selection from hour + mood + weather
# ---------------------------------------------------------------------------


def _select_palette_name(hour: int, mood_tag: str, weather_label: str) -> str:
    """Choose a palette name from PALETTES based on conditions."""
    # Use pareidolia's select_palette logic to pick, then find the name
    palette = select_palette(hour, mood=mood_tag, weather=weather_label)

    for name, p in PALETTES.items():
        if p == palette:
            return name

    return "day_calm"


# ---------------------------------------------------------------------------
# compose_scene
# ---------------------------------------------------------------------------



def _read_active_characters() -> list[str]:
    """Read which characters the music system is currently playing."""
    import json
    try:
        d = json.loads(open("/tmp/active_characters.json").read())
        if time.time() - d.get("timestamp", 0) < 300:  # within 5 min
            return d.get("active_characters", [])
    except Exception:
        pass
    return []


def _read_inner_life_arc() -> dict:
    """Read inner life arc phase for art timing alignment."""
    import json
    try:
        d = json.loads(open("/tmp/inner_life_state.json").read())
        return {"arc_phase": d.get("arc_phase", "build"), "mood": d.get("mood", 0)}
    except Exception:
        return {}


def compose_scene(mood: dict | None = None, hour: int | None = None) -> SceneSpec:
    """Compose a complete scene from house mood and time.

    If mood is None, reads from /tmp/organism_state.json.
    If hour is None, uses the current time.

    Returns a fully populated SceneSpec ready for rendering.
    """
    # --- Resolve hour ---
    if hour is None:
        hour = datetime.now().hour

    # --- Resolve mood ---
    if mood is None:
        mood = _read_organism_mood()

    # --- Mood tag via mood_mirror ---
    mood_tag = mood_to_face_expression(mood)

    # --- Art params from mood ---
    art_params = mood_to_art_params(mood)

    # --- Season ---
    month = datetime.now().month
    season = estimate_season(month)

    # --- Weather ---
    weather = _infer_weather(mood, hour, season)
    w_label = _weather_label(weather)

    # --- Palette ---
    palette_name = _select_palette_name(hour, mood_tag, w_label)

    # --- Character count based on energy ---
    energy = mood.get("energy", 0.5)
    if energy >= 0.7:
        char_count = 4
    elif energy >= 0.5:
        char_count = 3
    elif energy >= 0.3:
        char_count = 2
    else:
        char_count = 1

    # --- Pick characters ---
    # Prefer characters that the music system is currently playing
    _active = _read_active_characters()
    if _active:
        characters = pick_characters(mood, char_count, prefer=_active)
    else:
        characters = pick_characters(mood, char_count)

    # --- Pick elements ---
    elements = pick_elements(season, w_label)

    # --- Title ---
    title = generate_title(characters, mood_tag, w_label)

    return SceneSpec(
        characters=characters,
        elements=elements,
        weather=weather,
        hour=hour,
        palette_name=palette_name,
        title=title,
        mood_tag=mood_tag,
    )


# ---------------------------------------------------------------------------
# render_composed_scene
# ---------------------------------------------------------------------------


def render_composed_scene(
    spec: SceneSpec,
    width: int = 1280,
    height: int = 1024,
) -> "Image.Image":
    """Convert a SceneSpec into a rendered PIL Image via pareidolia.

    Maps SceneSpec characters/elements/weather into pareidolia's
    SceneCharacter, SceneElement, and WeatherEffects dataclasses,
    then calls render_scene().
    """
    if not HAS_PILLOW:
        raise ImportError("Pillow is required for scene rendering")

    # --- Palette ---
    palette = PALETTES.get(spec.palette_name)
    if palette is None:
        palette = select_palette(spec.hour, mood=spec.mood_tag)

    # --- Characters -> SceneCharacter ---
    scene_chars: list[SceneCharacter] = []
    for c in spec.characters:
        pos = c.get("position", (width // 2, int(height * 0.65)))
        scene_chars.append(SceneCharacter(
            name=c.get("name", "generic"),
            expression=c.get("expression", "neutral"),
            x=pos[0],
            y=pos[1],
            size=c.get("size", 60),
        ))

    # --- Elements -> SceneElement ---
    scene_elems: list[SceneElement] = []
    for e in spec.elements:
        pos = e.get("position", (width // 2, int(height * 0.7)))
        elem_type = e.get("type", "rock")
        # Map non-standard types to renderable types
        type_map = {
            "flower": "bush",
            "butterfly": "bush",
            "mushroom": "rock",
            "path": "rock",
            "bare_tree": "tree",
            "snow_drift": "rock",
        }
        renderable_type = type_map.get(elem_type, elem_type)
        scene_elems.append(SceneElement(
            type=renderable_type,
            x=pos[0],
            y=pos[1],
            size=40,
        ))

    # --- Weather -> WeatherEffects ---
    rain = spec.weather.get("rain", 0.0)
    snow = spec.weather.get("snow", 0.0)
    clouds = spec.weather.get("clouds", 0)
    is_night = spec.hour < 6 or spec.hour >= 20
    is_day_clear = not is_night and rain < 0.1 and snow < 0.1 and clouds < 3

    weather_fx = WeatherEffects(
        rain_intensity=rain,
        snow_intensity=snow,
        cloud_count=clouds,
        show_sun=is_day_clear and 7 <= spec.hour <= 18,
        show_moon=is_night,
        moon_phase=0.6,
        star_count=50 if is_night else 0,
    )

    return render_scene(
        width=width,
        height=height,
        characters=scene_chars,
        elements=scene_elems,
        palette=palette,
        weather_effects=weather_fx,
        hour=spec.hour,
        title=spec.title,
    )


# ---------------------------------------------------------------------------
# save_to_gallery
# ---------------------------------------------------------------------------


def save_to_gallery(
    image: "Image.Image",
    spec: SceneSpec,
    gallery_dir: str = "/home/user/cypherclaw/gallery/renders/",
) -> str:
    """Save a rendered scene PNG and JSON sidecar to the gallery.

    Creates the gallery directory if it does not exist.
    Returns the path of the saved PNG file.
    """
    os.makedirs(gallery_dir, exist_ok=True)

    timestamp = int(time.time())
    slug = spec.mood_tag or "scene"
    basename = f"scene_{slug}_{timestamp}"

    png_path = os.path.join(gallery_dir, f"{basename}.png")
    json_path = os.path.join(gallery_dir, f"{basename}.json")

    # Save image
    image.save(png_path, "PNG")

    # Save metadata sidecar
    metadata = {
        "title": spec.title,
        "mood_tag": spec.mood_tag,
        "hour": spec.hour,
        "palette_name": spec.palette_name,
        "characters": spec.characters,
        "elements": spec.elements,
        "weather": spec.weather,
        "timestamp": timestamp,
    }
    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")

    return png_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_organism_mood() -> dict:
    """Read organism mood from state file, with graceful fallback."""
    try:
        with open(ORGANISM_STATE_PATH) as f:
            state = json.load(f)
        return state.get("organism_mood", dict(_DEFAULT_MOOD))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return dict(_DEFAULT_MOOD)
