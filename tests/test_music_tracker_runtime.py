"""Tests for tracker runtime scheduling and row-state emission."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.generative_scores import Note, Phrase, Score
from senseweave.music_tracker import AutomationLane, MetricModulation, TrackerSong, build_scene_from_score
from senseweave.music_tracker_runtime import (
    _apply_sensor_modulation,
    _clamp_sensor,
    _SENSOR_NEUTRAL,
    _tmp_state_path,
    build_scene_events,
    event_to_pbind_dict,
    load_delta_track,
    pbind_dict_to_event,
    replay_sensor_fn,
    schedule_scene,
    schedule_song,
    ScheduledTrackerEvent,
    write_delta_track,
)
from cypherclaw.render.events import Event
from cypherclaw.space_reverb import VOICE_REVERB_PROFILES


def _sample_scene():
    score = Score(
        phrases=[
            Phrase(
                notes=[Note(1, 1.0, False), Note(3, 0.5, True), Note(5, 1.5, False)],
                voice="pluck",
                dynamic="mf",
                role="melody",
            ),
            Phrase(
                notes=[Note(1, 1.0, True), Note(5, 1.0, False), Note(1, 1.0, False)],
                voice="gong",
                dynamic="mp",
                role="bass",
            ),
            Phrase(
                notes=[Note(1, 2.0, False), Note(3, 2.0, False)],
                voice="pad",
                dynamic="pp",
                role="color",
            ),
        ],
        key="C",
        tempo_bpm=120.0,
        mood="calm",
        created_at=0.0,
    )
    return build_scene_from_score(
        score,
        name="Theme",
        allowed_roles=("melody", "bass", "color"),
        rows_per_beat=4,
        max_polyphony=3,
        # Disable polyrhythmic-cross default lane offsets so this test fixture
        # exercises raw event ordering / register routing.
        scene_metadata={"groove_lane_phase_offsets": "0,0,0,0,0"},
    )


class TestBuildSceneEvents:
    def test_builds_sorted_events_with_routed_voices(self):
        scene = _sample_scene()
        events = build_scene_events(scene)

        assert [event.row for event in events] == sorted(event.row for event in events)
        assert events[0].scene_name == "Theme"
        assert events[0].lane_name == "melody"
        assert any(event.lane_name == "foundation" and event.voice == "gong" for event in events)
        assert any(event.lane_name == "texture" and event.voice == "breath" for event in events)

    def test_duration_seconds_follow_row_length(self):
        scene = _sample_scene()
        events = build_scene_events(scene)
        melody = next(event for event in events if event.lane_name == "melody" and event.row == 0)
        assert round(melody.duration_seconds, 3) == 0.5

    def test_preserves_extended_lane_voices_except_pad_safety_fallback(self):
        scene = _sample_scene()
        scene.pattern.lanes[1].voice = "tabla_ge"
        scene.pattern.lanes[2].voice = "pad"

        events = build_scene_events(scene)

        assert any(event.lane_name == "foundation" and event.voice == "tabla_ge" for event in events)
        assert any(event.lane_name == "texture" and event.voice == "breath" for event in events)

    def test_quarantines_grain_texture_voice_to_breath(self):
        scene = _sample_scene()
        scene.pattern.lanes[2].voice = "grain"

        events = build_scene_events(scene)

        assert any(event.lane_name == "texture" and event.voice == "breath" for event in events)

    def test_preserves_non_quarantined_extended_texture_voices(self):
        scene = _sample_scene()
        scene.pattern.lanes[2].voice = "choir"

        events = build_scene_events(scene)

        assert any(event.lane_name == "texture" and event.voice == "choir" for event in events)

    def test_spreads_roles_across_a_wider_register_band(self):
        scene = _sample_scene()
        events = build_scene_events(scene)

        bass = next(event for event in events if event.lane_name == "foundation" and event.row == 0)
        melody = next(event for event in events if event.lane_name == "melody" and event.row == 0)
        texture = next(event for event in events if event.lane_name == "texture" and event.row == 0)

        assert bass.frequency_hz < (melody.frequency_hz / 2.5)
        assert texture.frequency_hz > (melody.frequency_hz * 2.5)

    def test_patch_metadata_changes_live_register_profile(self):
        monastery = _sample_scene()
        monastery.metadata["patch_name"] = "house_monastery"
        procession = _sample_scene()
        procession.metadata["patch_name"] = "house_procession"

        monastery_events = build_scene_events(monastery)
        procession_events = build_scene_events(procession)

        monastery_melody = next(event for event in monastery_events if event.lane_name == "melody" and event.row == 0)
        procession_melody = next(event for event in procession_events if event.lane_name == "melody" and event.row == 0)
        monastery_texture = next(event for event in monastery_events if event.lane_name == "texture" and event.row == 0)
        procession_texture = next(event for event in procession_events if event.lane_name == "texture" and event.row == 0)

        assert monastery_melody.frequency_hz < procession_melody.frequency_hz
        assert monastery_texture.frequency_hz <= procession_texture.frequency_hz

    def test_resolves_mood_space_metadata_from_scene_context(self):
        scene = _sample_scene()
        scene.metadata["mood_mode"] = "house-bound"
        scene.metadata["patch_name"] = "house_garden"

        events = build_scene_events(scene)
        profiled_events = [
            event for event in events if event.voice in VOICE_REVERB_PROFILES
        ]
        garden_profile = VOICE_REVERB_PROFILES["tabla_tin"]

        assert profiled_events
        assert any(event.voice != "tabla_tin" for event in profiled_events)
        for event in profiled_events:
            assert event.scene_metadata["mood_mode"] == "house-bound"
            assert event.scene_metadata["patch_name"] == "house_garden"
            assert event.metadata["mood_mode"] == "house-bound"
            assert event.metadata["active_house"] == "house_garden"
            assert event.metadata["render_space_voice"] == "tabla_tin"
            assert event.metadata["render_space_id"] == garden_profile.space_id
            assert event.metadata["render_fx_bus_id"] == str(garden_profile.fx_bus_id)

    def test_keeps_primary_roles_above_live_audibility_floor(self):
        scene = _sample_scene()

        events = build_scene_events(scene)

        melody_peak = max(event.amplitude for event in events if event.role == "melody")
        bass_peak = max(event.amplitude for event in events if event.role == "bass")
        color_peak = max(event.amplitude for event in events if event.role == "color")

        assert melody_peak >= 0.14
        assert bass_peak >= 0.12
        assert color_peak >= 0.02

    def test_sample_events_expose_sample_gesture_metadata_for_journaling(self):
        score = Score(
            phrases=[
                Phrase(
                    notes=[Note(1, 1.0, True), Note(3, 1.0, False), Note(5, 1.0, False)],
                    voice="pluck",
                    dynamic="mf",
                    role="melody",
                ),
                Phrase(
                    notes=[Note(1, 1.0, True), Note(5, 1.0, False), Note(1, 1.0, False)],
                    voice="gong",
                    dynamic="mp",
                    role="bass",
                ),
            ],
            key="C",
            tempo_bpm=118.0,
            mood="active",
            created_at=0.0,
        )
        scene = build_scene_from_score(
            score,
            name="Development",
            allowed_roles=("melody", "bass"),
            rows_per_beat=4,
            max_polyphony=4,
            scene_metadata={
                "sample_gesture_voice": "sample_grain",
                "sample_gesture_source": "room_mic",
                "sample_gesture_mode": "grain_cloud",
                "sample_gesture_transforms": json.dumps(["slice_rearrange", "granular_cloud"]),
                "sample_gesture_density": "0.42",
                "sample_gesture_max_events": "5",
            },
        )

        events = build_scene_events(scene, song_title="Journal Probe")
        sample_event = next(event for event in events if event.role == "sample")

        assert sample_event.song_title == "Journal Probe"
        assert sample_event.metadata["sample_gesture_source"] == "room_mic"
        assert json.loads(sample_event.metadata["sample_gesture_transforms"]) == [
            "slice_rearrange",
            "granular_cloud",
        ]
        assert sample_event.scene_metadata["sample_gesture_mode"] == "grain_cloud"


class TestRuntimeStatePaths:
    def test_tmp_state_path_is_unique_per_call(self, tmp_path):
        target = tmp_path / "tracker_state.json"

        first = _tmp_state_path(target)
        second = _tmp_state_path(target)

        assert first != second
        assert first.parent == target.parent
        assert second.parent == target.parent


class TestScheduleScene:
    def test_emits_events_and_sleep_intervals(self, tmp_path):
        scene = _sample_scene()
        scene.metadata["payoff_focus"] = "primary"
        scene.metadata["section_function"] = "arrival"
        scene.metadata["text_hook"] = "answer the room"
        played = []
        slept = []
        state_path = tmp_path / "tracker_state.json"

        result = schedule_scene(
            scene,
            play_event=played.append,
            sleep_fn=slept.append,
            stop_check=lambda row: False,
            state_path=state_path,
            time_fn=lambda: 1000.0,
            song_title="Test Song",
        )

        assert result.completed is True
        assert result.rows_processed == scene.pattern.rows
        assert result.events_emitted == len(played) == len(build_scene_events(scene))
        assert len(slept) == scene.pattern.rows - 1
        assert all(round(seconds, 3) == 0.125 for seconds in slept)

        runtime_state = json.loads(state_path.read_text())
        assert runtime_state["song_title"] == "Test Song"
        assert runtime_state["scene_name"] == "Theme"
        assert runtime_state["row"] == scene.pattern.rows - 1
        assert "active_lanes" in runtime_state
        assert runtime_state["scene_metadata"]["payoff_focus"] == "primary"
        assert runtime_state["scene_metadata"]["section_function"] == "arrival"
        assert runtime_state["scene_metadata"]["text_hook"] == "answer the room"

    def test_metric_modulation_changes_event_duration_and_row_sleeps_from_target_row(self, tmp_path):
        scene = _sample_scene()
        scene.metric_modulations = [
            MetricModulation(at_row=4, ratio_num=3, ratio_den=2),
        ]
        played = []
        slept = []

        result = schedule_scene(
            scene,
            play_event=played.append,
            sleep_fn=slept.append,
            state_path=tmp_path / "tracker_state.json",
            time_fn=lambda: 1000.0,
        )

        melody_after_modulation = next(
            event for event in played if event.lane_name == "melody" and event.row == 4
        )
        assert result.completed is True
        assert round(melody_after_modulation.duration_seconds, 4) == 0.375
        assert slept[:4] == [0.125, 0.125, 0.125, 0.125]
        assert slept[4:6] == [0.1875, 0.1875]

    def test_can_abort_mid_scene(self, tmp_path):
        scene = _sample_scene()
        played = []

        result = schedule_scene(
            scene,
            play_event=played.append,
            sleep_fn=lambda _seconds: None,
            stop_check=lambda row: row >= 4,
            state_path=tmp_path / "tracker_state.json",
            time_fn=lambda: 2000.0,
        )

        assert result.completed is False
        assert result.rows_processed == 4
        assert all(event.row < 4 for event in played)

    def test_runtime_state_exposes_interpolated_automation(self, tmp_path):
        scene = _sample_scene()
        scene.pattern.automation = [
            AutomationLane(
                name="density",
                default=0.4,
                points=[(0, 0.2), (scene.pattern.rows - 1, 0.8)],
            )
        ]

        schedule_scene(
            scene,
            play_event=lambda _event: None,
            sleep_fn=lambda _seconds: None,
            stop_check=lambda row: row >= scene.pattern.rows // 2,
            state_path=tmp_path / "tracker_state.json",
            time_fn=lambda: 2100.0,
        )

        runtime_state = json.loads((tmp_path / "tracker_state.json").read_text())
        assert runtime_state["automation"]["density"] > 0.2
        assert runtime_state["automation"]["density"] < 0.8

    def test_runtime_state_exposes_current_lead_and_support_roles(self, tmp_path):
        scene = _sample_scene()
        scene.metadata["current_lead_role"] = "theramini"
        scene.metadata["current_support_role"] = "cypherclaw"

        schedule_scene(
            scene,
            play_event=lambda _event: None,
            sleep_fn=lambda _seconds: None,
            stop_check=lambda row: row >= 1,
            state_path=tmp_path / "tracker_state.json",
            time_fn=lambda: 2150.0,
        )

        runtime_state = json.loads((tmp_path / "tracker_state.json").read_text())
        assert runtime_state["scene_metadata"]["current_lead_role"] == "theramini"
        assert runtime_state["scene_metadata"]["current_support_role"] == "cypherclaw"

    def test_row_callback_receives_current_automation(self, tmp_path):
        scene = _sample_scene()
        scene.pattern.automation = [
            AutomationLane(
                name="master_amp",
                default=0.5,
                points=[(0, 0.25), (scene.pattern.rows - 1, 0.75)],
            )
        ]
        seen = []

        schedule_scene(
            scene,
            play_event=lambda _event: None,
            sleep_fn=lambda _seconds: None,
            stop_check=lambda row: row >= 3,
            state_path=tmp_path / "tracker_state.json",
            time_fn=lambda: 2200.0,
            on_row=lambda _scene, row, state: seen.append((row, state["automation"]["master_amp"])),
        )

        assert [row for row, _value in seen] == [0, 1, 2]
        assert seen[0][1] < seen[-1][1]

    def test_low_density_automation_thins_optional_support_events(self, tmp_path):
        scene = _sample_scene()
        scene.pattern.automation = [
            AutomationLane(
                name="density",
                default=0.1,
                points=[(0, 0.1), (scene.pattern.rows - 1, 0.1)],
            )
        ]
        played = []

        result = schedule_scene(
            scene,
            play_event=played.append,
            sleep_fn=lambda _seconds: None,
            state_path=tmp_path / "tracker_state.json",
            time_fn=lambda: 2300.0,
        )

        expected = build_scene_events(scene)
        expected_primary = {
            (event.lane_name, event.row, event.frequency_hz)
            for event in expected
            if event.role in {"melody", "bass"}
        }
        played_primary = {
            (event.lane_name, event.row, event.frequency_hz)
            for event in played
            if event.role in {"melody", "bass"}
        }

        assert result.completed is True
        assert len(played) < len(expected)
        assert expected_primary <= played_primary
        assert sum(1 for event in played if event.role == "color") < sum(
            1 for event in expected if event.role == "color"
        )


class TestScheduleSong:
    def test_runs_all_scenes_and_calls_scene_hook(self, tmp_path):
        scene = _sample_scene()
        song = TrackerSong(title="Suite", scenes=[scene, scene])
        started = []
        played = []

        result = schedule_song(
            song,
            play_event=played.append,
            sleep_fn=lambda _seconds: None,
            stop_check=lambda _scene, _row: False,
            state_path=tmp_path / "tracker_state.json",
            time_fn=lambda: 3000.0,
            on_scene_start=lambda current_scene, _index: started.append(current_scene.name),
        )

        assert result.completed is True
        assert started == ["Theme", "Theme"]
        assert result.events_emitted == len(played) == len(build_scene_events(scene)) * 2


class TestSensorClamping:
    def test_within_bounds_unchanged(self):
        assert _clamp_sensor("sensor_tempo_scale", 1.0) == 1.0
        assert _clamp_sensor("sensor_amp_scale", 0.95) == 0.95
        assert _clamp_sensor("sensor_brightness", 0.5) == 0.5

    def test_clamps_above_upper_bound(self):
        assert _clamp_sensor("sensor_tempo_scale", 1.5) == 1.08
        assert _clamp_sensor("sensor_amp_scale", 2.0) == 1.2
        assert _clamp_sensor("sensor_brightness", 3.0) == 1.0

    def test_clamps_below_lower_bound(self):
        assert _clamp_sensor("sensor_tempo_scale", 0.5) == 0.92
        assert _clamp_sensor("sensor_amp_scale", 0.1) == 0.8
        assert _clamp_sensor("sensor_brightness", -5.0) == -1.0

    def test_at_exact_bounds(self):
        assert _clamp_sensor("sensor_tempo_scale", 0.92) == 0.92
        assert _clamp_sensor("sensor_tempo_scale", 1.08) == 1.08
        assert _clamp_sensor("sensor_amp_scale", 0.80) == 0.80
        assert _clamp_sensor("sensor_amp_scale", 1.20) == 1.20
        assert _clamp_sensor("sensor_brightness", -1.0) == -1.0
        assert _clamp_sensor("sensor_brightness", 1.0) == 1.0

    def test_logs_warning_on_clamp(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            _clamp_sensor("sensor_tempo_scale", 2.0)

        assert "sensor_tempo_scale clamped" in caplog.text

    def test_no_warning_when_within_bounds(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            _clamp_sensor("sensor_tempo_scale", 1.0)

        assert "clamped" not in caplog.text


class TestApplySensorModulation:
    def test_stamps_sensor_values_on_event(self):
        event = ScheduledTrackerEvent(
            song_title="T", scene_name="S", lane_name="melody",
            row=0, voice="pluck", role="melody",
            frequency_hz=440.0, duration_seconds=0.5,
            amplitude=0.16, accent=False,
        )
        modulated = _apply_sensor_modulation(event, {
            "sensor_tempo_scale": 1.04,
            "sensor_amp_scale": 0.90,
            "sensor_brightness": 0.3,
        })
        assert modulated.sensor_tempo_scale == 1.04
        assert modulated.sensor_amp_scale == 0.9
        assert modulated.sensor_brightness == 0.3
        assert modulated.frequency_hz == 440.0

    def test_clamps_out_of_bounds_values(self):
        event = ScheduledTrackerEvent(
            song_title="T", scene_name="S", lane_name="bass",
            row=0, voice="bowed", role="bass",
            frequency_hz=110.0, duration_seconds=1.0,
            amplitude=0.12, accent=True,
        )
        modulated = _apply_sensor_modulation(event, {
            "sensor_tempo_scale": 5.0,
            "sensor_amp_scale": 0.01,
            "sensor_brightness": -9.0,
        })
        assert modulated.sensor_tempo_scale == 1.08
        assert modulated.sensor_amp_scale == 0.80
        assert modulated.sensor_brightness == -1.0

    def test_defaults_for_missing_keys(self):
        event = ScheduledTrackerEvent(
            song_title="T", scene_name="S", lane_name="melody",
            row=0, voice="pluck", role="melody",
            frequency_hz=440.0, duration_seconds=0.5,
            amplitude=0.16, accent=False,
        )
        modulated = _apply_sensor_modulation(event, {})
        assert modulated.sensor_tempo_scale == 1.0
        assert modulated.sensor_amp_scale == 1.0
        assert modulated.sensor_brightness == 0.0


class TestDeltaTrackPersistence:
    def test_write_and_load_roundtrip(self, tmp_path):
        entries = [
            {"row": 0, "lane_name": "melody", "sensor_tempo_scale": 1.02,
             "sensor_amp_scale": 0.95, "sensor_brightness": 0.3},
            {"row": 1, "lane_name": "bass", "sensor_tempo_scale": 0.98,
             "sensor_amp_scale": 1.10, "sensor_brightness": -0.2},
        ]
        path = tmp_path / "delta_track.json"
        write_delta_track(path, entries)
        loaded = load_delta_track(path)
        assert loaded == entries

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "track.json"
        write_delta_track(path, [{"row": 0, "lane_name": "m",
                                   "sensor_tempo_scale": 1.0,
                                   "sensor_amp_scale": 1.0,
                                   "sensor_brightness": 0.0}])
        assert path.exists()
        assert load_delta_track(path)[0]["row"] == 0


class TestReplaySensorFn:
    def test_replays_stored_values(self):
        entries = [
            {"row": 0, "lane_name": "melody", "sensor_tempo_scale": 1.04,
             "sensor_amp_scale": 0.85, "sensor_brightness": 0.7},
            {"row": 2, "lane_name": "bass", "sensor_tempo_scale": 0.96,
             "sensor_amp_scale": 1.15, "sensor_brightness": -0.5},
        ]
        fn = replay_sensor_fn(entries)
        assert fn(0) == {"sensor_tempo_scale": 1.04, "sensor_amp_scale": 0.85,
                         "sensor_brightness": 0.7}
        assert fn(2) == {"sensor_tempo_scale": 0.96, "sensor_amp_scale": 1.15,
                         "sensor_brightness": -0.5}

    def test_returns_neutral_for_missing_rows(self):
        fn = replay_sensor_fn([
            {"row": 0, "lane_name": "melody", "sensor_tempo_scale": 1.04,
             "sensor_amp_scale": 0.85, "sensor_brightness": 0.7},
        ])
        neutral = fn(99)
        assert neutral == _SENSOR_NEUTRAL

    def test_replay_returns_independent_copies(self):
        entries = [
            {"row": 0, "lane_name": "melody", "sensor_tempo_scale": 1.04,
             "sensor_amp_scale": 0.85, "sensor_brightness": 0.7},
        ]
        fn = replay_sensor_fn(entries)
        first = fn(99)
        first["sensor_tempo_scale"] = 999.0
        second = fn(99)
        assert second["sensor_tempo_scale"] == 1.0


class TestScheduleSceneSensorIntegration:
    def test_sensor_fn_stamps_events(self, tmp_path):
        scene = _sample_scene()
        played = []

        def sensor(row):
            return {
                "sensor_tempo_scale": 1.04,
                "sensor_amp_scale": 0.90,
                "sensor_brightness": 0.5,
            }

        schedule_scene(
            scene,
            play_event=played.append,
            sleep_fn=lambda _: None,
            state_path=tmp_path / "state.json",
            time_fn=lambda: 0.0,
            sensor_fn=sensor,
        )

        assert len(played) > 0
        assert all(e.sensor_tempo_scale == 1.04 for e in played)
        assert all(e.sensor_amp_scale == 0.9 for e in played)
        assert all(e.sensor_brightness == 0.5 for e in played)

    def test_no_sensor_fn_uses_neutral_defaults(self, tmp_path):
        scene = _sample_scene()
        played = []

        schedule_scene(
            scene,
            play_event=played.append,
            sleep_fn=lambda _: None,
            state_path=tmp_path / "state.json",
            time_fn=lambda: 0.0,
        )

        assert len(played) > 0
        assert all(e.sensor_tempo_scale == 1.0 for e in played)
        assert all(e.sensor_amp_scale == 1.0 for e in played)
        assert all(e.sensor_brightness == 0.0 for e in played)

    def test_delta_track_persisted_alongside_output(self, tmp_path):
        scene = _sample_scene()
        delta_path = tmp_path / "delta_track.json"

        def sensor(row):
            return {
                "sensor_tempo_scale": 1.0 + (row * 0.001),
                "sensor_amp_scale": 1.0,
                "sensor_brightness": 0.0,
            }

        result = schedule_scene(
            scene,
            play_event=lambda _: None,
            sleep_fn=lambda _: None,
            state_path=tmp_path / "state.json",
            time_fn=lambda: 0.0,
            sensor_fn=sensor,
            delta_track_path=delta_path,
        )

        assert delta_path.exists()
        entries = load_delta_track(delta_path)
        assert len(entries) == result.events_emitted
        assert all("sensor_tempo_scale" in e for e in entries)
        assert all("sensor_amp_scale" in e for e in entries)
        assert all("sensor_brightness" in e for e in entries)
        assert all("row" in e for e in entries)
        assert all("lane_name" in e for e in entries)

    def test_delta_track_replay_produces_same_events(self, tmp_path):
        scene = _sample_scene()
        delta_path = tmp_path / "delta_track.json"

        def sensor(row):
            return {
                "sensor_tempo_scale": 1.02 + (row * 0.001),
                "sensor_amp_scale": 0.95,
                "sensor_brightness": 0.3 - (row * 0.01),
            }

        original_played = []
        schedule_scene(
            scene,
            play_event=original_played.append,
            sleep_fn=lambda _: None,
            state_path=tmp_path / "state.json",
            time_fn=lambda: 0.0,
            sensor_fn=sensor,
            delta_track_path=delta_path,
        )

        entries = load_delta_track(delta_path)
        replay_fn = replay_sensor_fn(entries)
        replayed = []
        schedule_scene(
            scene,
            play_event=replayed.append,
            sleep_fn=lambda _: None,
            state_path=tmp_path / "state2.json",
            time_fn=lambda: 0.0,
            sensor_fn=replay_fn,
        )

        assert len(replayed) == len(original_played)
        for orig, rep in zip(original_played, replayed):
            assert orig.sensor_tempo_scale == rep.sensor_tempo_scale
            assert orig.sensor_amp_scale == rep.sensor_amp_scale
            assert orig.sensor_brightness == rep.sensor_brightness

    def test_delta_track_persisted_on_early_abort(self, tmp_path):
        scene = _sample_scene()
        delta_path = tmp_path / "delta_track.json"

        result = schedule_scene(
            scene,
            play_event=lambda _: None,
            sleep_fn=lambda _: None,
            stop_check=lambda row: row >= 2,
            state_path=tmp_path / "state.json",
            time_fn=lambda: 0.0,
            sensor_fn=lambda row: {
                "sensor_tempo_scale": 1.05,
                "sensor_amp_scale": 1.0,
                "sensor_brightness": 0.0,
            },
            delta_track_path=delta_path,
        )

        assert result.completed is False
        assert delta_path.exists()
        entries = load_delta_track(delta_path)
        assert len(entries) == result.events_emitted
        assert all(e["row"] < 2 for e in entries)

    def test_sensor_values_clamped_in_scheduled_events(self, tmp_path):
        scene = _sample_scene()
        played = []

        schedule_scene(
            scene,
            play_event=played.append,
            sleep_fn=lambda _: None,
            state_path=tmp_path / "state.json",
            time_fn=lambda: 0.0,
            sensor_fn=lambda row: {
                "sensor_tempo_scale": 5.0,
                "sensor_amp_scale": 0.01,
                "sensor_brightness": -99.0,
            },
        )

        assert all(e.sensor_tempo_scale == 1.08 for e in played)
        assert all(e.sensor_amp_scale == 0.80 for e in played)
        assert all(e.sensor_brightness == -1.0 for e in played)


class TestPbindRoundTrip:
    def test_full_event_survives_pbind_round_trip(self):
        event = Event(
            event_id="evt-42",
            phrase_id="phrase-b",
            section_id="bridge",
            voice_id="vln-2",
            role="melody",
            pitch=67,
            nominal_beat=2.0,
            nominal_dur_beats=1.5,
            harmonic_charge=0.4,
            melodic_charge=0.9,
            metric_weight=0.75,
            is_phrase_start=True,
            is_phrase_end=False,
            is_cadential=True,
            intent_tag="build",
            onset_sec=3.5,
            dur_sec=0.8,
            velocity=0.65,
            timing_deviation_ms=-2.0,
            articulation="staccato",
            sensor_tempo_scale=1.03,
            sensor_amp_scale=0.92,
            sensor_brightness=0.4,
            rule_stack=["R2", "R7", "R8"],
            seed_path=(7, 11, 42),
            normalized_phrase_position=0.6,
            normalized_section_position=0.3,
            tempo_mult=1.02,
            amp_mult=0.95,
            contour_apex=0.8,
            contour_apex_index=3,
            is_contour_apex=True,
            metadata={"origin": "tracker", "patch": "monastery"},
        )

        pbind = event_to_pbind_dict(event)
        restored = pbind_dict_to_event(pbind)

        assert restored.event_id == event.event_id
        assert restored.phrase_id == event.phrase_id
        assert restored.section_id == event.section_id
        assert restored.voice_id == event.voice_id
        assert restored.role == event.role
        assert restored.pitch == event.pitch
        assert restored.nominal_beat == event.nominal_beat
        assert restored.nominal_dur_beats == event.nominal_dur_beats
        assert restored.harmonic_charge == event.harmonic_charge
        assert restored.melodic_charge == event.melodic_charge
        assert restored.metric_weight == event.metric_weight
        assert restored.is_phrase_start == event.is_phrase_start
        assert restored.is_phrase_end == event.is_phrase_end
        assert restored.is_cadential == event.is_cadential
        assert restored.intent_tag == event.intent_tag
        assert restored.onset_sec == event.onset_sec
        assert restored.dur_sec == event.dur_sec
        assert restored.velocity == event.velocity
        assert restored.timing_deviation_ms == event.timing_deviation_ms
        assert restored.articulation == event.articulation
        assert restored.sensor_tempo_scale == event.sensor_tempo_scale
        assert restored.sensor_amp_scale == event.sensor_amp_scale
        assert restored.sensor_brightness == event.sensor_brightness
        assert restored.rule_stack == event.rule_stack
        assert restored.seed_path == event.seed_path
        assert restored.normalized_phrase_position == event.normalized_phrase_position
        assert restored.normalized_section_position == event.normalized_section_position
        assert restored.tempo_mult == event.tempo_mult
        assert restored.amp_mult == event.amp_mult
        assert restored.contour_apex == event.contour_apex
        assert restored.contour_apex_index == event.contour_apex_index
        assert restored.is_contour_apex == event.is_contour_apex
        assert restored.metadata == event.metadata

    def test_rule_stack_preserved_as_list(self):
        event = Event(rule_stack=["R1", "R3", "R5"])
        pbind = event_to_pbind_dict(event)
        assert isinstance(pbind["ruleStack"], str)
        assert json.loads(pbind["ruleStack"]) == ["R1", "R3", "R5"]
        restored = pbind_dict_to_event(pbind)
        assert restored.rule_stack == ["R1", "R3", "R5"]

    def test_seed_path_preserved_as_tuple(self):
        event = Event(seed_path=(3, 14, 159))
        pbind = event_to_pbind_dict(event)
        assert isinstance(pbind["seedPath"], str)
        assert json.loads(pbind["seedPath"]) == [3, 14, 159]
        restored = pbind_dict_to_event(pbind)
        assert restored.seed_path == (3, 14, 159)

    def test_none_pitch_round_trips(self):
        event = Event(pitch=None)
        pbind = event_to_pbind_dict(event)
        assert pbind["midinote"] == ""
        restored = pbind_dict_to_event(pbind)
        assert restored.pitch is None

    def test_boolean_fields_encoded_as_int(self):
        event = Event(is_phrase_start=True, is_phrase_end=False, is_cadential=True)
        pbind = event_to_pbind_dict(event)
        assert pbind["phraseStart"] == 1
        assert pbind["phraseEnd"] == 0
        assert pbind["cadential"] == 1

    def test_unknown_pbind_keys_ignored_on_decode(self):
        pbind = event_to_pbind_dict(Event(pitch=60))
        pbind["futureField"] = "ignored"
        restored = pbind_dict_to_event(pbind)
        assert restored.pitch == 60

    def test_empty_event_round_trips(self):
        event = Event()
        restored = pbind_dict_to_event(event_to_pbind_dict(event))
        assert restored.rule_stack == []
        assert restored.seed_path == ()
        assert restored.metadata == {}
        assert restored.pitch is None
