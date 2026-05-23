"""Tests for music_tracker.py -- tracker-scene planning around generative scores."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.generative_scores import Note, Phrase, Score
from senseweave.music_tracker import (
    _SCENE_SPATIAL_DEFAULTS,
    build_role_hints_from_cast,
    MetricModulation,
    SceneConstraint,
    build_korsakov_tracker_song,
    build_scene_from_score,
    enrich_score_for_tracker,
    metric_modulated_row_durations_seconds,
    metric_modulated_row_starts_seconds,
    rows_for_beats,
    tracker_form_for_family,
    validate_scene,
)


def _sample_score() -> Score:
    melody = Phrase(
        notes=[Note(1, 1.0, False), Note(3, 0.5, True), Note(5, 1.5, False)],
        voice="pluck",
        dynamic="mf",
        role="melody",
    )
    bass = Phrase(
        notes=[Note(1, 1.0, True), Note(5, 1.0, False), Note(1, 1.0, False)],
        voice="gong",
        dynamic="mp",
        role="bass",
    )
    counter = Phrase(
        notes=[Note(8, 0.5, False), Note(6, 0.5, False), Note(4, 1.0, True)],
        voice="bell",
        dynamic="p",
        role="counter",
    )
    color = Phrase(
        notes=[Note(1, 2.0, False), Note(3, 2.0, False)],
        voice="breath",
        dynamic="pp",
        role="color",
    )
    return Score(
        phrases=[melody, bass, counter, color],
        key="C",
        tempo_bpm=96.0,
        mood="calm",
        created_at=0.0,
    )


def _sparse_score(*, mood: str = "calm", tempo_bpm: float = 56.0) -> Score:
    melody = Phrase(
        notes=[Note(1, 1.5, True), Note(3, 1.0, False), Note(5, 1.5, False)],
        voice="pluck",
        dynamic="mp",
        role="melody",
    )
    return Score(
        phrases=[melody],
        key="C",
        tempo_bpm=tempo_bpm,
        mood=mood,
        created_at=0.0,
    )


class TestRowsForBeats:
    def test_quantizes_to_rows(self):
        assert rows_for_beats(1.0, rows_per_beat=4) == 4
        assert rows_for_beats(0.5, rows_per_beat=4) == 2

    def test_never_returns_zero_rows(self):
        assert rows_for_beats(0.01, rows_per_beat=4) == 1


class TestMetricModulationTiming:
    def test_applies_three_to_two_modulation_from_target_row(self):
        score = _sample_score()
        score.tempo_bpm = 120.0
        scene = build_scene_from_score(
            score,
            name="Theme",
            allowed_roles=("melody",),
            rows_per_beat=4,
            scene_metadata={"groove_lane_phase_offsets": "0,0,0,0,0"},
        )
        scene.metric_modulations = [
            MetricModulation(at_row=4, ratio_num=3, ratio_den=2),
        ]

        row_durations = metric_modulated_row_durations_seconds(scene)
        row_starts = metric_modulated_row_starts_seconds(scene)

        assert row_durations[:4] == [0.125, 0.125, 0.125, 0.125]
        assert row_durations[4:7] == [0.1875, 0.1875, 0.1875]
        assert row_starts[:7] == [
            0.0,
            0.125,
            0.25,
            0.375,
            0.5,
            0.6875,
            0.875,
        ]


class TestBuildSceneFromScore:
    def test_builds_lanes_for_filtered_roles(self):
        scene = build_scene_from_score(
            _sample_score(),
            name="Theme",
            allowed_roles=("melody", "bass", "color"),
            rows_per_beat=4,
            max_polyphony=3,
        )

        lane_names = [lane.name for lane in scene.pattern.lanes]
        assert lane_names == ["melody", "foundation", "texture"]
        assert scene.constraints.allowed_roles == ("melody", "bass", "color")
        assert scene.constraints.max_polyphony == 3

    def test_quantizes_phrase_timing_into_rows(self):
        scene = build_scene_from_score(
            _sample_score(),
            name="Theme",
            allowed_roles=("melody",),
            rows_per_beat=4,
            # Disable default polyrhythmic-cross lane offsets so this test
            # checks raw quantization without phase displacement.
            scene_metadata={"groove_lane_phase_offsets": "0,0,0,0,0"},
        )

        lane = scene.pattern.lanes[0]
        assert [step.row for step in lane.steps] == [0, 4, 6]
        assert [step.length_rows for step in lane.steps] == [4, 2, 6]

    def test_meter_policy_metadata_does_not_change_row_schedule(self):
        scene = build_scene_from_score(
            _sample_score(),
            name="Development",
            allowed_roles=("melody",),
            rows_per_beat=4,
            scene_metadata={
                "arc_phase": "Convergence",
                "transition_metric_ratio": "3:2",
                "groove_lane_phase_offsets": "0,0,0,0,0",
            },
        )

        lane = scene.pattern.lanes[0]
        assert [step.row for step in lane.steps] == [0, 4, 6]
        assert scene.metadata["groove_meter"] == "7/8"
        assert scene.metadata["groove_subdivision"] == "polyrhythmic"
        assert scene.metadata["groove_metric_modulation"] == "3:2"
        assert lane.steps[0].metadata["groove_meter"] == "7/8"
        assert lane.steps[0].metadata["groove_subdivision"] == "polyrhythmic"
        assert lane.steps[0].metadata["groove_phrase_breath"] == "asymmetric"

    def test_adds_default_automation_lanes(self):
        scene = build_scene_from_score(
            _sample_score(),
            name="Theme",
            allowed_roles=("melody",),
            automation_defaults={"density": 0.45, "master_amp": 0.7},
        )

        automation = {lane.name: lane.default for lane in scene.pattern.automation}
        assert automation == {"density": 0.45, "master_amp": 0.7}

    def test_adds_arrangement_automation_curves_from_section_metadata(self):
        scene = build_scene_from_score(
            _sample_score(),
            name="Development",
            allowed_roles=("melody", "bass", "counter", "color"),
            repeat_count=4,
            automation_defaults={"density": 0.6, "master_amp": 0.7, "reverb_send": 0.15},
            scene_metadata={
                "motif_development": "sequence_fragment",
                "rhythm_development": "syncopated_fragment",
            },
        )

        automation = {lane.name: lane for lane in scene.pattern.automation}
        density = automation["density"].points
        master_amp = automation["master_amp"].points

        assert scene.metadata["arrangement_curve"] == "development_rise"
        assert density[0][0] == 0
        assert density[-1][0] == scene.pattern.rows - 1
        assert density[0][1] < density[-1][1]
        assert master_amp[0][1] < master_amp[-1][1]

    def test_adds_sample_gesture_lane_from_scene_metadata(self):
        scene = build_scene_from_score(
            _sample_score(),
            name="Development",
            allowed_roles=("melody", "bass", "counter", "color"),
            repeat_count=4,
            max_polyphony=5,
            scene_metadata={
                "sample_gesture_voice": "sample_grain",
                "sample_gesture_source": "room_mic",
                "sample_gesture_mode": "grain_cloud",
                "sample_gesture_transforms": json.dumps(["slice_rearrange", "granular_cloud"]),
                "sample_gesture_density": "0.42",
                "sample_gesture_max_events": "5",
            },
        )

        sample_lane = next(lane for lane in scene.pattern.lanes if lane.role == "sample")

        assert sample_lane.name == "sample_gesture"
        assert sample_lane.voice == "sample_grain"
        assert scene.constraints.allowed_roles[-1] == "sample"
        assert len(sample_lane.steps) <= 5
        assert all(step.metadata["sample_gesture_mode"] == "grain_cloud" for step in sample_lane.steps)

    def test_arrangement_curve_shapes_step_velocity_without_raising_register(self):
        scene = build_scene_from_score(
            _sample_score(),
            name="Development",
            allowed_roles=("melody", "bass", "counter", "color"),
            repeat_count=4,
            scene_metadata={
                "motif_development": "sequence_fragment",
                "rhythm_development": "syncopated_fragment",
            },
        )

        melody = next(lane for lane in scene.pattern.lanes if lane.role == "melody")
        first = min(melody.steps, key=lambda step: step.row)
        last = max(melody.steps, key=lambda step: step.row)

        assert last.velocity > first.velocity
        assert first.metadata["arrangement_curve"] == "development_rise"
        assert last.metadata["arrangement_position"] == "1.000"
        assert max(step.octave_shift for step in melody.steps) <= 0

    def test_adds_voice_leading_metadata_and_bounds_role_leaps(self):
        leapy = Score(
            phrases=[
                Phrase(
                    notes=[Note(1, 1.0, True), Note(8, 1.0, False), Note(1, 1.0, False)],
                    voice="pluck",
                    dynamic="mf",
                    role="melody",
                ),
                Phrase(
                    notes=[Note(1, 1.0, True), Note(7, 1.0, False), Note(1, 1.0, False)],
                    voice="gong",
                    dynamic="mp",
                    role="bass",
                ),
                Phrase(
                    notes=[Note(8, 1.0, True), Note(1, 1.0, False), Note(3, 1.0, False)],
                    voice="bell",
                    dynamic="p",
                    role="counter",
                ),
                Phrase(
                    notes=[Note(1, 1.0, False), Note(8, 1.0, False), Note(5, 1.0, False)],
                    voice="breath",
                    dynamic="pp",
                    role="color",
                ),
            ],
            key="C",
            tempo_bpm=96.0,
            mood="calm",
            created_at=0.0,
        )

        scene = build_scene_from_score(
            leapy,
            name="Resolution",
            allowed_roles=("melody", "bass", "counter", "color"),
            scene_metadata={
                "cadence_type": "authentic",
                "section_progression": json.dumps([1, 4, 5, 1]),
            },
        )

        assert scene.metadata["cadence_type"] == "authentic"
        for lane in scene.pattern.lanes:
            limit = int(lane.metadata["voice_leading_max_leap"])
            ordered = sorted(lane.steps, key=lambda step: (step.row, step.length_rows))
            assert ordered
            assert lane.metadata["voice_leading"] == "bounded"
            assert all(
                abs(current.scale_degree - previous.scale_degree) <= limit
                for previous, current in zip(ordered, ordered[1:])
            )
            assert all("voice_leading_interval" in step.metadata for step in ordered)
            assert all("guide_tone_degree" in step.metadata for step in ordered)

        final_steps = {
            lane.role: max(lane.steps, key=lambda step: (step.row, step.length_rows))
            for lane in scene.pattern.lanes
        }
        assert final_steps["melody"].scale_degree == 1
        assert final_steps["bass"].scale_degree == 1
        assert final_steps["melody"].metadata["cadence_role"] == "resolution"
        assert final_steps["bass"].metadata["cadence_type"] == "authentic"


class TestValidateScene:
    def test_reports_polyphony_violation(self):
        scene = build_scene_from_score(
            _sample_score(),
            name="TooDense",
            allowed_roles=("melody", "bass", "counter"),
            max_polyphony=1,
        )

        violations = validate_scene(scene)
        assert any("polyphony" in violation for violation in violations)

    def test_reports_disallowed_roles(self):
        scene = build_scene_from_score(
            _sample_score(),
            name="Theme",
            allowed_roles=("melody",),
        )
        scene.constraints = SceneConstraint(max_polyphony=4, allowed_roles=("bass",))

        violations = validate_scene(scene)
        assert any("role" in violation for violation in violations)


class TestBuildKorsakovTrackerSong:
    def test_builds_five_scene_form(self):
        song = build_korsakov_tracker_song(_sample_score(), title="CypherClaw Form")
        assert song.title == "CypherClaw Form"
        assert [scene.name for scene in song.scenes] == [
            "Emergence",
            "Theme",
            "Development",
            "Recap",
            "Resolution",
        ]

    def test_development_is_wider_than_emergence(self):
        song = build_korsakov_tracker_song(_sample_score())
        emergence = song.scenes[0]
        development = song.scenes[2]

        assert emergence.constraints.max_polyphony < development.constraints.max_polyphony
        assert len(emergence.pattern.lanes) < len(development.pattern.lanes)

    def test_resolution_filters_down_to_light_roles(self):
        song = build_korsakov_tracker_song(_sample_score())
        resolution = song.scenes[-1]
        lane_names = [lane.name for lane in resolution.pattern.lanes]
        assert lane_names == ["melody", "texture"]

    def test_subdued_scores_keep_foundation_in_theme_and_development(self):
        subdued = enrich_score_for_tracker(
            _sparse_score(mood="sleeping", tempo_bpm=50.0),
            mood={"energy": 0.05, "valence": 0.56, "arousal": 0.08},
        )
        assert [phrase.role for phrase in subdued.phrases] == ["melody", "color"]

        song = build_korsakov_tracker_song(
            subdued,
            mood={"energy": 0.05, "valence": 0.56, "arousal": 0.08},
        )

        assert [lane.name for lane in song.scenes[0].pattern.lanes] == ["melody"]
        assert [lane.name for lane in song.scenes[1].pattern.lanes] == [
            "melody",
            "foundation",
            "texture",
        ]
        assert [lane.name for lane in song.scenes[2].pattern.lanes] == [
            "melody",
            "foundation",
            "texture",
        ]
        assert [lane.name for lane in song.scenes[-1].pattern.lanes] == [
            "melody",
            "texture",
        ]

    def test_scene_role_floors_do_not_duplicate_existing_foundation(self):
        song = build_korsakov_tracker_song(
            _sample_score(),
            mood={"energy": 0.1, "valence": 0.5, "arousal": 0.1},
        )

        theme_roles = [lane.role for lane in song.scenes[1].pattern.lanes]
        development_roles = [lane.role for lane in song.scenes[2].pattern.lanes]

        assert theme_roles.count("bass") == 1
        assert development_roles.count("bass") == 1

    def test_applies_cast_role_hints_to_scene_floor_lanes(self):
        subdued = enrich_score_for_tracker(
            _sparse_score(mood="sleeping", tempo_bpm=50.0),
            mood={"energy": 0.05, "valence": 0.56, "arousal": 0.08},
        )
        role_hints = {
            "bass": {
                "voice": "gong",
                "character_id": "basalt",
                "character_role": "foundation",
            },
            "color": {
                "voice": "breath",
                "character_id": "weaver",
                "character_role": "texture",
            },
        }

        song = build_korsakov_tracker_song(
            subdued,
            mood={"energy": 0.05, "valence": 0.56, "arousal": 0.08},
            role_hints=role_hints,
        )

        theme = song.scenes[1]
        foundation = next(lane for lane in theme.pattern.lanes if lane.role == "bass")
        texture = next(lane for lane in theme.pattern.lanes if lane.role == "color")

        assert foundation.voice == "gong"
        assert {
            key: foundation.metadata[key]
            for key in ("source", "character_id", "character_role")
        } == {
            "source": "scene_floor",
            "character_id": "basalt",
            "character_role": "foundation",
        }
        assert foundation.metadata["voice_leading"] == "bounded"
        assert foundation.metadata["voice_leading_max_leap"] == "4"
        assert texture.voice == "breath"
        assert {
            key: texture.metadata[key]
            for key in ("source", "character_id", "character_role")
        } == {
            "source": "score",
            "character_id": "weaver",
            "character_role": "texture",
        }
        assert texture.metadata["voice_leading"] == "bounded"
        assert texture.metadata["voice_leading_max_leap"] == "2"

    def test_can_build_song_with_family_form_and_metadata(self):
        family_form = tracker_form_for_family("pulse")
        song = build_korsakov_tracker_song(
            _sample_score(),
            form_templates=family_form,
            family_name="pulse",
        )

        assert song.metadata["family"] == "pulse"

    def test_tracker_form_variant_hint_overrides_song_rotation(self):
        family_form = tracker_form_for_family("bloom", song_num=1, variant_hint="afterglow")

        assert [scene.name for scene in family_form][-1] == "Afterglow"

    def test_can_apply_scene_key_overrides_for_modulation(self):
        song = build_korsakov_tracker_song(
            _sample_score(),
            scene_keys={
                "Emergence": "C",
                "Theme": "C",
                "Development": "G:mixolydian",
                "Recap": "D:dorian",
                "Resolution": "Am",
            },
        )

        assert [scene.key for scene in song.scenes] == [
            "C",
            "C",
            "G:mixolydian",
            "D:dorian",
            "Am",
        ]
        assert song.scenes[2].tempo_bpm > song.scenes[1].tempo_bpm

    def test_preserves_patch_metadata_into_song_and_scenes(self):
        score = _sample_score()
        score.metadata["patch_name"] = "house_monastery"
        score.metadata["section_functions"] = json.dumps({
            "Theme": "tonic",
            "Development": "dominant",
            "Recap": "tonic",
        })
        score.metadata["section_cadences"] = json.dumps({
            "Theme": "half",
            "Development": "deceptive",
            "Recap": "authentic",
        })
        score.metadata["groove_family"] = "lyric"
        score.metadata["text_hook"] = "hold the light"
        score.metadata["repertoire_payoff_scene"] = "Recap"
        score.metadata["repertoire_payoff_bias"] = "0.12"

        song = build_korsakov_tracker_song(score, title="Patch Song")

        assert song.metadata["patch_name"] == "house_monastery"
        assert all(scene.metadata["patch_name"] == "house_monastery" for scene in song.scenes)
        theme = next(scene for scene in song.scenes if scene.name == "Theme")
        assert theme.metadata["section_function"] == "tonic"
        assert theme.metadata["cadence_type"] == "half"
        assert theme.metadata["groove_family"] == "lyric"
        assert theme.metadata["text_hook"] == "hold the light"
        recap = next(scene for scene in song.scenes if scene.name == "Recap")
        assert recap.metadata["payoff_focus"] == "primary"

    def test_emits_meter_trajectory_entries_from_compact_score_metadata(self):
        score = _sample_score()
        score.metadata["meter_trajectory"] = json.dumps(
            {
                "trajectory_id": "meter-arc-song",
                "arc_plan": "arc_phase_drift",
                "arc_phase": "Emergence->Conversation->Convergence",
                "scene_count": 3,
                "meter_path": ["4/4", "15/16", "7/8"],
                "scene_entries": [
                    {
                        "scene_name": "Theme",
                        "index": 0,
                        "scene_count": 3,
                        "meter": "4/4",
                        "subdivision": "straight",
                        "groove_timing": "grid",
                        "phrase_breath": "regular",
                    },
                    {
                        "scene_name": "Development",
                        "index": 1,
                        "scene_count": 3,
                        "meter": "15/16",
                        "subdivision": "polyrhythmic",
                        "groove_timing": "metric_modulation",
                        "phrase_breath": "asymmetric",
                        "metric_modulation": "5:4",
                        "polymeter": [3, 4],
                    },
                    {
                        "scene_name": "Recap",
                        "index": 2,
                        "scene_count": 3,
                        "meter": "7/8",
                        "subdivision": "shuffle",
                        "groove_timing": "push",
                        "phrase_breath": "fractured",
                        "metric_modulation": "3:2",
                    },
                ],
            }
        )

        song = build_korsakov_tracker_song(score, title="Meter Path")

        theme = next(scene for scene in song.scenes if scene.name == "Theme")
        development = next(scene for scene in song.scenes if scene.name == "Development")
        emergence = next(scene for scene in song.scenes if scene.name == "Emergence")
        assert theme.metadata["meter_trajectory_id"] == "meter-arc-song"
        assert theme.metadata["meter_trajectory_scene"] == "Theme"
        assert theme.metadata["meter_trajectory_index"] == "0"
        assert theme.metadata["meter_trajectory_meter"] == "4/4"
        assert json.loads(theme.metadata["meter_trajectory_path"]) == ["4/4", "15/16", "7/8"]
        development_entry = json.loads(development.metadata["meter_trajectory_entry"])
        assert development.metadata["meter_trajectory_meter"] == "15/16"
        assert development.metadata["meter_trajectory_metric_modulation"] == "5:4"
        assert json.loads(development.metadata["meter_trajectory_polymeter"]) == [3, 4]
        assert development_entry["scene_name"] == "Development"
        assert development_entry["meter"] == "15/16"
        assert development_entry["polymeter"] == [3, 4]
        assert "meter_trajectory_entry" not in emergence.metadata

    def test_tracker_metadata_identifies_current_lead_and_support_roles(self):
        score = _sample_score()
        score.metadata["current_lead_role"] = "theramini"
        score.metadata["current_support_role"] = "cypherclaw"

        song = build_korsakov_tracker_song(score, title="Partner Form")
        theme = next(scene for scene in song.scenes if scene.name == "Theme")

        assert song.metadata["current_lead_role"] == "theramini"
        assert song.metadata["current_support_role"] == "cypherclaw"
        assert song.metadata["ensemble_lead_role"] == "theramini"
        assert song.metadata["ensemble_support_role"] == "cypherclaw"
        assert theme.metadata["current_lead_role"] == "theramini"
        assert theme.metadata["current_support_role"] == "cypherclaw"

    def test_recap_reuses_theme_motif_with_answering_resolution(self):
        song = build_korsakov_tracker_song(_sample_score())

        theme = next(scene for scene in song.scenes if scene.name == "Theme")
        recap = next(scene for scene in song.scenes if scene.name == "Recap")

        theme_melody = next(lane for lane in theme.pattern.lanes if lane.role == "melody")
        recap_melody = next(lane for lane in recap.pattern.lanes if lane.role == "melody")

        assert [step.scale_degree for step in theme_melody.steps] == [1, 3, 5]
        assert [step.scale_degree for step in recap_melody.steps] == [1, 3, 1]
        assert recap_melody.metadata["motif_source_scene"] == "Theme"
        assert recap_melody.metadata["motif_transform"] == "answer"

    def test_release_variant_reuses_theme_motif_with_scene_metadata(self):
        song = build_korsakov_tracker_song(
            _sample_score(),
            form_templates=tracker_form_for_family("bloom", song_num=3),
        )

        theme = next(scene for scene in song.scenes if scene.name == "Theme")
        release = next(scene for scene in song.scenes if scene.name == "Release")

        theme_melody = next(lane for lane in theme.pattern.lanes if lane.role == "melody")
        release_melody = next(lane for lane in release.pattern.lanes if lane.role == "melody")

        assert [step.scale_degree for step in release_melody.steps][:2] == [
            step.scale_degree for step in theme_melody.steps
        ][:2]
        assert release_melody.metadata["motif_source_scene"] == "Theme"
        assert release_melody.metadata["motif_transform"] == "answer"

    def test_hook_answer_degrees_shape_late_section_melody_when_present(self):
        score = _sample_score()
        score.metadata["hook_answer_degrees"] = json.dumps([8, 6, 5])
        score.metadata["repertoire_source_title"] = "Quiet Rooms"

        song = build_korsakov_tracker_song(score)

        resolution = next(scene for scene in song.scenes if scene.name == "Resolution")
        melody = next(lane for lane in resolution.pattern.lanes if lane.role == "melody")

        assert melody.steps[0].scale_degree == 8
        assert melody.metadata["hook_phrase_role"] == "answer"
        assert resolution.metadata["hook_phrase_role"] == "answer"
        assert resolution.metadata["repertoire_source_title"] == "Quiet Rooms"


class TestTrackerForms:
    def test_family_forms_shift_density_and_tempo(self):
        nocturne = tracker_form_for_family("nocturne")
        pulse = tracker_form_for_family("pulse")

        assert nocturne[2].tempo_multiplier < pulse[2].tempo_multiplier
        assert nocturne[2].automation_defaults["density"] < pulse[2].automation_defaults["density"]

    def test_song_number_changes_form_shape_and_scene_count(self):
        first = tracker_form_for_family("pulse", song_num=1)
        second = tracker_form_for_family("pulse", song_num=2)
        third = tracker_form_for_family("pulse", song_num=3)

        assert [scene.name for scene in first] != [scene.name for scene in second]
        assert len({len(first), len(second), len(third)}) >= 2

    def test_scene_spatial_defaults_cover_all_template_names(self):
        """Every scene name used in tracker forms has spatial defaults."""
        for family in ("default", "nocturne", "ember", "drift", "bloom", "pulse", "forge"):
            form = tracker_form_for_family(family)
            for template in form:
                assert template.name in _SCENE_SPATIAL_DEFAULTS, (
                    f"Scene '{template.name}' in family '{family}' has no spatial defaults"
                )

    def test_emergence_wider_than_development_in_spatial(self):
        """Opening scenes should have wider stereo than dense development scenes."""
        assert _SCENE_SPATIAL_DEFAULTS["Emergence"]["stereo_width"] > _SCENE_SPATIAL_DEFAULTS["Development"]["stereo_width"]
        assert _SCENE_SPATIAL_DEFAULTS["Emergence"]["depth"] > _SCENE_SPATIAL_DEFAULTS["Development"]["depth"]

    def test_resolution_has_delay_send(self):
        """Resolution / closing scenes should expose delay sends."""
        assert _SCENE_SPATIAL_DEFAULTS["Resolution"]["delay_send"] > 0.0
        assert _SCENE_SPATIAL_DEFAULTS["Afterglow"]["delay_send"] > 0.0

    def test_form_variants_change_scene_length_multiplier(self):
        first = tracker_form_for_family("bloom", song_num=1)
        second = tracker_form_for_family("bloom", song_num=4)

        assert [scene.length_multiplier for scene in first] != [
            scene.length_multiplier for scene in second
        ]


class TestEnrichScoreForTracker:
    def test_adds_foundation_and_texture_to_sparse_calm_score(self):
        enriched = enrich_score_for_tracker(
            _sparse_score(),
            mood={"energy": 0.18, "valence": 0.62, "arousal": 0.22},
        )

        roles = [phrase.role for phrase in enriched.phrases]
        assert roles == ["melody", "bass", "color"]

        theme = build_korsakov_tracker_song(enriched).scenes[1]
        assert [lane.name for lane in theme.pattern.lanes] == [
            "melody",
            "foundation",
            "texture",
        ]

    def test_adds_counter_in_higher_energy_states(self):
        enriched = enrich_score_for_tracker(
            _sparse_score(mood="energetic", tempo_bpm=118.0),
            mood={"energy": 0.82, "valence": 0.71, "arousal": 0.78},
        )

        roles = [phrase.role for phrase in enriched.phrases]
        assert roles == ["melody", "bass", "counter", "color"]

        development = build_korsakov_tracker_song(enriched).scenes[2]
        assert [lane.role for lane in development.pattern.lanes] == [
            "melody",
            "bass",
            "counter",
            "color",
        ]

    def test_preserves_existing_roles_without_duplication(self):
        enriched = enrich_score_for_tracker(
            _sample_score(),
            mood={"energy": 0.65, "valence": 0.5, "arousal": 0.61},
        )

        assert [phrase.role for phrase in enriched.phrases] == [
            "melody",
            "bass",
            "counter",
            "color",
        ]


class TestBuildRoleHintsFromCast:
    def test_maps_cast_roles_to_tracker_roles(self):
        cast = [
            {"id": "poet", "role": "melody", "synth": "sw_pluck"},
            {"id": "basalt", "role": "foundation", "synth": "sw_gong"},
            {"id": "weaver", "role": "texture", "synth": "sw_breath"},
            {"id": "navigator", "role": "harmony", "synth": "sw_bowed"},
        ]

        hints = build_role_hints_from_cast(
            cast,
            synth_voice_map={
                "sw_pluck": "pluck",
                "sw_gong": "gong",
                "sw_breath": "breath",
                "sw_bowed": "bowed",
            },
        )

        assert hints == {
            "melody": {
                "voice": "pluck",
                "character_id": "poet",
                "character_role": "melody",
            },
            "bass": {
                "voice": "gong",
                "character_id": "basalt",
                "character_role": "foundation",
            },
            "color": {
                "voice": "breath",
                "character_id": "weaver",
                "character_role": "texture",
            },
            "counter": {
                "voice": "bowed",
                "character_id": "navigator",
                "character_role": "harmony",
            },
        }

    def test_falls_back_to_related_cast_roles_when_foundation_missing(self):
        cast = [
            {"id": "conductor", "role": "harmony", "synth": "sw_bowed"},
            {"id": "heartbeat", "role": "rhythm", "synth": "sw_gong"},
        ]

        hints = build_role_hints_from_cast(
            cast,
            synth_voice_map={
                "sw_bowed": "bowed",
                "sw_gong": "gong",
            },
        )

        assert hints["bass"] == {
            "voice": "gong",
            "character_id": "heartbeat",
            "character_role": "rhythm",
        }
        assert hints["counter"] == {
            "voice": "bowed",
            "character_id": "conductor",
            "character_role": "harmony",
        }

    def test_maps_extended_tracker_instruments_and_support_roles(self):
        cast = [
            {"id": "pulse", "role": "rhythm", "synth": "sw_tabla_ge"},
            {"id": "archive", "role": "counter_melody", "synth": "sw_metal"},
            {"id": "skin", "role": "texture", "synth": "sw_grain"},
            {"id": "stone", "role": "foundation", "synth": "sw_pad"},
        ]

        hints = build_role_hints_from_cast(
            cast,
            synth_voice_map={
                "sw_tabla_ge": "tabla_ge",
                "sw_metal": "metal",
                "sw_grain": "grain",
                "sw_pad": "pad",
            },
        )

        assert hints["bass"] == {
            "voice": "bowed",
            "character_id": "stone",
            "character_role": "foundation",
        }
        assert hints["counter"] == {
            "voice": "metal",
            "character_id": "archive",
            "character_role": "counter_melody",
        }
        assert hints["color"] == {
            "voice": "grain",
            "character_id": "skin",
            "character_role": "texture",
        }

    def test_normalizes_ringing_color_and_pad_counter_voices(self):
        cast = [
            {"id": "gallery", "role": "color", "synth": "sw_metal"},
            {"id": "room", "role": "foundation", "synth": "sw_pad"},
            {"id": "chorus", "role": "harmony", "synth": "sw_pad"},
            {"id": "poet", "role": "melody", "synth": "sw_pluck"},
        ]

        hints = build_role_hints_from_cast(
            cast,
            synth_voice_map={
                "sw_metal": "metal",
                "sw_pad": "pad",
                "sw_pluck": "pluck",
            },
        )

        assert hints["bass"] == {
            "voice": "bowed",
            "character_id": "room",
            "character_role": "foundation",
        }
        assert hints["color"] == {
            "voice": "breath",
            "character_id": "gallery",
            "character_role": "color",
        }
        assert hints["counter"] == {
            "voice": "choir",
            "character_id": "chorus",
            "character_role": "harmony",
        }

    def test_softens_chirpy_wind_down_cast_voices(self):
        cast = [
            {"id": "pebble", "role": "melody", "synth": "sw_pluck"},
            {"id": "heartbeat", "role": "rhythm", "synth": "sw_kotekan"},
            {"id": "skin", "role": "texture", "synth": "sw_grain"},
            {"id": "chorus", "role": "harmony", "synth": "sw_choir"},
        ]

        hints = build_role_hints_from_cast(
            cast,
            synth_voice_map={
                "sw_pluck": "pluck",
                "sw_kotekan": "kotekan",
                "sw_grain": "grain",
                "sw_choir": "choir",
            },
            cadence_state="wind_down",
        )

        assert hints["melody"] == {
            "voice": "bowed",
            "character_id": "pebble",
            "character_role": "melody",
        }
        assert hints["bass"] == {
            "voice": "bowed",
            "character_id": "heartbeat",
            "character_role": "rhythm",
        }
        assert hints["color"] == {
            "voice": "breath",
            "character_id": "skin",
            "character_role": "texture",
        }
        assert hints["counter"] == {
            "voice": "choir",
            "character_id": "chorus",
            "character_role": "harmony",
        }

    def test_applies_western_patch_to_normal_occupied_cast(self):
        cast = [
            {"id": "window", "role": "melody", "synth": "sw_bell"},
            {"id": "heartbeat", "role": "rhythm", "synth": "sw_tabla_tin"},
            {"id": "gallery", "role": "color", "synth": "sw_metal"},
            {"id": "archive", "role": "counter_melody", "synth": "sw_kotekan"},
        ]

        hints = build_role_hints_from_cast(
            cast,
            synth_voice_map={
                "sw_bell": "bell",
                "sw_tabla_tin": "tabla_tin",
                "sw_metal": "metal",
                "sw_kotekan": "kotekan",
            },
            cadence_state="occupied_day",
            family_name="pulse",
        )

        assert hints["melody"]["voice"] == "pluck"
        assert hints["bass"]["voice"] == "pluck"
        assert hints["color"]["voice"] == "breath"
        assert hints["counter"]["voice"] == "pluck"

    def test_experimental_patch_preserves_non_western_cast_voices(self):
        cast = [
            {"id": "pulse", "role": "rhythm", "synth": "sw_tabla_tin"},
            {"id": "archive", "role": "counter_melody", "synth": "sw_metal"},
            {"id": "eye", "role": "melody", "synth": "sw_kotekan"},
            {"id": "skin", "role": "texture", "synth": "sw_grain"},
        ]

        hints = build_role_hints_from_cast(
            cast,
            synth_voice_map={
                "sw_tabla_tin": "tabla_tin",
                "sw_metal": "metal",
                "sw_kotekan": "kotekan",
                "sw_grain": "grain",
            },
            cadence_state="away_practice",
            family_name="forge",
        )

        assert hints["melody"]["voice"] == "kotekan"
        assert hints["bass"]["voice"] == "tabla_tin"
        assert hints["counter"]["voice"] == "choir"
        assert hints["color"]["voice"] == "breath"
