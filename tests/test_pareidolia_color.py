"""Tests for Pareidolia scene engine — PARE-002 (color palettes) and PARE-004 (weather/time).

Covers:
- ColorPalette dataclass and PALETTES dict
- select_palette logic (time, mood, weather)
- Sky gradient rendering
- Weather effects (rain, snow, stars, sun, moon, clouds)
- Ground drawing with palette
- Character drawing with palette
- Scene elements (rock, tree, puddle, bush)
- Named characters (Basalt, Pebble)
- Full render_scene composition
- PanelSpec / StorySpec rendering with palettes
"""
import sys
import unittest
from pathlib import Path

# Add my-claw/tools to path
sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

from PIL import Image, ImageDraw

from senseweave.pareidolia import (
    ColorPalette,
    PALETTES,
    PanelSpec,
    SceneCharacter,
    SceneElement,
    StorySpec,
    WeatherEffects,
    _lerp_color,
    draw_basalt,
    draw_bush,
    draw_character,
    draw_clouds,
    draw_face_eyes,
    draw_face_mouth,
    draw_ground,
    draw_moon,
    draw_pebble,
    draw_puddle,
    draw_rain,
    draw_rock,
    draw_sky_gradient,
    draw_snow,
    draw_stars,
    draw_sun,
    draw_tree,
    render_panel,
    render_scene,
    render_story,
    select_palette,
)


# ---------------------------------------------------------------------------
# PARE-002: ColorPalette and PALETTES
# ---------------------------------------------------------------------------

class TestColorPalette(unittest.TestCase):
    """Tests for the ColorPalette dataclass."""

    def test_palette_fields(self):
        p = ColorPalette(
            bg=(0, 0, 0), ground=(1, 1, 1), sky=(2, 2, 2),
            character_fill=(3, 3, 3), character_outline=(4, 4, 4),
            accent=(5, 5, 5), text=(6, 6, 6),
        )
        self.assertEqual(p.bg, (0, 0, 0))
        self.assertEqual(p.ground, (1, 1, 1))
        self.assertEqual(p.sky, (2, 2, 2))
        self.assertEqual(p.character_fill, (3, 3, 3))
        self.assertEqual(p.character_outline, (4, 4, 4))
        self.assertEqual(p.accent, (5, 5, 5))
        self.assertEqual(p.text, (6, 6, 6))

    def test_palette_is_frozen(self):
        p = PALETTES["dawn"]
        with self.assertRaises(AttributeError):
            p.bg = (255, 255, 255)  # type: ignore[misc]

    def test_all_palettes_have_seven_fields(self):
        for name, p in PALETTES.items():
            for field_name in ("bg", "ground", "sky", "character_fill",
                               "character_outline", "accent", "text"):
                val = getattr(p, field_name)
                self.assertIsInstance(val, tuple, f"{name}.{field_name} not a tuple")
                self.assertEqual(len(val), 3, f"{name}.{field_name} not RGB")

    def test_all_palette_values_in_range(self):
        for name, p in PALETTES.items():
            for field_name in ("bg", "ground", "sky", "character_fill",
                               "character_outline", "accent", "text"):
                for i, v in enumerate(getattr(p, field_name)):
                    self.assertTrue(0 <= v <= 255,
                                    f"{name}.{field_name}[{i}] = {v} out of range")


class TestPalettesDict(unittest.TestCase):
    """Tests for the PALETTES dictionary entries."""

    EXPECTED_KEYS = [
        "dawn", "day_happy", "day_calm", "overcast", "dusk",
        "night", "night_calm", "rain", "snow",
    ]

    def test_all_expected_palettes_exist(self):
        for key in self.EXPECTED_KEYS:
            self.assertIn(key, PALETTES, f"Missing palette: {key}")

    def test_palette_count(self):
        self.assertEqual(len(PALETTES), len(self.EXPECTED_KEYS))

    def test_dawn_has_warm_sky(self):
        p = PALETTES["dawn"]
        # Dawn sky should have red component > blue
        self.assertGreater(p.sky[0], p.sky[2])

    def test_night_has_dark_bg(self):
        p = PALETTES["night"]
        # Night bg should be very dark
        self.assertLess(sum(p.bg), 100)

    def test_snow_has_light_ground(self):
        p = PALETTES["snow"]
        # Snow ground should be bright
        self.assertGreater(sum(p.ground), 600)

    def test_rain_has_cool_sky(self):
        p = PALETTES["rain"]
        # Rain sky blue >= red
        self.assertGreaterEqual(p.sky[2], p.sky[0])


