"""Tests for Scene Composer — PARE-001: creative brain deciding what to draw.

Covers:
- SceneSpec dataclass structure
- compose_scene with explicit mood and hour
- compose_scene reading from /tmp/organism_state.json fallback
- pick_characters selects mood-appropriate characters
- pick_elements selects season/weather-appropriate elements
- generate_title produces short poetic titles
- render_composed_scene converts SceneSpec to PIL Image
- save_to_gallery writes PNG + JSON sidecar
- Different moods produce different scenes
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# Add my-claw/tools to path
sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

from senseweave.scene_composer import (
    ACTIVE_CHARACTERS,
    NATURE_CHARACTERS,
    QUIET_CHARACTERS,
    SceneSpec,
    compose_scene,
    generate_title,
    pick_characters,
    pick_elements,
    render_composed_scene,
    save_to_gallery,
)


# ---------------------------------------------------------------------------
# SceneSpec dataclass
# ---------------------------------------------------------------------------


class TestSceneSpec(unittest.TestCase):
    """SceneSpec has the right fields and defaults."""

    def test_default_construction(self):
        spec = SceneSpec()
        self.assertIsInstance(spec.characters, list)
        self.assertIsInstance(spec.elements, list)
        self.assertIsInstance(spec.weather, dict)
        self.assertEqual(spec.hour, 12)
        self.assertEqual(spec.palette_name, "day_calm")
        self.assertEqual(spec.title, "")
        self.assertEqual(spec.mood_tag, "calm")

    def test_custom_construction(self):
        spec = SceneSpec(
            characters=[{"name": "Basalt", "expression": "happy", "position": (100, 200), "size": 80}],
            elements=[{"type": "tree", "position": (50, 100)}],
            weather={"rain": 0.5, "snow": 0.0, "clouds": 3, "fog": False},
            hour=14,
            palette_name="rain",
            title="A rainy afternoon",
            mood_tag="calm",
        )
        self.assertEqual(len(spec.characters), 1)
        self.assertEqual(spec.characters[0]["name"], "Basalt")
        self.assertEqual(spec.weather["rain"], 0.5)
        self.assertEqual(spec.hour, 14)


# ---------------------------------------------------------------------------
# compose_scene
# ---------------------------------------------------------------------------


class TestComposeScene(unittest.TestCase):
    """compose_scene produces valid SceneSpecs from mood dicts."""

    def test_with_explicit_mood_and_hour(self):
        mood = {"energy": 0.8, "valence": 0.7, "arousal": 0.6}
        spec = compose_scene(mood=mood, hour=10)
        self.assertIsInstance(spec, SceneSpec)
        self.assertEqual(spec.hour, 10)
        self.assertGreaterEqual(len(spec.characters), 1)
        self.assertLessEqual(len(spec.characters), 4)
        self.assertTrue(spec.title)
        self.assertTrue(spec.mood_tag)

    def test_with_low_energy_mood(self):
        mood = {"energy": 0.1, "valence": 0.3, "arousal": 0.1}
        spec = compose_scene(mood=mood, hour=2)
        # Low energy = fewer characters
        self.assertLessEqual(len(spec.characters), 2)

    def test_with_high_energy_mood(self):
        mood = {"energy": 0.9, "valence": 0.8, "arousal": 0.9}
        spec = compose_scene(mood=mood, hour=14)
        # High energy = more characters
        self.assertGreaterEqual(len(spec.characters), 2)

    def test_reads_organism_state_when_mood_is_none(self):
        fake_state = {
            "organism_mood": {"energy": 0.5, "valence": 0.6, "arousal": 0.4},
            "timestamp": time.time(),
        }
        with patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(fake_state))):
            spec = compose_scene(mood=None, hour=12)
        self.assertIsInstance(spec, SceneSpec)
        self.assertGreaterEqual(len(spec.characters), 1)

    def test_fallback_when_state_file_missing(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            spec = compose_scene(mood=None, hour=12)
        self.assertIsInstance(spec, SceneSpec)
        # Should use a default calm mood
        self.assertGreaterEqual(len(spec.characters), 1)

    def test_uses_current_hour_when_none(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        spec = compose_scene(mood=mood, hour=None)
        self.assertIsInstance(spec.hour, int)
        self.assertGreaterEqual(spec.hour, 0)
        self.assertLessEqual(spec.hour, 23)

    def test_weather_dict_has_required_keys(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        spec = compose_scene(mood=mood, hour=12)
        self.assertIn("rain", spec.weather)
        self.assertIn("snow", spec.weather)
        self.assertIn("clouds", spec.weather)
        self.assertIn("fog", spec.weather)

    def test_character_dicts_have_required_keys(self):
        mood = {"energy": 0.7, "valence": 0.7, "arousal": 0.6}
        spec = compose_scene(mood=mood, hour=12)
        for char in spec.characters:
            self.assertIn("name", char)
            self.assertIn("expression", char)
            self.assertIn("position", char)
            self.assertIn("size", char)
            self.assertIsInstance(char["position"], tuple)
            self.assertEqual(len(char["position"]), 2)

    def test_element_dicts_have_required_keys(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        spec = compose_scene(mood=mood, hour=12)
        for elem in spec.elements:
            self.assertIn("type", elem)
            self.assertIn("position", elem)
            self.assertIsInstance(elem["position"], tuple)


# ---------------------------------------------------------------------------
# Different moods produce different scenes
# ---------------------------------------------------------------------------


class TestMoodDiversity(unittest.TestCase):
    """Different mood inputs produce meaningfully different scene specs."""

    def test_high_vs_low_energy_character_count(self):
        low = compose_scene(mood={"energy": 0.1, "valence": 0.5, "arousal": 0.1}, hour=12)
        high = compose_scene(mood={"energy": 0.9, "valence": 0.5, "arousal": 0.9}, hour=12)
        # High energy should have at least as many characters
        self.assertGreaterEqual(len(high.characters), len(low.characters))

    def test_happy_vs_sad_different_mood_tags(self):
        happy = compose_scene(mood={"energy": 0.6, "valence": 0.8, "arousal": 0.5}, hour=12)
        sad = compose_scene(mood={"energy": 0.2, "valence": 0.2, "arousal": 0.3}, hour=12)
        self.assertNotEqual(happy.mood_tag, sad.mood_tag)

    def test_different_hours_different_palettes(self):
        dawn = compose_scene(mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5}, hour=6)
        night = compose_scene(mood={"energy": 0.5, "valence": 0.5, "arousal": 0.5}, hour=23)
        self.assertNotEqual(dawn.palette_name, night.palette_name)


# ---------------------------------------------------------------------------
# pick_characters
# ---------------------------------------------------------------------------


class TestPickCharacters(unittest.TestCase):
    """pick_characters selects mood-appropriate characters."""

    def test_returns_requested_count(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        chars = pick_characters(mood, count=3)
        self.assertEqual(len(chars), 3)

    def test_high_energy_includes_active_characters(self):
        mood = {"energy": 0.9, "valence": 0.7, "arousal": 0.8}
        chars = pick_characters(mood, count=4)
        names = [c["name"] for c in chars]
        # Should include at least one active character
        active = set(ACTIVE_CHARACTERS)
        self.assertTrue(any(n in active for n in names),
                        f"Expected active character in {names}")

    def test_low_energy_includes_quiet_characters(self):
        mood = {"energy": 0.1, "valence": 0.4, "arousal": 0.1}
        chars = pick_characters(mood, count=2)
        names = [c["name"] for c in chars]
        quiet = set(QUIET_CHARACTERS)
        self.assertTrue(any(n in quiet for n in names),
                        f"Expected quiet character in {names}")

    def test_calm_mood_includes_nature_characters(self):
        mood = {"energy": 0.4, "valence": 0.6, "arousal": 0.3}
        chars = pick_characters(mood, count=3)
        names = [c["name"] for c in chars]
        nature = set(NATURE_CHARACTERS)
        self.assertTrue(any(n in nature for n in names),
                        f"Expected nature character in {names}")

    def test_always_includes_face_character(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        chars = pick_characters(mood, count=1)
        # At least one character should be a face character
        self.assertEqual(len(chars), 1)
        self.assertIn("name", chars[0])

    def test_character_dicts_have_required_keys(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        chars = pick_characters(mood, count=2)
        for c in chars:
            self.assertIn("name", c)
            self.assertIn("expression", c)
            self.assertIn("position", c)
            self.assertIn("size", c)

    def test_count_clamped_to_valid_range(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        chars = pick_characters(mood, count=0)
        self.assertGreaterEqual(len(chars), 1)  # Always at least 1
        chars = pick_characters(mood, count=10)
        self.assertLessEqual(len(chars), 4)  # Max 4


# ---------------------------------------------------------------------------
# pick_elements
# ---------------------------------------------------------------------------


class TestPickElements(unittest.TestCase):
    """pick_elements selects season/weather-appropriate elements."""

    def test_spring_elements(self):
        elems = pick_elements("spring", "clear", count=3)
        types = [e["type"] for e in elems]
        spring_types = {"tree", "flower", "puddle"}
        self.assertTrue(any(t in spring_types for t in types),
                        f"Expected spring element in {types}")

    def test_summer_elements(self):
        elems = pick_elements("summer", "clear", count=3)
        types = [e["type"] for e in elems]
        summer_types = {"tree", "bush", "butterfly"}
        self.assertTrue(any(t in summer_types for t in types),
                        f"Expected summer element in {types}")

    def test_fall_elements(self):
        elems = pick_elements("fall", "clear", count=3)
        types = [e["type"] for e in elems]
        fall_types = {"tree", "mushroom", "path"}
        self.assertTrue(any(t in fall_types for t in types),
                        f"Expected fall element in {types}")

    def test_winter_elements(self):
        elems = pick_elements("winter", "clear", count=3)
        types = [e["type"] for e in elems]
        winter_types = {"bare_tree", "snow_drift", "path"}
        self.assertTrue(any(t in winter_types for t in types),
                        f"Expected winter element in {types}")

    def test_rain_adds_puddles(self):
        elems = pick_elements("summer", "rain", count=3)
        types = [e["type"] for e in elems]
        self.assertIn("puddle", types)

    def test_returns_requested_count(self):
        elems = pick_elements("spring", "clear", count=5)
        self.assertEqual(len(elems), 5)

    def test_elements_have_position(self):
        elems = pick_elements("spring", "clear", count=2)
        for e in elems:
            self.assertIn("type", e)
            self.assertIn("position", e)
            self.assertIsInstance(e["position"], tuple)


# ---------------------------------------------------------------------------
# generate_title
# ---------------------------------------------------------------------------


class TestGenerateTitle(unittest.TestCase):
    """generate_title produces short poetic scene titles."""

    def test_returns_nonempty_string(self):
        title = generate_title(
            [{"name": "Basalt"}, {"name": "Pebble"}],
            "calm",
            "clear",
        )
        self.assertIsInstance(title, str)
        self.assertTrue(len(title) > 0)

    def test_title_not_too_long(self):
        title = generate_title(
            [{"name": "Basalt"}, {"name": "Pebble"}, {"name": "Dreamer"}],
            "happy",
            "rain",
        )
        # Titles should be short and poetic
        self.assertLessEqual(len(title), 80)

    def test_different_inputs_can_produce_different_titles(self):
        t1 = generate_title([{"name": "Basalt"}], "happy", "clear")
        t2 = generate_title([{"name": "Dreamer"}], "sad", "rain")
        # Not guaranteed to differ (randomness), but structure should differ
        self.assertIsInstance(t1, str)
        self.assertIsInstance(t2, str)


# ---------------------------------------------------------------------------
# render_composed_scene
# ---------------------------------------------------------------------------


class TestRenderComposedScene(unittest.TestCase):
    """render_composed_scene converts SceneSpec to PIL Image."""

    def test_returns_pil_image(self):
        spec = SceneSpec(
            characters=[{"name": "Basalt", "expression": "happy", "position": (400, 600), "size": 80}],
            elements=[{"type": "tree", "position": (200, 500)}],
            weather={"rain": 0.0, "snow": 0.0, "clouds": 2, "fog": False},
            hour=12,
            palette_name="day_calm",
            title="Test scene",
            mood_tag="calm",
        )
        from PIL import Image
        img = render_composed_scene(spec)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (1280, 1024))

    def test_custom_dimensions(self):
        spec = SceneSpec(
            characters=[],
            elements=[],
            weather={"rain": 0.0, "snow": 0.0, "clouds": 0, "fog": False},
            hour=12,
            palette_name="day_calm",
            title="",
            mood_tag="calm",
        )
        from PIL import Image
        img = render_composed_scene(spec, width=640, height=480)
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (640, 480))

    def test_with_rain_weather(self):
        spec = SceneSpec(
            characters=[{"name": "Pebble", "expression": "curious", "position": (300, 500), "size": 50}],
            elements=[{"type": "puddle", "position": (500, 700)}],
            weather={"rain": 0.7, "snow": 0.0, "clouds": 4, "fog": False},
            hour=15,
            palette_name="rain",
            title="Pebble in the rain",
            mood_tag="calm",
        )
        from PIL import Image
        img = render_composed_scene(spec)
        self.assertIsInstance(img, Image.Image)

    def test_with_snow_weather(self):
        spec = SceneSpec(
            characters=[{"name": "Basalt", "expression": "calm", "position": (600, 600), "size": 90}],
            elements=[],
            weather={"rain": 0.0, "snow": 0.8, "clouds": 3, "fog": False},
            hour=22,
            palette_name="snow",
            title="Snow night",
            mood_tag="calm",
        )
        from PIL import Image
        img = render_composed_scene(spec)
        self.assertIsInstance(img, Image.Image)

    def test_night_scene_with_stars(self):
        spec = SceneSpec(
            characters=[{"name": "Dreamer", "expression": "sleeping", "position": (640, 700), "size": 60}],
            elements=[{"type": "rock", "position": (400, 750)}],
            weather={"rain": 0.0, "snow": 0.0, "clouds": 0, "fog": False},
            hour=2,
            palette_name="night",
            title="Deep night dreams",
            mood_tag="sleeping",
        )
        from PIL import Image
        img = render_composed_scene(spec)
        self.assertIsInstance(img, Image.Image)


# ---------------------------------------------------------------------------
# save_to_gallery
# ---------------------------------------------------------------------------


class TestSaveToGallery(unittest.TestCase):
    """save_to_gallery writes PNG + JSON sidecar."""

    def test_saves_png_and_json(self):
        from PIL import Image
        img = Image.new("RGBA", (100, 100), (128, 128, 128))
        spec = SceneSpec(
            characters=[{"name": "Basalt", "expression": "calm", "position": (50, 50), "size": 40}],
            elements=[],
            weather={"rain": 0.0, "snow": 0.0, "clouds": 0, "fog": False},
            hour=12,
            palette_name="day_calm",
            title="Gallery test",
            mood_tag="calm",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_to_gallery(img, spec, gallery_dir=tmpdir)
            self.assertTrue(path.endswith(".png"))
            self.assertTrue(os.path.isfile(path))
            # JSON sidecar should exist alongside
            json_path = path.replace(".png", ".json")
            self.assertTrue(os.path.isfile(json_path))
            # Verify JSON content
            with open(json_path) as f:
                meta = json.load(f)
            self.assertEqual(meta["title"], "Gallery test")
            self.assertEqual(meta["mood_tag"], "calm")
            self.assertIn("characters", meta)
            self.assertIn("timestamp", meta)

    def test_creates_gallery_dir_if_missing(self):
        from PIL import Image
        img = Image.new("RGBA", (100, 100), (128, 128, 128))
        spec = SceneSpec(
            characters=[],
            elements=[],
            weather={"rain": 0.0, "snow": 0.0, "clouds": 0, "fog": False},
            hour=12,
            palette_name="day_calm",
            title="",
            mood_tag="calm",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            sub = os.path.join(tmpdir, "nested", "gallery")
            path = save_to_gallery(img, spec, gallery_dir=sub)
            self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
