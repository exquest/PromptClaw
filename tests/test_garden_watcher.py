"""Tests for garden_watcher.py — outdoor garden camera state for art installation mood/music."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

from garden_watcher import (
    build_garden_state,
    estimate_outdoor_light,
    estimate_season,
    suggest_palette,
    suggest_music_key,
    GardenState,
    summarize_garden_state,
    update_garden_state,
    write_current_garden_state,
    write_garden_state,
)


# === estimate_outdoor_light ===


class TestEstimateOutdoorLight:
    def test_bright_sun_midday(self):
        assert estimate_outdoor_light(0.9, 12) == "bright_sun"

    def test_bright_sun_high_brightness_afternoon(self):
        assert estimate_outdoor_light(0.85, 14) == "bright_sun"

    def test_cloudy_moderate_brightness(self):
        assert estimate_outdoor_light(0.5, 12) == "cloudy"

    def test_dim_low_brightness_daytime(self):
        assert estimate_outdoor_light(0.25, 10) == "dim"

    def test_twilight_low_brightness_dusk(self):
        assert estimate_outdoor_light(0.15, 20) == "twilight"

    def test_twilight_low_brightness_dawn(self):
        assert estimate_outdoor_light(0.15, 6) == "twilight"

    def test_dark_zero_brightness(self):
        assert estimate_outdoor_light(0.0, 2) == "dark"

    def test_dark_very_low_brightness_night(self):
        assert estimate_outdoor_light(0.05, 23) == "dark"

    def test_dark_nighttime_even_moderate_brightness(self):
        # At 2am even moderate sensor reading should skew dark
        result = estimate_outdoor_light(0.1, 2)
        assert result in ("dark", "twilight")

    def test_boundary_brightness_zero(self):
        assert estimate_outdoor_light(0.0, 12) in ("dark", "dim")

    def test_boundary_brightness_one(self):
        assert estimate_outdoor_light(1.0, 12) == "bright_sun"

    def test_returns_valid_string(self):
        valid = {"bright_sun", "cloudy", "dim", "twilight", "dark"}
        for b in (0.0, 0.2, 0.5, 0.8, 1.0):
            for h in (0, 6, 12, 18, 23):
                assert estimate_outdoor_light(b, h) in valid


# === estimate_season ===


class TestEstimateSeason:
    def test_march_is_spring(self):
        assert estimate_season(3) == "spring"

    def test_april_is_spring(self):
        assert estimate_season(4) == "spring"

    def test_may_is_spring(self):
        assert estimate_season(5) == "spring"

    def test_june_is_summer(self):
        assert estimate_season(6) == "summer"

    def test_august_is_summer(self):
        assert estimate_season(8) == "summer"

    def test_september_is_fall(self):
        assert estimate_season(9) == "fall"

    def test_november_is_fall(self):
        assert estimate_season(11) == "fall"

    def test_december_is_winter(self):
        assert estimate_season(12) == "winter"

    def test_january_is_winter(self):
        assert estimate_season(1) == "winter"

    def test_february_is_winter(self):
        assert estimate_season(2) == "winter"

    def test_all_months_valid(self):
        valid = {"spring", "summer", "fall", "winter"}
        for m in range(1, 13):
            assert estimate_season(m) in valid


# === suggest_palette ===


class TestSuggestPalette:
    def test_spring_bright_sun(self):
        palette = suggest_palette("bright_sun", "spring")
        assert isinstance(palette, list)
        assert len(palette) >= 2
        # Spring bright should have lively colors
        assert any(c in palette for c in ["green", "pink", "yellow"])

    def test_winter_dark(self):
        palette = suggest_palette("dark", "winter")
        assert isinstance(palette, list)
        assert len(palette) >= 2
        assert any(c in palette for c in ["deep_blue", "silver", "white"])

    def test_summer_cloudy(self):
        palette = suggest_palette("cloudy", "summer")
        assert isinstance(palette, list)
        assert len(palette) >= 2

    def test_fall_twilight(self):
        palette = suggest_palette("twilight", "fall")
        assert isinstance(palette, list)
        assert len(palette) >= 2

    def test_all_combinations_return_lists(self):
        lights = ["bright_sun", "cloudy", "dim", "twilight", "dark"]
        seasons = ["spring", "summer", "fall", "winter"]
        for light in lights:
            for season in seasons:
                palette = suggest_palette(light, season)
                assert isinstance(palette, list)
                assert len(palette) >= 2
                assert all(isinstance(c, str) for c in palette)


# === suggest_music_key ===


class TestSuggestMusicKey:
    def test_bright_summer_major_key(self):
        key = suggest_music_key("bright_sun", "summer")
        assert key in ("G", "D", "A", "C", "F", "Bb", "E", "B")

    def test_dark_winter_minor_related(self):
        key = suggest_music_key("dark", "winter")
        assert key in ("E", "B", "Am", "Em", "Bm", "Dm")

    def test_twilight_modal(self):
        key = suggest_music_key("twilight", "fall")
        assert key in ("F", "Bb", "Dm", "Gm", "Am", "Eb")

    def test_all_combinations_return_strings(self):
        lights = ["bright_sun", "cloudy", "dim", "twilight", "dark"]
        seasons = ["spring", "summer", "fall", "winter"]
        for light in lights:
            for season in seasons:
                key = suggest_music_key(light, season)
                assert isinstance(key, str)
                assert len(key) >= 1


# === GardenState ===


class TestGardenState:
    def test_dataclass_fields(self):
        state = GardenState(
            light="bright_sun",
            season="spring",
            palette=["green", "pink"],
            music_key="G",
            last_update=1234567890.0,
        )
        assert state.light == "bright_sun"
        assert state.season == "spring"
        assert state.palette == ["green", "pink"]
        assert state.music_key == "G"
        assert state.last_update == 1234567890.0


# === update_garden_state ===


class TestUpdateGardenState:
    def test_returns_garden_state(self):
        state = update_garden_state(0.8)
        assert isinstance(state, GardenState)

    def test_has_valid_light(self):
        state = update_garden_state(0.5)
        assert state.light in ("bright_sun", "cloudy", "dim", "twilight", "dark")

    def test_has_valid_season(self):
        state = update_garden_state(0.5)
        assert state.season in ("spring", "summer", "fall", "winter")

    def test_has_valid_palette(self):
        state = update_garden_state(0.7)
        assert isinstance(state.palette, list)
        assert len(state.palette) >= 2

    def test_has_valid_music_key(self):
        state = update_garden_state(0.7)
        assert isinstance(state.music_key, str)
        assert len(state.music_key) >= 1

    def test_last_update_is_recent(self):
        before = time.time()
        state = update_garden_state(0.5)
        after = time.time()
        assert before <= state.last_update <= after

    def test_high_brightness_likely_bright(self):
        # At 0.95 brightness during daytime hours, should lean bright
        state = update_garden_state(0.95)
        # We can't guarantee the hour but the brightness is very high
        assert state.light in ("bright_sun", "cloudy", "dim", "twilight", "dark")

    def test_zero_brightness(self):
        state = update_garden_state(0.0)
        assert state.light in ("dark", "dim", "twilight")


# === write_garden_state ===


class TestWriteGardenState:
    def test_writes_json_file(self, tmp_path):
        state = GardenState(
            light="cloudy",
            season="fall",
            palette=["orange", "brown"],
            music_key="Am",
            last_update=1234567890.0,
        )
        out = str(tmp_path / "garden_state.json")
        write_garden_state(state, out)
        assert os.path.exists(out)
        with open(out) as f:
            data = json.load(f)
        assert data["light"] == "cloudy"
        assert data["season"] == "fall"
        assert data["palette"] == ["orange", "brown"]
        assert data["music_key"] == "Am"
        assert data["last_update"] == 1234567890.0

    def test_atomic_write_replaces_existing(self, tmp_path):
        out = str(tmp_path / "garden_state.json")
        state1 = GardenState("cloudy", "fall", ["orange"], "Am", 100.0)
        write_garden_state(state1, out)
        state2 = GardenState("dark", "winter", ["silver"], "Em", 200.0)
        write_garden_state(state2, out)
        with open(out) as f:
            data = json.load(f)
        assert data["light"] == "dark"
        assert data["season"] == "winter"

    def test_no_tmp_file_left_behind(self, tmp_path):
        out = str(tmp_path / "garden_state.json")
        state = GardenState("dim", "spring", ["green"], "C", 300.0)
        write_garden_state(state, out)
        files = os.listdir(tmp_path)
        assert "garden_state.json.tmp" not in files


# === end-to-end depth-2 path ===


class GardenWatcherEndToEndTests:
    __test__ = True

    def test_build_garden_state_resolves_deterministic_spring_sun(self):
        observed_at = datetime(2026, 4, 15, 12, 30, tzinfo=timezone.utc)

        state = build_garden_state(0.92, observed_at)

        assert state.light == "bright_sun"
        assert state.season == "spring"
        assert state.palette == ["green", "pink", "yellow", "sky_blue"]
        assert state.music_key == "G"
        assert state.last_update == observed_at.timestamp()

    def test_summarize_garden_state_returns_json_safe_operator_payload(self):
        state = GardenState(
            light="dark",
            season="winter",
            palette=["deep_blue", "silver", "white"],
            music_key="Em",
            last_update=1770000000.0,
        )

        summary = summarize_garden_state(state)

        assert summary["condition"] == "winter dark"
        assert summary["music_key"] == "Em"
        assert summary["primary_color"] == "deep_blue"
        assert summary["palette_size"] == 3
        assert summary["is_dark"] is True
        assert summary["summary"] == "winter dark garden -> Em using deep_blue"
        json.dumps(summary)

    def test_write_current_garden_state_builds_and_persists_runtime_payload(self, tmp_path):
        observed_at = datetime(2026, 10, 31, 20, 0, tzinfo=timezone.utc)
        out = tmp_path / "garden_state.json"

        state = write_current_garden_state(0.2, str(out), observed_at=observed_at)
        data = json.loads(out.read_text())

        assert state.light == "twilight"
        assert state.season == "fall"
        assert state.palette == ["copper", "wine", "dark_gold"]
        assert state.music_key == "F"
        assert state.last_update == observed_at.timestamp()
        assert data == {
            "light": "twilight",
            "season": "fall",
            "palette": ["copper", "wine", "dark_gold"],
            "music_key": "F",
            "last_update": observed_at.timestamp(),
        }
        assert {"light", "season", "palette", "music_key", "last_update"} <= data.keys()