# ---------------------------------------------------------------------------
# PARE-002: select_palette
# ---------------------------------------------------------------------------

class TestSelectPalette(unittest.TestCase):
    """Tests for the select_palette function."""

    def test_dawn_hours(self):
        for h in (5, 6, 7):
            p = select_palette(h)
            self.assertEqual(p, PALETTES["dawn"], f"hour={h} should be dawn")

    def test_day_happy(self):
        p = select_palette(10, mood="happy")
        self.assertEqual(p, PALETTES["day_happy"])

    def test_day_calm_default(self):
        p = select_palette(10, mood="calm")
        self.assertEqual(p, PALETTES["day_calm"])

    def test_afternoon_happy(self):
        p = select_palette(14, mood="happy")
        self.assertEqual(p, PALETTES["day_happy"])

    def test_afternoon_calm(self):
        p = select_palette(14, mood="calm")
        self.assertEqual(p, PALETTES["day_calm"])

    def test_dusk_hours(self):
        for h in (17, 18, 19):
            p = select_palette(h)
            self.assertEqual(p, PALETTES["dusk"], f"hour={h} should be dusk")

    def test_night_default(self):
        # Default mood is "calm", so night hours return night_calm
        p = select_palette(22)
        self.assertEqual(p, PALETTES["night_calm"])

    def test_night_non_calm(self):
        p = select_palette(22, mood="happy")
        self.assertEqual(p, PALETTES["night"])

    def test_night_calm(self):
        p = select_palette(22, mood="calm")
        self.assertEqual(p, PALETTES["night_calm"])

    def test_deep_night(self):
        p = select_palette(3)
        self.assertEqual(p, PALETTES["night"])

    def test_rain_overrides_time(self):
        p = select_palette(12, weather="rain")
        self.assertEqual(p, PALETTES["rain"])

    def test_snow_overrides_time(self):
        p = select_palette(12, weather="snow")
        self.assertEqual(p, PALETTES["snow"])

    def test_overcast_overrides_time(self):
        p = select_palette(12, weather="overcast")
        self.assertEqual(p, PALETTES["overcast"])

    def test_fog_maps_to_overcast(self):
        p = select_palette(12, weather="fog")
        self.assertEqual(p, PALETTES["overcast"])

    def test_clamps_negative_hour(self):
        p = select_palette(-1)
        # hour clamped to 0, which falls to night
        self.assertIn(p, [PALETTES["night"], PALETTES["night_calm"]])

    def test_clamps_high_hour(self):
        p = select_palette(30)
        # hour clamped to 23
        self.assertIn(p, [PALETTES["night"], PALETTES["night_calm"]])

    def test_midnight_returns_night(self):
        p = select_palette(0)
        self.assertIn(p, [PALETTES["night"], PALETTES["night_calm"]])


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

class TestLerpColor(unittest.TestCase):
    """Tests for the _lerp_color helper."""

    def test_lerp_zero(self):
        self.assertEqual(_lerp_color((0, 0, 0), (255, 255, 255), 0.0), (0, 0, 0))

    def test_lerp_one(self):
        self.assertEqual(_lerp_color((0, 0, 0), (255, 255, 255), 1.0), (255, 255, 255))

    def test_lerp_half(self):
        result = _lerp_color((0, 0, 0), (200, 100, 50), 0.5)
        self.assertEqual(result, (100, 50, 25))

    def test_lerp_clamps_below_zero(self):
        result = _lerp_color((100, 100, 100), (200, 200, 200), -0.5)
        self.assertEqual(result, (100, 100, 100))

    def test_lerp_clamps_above_one(self):
        result = _lerp_color((100, 100, 100), (200, 200, 200), 1.5)
        self.assertEqual(result, (200, 200, 200))


# ---------------------------------------------------------------------------
# PARE-004: Sky, stars, weather
# ---------------------------------------------------------------------------

