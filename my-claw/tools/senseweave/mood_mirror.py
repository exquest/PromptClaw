"""Mood Mirror — maps organism mood to visual/audio/art parameters.

Bridge between how CypherClaw's house *feels* and how it *looks/sounds*.
Mood dict keys: energy (0-1), valence (0-1), arousal (0-1).
"""
from __future__ import annotations


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Face expression
# ---------------------------------------------------------------------------

def mood_to_face_expression(mood: dict) -> str:
    """Map energy/valence/arousal to a face expression string.

    Priority-ordered rules (first match wins):
    - sleeping: low energy AND low arousal
    - excited:  high energy AND high arousal AND positive valence
    - anxious:  high arousal AND negative valence
    - happy:    positive valence AND moderate+ arousal or energy
    - sad:      low valence AND low energy
    - curious:  moderate arousal (catch-all active state)
    - calm:     default
    """
    energy = _clamp(mood.get("energy", 0.5))
    valence = _clamp(mood.get("valence", 0.5))
    arousal = _clamp(mood.get("arousal", 0.5))

    if energy < 0.25 and arousal < 0.25:
        return "sleeping"
    if energy >= 0.7 and arousal >= 0.7 and valence >= 0.6:
        return "excited"
    if arousal >= 0.7 and valence < 0.4:
        return "anxious"
    if valence >= 0.6 and (arousal >= 0.4 or energy >= 0.5):
        return "happy"
    if valence < 0.3 and energy < 0.4:
        return "sad"
    if arousal >= 0.5:
        return "curious"
    return "calm"


# ---------------------------------------------------------------------------
# Background colour
# ---------------------------------------------------------------------------

def mood_to_background_color(mood: dict) -> tuple[int, int, int]:
    """Map mood to an RGB background colour for CypherClaw's face display.

    Colour mapping intent:
    - calm    -> deep blue
    - happy   -> warm blue
    - anxious -> dark red
    - sleeping-> near black
    - excited -> purple
    """
    energy = _clamp(mood.get("energy", 0.5))
    valence = _clamp(mood.get("valence", 0.5))
    arousal = _clamp(mood.get("arousal", 0.5))

    expression = mood_to_face_expression(mood)

    colour_map: dict[str, tuple[int, int, int]] = {
        "sleeping": (15, 10, 25),
        "calm":     (30, 40, 140),
        "happy":    (60, 80, 160),
        "curious":  (50, 70, 130),
        "anxious":  (140, 30, 30),
        "excited":  (150, 40, 180),
        "sad":      (40, 35, 80),
    }

    base = colour_map.get(expression, (30, 40, 140))

    # Modulate brightness by energy (higher energy = slightly brighter)
    brightness = 0.7 + 0.3 * energy
    r = int(_clamp(base[0] * brightness, 0, 255))
    g = int(_clamp(base[1] * brightness, 0, 255))
    b = int(_clamp(base[2] * brightness, 0, 255))

    return (r, g, b)


# ---------------------------------------------------------------------------
# Music parameters
# ---------------------------------------------------------------------------

def mood_to_music_params(mood: dict) -> dict:
    """Map mood to music generation parameters.

    Returns dict with:
    - tempo_factor: 0.8 (sleepy) to 1.2 (excited)
    - volume_factor: 0.3 (sleeping) to 1.0 (active)
    - key_preference: "major" or "minor"
    - density: "sparse" or "dense"
    """
    energy = _clamp(mood.get("energy", 0.5))
    valence = _clamp(mood.get("valence", 0.5))
    arousal = _clamp(mood.get("arousal", 0.5))

    # Tempo: blend of energy and arousal, mapped to 0.8-1.2
    activity = (energy + arousal) / 2.0
    tempo_factor = 0.8 + 0.4 * activity

    # Volume: energy-driven, 0.3-1.0
    volume_factor = 0.3 + 0.7 * activity

    # Key: valence-driven
    key_preference = "major" if valence > 0.5 else "minor"

    # Density: energy-driven
    density = "dense" if energy >= 0.65 else "sparse" if energy < 0.35 else "sparse" if energy < 0.5 else "dense"
    # Simplify: threshold at 0.5 with some hysteresis
    if energy >= 0.65:
        density = "dense"
    elif energy <= 0.35:
        density = "sparse"
    else:
        # Middle band: lean on arousal
        density = "dense" if arousal >= 0.6 else "sparse"

    # Clamp ranges
    tempo_factor = round(_clamp(tempo_factor, 0.8, 1.2), 3)
    volume_factor = round(_clamp(volume_factor, 0.3, 1.0), 3)

    return {
        "tempo_factor": tempo_factor,
        "volume_factor": volume_factor,
        "key_preference": key_preference,
        "density": density,
    }


# ---------------------------------------------------------------------------
# Art parameters
# ---------------------------------------------------------------------------

def mood_to_art_params(mood: dict) -> dict:
    """Map mood to art generation hints.

    Returns dict with:
    - palette: "warm" / "cool" / "dark" / "bright"
    - complexity: "simple" / "moderate" / "complex"
    - theme_hints: list[str] contextual themes
    """
    energy = _clamp(mood.get("energy", 0.5))
    valence = _clamp(mood.get("valence", 0.5))
    arousal = _clamp(mood.get("arousal", 0.5))

    # --- Palette ---
    if valence >= 0.6 and energy >= 0.6:
        palette = "bright"
    elif valence >= 0.5:
        palette = "warm"
    elif energy < 0.4:
        palette = "dark"
    else:
        palette = "cool"

    # --- Complexity ---
    activity = (energy + arousal) / 2.0
    if activity >= 0.65:
        complexity = "complex"
    elif activity <= 0.35:
        complexity = "simple"
    else:
        complexity = "moderate"

    # --- Theme hints ---
    hints: list[str] = []

    if energy < 0.25 and arousal < 0.25:
        hints.extend(["night", "dreams", "sleeping"])
    elif energy < 0.3:
        hints.append("quiet")

    if valence >= 0.7:
        hints.append("joyful")
    elif valence < 0.3:
        hints.append("melancholy")

    if arousal >= 0.7 and valence >= 0.6:
        hints.append("celebration")
    elif arousal >= 0.7:
        hints.append("tension")

    if energy >= 0.7 and arousal >= 0.7:
        hints.append("energy")

    if valence >= 0.5 and arousal < 0.4:
        hints.append("peaceful")

    # Ensure at least one hint
    if not hints:
        hints.append("ambient")

    return {
        "palette": palette,
        "complexity": complexity,
        "theme_hints": hints,
    }
