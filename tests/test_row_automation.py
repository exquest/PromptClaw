"""Tests for row-level performance automation across tracker, master bus, sampler, and face state.

Verifies the state contract:
- Tracker runtime exposes interpolated automation per row.
- Master bus consumes automation_values at non-scene-start rows.
- Sampler scene profiles vary with row bucket.
- Composer state carries section_curve and automation_values.
- Runtime state includes total_rows.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.generative_scores import Note, Phrase, Score
from senseweave.music_tracker import AutomationLane, build_scene_from_score
from senseweave.music_tracker_runtime import (
    interpolate_automation_at_row,
    schedule_scene,
)
from senseweave.master_bus import master_bus_values_for_scene
from senseweave.sample_dsp_activity import _row_bucket, _scene_profile


def _sample_scene():
    score = Score(
        phrases=[
            Phrase(notes=[Note(1, 1.0, False), Note(3, 0.5, True), Note(5, 1.5, False)],
                   voice="pluck", dynamic="mf", role="melody"),
            Phrase(notes=[Note(1, 1.0, True), Note(5, 1.0, False), Note(1, 1.0, False)],
                   voice="gong", dynamic="mp", role="bass"),
        ],
        key="C", tempo_bpm=120.0, mood="calm", created_at=0.0,
    )
    return build_scene_from_score(
        score, name="Development", allowed_roles=("melody", "bass"),
        rows_per_beat=4, max_polyphony=3,
    )


# ---------- Tracker runtime: public interpolation API ----------

class TestInterpolateAutomationAtRow:
    def test_returns_interpolated_density_at_midpoint(self):
        scene = _sample_scene()
        last_row = scene.pattern.rows - 1
        scene.pattern.automation = [
            AutomationLane(name="density", default=0.5, points=[(0, 0.2), (last_row, 0.8)]),
        ]
        mid = last_row // 2
        values = interpolate_automation_at_row(scene, mid)
        assert "density" in values
        assert 0.2 < values["density"] < 0.8

    def test_returns_defaults_when_no_automation_lanes(self):
        scene = _sample_scene()
        scene.pattern.automation = []
        values = interpolate_automation_at_row(scene, 0)
        assert values == {}


# ---------- Runtime state contract ----------

class TestRuntimeStateContract:
    def test_runtime_state_includes_total_rows(self, tmp_path):
        scene = _sample_scene()
        state_path = tmp_path / "tracker_state.json"

        schedule_scene(
            scene,
            play_event=lambda _e: None,
            sleep_fn=lambda _s: None,
            stop_check=lambda row: row >= 1,
            state_path=state_path,
            time_fn=lambda: 1000.0,
        )

        state = json.loads(state_path.read_text())
        assert "total_rows" in state
        assert state["total_rows"] == scene.pattern.rows

    def test_automation_updates_happen_beyond_scene_start(self, tmp_path):
        """Verify that on_row fires with different automation values at non-zero rows."""
        scene = _sample_scene()
        last_row = scene.pattern.rows - 1
        scene.pattern.automation = [
            AutomationLane(name="master_amp", default=0.6,
                           points=[(0, 0.3), (last_row, 0.9)]),
        ]
        seen_rows: list[tuple[int, float]] = []

        schedule_scene(
            scene,
            play_event=lambda _e: None,
            sleep_fn=lambda _s: None,
            state_path=tmp_path / "tracker_state.json",
            time_fn=lambda: 1000.0,
            on_row=lambda _sc, row, state: seen_rows.append(
                (row, state["automation"]["master_amp"])
            ),
        )

        # on_row fires for every row, not just row 0
        assert len(seen_rows) == scene.pattern.rows
        non_zero = [r for r, _v in seen_rows if r > 0]
        assert len(non_zero) > 0

        # Values change between first and last row
        assert seen_rows[0][1] < seen_rows[-1][1]


# ---------- Master bus: mid-scene automation ----------

class TestMasterBusMidScene:
    def test_automation_values_shift_master_bus_output(self):
        scene = _sample_scene()
        scene.pattern.automation = [
            AutomationLane(name="density", default=0.5, points=[(0, 0.5)]),
            AutomationLane(name="master_amp", default=0.6, points=[(0, 0.6)]),
            AutomationLane(name="reverb_send", default=0.12, points=[(0, 0.12)]),
        ]

        early = master_bus_values_for_scene(
            scene, context=None,
            automation_values={"density": 0.2, "master_amp": 0.3, "reverb_send": 0.1},
        )
        late = master_bus_values_for_scene(
            scene, context=None,
            automation_values={"density": 0.9, "master_amp": 0.9, "reverb_send": 0.5},
        )

        # Louder amp at higher master_amp
        assert late["amp"] > early["amp"]
        # Higher reverb at higher reverb_send
        assert late["reverb"] > early["reverb"]


# ---------- Sampler: row bucket alignment ----------

class TestSamplerRowBucket:
    def test_row_bucket_early_mid_late(self):
        assert _row_bucket({"tracker_row": 0, "tracker_total_rows": 30}) == "early"
        assert _row_bucket({"tracker_row": 15, "tracker_total_rows": 30}) == "mid"
        assert _row_bucket({"tracker_row": 28, "tracker_total_rows": 30}) == "late"

    def test_row_bucket_defaults_to_mid_without_data(self):
        assert _row_bucket({}) == "mid"
        assert _row_bucket({"tracker_row": -1}) == "mid"

    def test_recap_scene_shifts_to_afterglow_in_late_bucket(self):
        early_state = {
            "tracker_scene_name": "Recap",
            "tracker_row": 2,
            "tracker_total_rows": 30,
        }
        late_state = {
            "tracker_scene_name": "Recap",
            "tracker_row": 28,
            "tracker_total_rows": 30,
        }

        early_profile, early_mode = _scene_profile(
            composer_state={}, self_state=early_state,
            sample_source="room_mic", base_mode="texture_bed",
        )
        late_profile, late_mode = _scene_profile(
            composer_state={}, self_state=late_state,
            sample_source="room_mic", base_mode="texture_bed",
        )

        assert early_profile == "recap_echo"
        assert early_mode == "window_echo"
        assert late_profile == "afterglow_residue"
        assert late_mode == "freeze_bed"

    def test_theme_scene_shifts_to_emergence_motion_in_late_bucket(self):
        early_state = {
            "tracker_scene_name": "Theme",
            "tracker_row": 1,
            "tracker_total_rows": 30,
        }
        late_state = {
            "tracker_scene_name": "Theme",
            "tracker_row": 28,
            "tracker_total_rows": 30,
        }

        early_profile, early_mode = _scene_profile(
            composer_state={}, self_state=early_state,
            sample_source="room_mic", base_mode="texture_bed",
        )
        late_profile, late_mode = _scene_profile(
            composer_state={}, self_state=late_state,
            sample_source="room_mic", base_mode="texture_bed",
        )

        assert early_profile == "theme_accents"
        assert early_mode == "slice_accents"
        assert late_profile == "emergence_motion"
        assert late_mode == "grain_cloud"

    def test_development_scene_consistent_across_buckets(self):
        """Development stays grain_cloud regardless of bucket."""
        for row in (0, 15, 29):
            profile, mode = _scene_profile(
                composer_state={},
                self_state={
                    "tracker_scene_name": "Development",
                    "tracker_row": row,
                    "tracker_total_rows": 30,
                },
                sample_source="room_mic",
                base_mode="texture_bed",
            )
            assert profile == "development_grains"
            assert mode == "grain_cloud"


# ---------- Composer state: section_curve + automation_values ----------

class TestComposerStateExtras:
    def test_runtime_state_includes_automation_curve(self, tmp_path):
        scene = _sample_scene()
        scene.metadata["arrangement_curve"] = "development_rise"
        state_path = tmp_path / "tracker_state.json"

        schedule_scene(
            scene,
            play_event=lambda _e: None,
            sleep_fn=lambda _s: None,
            stop_check=lambda row: row >= 1,
            state_path=state_path,
            time_fn=lambda: 1000.0,
        )

        state = json.loads(state_path.read_text())
        assert state["automation_curve"] == "development_rise"
