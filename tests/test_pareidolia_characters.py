"""Tests for PARE-003 — all 21 organism character draw functions.

Covers:
- Each character renders without error on a fresh RGBA canvas
- Each character produces non-empty (non-uniform) image content
- CHARACTER_REGISTRY maps all expected names
- render_scene and render_panel dispatch registered characters correctly
"""
import sys
import unittest
from pathlib import Path

# Add my-claw/tools to path
sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

from PIL import Image, ImageDraw

from senseweave.pareidolia import (
    CHARACTER_REGISTRY,
    PALETTES,
    ColorPalette,
    PanelSpec,
    SceneCharacter,
    draw_archivist,
    draw_basalt,
    draw_conductor,
    draw_dreamer,
    draw_face_eye,
    draw_gallery_face,
    draw_gallery_wall,
    draw_garden_eye,
    draw_heartbeat,
    draw_instrument,
    draw_membrane,
    draw_messenger,
    draw_navigator,
    draw_pebble,
    draw_poet,
    draw_porch_eye,
    draw_printer,
    draw_scribe,
    draw_skin,
    draw_speaker,
    draw_weaver,
    render_panel,
    render_scene,
)

# All 21 organism characters with their draw functions
ALL_CHARACTERS = {
    "membrane": draw_membrane,
    "heartbeat": draw_heartbeat,
    "face eye": draw_face_eye,
    "porch eye": draw_porch_eye,
    "garden eye": draw_garden_eye,
    "instrument": draw_instrument,
    "basalt": draw_basalt,
    "pebble": draw_pebble,
    "poet": draw_poet,
    "archivist": draw_archivist,
    "dreamer": draw_dreamer,
    "gallery face": draw_gallery_face,
    "gallery wall": draw_gallery_wall,
    "printer": draw_printer,
    "speaker": draw_speaker,
    "skin": draw_skin,
    "messenger": draw_messenger,
    "scribe": draw_scribe,
    "navigator": draw_navigator,
    "weaver": draw_weaver,
    "conductor": draw_conductor,
}

EXPRESSIONS = ["neutral", "happy", "sad", "curious", "sleeping"]


def _make_canvas(width: int = 200, height: int = 200) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Create a fresh RGBA canvas and draw object."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    return img, draw


def _image_is_non_empty(img: Image.Image) -> bool:
    """Check that the image is not fully transparent / uniform."""
    pixels = list(img.getdata())
    first = pixels[0]
    return not all(p == first for p in pixels)


class TestCharacterDrawFunctions(unittest.TestCase):
    """Test that each of the 21 character draw functions works."""

    def test_all_21_characters_present(self):
        """Verify we have exactly 21 unique draw functions."""
        self.assertEqual(len(ALL_CHARACTERS), 21)

    def test_each_character_renders_without_error_no_palette(self):
        """Each character draws without raising, using no palette."""
        for name, draw_fn in ALL_CHARACTERS.items():
            with self.subTest(character=name):
                img, draw = _make_canvas()
                draw_fn(draw, 100, 100, 60, "neutral", None)
                self.assertTrue(_image_is_non_empty(img), f"{name} produced empty image")

    def test_each_character_renders_with_palette(self):
        """Each character draws correctly with a color palette."""
        palette = PALETTES["day_happy"]
        for name, draw_fn in ALL_CHARACTERS.items():
            with self.subTest(character=name):
                img, draw = _make_canvas()
                draw_fn(draw, 100, 100, 60, "neutral", palette)
                self.assertTrue(_image_is_non_empty(img), f"{name} produced empty image with palette")

    def test_each_character_all_expressions(self):
        """Each character renders with every expression without error."""
        palette = PALETTES["day_calm"]
        for name, draw_fn in ALL_CHARACTERS.items():
            for expr in EXPRESSIONS:
                with self.subTest(character=name, expression=expr):
                    img, draw = _make_canvas()
                    draw_fn(draw, 100, 100, 60, expr, palette)
                    self.assertTrue(_image_is_non_empty(img))

    def test_each_character_small_size(self):
        """Characters render at small size (20px) without error."""
        for name, draw_fn in ALL_CHARACTERS.items():
            with self.subTest(character=name):
                img, draw = _make_canvas(80, 80)
                draw_fn(draw, 40, 40, 20, "neutral", None)
                self.assertTrue(_image_is_non_empty(img))

    def test_each_character_large_size(self):
        """Characters render at large size (200px) without error."""
        for name, draw_fn in ALL_CHARACTERS.items():
            with self.subTest(character=name):
                img, draw = _make_canvas(400, 400)
                draw_fn(draw, 200, 200, 200, "neutral", None)
                self.assertTrue(_image_is_non_empty(img))


