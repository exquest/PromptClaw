"""Tests for mood_mirror.py — mood-to-parameter mapping for CypherClaw face/audio/art."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

from mood_mirror import (
    mood_to_face_expression,
    mood_to_background_color,
    mood_to_music_params,
    mood_to_art_params,
)


# === mood_to_face_expression ===


class TestFaceExpression:
    def test_sleeping_low_energy_low_arousal(self):
        mood = {"energy": 0.1, "valence": 0.5, "arousal": 0.1}
        assert mood_to_face_expression(mood) == "sleeping"

    def test_calm_mid_energy_low_arousal_positive_valence(self):
        mood = {"energy": 0.4, "valence": 0.6, "arousal": 0.3}
        assert mood_to_face_expression(mood) == "calm"

    def test_happy_high_valence_mid_arousal(self):
        mood = {"energy": 0.6, "valence": 0.8, "arousal": 0.5}
        assert mood_to_face_expression(mood) == "happy"

    def test_excited_high_everything(self):
        mood = {"energy": 0.9, "valence": 0.8, "arousal": 0.9}
        assert mood_to_face_expression(mood) == "excited"

    def test_anxious_high_arousal_low_valence(self):
        mood = {"energy": 0.6, "valence": 0.2, "arousal": 0.8}
        assert mood_to_face_expression(mood) == "anxious"

    def test_sad_low_energy_low_valence(self):
        mood = {"energy": 0.3, "valence": 0.15, "arousal": 0.3}
        assert mood_to_face_expression(mood) == "sad"

    def test_curious_mid_energy_mid_arousal_mid_valence(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.6}
        assert mood_to_face_expression(mood) == "curious"

    def test_returns_valid_expression_for_zeros(self):
        mood = {"energy": 0.0, "valence": 0.0, "arousal": 0.0}
        result = mood_to_face_expression(mood)
        assert result in ("calm", "happy", "curious", "anxious", "sleeping", "excited", "sad")

    def test_returns_valid_expression_for_ones(self):
        mood = {"energy": 1.0, "valence": 1.0, "arousal": 1.0}
        result = mood_to_face_expression(mood)
        assert result in ("calm", "happy", "curious", "anxious", "sleeping", "excited", "sad")


# === mood_to_background_color ===


class TestBackgroundColor:
    def test_returns_rgb_tuple(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        color = mood_to_background_color(mood)
        assert isinstance(color, tuple)
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)

    def test_calm_is_deep_blue(self):
        mood = {"energy": 0.4, "valence": 0.6, "arousal": 0.3}
        r, g, b = mood_to_background_color(mood)
        # Deep blue: blue channel dominant, red low
        assert b > r
        assert b > g

    def test_happy_is_warm_blue(self):
        mood = {"energy": 0.6, "valence": 0.8, "arousal": 0.5}
        r, g, b = mood_to_background_color(mood)
        # Warm blue: still blue-ish but with some warmth
        assert b >= g

    def test_anxious_is_dark_red(self):
        mood = {"energy": 0.6, "valence": 0.2, "arousal": 0.8}
        r, g, b = mood_to_background_color(mood)
        # Dark red: red dominant
        assert r > b
        assert r > g

    def test_sleeping_is_near_black(self):
        mood = {"energy": 0.1, "valence": 0.5, "arousal": 0.1}
        r, g, b = mood_to_background_color(mood)
        # Near black: all channels low
        assert r < 60
        assert g < 60
        assert b < 60

    def test_excited_is_purple(self):
        mood = {"energy": 0.9, "valence": 0.8, "arousal": 0.9}
        r, g, b = mood_to_background_color(mood)
        # Purple: red and blue present, green lower
        assert r > g
        assert b > g

    def test_zero_mood_valid_rgb(self):
        r, g, b = mood_to_background_color({"energy": 0.0, "valence": 0.0, "arousal": 0.0})
        assert all(0 <= c <= 255 for c in (r, g, b))

    def test_max_mood_valid_rgb(self):
        r, g, b = mood_to_background_color({"energy": 1.0, "valence": 1.0, "arousal": 1.0})
        assert all(0 <= c <= 255 for c in (r, g, b))


# === mood_to_music_params ===


class TestMusicParams:
    def test_returns_expected_keys(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        params = mood_to_music_params(mood)
        assert "tempo_factor" in params
        assert "volume_factor" in params
        assert "key_preference" in params
        assert "density" in params

    def test_sleeping_is_slow_and_quiet(self):
        mood = {"energy": 0.1, "valence": 0.5, "arousal": 0.1}
        params = mood_to_music_params(mood)
        assert params["tempo_factor"] <= 0.9
        assert params["volume_factor"] <= 0.4
        assert params["density"] == "sparse"

    def test_excited_is_fast_and_loud(self):
        mood = {"energy": 0.9, "valence": 0.8, "arousal": 0.9}
        params = mood_to_music_params(mood)
        assert params["tempo_factor"] >= 1.1
        assert params["volume_factor"] >= 0.8
        assert params["density"] == "dense"

    def test_high_valence_major_key(self):
        mood = {"energy": 0.5, "valence": 0.8, "arousal": 0.5}
        params = mood_to_music_params(mood)
        assert params["key_preference"] == "major"

    def test_low_valence_minor_key(self):
        mood = {"energy": 0.5, "valence": 0.2, "arousal": 0.5}
        params = mood_to_music_params(mood)
        assert params["key_preference"] == "minor"

    def test_tempo_factor_range(self):
        for e in (0.0, 0.5, 1.0):
            for a in (0.0, 0.5, 1.0):
                mood = {"energy": e, "valence": 0.5, "arousal": a}
                params = mood_to_music_params(mood)
                assert 0.8 <= params["tempo_factor"] <= 1.2

    def test_volume_factor_range(self):
        for e in (0.0, 0.5, 1.0):
            for a in (0.0, 0.5, 1.0):
                mood = {"energy": e, "valence": 0.5, "arousal": a}
                params = mood_to_music_params(mood)
                assert 0.3 <= params["volume_factor"] <= 1.0

    def test_density_sparse_low_energy(self):
        mood = {"energy": 0.15, "valence": 0.5, "arousal": 0.5}
        params = mood_to_music_params(mood)
        assert params["density"] == "sparse"

    def test_density_dense_high_energy(self):
        mood = {"energy": 0.85, "valence": 0.5, "arousal": 0.5}
        params = mood_to_music_params(mood)
        assert params["density"] == "dense"


# === mood_to_art_params ===


class TestArtParams:
    def test_returns_expected_keys(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        params = mood_to_art_params(mood)
        assert "palette" in params
        assert "complexity" in params
        assert "theme_hints" in params
        assert isinstance(params["theme_hints"], list)

    def test_high_valence_warm_or_bright_palette(self):
        mood = {"energy": 0.7, "valence": 0.9, "arousal": 0.5}
        params = mood_to_art_params(mood)
        assert params["palette"] in ("warm", "bright")

    def test_low_valence_cool_or_dark_palette(self):
        mood = {"energy": 0.3, "valence": 0.1, "arousal": 0.5}
        params = mood_to_art_params(mood)
        assert params["palette"] in ("cool", "dark")

    def test_high_energy_complex(self):
        mood = {"energy": 0.9, "valence": 0.5, "arousal": 0.9}
        params = mood_to_art_params(mood)
        assert params["complexity"] == "complex"

    def test_low_energy_simple(self):
        mood = {"energy": 0.1, "valence": 0.5, "arousal": 0.1}
        params = mood_to_art_params(mood)
        assert params["complexity"] == "simple"

    def test_mid_energy_moderate(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        params = mood_to_art_params(mood)
        assert params["complexity"] == "moderate"

    def test_sleeping_theme_hints(self):
        mood = {"energy": 0.1, "valence": 0.5, "arousal": 0.1}
        params = mood_to_art_params(mood)
        hints = params["theme_hints"]
        assert any("night" in h or "sleep" in h or "dream" in h for h in hints)

    def test_excited_theme_hints(self):
        mood = {"energy": 0.9, "valence": 0.9, "arousal": 0.9}
        params = mood_to_art_params(mood)
        hints = params["theme_hints"]
        assert len(hints) >= 1

    def test_sad_theme_hints(self):
        mood = {"energy": 0.2, "valence": 0.1, "arousal": 0.2}
        params = mood_to_art_params(mood)
        hints = params["theme_hints"]
        assert any("melancholy" in h or "rain" in h or "quiet" in h for h in hints)

    def test_palette_valid_values(self):
        for e in (0.0, 0.5, 1.0):
            for v in (0.0, 0.5, 1.0):
                mood = {"energy": e, "valence": v, "arousal": 0.5}
                params = mood_to_art_params(mood)
                assert params["palette"] in ("warm", "cool", "dark", "bright")

    def test_complexity_valid_values(self):
        for e in (0.0, 0.5, 1.0):
            for a in (0.0, 0.5, 1.0):
                mood = {"energy": e, "valence": 0.5, "arousal": a}
                params = mood_to_art_params(mood)
                assert params["complexity"] in ("simple", "moderate", "complex")
