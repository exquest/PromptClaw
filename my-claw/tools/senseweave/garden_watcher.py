"""Garden Watcher — outdoor camera state for art installation mood and music.

Watches the outdoor garden camera for weather and light changes that
influence the art installation's palette and musical key choices.
Uses brightness (0-1 sensor value) and time of day to classify outdoor
conditions, then maps those to colour palettes and musical keys.

Writes state to /tmp/garden_state.json (atomic).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime


# ---------------------------------------------------------------------------
# Outdoor light classification
# ---------------------------------------------------------------------------


def estimate_outdoor_light(brightness: float, hour: int) -> str:
    """Classify outdoor light as bright_sun / cloudy / dim / twilight / dark.

    Uses both the camera brightness (0-1) and hour of day (0-23) to
    account for the fact that a sensor might read low in legitimate
    twilight vs. overcast midday.
    """
    is_night = hour < 5 or hour >= 22
    is_twilight_hour = hour in (5, 6, 7, 19, 20, 21)

    if brightness <= 0.08:
        return "dark"

    if is_night:
        if brightness <= 0.2:
            return "dark"
        return "twilight"

    if is_twilight_hour:
        if brightness < 0.1:
            return "dark"
        if brightness < 0.3:
            return "twilight"
        if brightness < 0.6:
            return "dim"
        return "cloudy"

    # Daytime hours (8-18)
    if brightness >= 0.75:
        return "bright_sun"
    if brightness >= 0.4:
        return "cloudy"
    if brightness >= 0.15:
        return "dim"
    return "dark"


# ---------------------------------------------------------------------------
# Season estimation (Eugene, Oregon — Pacific Northwest)
# ---------------------------------------------------------------------------


def estimate_season(month: int) -> str:
    """Return season for Eugene, Oregon given month (1-12).

    PNW seasons: spring 3-5, summer 6-8, fall 9-11, winter 12-2.
    """
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "fall"
    return "winter"


# ---------------------------------------------------------------------------
# Palette suggestions
# ---------------------------------------------------------------------------

_PALETTE_MAP: dict[tuple[str, str], list[str]] = {
    # Spring
    ("bright_sun", "spring"): ["green", "pink", "yellow", "sky_blue"],
    ("cloudy", "spring"):     ["sage", "lavender", "soft_green", "cream"],
    ("dim", "spring"):        ["moss", "grey_green", "muted_pink"],
    ("twilight", "spring"):   ["violet", "rose", "pale_gold"],
    ("dark", "spring"):       ["deep_green", "indigo", "charcoal"],
    # Summer
    ("bright_sun", "summer"): ["gold", "cyan", "coral", "bright_green"],
    ("cloudy", "summer"):     ["warm_grey", "soft_blue", "peach"],
    ("dim", "summer"):        ["olive", "dusty_rose", "tan"],
    ("twilight", "summer"):   ["amber", "magenta", "deep_orange"],
    ("dark", "summer"):       ["navy", "dark_teal", "plum"],
    # Fall
    ("bright_sun", "fall"):   ["orange", "red", "gold", "brown"],
    ("cloudy", "fall"):       ["rust", "taupe", "burgundy", "ochre"],
    ("dim", "fall"):          ["umber", "dark_orange", "slate"],
    ("twilight", "fall"):     ["copper", "wine", "dark_gold"],
    ("dark", "fall"):         ["dark_brown", "deep_red", "charcoal"],
    # Winter
    ("bright_sun", "winter"): ["ice_blue", "white", "pale_grey", "silver"],
    ("cloudy", "winter"):     ["grey", "slate_blue", "fog"],
    ("dim", "winter"):        ["steel", "ash", "muted_blue"],
    ("twilight", "winter"):   ["deep_purple", "cold_grey", "frost"],
    ("dark", "winter"):       ["deep_blue", "silver", "white"],
}


def suggest_palette(light: str, season: str) -> list[str]:
    """Return colour name suggestions for art generation.

    Falls back to a neutral palette if the combination is unknown.
    """
    key = (light, season)
    return list(_PALETTE_MAP.get(key, ["grey", "soft_blue", "cream"]))


# ---------------------------------------------------------------------------
# Music key suggestions
# ---------------------------------------------------------------------------

_KEY_MAP: dict[tuple[str, str], str] = {
    # Spring — fresh, hopeful
    ("bright_sun", "spring"): "G",
    ("cloudy", "spring"):     "C",
    ("dim", "spring"):        "Am",
    ("twilight", "spring"):   "F",
    ("dark", "spring"):       "Dm",
    # Summer — bright, energetic
    ("bright_sun", "summer"): "D",
    ("cloudy", "summer"):     "G",
    ("dim", "summer"):        "C",
    ("twilight", "summer"):   "Bb",
    ("dark", "summer"):       "Gm",
    # Fall — warm, reflective
    ("bright_sun", "fall"):   "A",
    ("cloudy", "fall"):       "D",
    ("dim", "fall"):          "Em",
    ("twilight", "fall"):     "F",
    ("dark", "fall"):         "Bm",
    # Winter — cold, introspective
    ("bright_sun", "winter"): "C",
    ("cloudy", "winter"):     "Am",
    ("dim", "winter"):        "Dm",
    ("twilight", "winter"):   "Eb",
    ("dark", "winter"):       "Em",
}


def suggest_music_key(light: str, season: str) -> str:
    """Suggest a musical key based on light condition and season.

    Bright/summer leans major (G, D, A). Dark/winter leans minor (E, B).
    Twilight leans modal (F, Bb).
    """
    return _KEY_MAP.get((light, season), "C")


# ---------------------------------------------------------------------------
# GardenState dataclass
# ---------------------------------------------------------------------------


@dataclass
class GardenState:
    """Snapshot of the outdoor garden conditions."""

    light: str
    season: str
    palette: list[str]
    music_key: str
    last_update: float


# ---------------------------------------------------------------------------
# State update
# ---------------------------------------------------------------------------


def build_garden_state(brightness: float, observed_at: datetime) -> GardenState:
    """Build a deterministic garden state for a known observation time."""
    light = estimate_outdoor_light(brightness, observed_at.hour)
    season = estimate_season(observed_at.month)
    palette = suggest_palette(light, season)
    music_key = suggest_music_key(light, season)

    return GardenState(
        light=light,
        season=season,
        palette=palette,
        music_key=music_key,
        last_update=observed_at.timestamp(),
    )


def update_garden_state(brightness: float) -> GardenState:
    """Combine all functions into a single GardenState using current time."""
    observed_ts = time.time()
    observed_at = datetime.fromtimestamp(observed_ts)
    state = build_garden_state(brightness, observed_at)
    state.last_update = observed_ts
    return state


def summarize_garden_state(state: GardenState) -> dict[str, object]:
    """Return a compact JSON-safe operator summary for a garden state."""
    primary_color = state.palette[0] if state.palette else "neutral"
    condition = f"{state.season} {state.light}"
    return {
        "condition": condition,
        "light": state.light,
        "season": state.season,
        "music_key": state.music_key,
        "palette": list(state.palette),
        "primary_color": primary_color,
        "palette_size": len(state.palette),
        "is_dark": state.light == "dark",
        "last_update": state.last_update,
        "summary": f"{condition} garden -> {state.music_key} using {primary_color}",
    }


# ---------------------------------------------------------------------------
# Atomic JSON write
# ---------------------------------------------------------------------------


def write_garden_state(state: GardenState, path: str = "/tmp/garden_state.json") -> None:
    """Atomic write of garden state — write to tmp file then os.replace."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(asdict(state), f, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


def write_current_garden_state(
    brightness: float,
    path: str = "/tmp/garden_state.json",
    *,
    observed_at: datetime | None = None,
) -> GardenState:
    """Build and atomically persist the current garden state."""
    state = build_garden_state(brightness, observed_at or datetime.now())
    write_garden_state(state, path)
    return state