class TestCharacterRegistry(unittest.TestCase):
    """Test the CHARACTER_REGISTRY dict."""

    def test_registry_contains_all_21_primary_names(self):
        """All 21 primary character names are in the registry."""
        for name in ALL_CHARACTERS:
            with self.subTest(name=name):
                self.assertIn(name, CHARACTER_REGISTRY)

    def test_registry_maps_to_correct_functions(self):
        """Registry maps each name to the expected draw function."""
        for name, expected_fn in ALL_CHARACTERS.items():
            with self.subTest(name=name):
                self.assertIs(CHARACTER_REGISTRY[name], expected_fn)

    def test_registry_alias_the_membrane(self):
        self.assertIs(CHARACTER_REGISTRY["the membrane"], draw_membrane)

    def test_registry_alias_the_heartbeat(self):
        self.assertIs(CHARACTER_REGISTRY["the heartbeat"], draw_heartbeat)

    def test_registry_alias_the_instrument(self):
        self.assertIs(CHARACTER_REGISTRY["the instrument"], draw_instrument)

    def test_registry_alias_the_poet(self):
        self.assertIs(CHARACTER_REGISTRY["the poet"], draw_poet)

    def test_registry_alias_the_archivist(self):
        self.assertIs(CHARACTER_REGISTRY["the archivist"], draw_archivist)

    def test_registry_alias_the_dreamer(self):
        self.assertIs(CHARACTER_REGISTRY["the dreamer"], draw_dreamer)

    def test_registry_alias_the_printer(self):
        self.assertIs(CHARACTER_REGISTRY["the printer"], draw_printer)

    def test_registry_alias_the_speaker(self):
        self.assertIs(CHARACTER_REGISTRY["the speaker"], draw_speaker)

    def test_registry_alias_the_messenger(self):
        self.assertIs(CHARACTER_REGISTRY["the messenger"], draw_messenger)

    def test_registry_alias_the_scribe(self):
        self.assertIs(CHARACTER_REGISTRY["the scribe"], draw_scribe)

    def test_registry_alias_the_navigator(self):
        self.assertIs(CHARACTER_REGISTRY["the navigator"], draw_navigator)

    def test_registry_alias_the_weaver(self):
        self.assertIs(CHARACTER_REGISTRY["the weaver"], draw_weaver)

    def test_registry_alias_the_conductor(self):
        self.assertIs(CHARACTER_REGISTRY["the conductor"], draw_conductor)

    def test_registry_values_are_callable(self):
        """Every registry value is callable."""
        for name, fn in CHARACTER_REGISTRY.items():
            with self.subTest(name=name):
                self.assertTrue(callable(fn))


class TestRegistryIntegration(unittest.TestCase):
    """Test that render_scene and render_panel use the registry."""

    def test_render_scene_dispatches_registered_character(self):
        """render_scene draws a registered character by name."""
        for name in ALL_CHARACTERS:
            with self.subTest(character=name):
                chars = [SceneCharacter(name=name, x=100, y=150, size=50)]
                img = render_scene(200, 200, characters=chars, seed=42)
                self.assertIsInstance(img, Image.Image)
                self.assertEqual(img.size, (200, 200))

    def test_render_panel_dispatches_registered_character(self):
        """render_panel draws a registered character by name."""
        for name in ALL_CHARACTERS:
            with self.subTest(character=name):
                spec = PanelSpec(
                    characters=[{"name": name, "expression": "happy", "x": 100, "y": 150, "size": 50}],
                    width=200,
                    height=200,
                )
                img = render_panel(spec)
                self.assertIsInstance(img, Image.Image)
                self.assertEqual(img.size, (200, 200))

    def test_render_scene_multiple_characters(self):
        """render_scene handles a scene with many different characters."""
        chars = [
            SceneCharacter(name=name, x=50 + i * 20, y=150, size=30)
            for i, name in enumerate(list(ALL_CHARACTERS.keys())[:6])
        ]
        img = render_scene(400, 300, characters=chars, seed=42)
        self.assertIsInstance(img, Image.Image)

    def test_unknown_character_falls_back_to_generic(self):
        """An unknown name falls back to draw_character, not an error."""
        chars = [SceneCharacter(name="unknown_entity", x=100, y=150, size=50)]
        img = render_scene(200, 200, characters=chars, seed=42)
        self.assertIsInstance(img, Image.Image)


class TestCharacterVisualDistinctness(unittest.TestCase):
    """Verify that different characters produce visually distinct images."""

    def test_characters_produce_different_pixels(self):
        """No two characters produce identical pixel output."""
        rendered: dict[str, list] = {}
        palette = PALETTES["day_calm"]

        for name, draw_fn in ALL_CHARACTERS.items():
            img, draw = _make_canvas()
            draw_fn(draw, 100, 100, 60, "neutral", palette)
            rendered[name] = list(img.getdata())

        names = list(rendered.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                with self.subTest(a=names[i], b=names[j]):
                    self.assertNotEqual(
                        rendered[names[i]], rendered[names[j]],
                        f"{names[i]} and {names[j]} produced identical images",
                    )


class TestCharacterGroupCoverage(unittest.TestCase):
    """Verify all character groups are fully covered."""

    SENSORS = ["membrane", "heartbeat", "face eye", "porch eye", "garden eye", "instrument"]
    VOICES = ["basalt", "pebble", "poet", "archivist", "dreamer"]
    OUTPUTS = ["gallery face", "gallery wall", "printer", "speaker"]
    BRIDGES = ["skin", "messenger", "scribe", "navigator", "weaver", "conductor"]

    def test_sensor_count(self):
        self.assertEqual(len(self.SENSORS), 6)

    def test_voice_count(self):
        self.assertEqual(len(self.VOICES), 5)

    def test_output_count(self):
        self.assertEqual(len(self.OUTPUTS), 4)

    def test_bridge_count(self):
        self.assertEqual(len(self.BRIDGES), 6)

    def test_total_is_21(self):
        total = self.SENSORS + self.VOICES + self.OUTPUTS + self.BRIDGES
        self.assertEqual(len(total), 21)

    def test_all_groups_in_registry(self):
        all_names = self.SENSORS + self.VOICES + self.OUTPUTS + self.BRIDGES
        for name in all_names:
            with self.subTest(name=name):
                self.assertIn(name, CHARACTER_REGISTRY)


if __name__ == "__main__":
    unittest.main()
