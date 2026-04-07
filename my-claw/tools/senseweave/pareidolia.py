"""Pareidolia Scene Engine — everything has a face, every surface has texture.

CypherClaw's visual art system: oval shapes, simple eyes, expressive mouths,
textured backgrounds, mood through color. Renders PIL images of characters
in environments driven by time-of-day, weather, and organism mood.

PARE-002: Color palette system — palettes driven by time, mood, weather.
PARE-004: Weather and time-of-day rendering — sky gradients, rain, snow,
          stars, sun/moon, clouds.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Sequence

try:
    from PIL import Image, ImageDraw
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    Image = ImageDraw = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PARE-002: Color Palette System
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColorPalette:
    """A coherent color palette for a Pareidolia scene.

    All colors are (R, G, B) tuples with values 0-255.
    """
    bg: tuple[int, int, int]
    ground: tuple[int, int, int]
    sky: tuple[int, int, int]
    character_fill: tuple[int, int, int]
    character_outline: tuple[int, int, int]
    accent: tuple[int, int, int]
    text: tuple[int, int, int]


PALETTES: dict[str, ColorPalette] = {
    # Dawn — pink/gold sky, warm brown ground, soft orange characters
    "dawn": ColorPalette(
        bg=(45, 30, 50),
        ground=(120, 85, 60),
        sky=(210, 140, 120),
        character_fill=(220, 160, 100),
        character_outline=(140, 80, 50),
        accent=(255, 190, 100),
        text=(255, 240, 220),
    ),
    # Day happy — light blue sky, green ground, bright characters
    "day_happy": ColorPalette(
        bg=(200, 220, 240),
        ground=(90, 160, 70),
        sky=(130, 190, 240),
        character_fill=(240, 200, 120),
        character_outline=(160, 120, 60),
        accent=(255, 220, 80),
        text=(40, 40, 60),
    ),
    # Day calm — soft blue sky, muted green ground, gentle colors
    "day_calm": ColorPalette(
        bg=(180, 200, 220),
        ground=(110, 150, 90),
        sky=(160, 190, 220),
        character_fill=(200, 180, 140),
        character_outline=(130, 110, 80),
        accent=(180, 190, 160),
        text=(50, 50, 70),
    ),
    # Overcast — gray sky, dark green ground, muted characters
    "overcast": ColorPalette(
        bg=(140, 145, 150),
        ground=(70, 100, 60),
        sky=(160, 165, 170),
        character_fill=(160, 150, 140),
        character_outline=(100, 90, 80),
        accent=(130, 140, 120),
        text=(60, 60, 70),
    ),
    # Dusk — orange/purple sky, dark ground, warm silhouettes
    "dusk": ColorPalette(
        bg=(60, 40, 70),
        ground=(50, 40, 35),
        sky=(180, 100, 120),
        character_fill=(80, 60, 70),
        character_outline=(50, 30, 40),
        accent=(220, 140, 80),
        text=(240, 220, 200),
    ),
    # Night — deep blue/black sky, dark ground, silver/blue characters
    "night": ColorPalette(
        bg=(15, 15, 35),
        ground=(25, 30, 25),
        sky=(20, 25, 55),
        character_fill=(100, 110, 140),
        character_outline=(60, 65, 90),
        accent=(160, 170, 200),
        text=(200, 210, 230),
    ),
    # Night calm — same but softer
    "night_calm": ColorPalette(
        bg=(20, 20, 40),
        ground=(30, 35, 30),
        sky=(30, 35, 60),
        character_fill=(110, 115, 135),
        character_outline=(70, 75, 95),
        accent=(140, 150, 180),
        text=(190, 200, 220),
    ),
    # Rain — gray-blue sky, wet-looking ground, cool characters
    "rain": ColorPalette(
        bg=(80, 90, 110),
        ground=(55, 65, 55),
        sky=(100, 110, 130),
        character_fill=(120, 130, 150),
        character_outline=(70, 80, 100),
        accent=(90, 120, 160),
        text=(200, 210, 225),
    ),
    # Snow — white-blue sky, white ground, dark characters for contrast
    "snow": ColorPalette(
        bg=(210, 220, 235),
        ground=(230, 235, 245),
        sky=(200, 215, 235),
        character_fill=(60, 60, 80),
        character_outline=(40, 40, 55),
        accent=(140, 160, 200),
        text=(40, 40, 60),
    ),
}


def select_palette(hour: int, mood: str = "calm", weather: str = "clear") -> ColorPalette:
    """Choose a color palette based on time-of-day, mood, and weather.

    Args:
        hour: Hour of day 0-23.
        mood: One of "happy", "calm", "sad", "anxious", "excited", "curious".
        weather: One of "clear", "rain", "snow", "overcast", "fog".

    Returns:
        A ColorPalette appropriate for the given conditions.
    """
    hour = max(0, min(23, hour))

    # Weather overrides take priority
    if weather == "rain":
        return PALETTES["rain"]
    if weather == "snow":
        return PALETTES["snow"]
    if weather in ("overcast", "fog"):
        return PALETTES["overcast"]

    # Time-of-day mapping
    if 5 <= hour <= 7:
        return PALETTES["dawn"]
    if 8 <= hour <= 11:
        if mood == "happy":
            return PALETTES["day_happy"]
        return PALETTES["day_calm"]
    if 12 <= hour <= 16:
        if mood in ("happy", "excited"):
            return PALETTES["day_happy"]
        return PALETTES["day_calm"]
    if 17 <= hour <= 19:
        return PALETTES["dusk"]
    if 20 <= hour <= 23 or 0 <= hour <= 1:
        if mood == "calm":
            return PALETTES["night_calm"]
        return PALETTES["night"]
    # 2-4am: deep night
    return PALETTES["night"]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _lerp_color(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colors. t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _require_pillow() -> None:
    if not HAS_PILLOW:
        raise ImportError("Pillow is required for Pareidolia rendering")


# ---------------------------------------------------------------------------
# PARE-004: Weather and Time-of-Day Rendering
# ---------------------------------------------------------------------------

def draw_sky_gradient(
    draw: "ImageDraw.ImageDraw",
    width: int,
    height: int,
    palette: ColorPalette,
    hour: int,
) -> None:
    """Draw a gradient sky on the upper portion of the image.

    Dawn and dusk get warm horizontal gradients blending sky and accent.
    Night gets a dark gradient suitable for stars.
    Day gets a gentle top-to-bottom gradient.

    Args:
        draw: PIL ImageDraw object.
        width: Image width in pixels.
        height: Image height in pixels.
        palette: The ColorPalette to use.
        hour: Hour of day (0-23) for gradient style selection.
    """
    sky_height = int(height * 0.6)

    is_dawn = 5 <= hour <= 7
    is_dusk = 17 <= hour <= 19

    if is_dawn or is_dusk:
        # Warm horizontal gradient — accent blends into sky color
        top_color = palette.sky
        bottom_color = palette.accent
    else:
        # Standard vertical gradient — darker at top
        top_color = _lerp_color(palette.sky, palette.bg, 0.3)
        bottom_color = palette.sky

    for y in range(sky_height):
        t = y / max(1, sky_height - 1)
        color = _lerp_color(top_color, bottom_color, t)
        draw.line([(0, y), (width, y)], fill=color)


def draw_stars(
    draw: "ImageDraw.ImageDraw",
    width: int,
    height: int,
    count: int = 50,
    seed: int | None = None,
) -> None:
    """Draw random small dots for a night sky.

    Stars are placed in the upper 60% of the image with varying brightness.

    Args:
        draw: PIL ImageDraw object.
        width: Image width.
        height: Image height.
        count: Number of stars to draw.
        seed: Optional RNG seed for reproducibility.
    """
    rng = random.Random(seed)
    sky_height = int(height * 0.6)

    for _ in range(count):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, sky_height - 1)
        brightness = rng.randint(150, 255)
        size = rng.choice([0, 0, 0, 1])  # mostly single pixels
        color = (brightness, brightness, rng.randint(brightness - 30, brightness))
        if size == 0:
            draw.point((x, y), fill=color)
        else:
            draw.ellipse([x, y, x + 2, y + 2], fill=color)


def draw_rain(
    draw: "ImageDraw.ImageDraw",
    width: int,
    height: int,
    intensity: float = 0.5,
    seed: int | None = None,
) -> None:
    """Draw vertical rain lines with a slight angle.

    Args:
        draw: PIL ImageDraw object.
        width: Image width.
        height: Image height.
        intensity: Rain density from 0.0 (none) to 1.0 (downpour).
        seed: Optional RNG seed for reproducibility.
    """
    intensity = max(0.0, min(1.0, intensity))
    rng = random.Random(seed)
    num_drops = int(80 * intensity * (width / 400))

    for _ in range(num_drops):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        length = rng.randint(8, 25)
        drift = rng.randint(1, 4)  # slight angle
        alpha = rng.randint(80, 180)
        color = (180, 190, 210, alpha)
        draw.line([(x, y), (x + drift, y + length)], fill=color, width=1)


def draw_snow(
    draw: "ImageDraw.ImageDraw",
    width: int,
    height: int,
    intensity: float = 0.5,
    seed: int | None = None,
) -> None:
    """Draw small white circles falling as snow.

    Args:
        draw: PIL ImageDraw object.
        width: Image width.
        height: Image height.
        intensity: Snow density from 0.0 to 1.0.
        seed: Optional RNG seed for reproducibility.
    """
    intensity = max(0.0, min(1.0, intensity))
    rng = random.Random(seed)
    num_flakes = int(60 * intensity * (width / 400))

    for _ in range(num_flakes):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        radius = rng.randint(1, 3)
        alpha = rng.randint(180, 250)
        color = (240, 245, 255, alpha)
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            fill=color,
        )


def draw_sun(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    radius: int,
    palette: ColorPalette,
) -> None:
    """Draw a simple sun circle with rays.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x coordinate.
        cy: Center y coordinate.
        radius: Sun body radius in pixels.
        palette: ColorPalette (uses accent for sun body, text for rays).
    """
    # Rays — lines radiating outward
    ray_length = int(radius * 1.8)
    num_rays = 12
    for i in range(num_rays):
        angle = (2 * math.pi * i) / num_rays
        x1 = cx + int(math.cos(angle) * (radius + 4))
        y1 = cy + int(math.sin(angle) * (radius + 4))
        x2 = cx + int(math.cos(angle) * ray_length)
        y2 = cy + int(math.sin(angle) * ray_length)
        draw.line([(x1, y1), (x2, y2)], fill=palette.accent, width=2)

    # Sun body — filled circle
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=palette.accent,
        outline=palette.text,
        width=1,
    )


def draw_moon(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    radius: int,
    phase: float = 0.5,
) -> None:
    """Draw a crescent or full moon for night sky.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x coordinate.
        cy: Center y coordinate.
        radius: Moon radius in pixels.
        phase: Moon phase from 0.0 (new/crescent) to 1.0 (full).
    """
    phase = max(0.0, min(1.0, phase))

    # Moon body
    moon_color = (230, 235, 215)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=moon_color,
    )

    if phase < 0.9:
        # Crescent — overlay a dark ellipse offset to the right
        shadow_color = (20, 25, 55)  # match night sky
        offset = int(radius * (1.0 - phase) * 0.8)
        draw.ellipse(
            [cx - radius + offset, cy - radius, cx + radius + offset, cy + radius],
            fill=shadow_color,
        )


def draw_clouds(
    draw: "ImageDraw.ImageDraw",
    width: int,
    y_range: tuple[int, int],
    count: int = 3,
    palette: ColorPalette | None = None,
    seed: int | None = None,
) -> None:
    """Draw cloud formations as overlapping ellipses.

    Args:
        draw: PIL ImageDraw object.
        width: Image width (clouds span the full width).
        y_range: (y_min, y_max) vertical range for cloud placement.
        count: Number of cloud clusters.
        palette: Optional palette for cloud color. Defaults to white.
        seed: Optional RNG seed for reproducibility.
    """
    rng = random.Random(seed)
    y_min, y_max = y_range

    if palette:
        base = _lerp_color(palette.sky, (255, 255, 255), 0.6)
    else:
        base = (235, 240, 245)

    for _ in range(count):
        cx = rng.randint(50, width - 50)
        cy = rng.randint(y_min, y_max)

        # Each cloud is 3-5 overlapping ovals
        num_puffs = rng.randint(3, 5)
        for _ in range(num_puffs):
            w = rng.randint(40, 90)
            h = rng.randint(20, 45)
            ox = rng.randint(-40, 40)
            oy = rng.randint(-15, 10)
            alpha = rng.randint(160, 220)
            color = (*base, alpha)
            draw.ellipse(
                [cx + ox - w, cy + oy - h, cx + ox + w, cy + oy + h],
                fill=color,
            )


# ---------------------------------------------------------------------------
# Core drawing primitives — the Pareidolia style
# ---------------------------------------------------------------------------

def draw_ground(
    draw: "ImageDraw.ImageDraw",
    width: int,
    height: int,
    palette: ColorPalette,
    texture_seed: int | None = None,
) -> None:
    """Draw the ground plane with subtle texture.

    Ground occupies the lower ~40% of the image with a slight gradient
    and scattered dots for a hand-drawn texture feel.

    Args:
        draw: PIL ImageDraw object.
        width: Image width.
        height: Image height.
        palette: ColorPalette for ground colors.
        texture_seed: Optional RNG seed for reproducibility.
    """
    ground_top = int(height * 0.6)
    rng = random.Random(texture_seed)

    # Ground gradient — darker at the bottom
    for y in range(ground_top, height):
        t = (y - ground_top) / max(1, height - ground_top - 1)
        color = _lerp_color(palette.ground, _lerp_color(palette.ground, palette.bg, 0.4), t)
        draw.line([(0, y), (width, y)], fill=color)

    # Texture dots
    num_dots = int(width * (height - ground_top) / 200)
    for _ in range(num_dots):
        x = rng.randint(0, width - 1)
        y = rng.randint(ground_top, height - 1)
        shade = rng.randint(-20, 20)
        g = palette.ground
        dot_color = (
            max(0, min(255, g[0] + shade)),
            max(0, min(255, g[1] + shade)),
            max(0, min(255, g[2] + shade)),
        )
        draw.point((x, y), fill=dot_color)


def draw_face_eyes(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    size: int,
    expression: str = "neutral",
    palette: ColorPalette | None = None,
) -> None:
    """Draw a pair of simple eyes — the Pareidolia signature.

    Every face has eyes. The expression changes the eye shape and position.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x of the face.
        cy: Center y of the face (eyes sit slightly above center).
        size: Overall face diameter — eyes scale proportionally.
        expression: One of "neutral", "happy", "sad", "curious", "sleeping".
        palette: Optional palette for eye color.
    """
    eye_color = (30, 30, 40) if palette is None else palette.character_outline
    eye_radius = max(2, size // 12)
    eye_spacing = max(4, size // 5)
    eye_y = cy - size // 8

    left_x = cx - eye_spacing
    right_x = cx + eye_spacing

    if expression == "sleeping":
        # Closed eyes — horizontal lines
        draw.line(
            [(left_x - eye_radius, eye_y), (left_x + eye_radius, eye_y)],
            fill=eye_color, width=2,
        )
        draw.line(
            [(right_x - eye_radius, eye_y), (right_x + eye_radius, eye_y)],
            fill=eye_color, width=2,
        )
    elif expression == "happy":
        # Upturned arcs (happy squint)
        draw.arc(
            [left_x - eye_radius, eye_y - eye_radius,
             left_x + eye_radius, eye_y + eye_radius],
            start=200, end=340, fill=eye_color, width=2,
        )
        draw.arc(
            [right_x - eye_radius, eye_y - eye_radius,
             right_x + eye_radius, eye_y + eye_radius],
            start=200, end=340, fill=eye_color, width=2,
        )
    elif expression == "sad":
        # Droopy ovals — slightly lower outer corners
        draw.ellipse(
            [left_x - eye_radius, eye_y - eye_radius + 1,
             left_x + eye_radius, eye_y + eye_radius + 1],
            fill=eye_color,
        )
        draw.ellipse(
            [right_x - eye_radius, eye_y - eye_radius + 1,
             right_x + eye_radius, eye_y + eye_radius + 1],
            fill=eye_color,
        )
    elif expression == "curious":
        # Slightly larger, different-sized eyes
        draw.ellipse(
            [left_x - eye_radius, eye_y - eye_radius,
             left_x + eye_radius, eye_y + eye_radius],
            fill=eye_color,
        )
        big_r = eye_radius + max(1, eye_radius // 2)
        draw.ellipse(
            [right_x - big_r, eye_y - big_r,
             right_x + big_r, eye_y + big_r],
            fill=eye_color,
        )
    else:
        # Neutral — simple dots
        draw.ellipse(
            [left_x - eye_radius, eye_y - eye_radius,
             left_x + eye_radius, eye_y + eye_radius],
            fill=eye_color,
        )
        draw.ellipse(
            [right_x - eye_radius, eye_y - eye_radius,
             right_x + eye_radius, eye_y + eye_radius],
            fill=eye_color,
        )

    # Pupils — tiny highlight dots (not when sleeping)
    if expression != "sleeping":
        highlight_r = max(1, eye_radius // 3)
        highlight_color = (255, 255, 255)
        draw.ellipse(
            [left_x - highlight_r + 1, eye_y - highlight_r - 1,
             left_x + highlight_r + 1, eye_y + highlight_r - 1],
            fill=highlight_color,
        )
        draw.ellipse(
            [right_x - highlight_r + 1, eye_y - highlight_r - 1,
             right_x + highlight_r + 1, eye_y + highlight_r - 1],
            fill=highlight_color,
        )


def draw_face_mouth(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    size: int,
    expression: str = "neutral",
    palette: ColorPalette | None = None,
) -> None:
    """Draw a simple mouth below the eyes.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x of the face.
        cy: Center y of the face.
        size: Face diameter.
        expression: Expression affects mouth shape.
        palette: Optional palette.
    """
    mouth_color = (40, 35, 40) if palette is None else palette.character_outline
    mouth_y = cy + size // 6
    mouth_w = max(3, size // 6)

    if expression == "happy":
        # Smile arc
        draw.arc(
            [cx - mouth_w, mouth_y - mouth_w // 2,
             cx + mouth_w, mouth_y + mouth_w],
            start=10, end=170, fill=mouth_color, width=2,
        )
    elif expression == "sad":
        # Frown arc
        draw.arc(
            [cx - mouth_w, mouth_y,
             cx + mouth_w, mouth_y + mouth_w],
            start=190, end=350, fill=mouth_color, width=2,
        )
    elif expression == "curious":
        # Small 'o'
        r = max(2, mouth_w // 2)
        draw.ellipse(
            [cx - r, mouth_y - r, cx + r, mouth_y + r],
            outline=mouth_color, width=2,
        )
    elif expression == "sleeping":
        # Tiny line
        draw.line(
            [(cx - mouth_w // 2, mouth_y), (cx + mouth_w // 2, mouth_y)],
            fill=mouth_color, width=1,
        )
    else:
        # Neutral — gentle horizontal line
        draw.line(
            [(cx - mouth_w, mouth_y), (cx + mouth_w, mouth_y)],
            fill=mouth_color, width=2,
        )


def draw_character(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    size: int,
    expression: str = "neutral",
    palette: ColorPalette | None = None,
    body_shape: str = "oval",
) -> None:
    """Draw a Pareidolia character — an oval body with eyes and mouth.

    The signature Pareidolia style: round shapes, simple faces, everything
    is alive and watching.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x position.
        cy: Center y position.
        size: Character diameter in pixels.
        expression: One of "neutral", "happy", "sad", "curious", "sleeping".
        palette: ColorPalette for colors. Falls back to gray defaults.
        body_shape: "oval", "round", "tall", "flat", or "spiky".
    """
    fill = (160, 160, 160) if palette is None else palette.character_fill
    outline = (80, 80, 80) if palette is None else palette.character_outline

    half = size // 2

    if body_shape == "round":
        draw.ellipse(
            [cx - half, cy - half, cx + half, cy + half],
            fill=fill, outline=outline, width=2,
        )
    elif body_shape == "tall":
        # Taller oval
        draw.ellipse(
            [cx - half, cy - int(half * 1.4), cx + half, cy + int(half * 1.4)],
            fill=fill, outline=outline, width=2,
        )
    elif body_shape == "flat":
        # Wide and short
        draw.ellipse(
            [cx - int(half * 1.4), cy - int(half * 0.7),
             cx + int(half * 1.4), cy + int(half * 0.7)],
            fill=fill, outline=outline, width=2,
        )
    elif body_shape == "spiky":
        # Oval body with small triangular spikes on top
        draw.ellipse(
            [cx - half, cy - half, cx + half, cy + half],
            fill=fill, outline=outline, width=2,
        )
        spike_count = 5
        for i in range(spike_count):
            angle = math.pi + (math.pi * i / (spike_count - 1))
            bx = cx + int(math.cos(angle) * half * 0.8)
            by = cy + int(math.sin(angle) * half * 0.8)
            tx = cx + int(math.cos(angle) * half * 1.3)
            ty = cy + int(math.sin(angle) * half * 1.3)
            draw.polygon(
                [(bx - 4, by), (tx, ty), (bx + 4, by)],
                fill=fill, outline=outline,
            )
    else:
        # Default oval — slightly taller than wide
        draw.ellipse(
            [cx - half, cy - int(half * 1.1), cx + half, cy + int(half * 1.1)],
            fill=fill, outline=outline, width=2,
        )

    # Face
    draw_face_eyes(draw, cx, cy, size, expression, palette)
    draw_face_mouth(draw, cx, cy, size, expression, palette)


# ---------------------------------------------------------------------------
# Scene elements — things that can appear in a Pareidolia scene
# ---------------------------------------------------------------------------

def draw_rock(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    size: int,
    palette: ColorPalette | None = None,
    has_face: bool = True,
) -> None:
    """Draw a rock (with optional face, because everything has a face).

    Args:
        draw: PIL ImageDraw object.
        cx: Center x.
        cy: Center y.
        size: Rock diameter.
        palette: ColorPalette.
        has_face: Whether the rock has eyes. Default True (Pareidolia!).
    """
    fill = (130, 125, 120) if palette is None else _lerp_color(palette.ground, (128, 128, 128), 0.5)
    outline = (90, 85, 80) if palette is None else _lerp_color(palette.ground, (60, 60, 60), 0.5)

    half = size // 2
    # Slightly irregular ellipse — wider than tall
    draw.ellipse(
        [cx - int(half * 1.2), cy - int(half * 0.7),
         cx + int(half * 1.2), cy + int(half * 0.7)],
        fill=fill, outline=outline, width=2,
    )

    if has_face:
        draw_face_eyes(draw, cx, cy - size // 10, size, "neutral", palette)


def draw_tree(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    ground_y: int,
    height: int,
    palette: ColorPalette | None = None,
    has_face: bool = True,
) -> None:
    """Draw a simple tree with a trunk and oval canopy.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x.
        ground_y: Y coordinate of the ground line.
        height: Tree height in pixels.
        palette: ColorPalette.
        has_face: Whether the tree has a face in its canopy.
    """
    trunk_color = (100, 70, 45) if palette is None else _lerp_color(palette.ground, (100, 70, 45), 0.6)
    canopy_color = (70, 130, 60) if palette is None else _lerp_color(palette.ground, (70, 140, 60), 0.4)
    outline = (50, 90, 40) if palette is None else _lerp_color(canopy_color, (30, 60, 20), 0.5)

    trunk_w = max(4, height // 8)
    trunk_top = ground_y - int(height * 0.4)

    # Trunk
    draw.rectangle(
        [cx - trunk_w, trunk_top, cx + trunk_w, ground_y],
        fill=trunk_color,
    )

    # Canopy — big oval
    canopy_cx = cx
    canopy_cy = trunk_top - int(height * 0.25)
    canopy_rx = int(height * 0.35)
    canopy_ry = int(height * 0.3)
    draw.ellipse(
        [canopy_cx - canopy_rx, canopy_cy - canopy_ry,
         canopy_cx + canopy_rx, canopy_cy + canopy_ry],
        fill=canopy_color, outline=outline, width=2,
    )

    if has_face:
        face_size = canopy_rx
        draw_face_eyes(draw, canopy_cx, canopy_cy, face_size, "calm", palette)


def draw_puddle(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    width_px: int,
    palette: ColorPalette | None = None,
    has_face: bool = True,
) -> None:
    """Draw a puddle — flat ellipse with optional face reflection.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x.
        cy: Center y.
        width_px: Puddle width.
        palette: ColorPalette.
        has_face: Whether the puddle shows a face.
    """
    fill = (80, 100, 140) if palette is None else _lerp_color(palette.sky, palette.ground, 0.3)
    height_px = max(4, width_px // 4)

    draw.ellipse(
        [cx - width_px // 2, cy - height_px, cx + width_px // 2, cy + height_px],
        fill=fill,
    )

    if has_face:
        # Faint face reflection in the puddle
        face_size = min(width_px // 2, height_px * 2)
        if face_size >= 6:
            draw_face_eyes(draw, cx, cy, face_size, "curious", palette)


def draw_bush(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    size: int,
    palette: ColorPalette | None = None,
) -> None:
    """Draw a small bush — overlapping green ovals.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x.
        cy: Center y.
        size: Bush diameter.
        palette: ColorPalette.
    """
    fill = (60, 120, 50) if palette is None else _lerp_color(palette.ground, (60, 130, 50), 0.5)
    outline = (40, 80, 30) if palette is None else _lerp_color(fill, (30, 60, 20), 0.5)

    half = size // 2
    # Three overlapping ovals
    for ox, oy in [(-half // 2, 0), (half // 2, 0), (0, -half // 3)]:
        draw.ellipse(
            [cx + ox - half // 2, cy + oy - half // 3,
             cx + ox + half // 2, cy + oy + half // 3],
            fill=fill, outline=outline, width=1,
        )


# ---------------------------------------------------------------------------
# Named characters — Basalt and Pebble
# ---------------------------------------------------------------------------

def draw_basalt(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    size: int,
    expression: str = "neutral",
    palette: ColorPalette | None = None,
) -> None:
    """Draw Basalt — the big rock character. Large, dark, steady.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x.
        cy: Center y.
        size: Character diameter.
        expression: Expression string.
        palette: ColorPalette.
    """
    fill = (90, 85, 80) if palette is None else _lerp_color(palette.character_fill, (90, 85, 80), 0.3)
    outline = (60, 55, 50) if palette is None else _lerp_color(palette.character_outline, (60, 55, 50), 0.3)

    half = size // 2
    # Basalt is a big, slightly flat oval
    draw.ellipse(
        [cx - int(half * 1.15), cy - int(half * 0.9),
         cx + int(half * 1.15), cy + int(half * 0.9)],
        fill=fill, outline=outline, width=3,
    )

    draw_face_eyes(draw, cx, cy, size, expression, palette)
    draw_face_mouth(draw, cx, cy, size, expression, palette)


def draw_pebble(
    draw: "ImageDraw.ImageDraw",
    cx: int,
    cy: int,
    size: int,
    expression: str = "neutral",
    palette: ColorPalette | None = None,
) -> None:
    """Draw Pebble — the small rock character. Small, round, energetic.

    Args:
        draw: PIL ImageDraw object.
        cx: Center x.
        cy: Center y.
        size: Character diameter (typically smaller than Basalt).
        expression: Expression string.
        palette: ColorPalette.
    """
    fill = (180, 175, 165) if palette is None else _lerp_color(palette.character_fill, (180, 175, 165), 0.3)
    outline = (120, 115, 105) if palette is None else _lerp_color(palette.character_outline, (120, 115, 105), 0.3)

    half = size // 2
    # Pebble is perfectly round
    draw.ellipse(
        [cx - half, cy - half, cx + half, cy + half],
        fill=fill, outline=outline, width=2,
    )

    draw_face_eyes(draw, cx, cy, size, expression, palette)
    draw_face_mouth(draw, cx, cy, size, expression, palette)


# ---------------------------------------------------------------------------
# Panel and story rendering (existing interface)
# ---------------------------------------------------------------------------

@dataclass
class PanelSpec:
    """Specification for a single comic panel."""
    characters: list[dict] = field(default_factory=list)
    # Each character dict: {"name": str, "expression": str, "x": int, "y": int, "size": int}
    elements: list[dict] = field(default_factory=list)
    # Each element dict: {"type": str, "x": int, "y": int, "size": int}
    dialogue: str = ""
    width: int = 640
    height: int = 480


def render_panel(
    spec: PanelSpec,
    palette: ColorPalette | None = None,
) -> "Image.Image":
    """Render a single comic panel as a PIL Image.

    Uses the Pareidolia style: oval characters with faces, textured ground,
    gradient sky. If no palette is given, uses a default day_calm palette.

    Args:
        spec: PanelSpec describing what to draw.
        palette: Optional ColorPalette. Defaults to day_calm.

    Returns:
        PIL Image (RGBA mode).
    """
    _require_pillow()

    if palette is None:
        palette = PALETTES["day_calm"]

    img = Image.new("RGBA", (spec.width, spec.height), palette.bg)
    draw = ImageDraw.Draw(img, "RGBA")

    # Sky gradient
    draw_sky_gradient(draw, spec.width, spec.height, palette, hour=12)

    # Ground
    draw_ground(draw, spec.width, spec.height, palette)

    # Scene elements
    for elem in spec.elements:
        elem_type = elem.get("type", "rock")
        ex = elem.get("x", spec.width // 2)
        ey = elem.get("y", int(spec.height * 0.7))
        es = elem.get("size", 40)

        if elem_type == "rock":
            draw_rock(draw, ex, ey, es, palette)
        elif elem_type == "tree":
            draw_tree(draw, ex, ey, es, palette)
        elif elem_type == "puddle":
            draw_puddle(draw, ex, ey, es, palette)
        elif elem_type == "bush":
            draw_bush(draw, ex, ey, es, palette)

    # Characters
    character_drawers = {
        "basalt": draw_basalt,
        "pebble": draw_pebble,
    }

    for char in spec.characters:
        name = char.get("name", "").lower()
        expr = char.get("expression", "neutral")
        cx = char.get("x", spec.width // 2)
        cy = char.get("y", int(spec.height * 0.65))
        cs = char.get("size", 60)

        drawer = character_drawers.get(name)
        if drawer:
            drawer(draw, cx, cy, cs, expr, palette)
        else:
            draw_character(draw, cx, cy, cs, expr, palette)

    # Dialogue overlay
    if spec.dialogue:
        _draw_dialogue(draw, spec.width, spec.height, spec.dialogue, palette)

    return img


def _draw_dialogue(
    draw: "ImageDraw.ImageDraw",
    width: int,
    height: int,
    text: str,
    palette: ColorPalette,
) -> None:
    """Draw a dialogue text overlay at the bottom of a panel."""
    try:
        from PIL import ImageFont
        font = None
        for font_path in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]:
            try:
                font = ImageFont.truetype(font_path, 16)
                break
            except (OSError, IOError):
                continue
        if font is None:
            font = ImageFont.load_default()
    except Exception:
        font = None

    # Semi-transparent background band
    band_y = height - 50
    draw.rectangle(
        [0, band_y, width, height],
        fill=(*palette.bg, 180),
    )
    draw.text(
        (width // 2, band_y + 10),
        text,
        fill=palette.text,
        font=font,
        anchor="mt" if font else None,
    )


@dataclass
class StorySpec:
    """Specification for a multi-panel story strip."""
    panels: list[PanelSpec] = field(default_factory=list)
    title: str = ""
    panel_width: int = 640
    panel_height: int = 480
    gap: int = 8


def render_story(
    spec: StorySpec,
    palette: ColorPalette | None = None,
) -> "Image.Image":
    """Render a multi-panel story strip as a single horizontal image.

    Args:
        spec: StorySpec with panel definitions.
        palette: Optional palette (applied to all panels).

    Returns:
        PIL Image (RGBA mode).
    """
    _require_pillow()

    if not spec.panels:
        img = Image.new("RGBA", (spec.panel_width, spec.panel_height), (30, 30, 40))
        return img

    if palette is None:
        palette = PALETTES["day_calm"]

    total_width = (spec.panel_width * len(spec.panels)) + (spec.gap * (len(spec.panels) - 1))
    total_height = spec.panel_height

    strip = Image.new("RGBA", (total_width, total_height), palette.bg)

    for i, panel_spec in enumerate(spec.panels):
        panel_spec.width = spec.panel_width
        panel_spec.height = spec.panel_height
        panel_img = render_panel(panel_spec, palette)
        x_offset = i * (spec.panel_width + spec.gap)
        strip.paste(panel_img, (x_offset, 0))

    return strip


# ---------------------------------------------------------------------------
# PARE-002 + PARE-004: Full scene renderer using color + weather
# ---------------------------------------------------------------------------

@dataclass
class SceneCharacter:
    """A character to place in a scene."""
    name: str = "generic"
    expression: str = "neutral"
    x: int = 0
    y: int = 0
    size: int = 60
    body_shape: str = "oval"


@dataclass
class SceneElement:
    """A scene element (rock, tree, puddle, bush, etc.)."""
    type: str = "rock"
    x: int = 0
    y: int = 0
    size: int = 40
    has_face: bool = True


@dataclass
class WeatherEffects:
    """Weather effect configuration for a scene."""
    rain_intensity: float = 0.0
    snow_intensity: float = 0.0
    cloud_count: int = 0
    show_sun: bool = False
    show_moon: bool = False
    moon_phase: float = 0.5
    star_count: int = 0


def render_scene(
    width: int,
    height: int,
    characters: Sequence[SceneCharacter] | None = None,
    elements: Sequence[SceneElement] | None = None,
    palette: ColorPalette | None = None,
    weather_effects: WeatherEffects | None = None,
    hour: int = 12,
    title: str = "",
    seed: int | None = None,
) -> "Image.Image":
    """Render a full Pareidolia scene using the color and weather systems.

    This is the primary rendering entry point for PARE-002 and PARE-004.
    Composes: sky gradient -> clouds -> sun/moon/stars -> ground -> elements
    -> characters -> weather overlay (rain/snow) -> title.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        characters: Sequence of SceneCharacter objects to draw.
        elements: Sequence of SceneElement objects to draw.
        palette: ColorPalette. If None, selects based on hour.
        weather_effects: WeatherEffects configuration. If None, no effects.
        hour: Hour of day (0-23) for sky gradient and palette selection.
        title: Optional title overlay at the bottom.
        seed: Optional RNG seed for reproducible rendering.

    Returns:
        PIL Image (RGBA mode).
    """
    _require_pillow()

    if palette is None:
        palette = select_palette(hour)

    if characters is None:
        characters = []
    if elements is None:
        elements = []
    if weather_effects is None:
        weather_effects = WeatherEffects()

    img = Image.new("RGBA", (width, height), palette.bg)
    draw = ImageDraw.Draw(img, "RGBA")

    # 1. Sky gradient
    draw_sky_gradient(draw, width, height, palette, hour)

    # 2. Stars (before clouds so they peek through gaps)
    if weather_effects.star_count > 0:
        draw_stars(draw, width, height, count=weather_effects.star_count, seed=seed)

    # 3. Sun or moon
    if weather_effects.show_sun:
        sun_x = int(width * 0.75)
        sun_y = int(height * 0.15)
        sun_radius = max(20, min(width, height) // 15)
        draw_sun(draw, sun_x, sun_y, sun_radius, palette)

    if weather_effects.show_moon:
        moon_x = int(width * 0.8)
        moon_y = int(height * 0.12)
        moon_radius = max(15, min(width, height) // 20)
        draw_moon(draw, moon_x, moon_y, moon_radius, weather_effects.moon_phase)

    # 4. Clouds
    if weather_effects.cloud_count > 0:
        cloud_y_range = (int(height * 0.05), int(height * 0.35))
        draw_clouds(
            draw, width, cloud_y_range,
            count=weather_effects.cloud_count, palette=palette, seed=seed,
        )

    # 5. Ground
    draw_ground(draw, width, height, palette, texture_seed=seed)

    # 6. Scene elements
    for elem in elements:
        if elem.type == "rock":
            draw_rock(draw, elem.x, elem.y, elem.size, palette, elem.has_face)
        elif elem.type == "tree":
            draw_tree(draw, elem.x, elem.y, elem.size, palette, elem.has_face)
        elif elem.type == "puddle":
            draw_puddle(draw, elem.x, elem.y, elem.size, palette, elem.has_face)
        elif elem.type == "bush":
            draw_bush(draw, elem.x, elem.y, elem.size, palette)

    # 7. Characters
    character_drawers = {
        "basalt": draw_basalt,
        "pebble": draw_pebble,
    }

    for char in characters:
        name = char.name.lower()
        drawer = character_drawers.get(name)
        if drawer:
            drawer(draw, char.x, char.y, char.size, char.expression, palette)
        else:
            draw_character(
                draw, char.x, char.y, char.size,
                char.expression, palette, char.body_shape,
            )

    # 8. Weather overlays (on top of everything)
    if weather_effects.rain_intensity > 0:
        draw_rain(draw, width, height, weather_effects.rain_intensity, seed=seed)

    if weather_effects.snow_intensity > 0:
        draw_snow(draw, width, height, weather_effects.snow_intensity, seed=seed)

    # 9. Title overlay
    if title:
        _draw_dialogue(draw, width, height, title, palette)

    return img