def _make_canvas(w=400, h=300):
    """Helper: create a test RGBA canvas and draw object."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    return img, draw


class TestDrawSkyGradient(unittest.TestCase):
    """Tests for draw_sky_gradient."""

    def test_fills_upper_region(self):
        img, draw = _make_canvas()
        palette = PALETTES["day_calm"]
        draw_sky_gradient(draw, 400, 300, palette, hour=12)
        # Top pixel should not be black anymore
        top_pixel = img.getpixel((200, 0))[:3]
        self.assertNotEqual(top_pixel, (0, 0, 0))

    def test_dawn_gradient_uses_accent(self):
        img, draw = _make_canvas()
        palette = PALETTES["dawn"]
        draw_sky_gradient(draw, 400, 300, palette, hour=6)
        # Bottom of sky region should be close to accent color
        mid_pixel = img.getpixel((200, int(300 * 0.55)))[:3]
        # At least one channel should be warm (>100)
        self.assertGreater(max(mid_pixel), 80)

    def test_night_gradient_is_dark(self):
        img, draw = _make_canvas()
        palette = PALETTES["night"]
        draw_sky_gradient(draw, 400, 300, palette, hour=23)
        top_pixel = img.getpixel((200, 5))[:3]
        self.assertLess(sum(top_pixel), 200)

    def test_does_not_touch_ground_region(self):
        img, draw = _make_canvas()
        palette = PALETTES["day_calm"]
        draw_sky_gradient(draw, 400, 300, palette, hour=12)
        # Pixel well below the 60% line should still be black (untouched)
        bottom_pixel = img.getpixel((200, 290))[:3]
        self.assertEqual(bottom_pixel, (0, 0, 0))


class TestDrawStars(unittest.TestCase):
    """Tests for draw_stars."""

    def test_stars_add_bright_pixels(self):
        img, draw = _make_canvas()
        draw_stars(draw, 400, 300, count=100, seed=42)
        # Sample the upper region — some pixels should be bright
        bright = 0
        for x in range(0, 400, 10):
            for y in range(0, 180, 10):
                r, g, b, a = img.getpixel((x, y))
                if r > 100 or g > 100 or b > 100:
                    bright += 1
        self.assertGreater(bright, 0)

    def test_stars_seed_reproducible(self):
        img1, draw1 = _make_canvas()
        draw_stars(draw1, 400, 300, count=30, seed=123)
        img2, draw2 = _make_canvas()
        draw_stars(draw2, 400, 300, count=30, seed=123)
        self.assertEqual(list(img1.getdata()), list(img2.getdata()))

    def test_zero_count_no_change(self):
        img, draw = _make_canvas()
        before = list(img.getdata())
        draw_stars(draw, 400, 300, count=0, seed=1)
        after = list(img.getdata())
        self.assertEqual(before, after)


class TestDrawRain(unittest.TestCase):
    """Tests for draw_rain."""

    def test_rain_adds_pixels(self):
        img, draw = _make_canvas()
        draw_rain(draw, 400, 300, intensity=0.8, seed=42)
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 0)

    def test_zero_intensity_no_rain(self):
        img, draw = _make_canvas()
        before = list(img.getdata())
        draw_rain(draw, 400, 300, intensity=0.0, seed=1)
        after = list(img.getdata())
        self.assertEqual(before, after)

    def test_high_intensity_more_drops(self):
        img1, draw1 = _make_canvas()
        draw_rain(draw1, 400, 300, intensity=0.2, seed=10)
        non_black_low = sum(1 for px in img1.getdata() if px != (0, 0, 0, 255))

        img2, draw2 = _make_canvas()
        draw_rain(draw2, 400, 300, intensity=1.0, seed=10)
        non_black_high = sum(1 for px in img2.getdata() if px != (0, 0, 0, 255))

        self.assertGreater(non_black_high, non_black_low)

    def test_rain_seed_reproducible(self):
        img1, draw1 = _make_canvas()
        draw_rain(draw1, 400, 300, intensity=0.5, seed=99)
        img2, draw2 = _make_canvas()
        draw_rain(draw2, 400, 300, intensity=0.5, seed=99)
        self.assertEqual(list(img1.getdata()), list(img2.getdata()))


class TestDrawSnow(unittest.TestCase):
    """Tests for draw_snow."""

    def test_snow_adds_pixels(self):
        img, draw = _make_canvas()
        draw_snow(draw, 400, 300, intensity=0.8, seed=42)
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 0)

    def test_zero_intensity_no_snow(self):
        img, draw = _make_canvas()
        before = list(img.getdata())
        draw_snow(draw, 400, 300, intensity=0.0, seed=1)
        after = list(img.getdata())
        self.assertEqual(before, after)

    def test_snow_seed_reproducible(self):
        img1, draw1 = _make_canvas()
        draw_snow(draw1, 400, 300, intensity=0.5, seed=77)
        img2, draw2 = _make_canvas()
        draw_snow(draw2, 400, 300, intensity=0.5, seed=77)
        self.assertEqual(list(img1.getdata()), list(img2.getdata()))


class TestDrawSun(unittest.TestCase):
    """Tests for draw_sun."""

    def test_sun_draws_circle(self):
        img, draw = _make_canvas()
        palette = PALETTES["day_happy"]
        draw_sun(draw, 200, 80, 30, palette)
        # Center pixel should be the accent color
        center = img.getpixel((200, 80))[:3]
        self.assertEqual(center, palette.accent)

    def test_sun_has_rays(self):
        img, draw = _make_canvas()
        palette = PALETTES["day_happy"]
        draw_sun(draw, 200, 80, 20, palette)
        # A pixel along a ray direction should be non-black
        ray_pixel = img.getpixel((200, 80 - 35))[:3]
        self.assertNotEqual(ray_pixel, (0, 0, 0))


class TestDrawMoon(unittest.TestCase):
    """Tests for draw_moon."""

    def test_full_moon_fills_circle(self):
        img, draw = _make_canvas()
        draw_moon(draw, 200, 80, 25, phase=1.0)
        center = img.getpixel((200, 80))[:3]
        # Should be moonlight color (bright)
        self.assertGreater(sum(center), 500)

    def test_crescent_has_shadow(self):
        img, draw = _make_canvas()
        draw_moon(draw, 200, 80, 25, phase=0.2)
        # Right side should be shadowed (dark)
        right_pixel = img.getpixel((218, 80))[:3]
        self.assertLess(sum(right_pixel), 200)

    def test_phase_clamped(self):
        img, draw = _make_canvas()
        # Should not raise
        draw_moon(draw, 200, 80, 25, phase=-0.5)
        draw_moon(draw, 200, 80, 25, phase=1.5)


class TestDrawClouds(unittest.TestCase):
    """Tests for draw_clouds."""

    def test_clouds_add_pixels(self):
        img, draw = _make_canvas()
        draw_clouds(draw, 400, (20, 100), count=3, seed=42)
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 0)

    def test_zero_clouds_no_change(self):
        img, draw = _make_canvas()
        before = list(img.getdata())
        draw_clouds(draw, 400, (20, 100), count=0, seed=1)
        after = list(img.getdata())
        self.assertEqual(before, after)

    def test_clouds_with_palette(self):
        img, draw = _make_canvas()
        palette = PALETTES["overcast"]
        draw_clouds(draw, 400, (20, 100), count=3, palette=palette, seed=42)
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 0)

    def test_clouds_seed_reproducible(self):
        img1, draw1 = _make_canvas()
        draw_clouds(draw1, 400, (20, 100), count=3, seed=55)
        img2, draw2 = _make_canvas()
        draw_clouds(draw2, 400, (20, 100), count=3, seed=55)
        self.assertEqual(list(img1.getdata()), list(img2.getdata()))


# ---------------------------------------------------------------------------
# Ground drawing
# ---------------------------------------------------------------------------

class TestDrawGround(unittest.TestCase):
    """Tests for draw_ground."""

    def test_fills_lower_region(self):
        img, draw = _make_canvas()
        palette = PALETTES["day_calm"]
        draw_ground(draw, 400, 300, palette)
        # Pixel in lower quarter should not be black
        bottom = img.getpixel((200, 280))[:3]
        self.assertNotEqual(bottom, (0, 0, 0))

    def test_upper_region_untouched(self):
        img, draw = _make_canvas()
        palette = PALETTES["day_calm"]
        draw_ground(draw, 400, 300, palette)
        top = img.getpixel((200, 10))[:3]
        self.assertEqual(top, (0, 0, 0))

    def test_texture_seed_reproducible(self):
        img1, draw1 = _make_canvas()
        draw_ground(draw1, 400, 300, PALETTES["day_calm"], texture_seed=42)
        img2, draw2 = _make_canvas()
        draw_ground(draw2, 400, 300, PALETTES["day_calm"], texture_seed=42)
        self.assertEqual(list(img1.getdata()), list(img2.getdata()))


# ---------------------------------------------------------------------------
# Character drawing
# ---------------------------------------------------------------------------

class TestDrawCharacter(unittest.TestCase):
    """Tests for draw_character with various shapes and expressions."""

    def test_draws_oval_character(self):
        img, draw = _make_canvas()
        palette = PALETTES["day_calm"]
        draw_character(draw, 200, 150, 60, "neutral", palette, "oval")
        center = img.getpixel((200, 150))[:3]
        self.assertEqual(center, palette.character_fill)

    def test_draws_round_character(self):
        img, draw = _make_canvas()
        draw_character(draw, 200, 150, 60, "happy", PALETTES["day_happy"], "round")
        center = img.getpixel((200, 150))[:3]
        self.assertNotEqual(center, (0, 0, 0))

    def test_draws_tall_character(self):
        img, draw = _make_canvas()
        draw_character(draw, 200, 150, 60, "sad", PALETTES["dusk"], "tall")
        center = img.getpixel((200, 150))[:3]
        self.assertNotEqual(center, (0, 0, 0))

    def test_draws_flat_character(self):
        img, draw = _make_canvas()
        draw_character(draw, 200, 150, 60, "curious", PALETTES["rain"], "flat")
        center = img.getpixel((200, 150))[:3]
        self.assertNotEqual(center, (0, 0, 0))

    def test_draws_spiky_character(self):
        img, draw = _make_canvas()
        draw_character(draw, 200, 150, 60, "neutral", PALETTES["night"], "spiky")
        center = img.getpixel((200, 150))[:3]
        self.assertNotEqual(center, (0, 0, 0))

    def test_draws_without_palette(self):
        img, draw = _make_canvas()
        draw_character(draw, 200, 150, 60, "neutral", None, "oval")
        center = img.getpixel((200, 150))[:3]
        self.assertEqual(center, (160, 160, 160))  # default gray


class TestDrawFaceEyes(unittest.TestCase):
    """Tests for draw_face_eyes expressions."""

    def test_neutral_eyes(self):
        img, draw = _make_canvas()
        draw_face_eyes(draw, 200, 150, 80, "neutral")
        # Should have drawn something (eyes not at exact center)
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 0)

    def test_happy_eyes(self):
        img, draw = _make_canvas()
        draw_face_eyes(draw, 200, 150, 80, "happy")
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 0)

    def test_sad_eyes(self):
        img, draw = _make_canvas()
        draw_face_eyes(draw, 200, 150, 80, "sad")
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 0)

    def test_curious_eyes(self):
        img, draw = _make_canvas()
        draw_face_eyes(draw, 200, 150, 80, "curious")
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 0)

    def test_sleeping_eyes_no_highlights(self):
        img, draw = _make_canvas()
        draw_face_eyes(draw, 200, 150, 80, "sleeping")
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 0)


class TestDrawFaceMouth(unittest.TestCase):
    """Tests for draw_face_mouth expressions."""

    def test_all_expressions(self):
        for expr in ("neutral", "happy", "sad", "curious", "sleeping"):
            img, draw = _make_canvas()
            draw_face_mouth(draw, 200, 150, 80, expr)
            non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
            self.assertGreater(non_black, 0, f"Expression '{expr}' drew nothing")


# ---------------------------------------------------------------------------
# Scene elements
# ---------------------------------------------------------------------------

class TestSceneElements(unittest.TestCase):
    """Tests for scene element drawing functions."""

    def test_rock_with_face(self):
        img, draw = _make_canvas()
        draw_rock(draw, 200, 200, 50, PALETTES["day_calm"], has_face=True)
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 10)

    def test_rock_without_face(self):
        img, draw = _make_canvas()
        draw_rock(draw, 200, 200, 50, PALETTES["day_calm"], has_face=False)
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 5)

    def test_tree(self):
        img, draw = _make_canvas()
        draw_tree(draw, 200, 250, 120, PALETTES["day_calm"])
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 20)

    def test_tree_no_face(self):
        img, draw = _make_canvas()
        draw_tree(draw, 200, 250, 120, PALETTES["day_calm"], has_face=False)
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 20)

    def test_puddle_with_face(self):
        img, draw = _make_canvas()
        draw_puddle(draw, 200, 250, 80, PALETTES["rain"])
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 5)

    def test_puddle_no_face(self):
        img, draw = _make_canvas()
        draw_puddle(draw, 200, 250, 80, PALETTES["rain"], has_face=False)
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 5)

    def test_bush(self):
        img, draw = _make_canvas()
        draw_bush(draw, 200, 200, 60, PALETTES["day_happy"])
        non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
        self.assertGreater(non_black, 5)


# ---------------------------------------------------------------------------
# Named characters
# ---------------------------------------------------------------------------

class TestNamedCharacters(unittest.TestCase):
    """Tests for Basalt and Pebble character drawing."""

    def test_basalt_draws(self):
        img, draw = _make_canvas()
        draw_basalt(draw, 200, 150, 80, "neutral", PALETTES["day_calm"])
        center = img.getpixel((200, 150))[:3]
        self.assertNotEqual(center, (0, 0, 0))

    def test_basalt_expressions(self):
        for expr in ("neutral", "happy", "sad", "curious", "sleeping"):
            img, draw = _make_canvas()
            draw_basalt(draw, 200, 150, 80, expr, PALETTES["dusk"])
            non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
            self.assertGreater(non_black, 10, f"Basalt '{expr}' drew nothing")

    def test_basalt_without_palette(self):
        img, draw = _make_canvas()
        draw_basalt(draw, 200, 150, 80, "neutral", None)
        center = img.getpixel((200, 150))[:3]
        self.assertNotEqual(center, (0, 0, 0))

    def test_pebble_draws(self):
        img, draw = _make_canvas()
        draw_pebble(draw, 200, 150, 50, "happy", PALETTES["day_happy"])
        center = img.getpixel((200, 150))[:3]
        self.assertNotEqual(center, (0, 0, 0))

    def test_pebble_expressions(self):
        for expr in ("neutral", "happy", "sad", "curious", "sleeping"):
            img, draw = _make_canvas()
            draw_pebble(draw, 200, 150, 50, expr, PALETTES["night"])
            non_black = sum(1 for px in img.getdata() if px != (0, 0, 0, 255))
            self.assertGreater(non_black, 10, f"Pebble '{expr}' drew nothing")

    def test_pebble_without_palette(self):
        img, draw = _make_canvas()
        draw_pebble(draw, 200, 150, 50, "neutral", None)
        center = img.getpixel((200, 150))[:3]
        self.assertNotEqual(center, (0, 0, 0))

    def test_pebble_smaller_than_basalt(self):
        """Pebble is conceptually smaller; verify both render at given sizes."""
        img1, draw1 = _make_canvas()
        draw_basalt(draw1, 200, 150, 100, "neutral", PALETTES["day_calm"])
        basalt_pixels = sum(1 for px in img1.getdata() if px != (0, 0, 0, 255))

        img2, draw2 = _make_canvas()
        draw_pebble(draw2, 200, 150, 50, "neutral", PALETTES["day_calm"])
        pebble_pixels = sum(1 for px in img2.getdata() if px != (0, 0, 0, 255))

        self.assertGreater(basalt_pixels, pebble_pixels)


# ---------------------------------------------------------------------------
# render_panel
# ---------------------------------------------------------------------------

class TestRenderPanel(unittest.TestCase):
    """Tests for the render_panel function."""

    def test_empty_panel(self):
        spec = PanelSpec()
        img = render_panel(spec)
        self.assertEqual(img.size, (640, 480))
        self.assertEqual(img.mode, "RGBA")

    def test_panel_with_characters(self):
        spec = PanelSpec(
            characters=[
                {"name": "basalt", "expression": "happy", "x": 200, "y": 300, "size": 80},
                {"name": "pebble", "expression": "curious", "x": 400, "y": 330, "size": 50},
            ],
        )
        img = render_panel(spec, palette=PALETTES["day_happy"])
        self.assertEqual(img.size, (640, 480))

    def test_panel_with_elements(self):
        spec = PanelSpec(
            elements=[
                {"type": "rock", "x": 100, "y": 350, "size": 40},
                {"type": "tree", "x": 500, "y": 350, "size": 100},
                {"type": "puddle", "x": 300, "y": 380, "size": 60},
                {"type": "bush", "x": 50, "y": 360, "size": 30},
            ],
        )
        img = render_panel(spec)
        self.assertEqual(img.size, (640, 480))

    def test_panel_with_dialogue(self):
        spec = PanelSpec(
            characters=[
                {"name": "basalt", "expression": "neutral", "x": 320, "y": 300, "size": 80},
            ],
            dialogue="The rain sounds like music.",
        )
        img = render_panel(spec)
        self.assertEqual(img.size, (640, 480))

    def test_panel_custom_size(self):
        spec = PanelSpec(width=800, height=600)
        img = render_panel(spec)
        self.assertEqual(img.size, (800, 600))

    def test_panel_default_palette(self):
        spec = PanelSpec()
        img = render_panel(spec)
        # Should use day_calm by default — top of sky should not be black
        top = img.getpixel((320, 5))[:3]
        self.assertNotEqual(top, (0, 0, 0))

    def test_panel_unknown_character_uses_generic(self):
        spec = PanelSpec(
            characters=[
                {"name": "unknown_entity", "expression": "happy", "x": 320, "y": 300, "size": 60},
            ],
        )
        img = render_panel(spec)
        self.assertEqual(img.size, (640, 480))


# ---------------------------------------------------------------------------
# render_story
# ---------------------------------------------------------------------------

class TestRenderStory(unittest.TestCase):
    """Tests for the render_story function."""

    def test_empty_story(self):
        spec = StorySpec()
        img = render_story(spec)
        self.assertEqual(img.size, (640, 480))

    def test_single_panel_story(self):
        spec = StorySpec(
            panels=[PanelSpec()],
            panel_width=400,
            panel_height=300,
        )
        img = render_story(spec)
        self.assertEqual(img.size, (400, 300))

    def test_multi_panel_story(self):
        spec = StorySpec(
            panels=[PanelSpec(), PanelSpec(), PanelSpec()],
            panel_width=200,
            panel_height=200,
            gap=10,
        )
        img = render_story(spec)
        expected_width = 200 * 3 + 10 * 2
        self.assertEqual(img.size, (expected_width, 200))

    def test_story_with_palette(self):
        spec = StorySpec(
            panels=[PanelSpec(characters=[
                {"name": "basalt", "expression": "happy", "x": 100, "y": 150, "size": 60},
            ])],
            panel_width=300,
            panel_height=200,
        )
        img = render_story(spec, palette=PALETTES["dusk"])
        self.assertEqual(img.size, (300, 200))


# ---------------------------------------------------------------------------
# render_scene (PARE-002 + PARE-004 combined)
# ---------------------------------------------------------------------------

class TestRenderScene(unittest.TestCase):
    """Tests for the full render_scene function."""

    def test_minimal_scene(self):
        img = render_scene(640, 480)
        self.assertEqual(img.size, (640, 480))
        self.assertEqual(img.mode, "RGBA")

    def test_scene_with_characters(self):
        chars = [
            SceneCharacter(name="basalt", expression="happy", x=200, y=300, size=80),
            SceneCharacter(name="pebble", expression="curious", x=400, y=330, size=50),
        ]
        img = render_scene(640, 480, characters=chars)
        self.assertEqual(img.size, (640, 480))

    def test_scene_with_elements(self):
        elems = [
            SceneElement(type="rock", x=100, y=350, size=40),
            SceneElement(type="tree", x=500, y=350, size=100),
            SceneElement(type="puddle", x=300, y=380, size=60),
            SceneElement(type="bush", x=50, y=360, size=30),
        ]
        img = render_scene(640, 480, elements=elems)
        self.assertEqual(img.size, (640, 480))

    def test_scene_with_rain(self):
        weather = WeatherEffects(rain_intensity=0.7, cloud_count=4)
        img = render_scene(640, 480, weather_effects=weather, palette=PALETTES["rain"])
        self.assertEqual(img.size, (640, 480))

    def test_scene_with_snow(self):
        weather = WeatherEffects(snow_intensity=0.6, cloud_count=2)
        img = render_scene(640, 480, weather_effects=weather, palette=PALETTES["snow"])
        self.assertEqual(img.size, (640, 480))

    def test_scene_with_sun(self):
        weather = WeatherEffects(show_sun=True, cloud_count=2)
        img = render_scene(640, 480, weather_effects=weather, hour=10)
        self.assertEqual(img.size, (640, 480))

    def test_scene_with_moon_and_stars(self):
        weather = WeatherEffects(show_moon=True, moon_phase=0.3, star_count=80)
        img = render_scene(640, 480, weather_effects=weather, hour=23)
        self.assertEqual(img.size, (640, 480))

    def test_scene_auto_selects_palette(self):
        # No palette given — should select based on hour
        img = render_scene(640, 480, hour=6)
        # Dawn palette — check sky is not pitch black
        top = img.getpixel((320, 5))[:3]
        self.assertNotEqual(top, (0, 0, 0))

    def test_scene_explicit_palette_overrides(self):
        img = render_scene(640, 480, palette=PALETTES["snow"], hour=12)
        # Snow palette ground is light — bottom pixel should be bright
        bottom = img.getpixel((320, 470))[:3]
        self.assertGreater(sum(bottom), 400)

    def test_scene_with_title(self):
        img = render_scene(640, 480, title="A Quiet Evening")
        self.assertEqual(img.size, (640, 480))

    def test_scene_seed_reproducible(self):
        chars = [SceneCharacter(name="basalt", x=200, y=300, size=60)]
        elems = [SceneElement(type="rock", x=100, y=350, size=40)]
        weather = WeatherEffects(rain_intensity=0.5, star_count=20, cloud_count=2)

        img1 = render_scene(400, 300, characters=chars, elements=elems,
                            weather_effects=weather, palette=PALETTES["rain"], seed=42)
        img2 = render_scene(400, 300, characters=chars, elements=elems,
                            weather_effects=weather, palette=PALETTES["rain"], seed=42)
        self.assertEqual(list(img1.getdata()), list(img2.getdata()))

    def test_scene_generic_character(self):
        chars = [
            SceneCharacter(name="lamp_post", expression="neutral", x=300, y=300,
                           size=50, body_shape="tall"),
        ]
        img = render_scene(640, 480, characters=chars)
        self.assertEqual(img.size, (640, 480))

    def test_scene_all_element_types(self):
        elems = [
            SceneElement(type="rock", x=80, y=350, size=30),
            SceneElement(type="tree", x=200, y=350, size=80),
            SceneElement(type="puddle", x=350, y=370, size=50),
            SceneElement(type="bush", x=500, y=360, size=35),
        ]
        img = render_scene(640, 480, elements=elems)
        self.assertEqual(img.size, (640, 480))

    def test_scene_small_dimensions(self):
        img = render_scene(100, 80)
        self.assertEqual(img.size, (100, 80))

    def test_scene_large_dimensions(self):
        img = render_scene(1280, 1024)
        self.assertEqual(img.size, (1280, 1024))

    def test_weather_effects_defaults(self):
        w = WeatherEffects()
        self.assertEqual(w.rain_intensity, 0.0)
        self.assertEqual(w.snow_intensity, 0.0)
        self.assertEqual(w.cloud_count, 0)
        self.assertFalse(w.show_sun)
        self.assertFalse(w.show_moon)
        self.assertEqual(w.moon_phase, 0.5)
        self.assertEqual(w.star_count, 0)

    def test_scene_character_dataclass(self):
        c = SceneCharacter(name="basalt", expression="happy", x=100, y=200, size=60)
        self.assertEqual(c.name, "basalt")
        self.assertEqual(c.body_shape, "oval")

    def test_scene_element_dataclass(self):
        e = SceneElement(type="tree", x=100, y=200, size=80, has_face=False)
        self.assertEqual(e.type, "tree")
        self.assertFalse(e.has_face)

    def test_dusk_scene_composition(self):
        """Full dusk scene: Basalt + Pebble, rocks, clouds, crescent moon."""
        chars = [
            SceneCharacter(name="basalt", expression="calm", x=250, y=380, size=90),
            SceneCharacter(name="pebble", expression="happy", x=380, y=400, size=50),
        ]
        elems = [
            SceneElement(type="rock", x=100, y=400, size=35),
            SceneElement(type="bush", x=500, y=390, size=25),
        ]
        weather = WeatherEffects(show_moon=True, moon_phase=0.3, star_count=40, cloud_count=2)
        img = render_scene(
            640, 480,
            characters=chars,
            elements=elems,
            palette=PALETTES["dusk"],
            weather_effects=weather,
            hour=19,
            title="Evening Watch",
            seed=7,
        )
        self.assertEqual(img.size, (640, 480))
        self.assertEqual(img.mode, "RGBA")


# ---------------------------------------------------------------------------
# Integration: palette + render_panel
# ---------------------------------------------------------------------------

class TestPaletteIntegration(unittest.TestCase):
    """Ensure palettes are correctly threaded through render_panel."""

    def test_night_panel_is_dark(self):
        spec = PanelSpec()
        img = render_panel(spec, palette=PALETTES["night"])
        # Bottom-right pixel should be dark (ground)
        br = img.getpixel((630, 470))[:3]
        self.assertLess(sum(br), 200)

    def test_snow_panel_is_bright(self):
        spec = PanelSpec()
        img = render_panel(spec, palette=PALETTES["snow"])
        # Ground area should be bright
        ground = img.getpixel((320, 400))[:3]
        self.assertGreater(sum(ground), 400)

    def test_each_palette_produces_different_images(self):
        """Different palettes should produce visually different results."""
        images = {}
        for name in ("dawn", "night", "snow", "rain"):
            spec = PanelSpec(width=200, height=150)
            img = render_panel(spec, palette=PALETTES[name])
            images[name] = img.getpixel((100, 10))[:3]

        # At least 3 of 4 should have distinct top-sky colors
        unique = set(images.values())
        self.assertGreaterEqual(len(unique), 3)


if __name__ == "__main__":
    unittest.main()
