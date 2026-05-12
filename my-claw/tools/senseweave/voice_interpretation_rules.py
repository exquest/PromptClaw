"""SenseWeave voice-to-music interpretation rules.

Maps environmental and instrument sources to musical parameters so that
the organism can translate what it *hears* into compositional intent.

Each source type has an interpretation function that accepts a sensor
state dict and returns a frozen ``MusicalMapping`` with seven normalised
dimensions: pitch, rhythm, density, harmony, timbre, mix, and deference.

Sources covered:
  room_mic / perform_ve_condenser  — air microphone (quiet vs noisy room)
  contact_mic / membrane_mic       — membrane/contact vibration
  garden_mic                       — outdoor garden (rain, wind, inactivity)
  theramini_in                     — Theramini instrument (playing vs idle)
  archive                          — internal self-bus / memory recall
  network                          — network traffic / weather data
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _float_val(source: Mapping[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in source:
            try:
                return float(source[key])
            except (TypeError, ValueError):
                continue
    return default


def _str_val(source: Mapping[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        if key in source:
            val = source[key]
            if val is not None:
                return str(val)
    return default


def _bool_val(source: Mapping[str, Any], *keys: str, default: bool = False) -> bool:
    for key in keys:
        if key in source:
            val = source[key]
            if isinstance(val, str):
                return val.strip().lower() in {"1", "true", "yes"}
            return bool(val)
    return default


# ---------------------------------------------------------------------------
# MusicalMapping dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MusicalMapping:
    """Musical interpretation of a single sensor source.

    All fields are normalised to [0, 1]:
      pitch      — register bias (0 = low, 1 = high)
      rhythm     — rhythmic density (0 = sparse/still, 1 = driving/busy)
      density    — note/event density (0 = minimal, 1 = saturated)
      harmony    — harmonic complexity (0 = unison/simple, 1 = dense/dissonant)
      timbre     — brightness (0 = dark/warm, 1 = bright/cold)
      mix        — presence in the mix (0 = background, 1 = foreground)
      deference  — willingness to yield to other voices
                   (0 = assertive/leading, 1 = yielding/following)
    """

    source: str
    pitch: float
    rhythm: float
    density: float
    harmony: float
    timbre: float
    mix: float
    deference: float


# ---------------------------------------------------------------------------
# Source name resolution
# ---------------------------------------------------------------------------

SOURCE_ALIASES: dict[str, str] = {
    "perform_ve_condenser": "room_mic",
    "room_perform_ve": "room_mic",
    "membrane_mic": "contact_mic",
}

#: Canonical source names recognised by the interpreter.
KNOWN_SOURCES: frozenset[str] = frozenset({
    "room_mic",
    "contact_mic",
    "garden_mic",
    "theramini_in",
    "archive",
    "network",
})


def canonical_source(name: str) -> str:
    """Resolve aliases and return the canonical source name."""
    return SOURCE_ALIASES.get(name, name)


# ---------------------------------------------------------------------------
# Room mic interpretation
# ---------------------------------------------------------------------------

def _interpret_room(state: Mapping[str, Any]) -> MusicalMapping:
    """Room mic / Perform-VE condenser.

    Quiet rooms produce high-register, sparse, yielding textures.
    Noisy rooms produce denser, rhythmic, forward material.
    """
    activity = _str_val(state, "activity_level", "activity", default="quiet")
    has_transient = _bool_val(state, "recent_transient", "transient")
    speech = _bool_val(state, "speech_detected", "detected")
    rms = _float_val(state, "rms", default=0.0)

    if activity == "active":
        base_energy = 0.8
    elif activity == "moderate":
        base_energy = 0.5
    else:
        base_energy = 0.15

    if has_transient:
        base_energy = min(base_energy + 0.15, 1.0)
    if speech:
        base_energy = min(base_energy + 0.1, 1.0)
    if rms > 0:
        base_energy = _clamp(base_energy + rms * 0.2)

    return MusicalMapping(
        source="room_mic",
        pitch=_clamp(0.7 - base_energy * 0.4),
        rhythm=_clamp(base_energy * 0.8),
        density=_clamp(base_energy * 0.75),
        harmony=_clamp(0.2 + base_energy * 0.4),
        timbre=_clamp(0.3 + base_energy * 0.35),
        mix=_clamp(0.15 + base_energy * 0.55),
        deference=_clamp(0.85 - base_energy * 0.55),
    )


# ---------------------------------------------------------------------------
# Contact / membrane mic interpretation
# ---------------------------------------------------------------------------

_VIBRATION_PROFILES: dict[str, dict[str, float]] = {
    "rain": {
        "pitch": 0.55,
        "rhythm": 0.65,
        "density": 0.7,
        "harmony": 0.35,
        "timbre": 0.45,
        "mix": 0.5,
        "deference": 0.55,
    },
    "wind": {
        "pitch": 0.3,
        "rhythm": 0.2,
        "density": 0.25,
        "harmony": 0.2,
        "timbre": 0.25,
        "mix": 0.35,
        "deference": 0.7,
    },
    "impact": {
        "pitch": 0.35,
        "rhythm": 0.8,
        "density": 0.6,
        "harmony": 0.45,
        "timbre": 0.7,
        "mix": 0.65,
        "deference": 0.3,
    },
}


def _interpret_contact(state: Mapping[str, Any]) -> MusicalMapping:
    """Contact / membrane mic — surface vibrations.

    Recognises vibration profiles (rain, wind, impact) when provided,
    otherwise derives mapping from activity level and transient presence.
    """
    vibration_type = _str_val(state, "vibration_type", "vibration", default="")
    profile = _VIBRATION_PROFILES.get(vibration_type)
    if profile is not None:
        return MusicalMapping(source="contact_mic", **{k: _clamp(v) for k, v in profile.items()})

    activity = _str_val(state, "activity_level", "activity", default="quiet")
    has_transient = _bool_val(state, "recent_transient", "transient")
    rms = _float_val(state, "rms", default=0.0)

    if activity == "active":
        energy = 0.75
    elif activity == "moderate":
        energy = 0.45
    else:
        energy = 0.1

    if has_transient:
        energy = min(energy + 0.2, 1.0)
    if rms > 0:
        energy = _clamp(energy + rms * 0.25)

    return MusicalMapping(
        source="contact_mic",
        pitch=_clamp(0.35 + energy * 0.15),
        rhythm=_clamp(energy * 0.85),
        density=_clamp(energy * 0.7),
        harmony=_clamp(0.25 + energy * 0.3),
        timbre=_clamp(0.4 + energy * 0.35),
        mix=_clamp(0.2 + energy * 0.5),
        deference=_clamp(0.6 - energy * 0.35),
    )


# ---------------------------------------------------------------------------
# Garden mic interpretation
# ---------------------------------------------------------------------------

def _interpret_garden(state: Mapping[str, Any]) -> MusicalMapping:
    """Outdoor garden mic.

    Inactive garden = minimal, yielding.  Rain/wind push specific shapes.
    Active garden (birds, rustling) drives mid-level organic textures.
    """
    activity = _str_val(state, "activity_level", "activity", default="quiet")
    weather = _str_val(state, "weather", default="")
    brightness = _float_val(state, "brightness", default=0.5)
    rms = _float_val(state, "rms", default=0.0)

    # Weather overrides
    if weather == "rain":
        return MusicalMapping(
            source="garden_mic",
            pitch=0.5,
            rhythm=0.6,
            density=0.65,
            harmony=0.3,
            timbre=0.4,
            mix=0.45,
            deference=0.6,
        )
    if weather == "wind":
        return MusicalMapping(
            source="garden_mic",
            pitch=0.25,
            rhythm=0.15,
            density=0.2,
            harmony=0.15,
            timbre=0.2,
            mix=0.3,
            deference=0.75,
        )

    # Activity-based
    if activity == "active":
        energy = 0.6
    elif activity == "moderate":
        energy = 0.35
    else:
        # Inactive garden — very quiet
        energy = 0.05

    if rms > 0:
        energy = _clamp(energy + rms * 0.2)

    # Brightness gently shifts timbre (brighter day = slightly brighter sound)
    timbre_shift = (brightness - 0.5) * 0.15

    return MusicalMapping(
        source="garden_mic",
        pitch=_clamp(0.4 + energy * 0.2),
        rhythm=_clamp(energy * 0.5),
        density=_clamp(energy * 0.55),
        harmony=_clamp(0.1 + energy * 0.25),
        timbre=_clamp(0.3 + energy * 0.2 + timbre_shift),
        mix=_clamp(0.1 + energy * 0.4),
        deference=_clamp(0.8 - energy * 0.4),
    )


# ---------------------------------------------------------------------------
# Theramini interpretation
# ---------------------------------------------------------------------------

def _interpret_theramini(state: Mapping[str, Any]) -> MusicalMapping:
    """Theramini instrument source.

    When playing, the Theramini leads — high mix, low deference, melodic.
    When idle, it yields completely and fades to near-silence.
    """
    is_playing = _bool_val(state, "is_playing", "playing")
    pitch_note = _str_val(state, "pitch_note", "pitch", default="")
    rms = _float_val(state, "rms", default=0.0)

    if not is_playing:
        return MusicalMapping(
            source="theramini_in",
            pitch=0.5,
            rhythm=0.0,
            density=0.0,
            harmony=0.1,
            timbre=0.3,
            mix=0.0,
            deference=1.0,
        )

    # Playing — lead voice
    energy = 0.7
    if rms > 0:
        energy = _clamp(energy + rms * 0.3)

    # Pitch affects register mapping: higher notes -> higher pitch bias
    pitch_bias = 0.6
    if pitch_note:
        # Simple heuristic: notes with sharps/high octave letters tend higher
        if any(c in pitch_note for c in "567"):
            pitch_bias = 0.8
        elif any(c in pitch_note for c in "234"):
            pitch_bias = 0.5
        elif any(c in pitch_note for c in "01"):
            pitch_bias = 0.3

    return MusicalMapping(
        source="theramini_in",
        pitch=_clamp(pitch_bias),
        rhythm=_clamp(0.3 + energy * 0.3),
        density=_clamp(0.25 + energy * 0.35),
        harmony=_clamp(0.35 + energy * 0.25),
        timbre=_clamp(0.5 + energy * 0.2),
        mix=_clamp(0.55 + energy * 0.35),
        deference=_clamp(0.15),
    )


# ---------------------------------------------------------------------------
# Archive / self-bus interpretation
# ---------------------------------------------------------------------------

def _interpret_archive(state: Mapping[str, Any]) -> MusicalMapping:
    """Archive / self-bus — recall of previously recorded material.

    Active recall surfaces memory textures at moderate presence.
    Idle archive remains silent and fully deferential.
    """
    is_playing = _bool_val(state, "is_playing", "active")
    has_clicks = _bool_val(state, "has_clicks")
    rms = _float_val(state, "rms", default=0.0)
    age_factor = _float_val(state, "age_factor", default=0.5)

    if not is_playing or has_clicks:
        return MusicalMapping(
            source="archive",
            pitch=0.5,
            rhythm=0.0,
            density=0.0,
            harmony=0.1,
            timbre=0.3,
            mix=0.0,
            deference=1.0,
        )

    energy = 0.5
    if rms > 0:
        energy = _clamp(energy + rms * 0.3)

    # Older archive material is warmer and more deferential
    warmth = _clamp(age_factor * 0.3)

    return MusicalMapping(
        source="archive",
        pitch=_clamp(0.45 - warmth * 0.15),
        rhythm=_clamp(0.2 + energy * 0.25),
        density=_clamp(0.3 + energy * 0.25),
        harmony=_clamp(0.25 + energy * 0.2),
        timbre=_clamp(0.4 - warmth * 0.2 + energy * 0.15),
        mix=_clamp(0.3 + energy * 0.3),
        deference=_clamp(0.55 + warmth * 0.15 - energy * 0.2),
    )


# ---------------------------------------------------------------------------
# Network / weather interpretation
# ---------------------------------------------------------------------------

# Network activity classifications mirroring antenna_to_skin.py thresholds
_BPS_QUIET = 10_000
_BPS_MODERATE = 100_000
_BPS_BUSY = 1_000_000


def _interpret_network(state: Mapping[str, Any]) -> MusicalMapping:
    """Network traffic and weather signals.

    High traffic = restless energy.  Weather conditions shape timbre.
    Calm network = yielding background hum.
    """
    activity = _str_val(state, "activity", default="")
    bps = _float_val(state, "bytes_per_second", "bps", default=0.0)
    latency = _float_val(state, "latency_ms", default=0.0)
    weather = _str_val(state, "weather", default="")
    connections = _float_val(state, "connections_active", "connections", default=0.0)

    # Derive activity from bps if not explicitly given
    if not activity:
        if bps >= _BPS_BUSY:
            activity = "storm"
        elif bps >= _BPS_MODERATE:
            activity = "busy"
        elif bps >= _BPS_QUIET:
            activity = "moderate"
        else:
            activity = "quiet"

    if activity == "storm":
        net_energy = 0.85
    elif activity == "busy":
        net_energy = 0.6
    elif activity == "moderate":
        net_energy = 0.35
    else:
        net_energy = 0.1

    # Latency adds tension
    latency_factor = _clamp(latency / 500.0)

    # Connection count adds density
    conn_factor = _clamp(connections / 200.0)

    # Weather overlay (shifts timbre and harmony)
    weather_timbre = 0.0
    weather_harmony = 0.0
    if weather in {"rain", "overcast"}:
        weather_timbre = -0.1
        weather_harmony = 0.1
    elif weather in {"storm", "thunderstorm"}:
        weather_timbre = 0.15
        weather_harmony = 0.2
    elif weather in {"clear", "day", "bright_sun"}:
        weather_timbre = 0.1
        weather_harmony = -0.05

    return MusicalMapping(
        source="network",
        pitch=_clamp(0.4 + net_energy * 0.25 + latency_factor * 0.1),
        rhythm=_clamp(net_energy * 0.6 + conn_factor * 0.15),
        density=_clamp(net_energy * 0.5 + conn_factor * 0.25),
        harmony=_clamp(0.2 + net_energy * 0.3 + latency_factor * 0.15 + weather_harmony),
        timbre=_clamp(0.35 + net_energy * 0.2 + weather_timbre),
        mix=_clamp(0.1 + net_energy * 0.35),
        deference=_clamp(0.75 - net_energy * 0.4),
    )


# ---------------------------------------------------------------------------
# Unified interpreter dispatch
# ---------------------------------------------------------------------------

_INTERPRETERS: dict[str, Any] = {
    "room_mic": _interpret_room,
    "contact_mic": _interpret_contact,
    "garden_mic": _interpret_garden,
    "theramini_in": _interpret_theramini,
    "archive": _interpret_archive,
    "network": _interpret_network,
}


def interpret_source(source_name: str, state: Mapping[str, Any]) -> MusicalMapping:
    """Interpret a sensor source state into musical mapping.

    Resolves aliases (e.g. ``perform_ve_condenser`` -> ``room_mic``,
    ``membrane_mic`` -> ``contact_mic``) before dispatching.

    Raises ``KeyError`` if the source name is not recognised.
    """
    canonical = canonical_source(source_name)
    interpreter = _INTERPRETERS.get(canonical)
    if interpreter is None:
        raise KeyError(f"Unknown source: {source_name!r} (canonical: {canonical!r})")
    return interpreter(state)


def interpret_all(
    source_states: Mapping[str, Mapping[str, Any]],
) -> dict[str, MusicalMapping]:
    """Interpret all provided source states into musical mappings.

    Keys in *source_states* are source names (aliases accepted).
    Returns a dict keyed by canonical source name.
    """
    result: dict[str, MusicalMapping] = {}
    for name, state in source_states.items():
        canonical = canonical_source(name)
        if canonical in _INTERPRETERS:
            result[canonical] = _INTERPRETERS[canonical](state)
    return result
