"""Tests for counterpoint_relation metadata wiring through the score/tracker pipeline.

Covers the three acceptance criteria:
  1. Independent lane contours
  2. Staggered climaxes
  3. No lane crowding (register separation)
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.arrangement_engine import RegisterBand
from senseweave.counterpoint_rules import COUNTERPOINT_REGISTRY, resolve_rule
from senseweave.generative_scores import Note, Phrase, Score
from senseweave.music_tracker import (
    _COUNTERPOINT_RELATION_TO_RULE_ID,
    _counterpoint_metadata_for_lane,
    _lane_activity,
    _lane_contour,
    _lane_register_band,
    _resolve_counterpoint_rule_id,
    TrackerLane,
    TrackerStep,
    build_scene_from_score,
    validate_scene_counterpoint,
)


# === Fixtures ===


def _multi_voice_score(*, counterpoint_relation: str = "") -> Score:
    melody = Phrase(
        notes=[Note(5, 1.0, False), Note(6, 0.5, True), Note(7, 1.0, False), Note(8, 0.5, False)],
        voice="pluck",
        dynamic="mf",
        role="melody",
    )
    bass = Phrase(
        notes=[Note(1, 1.0, False), Note(5, 1.0, False), Note(3, 1.0, True)],
        voice="gong",
        dynamic="mp",
        role="bass",
    )
    counter = Phrase(
        notes=[Note(8, 0.5, True), Note(6, 0.5, False), Note(4, 0.5, False), Note(3, 0.5, False)],
        voice="bell",
        dynamic="p",
        role="counter",
    )
    color = Phrase(
        notes=[Note(1, 2.0, False), Note(3, 2.0, False), Note(5, 2.0, True)],
        voice="breath",
        dynamic="pp",
        role="color",
    )
    metadata: dict[str, str] = {}
    if counterpoint_relation:
        metadata["production_counterpoint_relation"] = counterpoint_relation
    return Score(
        phrases=[melody, bass, counter, color],
        key="C",
        tempo_bpm=96.0,
        mood="calm",
        created_at=0.0,
        metadata=metadata,
    )


def _build_scene(counterpoint_relation: str = "", *, name: str = "Development") -> object:
    score = _multi_voice_score(counterpoint_relation=counterpoint_relation)
    # Counterpoint tests probe note-pitch relationships, not lane timing.
    # Disable polyrhythmic-cross default lane offsets so climax-stagger and
    # contour-lock checks see the raw quantization grid.
    scene_metadata: dict[str, str] = {"groove_lane_phase_offsets": "0,0,0,0,0"}
    if counterpoint_relation:
        scene_metadata["production_counterpoint_relation"] = counterpoint_relation
    return build_scene_from_score(
        score,
        name=name,
        allowed_roles=("bass", "melody", "counter", "color"),
        rows_per_beat=4,
        max_polyphony=5,
        scene_metadata=scene_metadata,
    )


# === Counterpoint relation mapping ===


class TestCounterpointRelationMapping:
    def test_all_production_course_values_map_to_valid_rule_ids(self) -> None:
        for relation, rule_id in _COUNTERPOINT_RELATION_TO_RULE_ID.items():
            assert rule_id in COUNTERPOINT_REGISTRY, (
                f"production course value {relation!r} maps to unknown rule {rule_id!r}"
            )

    def test_resolve_known_values(self) -> None:
        assert _resolve_counterpoint_rule_id("contrary_motion") == "contrary"
        assert _resolve_counterpoint_rule_id("oblique_pedal") == "oblique"
        assert _resolve_counterpoint_rule_id("parallel_thirds") == "parallel"
        assert _resolve_counterpoint_rule_id("imitative_canon") == "echo"
        assert _resolve_counterpoint_rule_id("unison_shadow") == "parallel"

    def test_unknown_value_falls_back_to_parallel(self) -> None:
        assert _resolve_counterpoint_rule_id("unknown_relation") == "parallel"
        assert _resolve_counterpoint_rule_id("") == "parallel"


# === Metadata propagation ===


class TestCounterpointMetadataPropagation:
    def test_lane_metadata_contains_counterpoint_fields(self) -> None:
        meta = _counterpoint_metadata_for_lane("contrary_motion", "melody")
        assert meta["counterpoint_relation"] == "contrary_motion"
        assert meta["counterpoint_rule_id"] == "contrary"
        assert "counterpoint_max_leap" in meta
        assert "counterpoint_preferred_intervals" in meta
        assert "counterpoint_allow_parallel_fifths" in meta
        assert "counterpoint_allow_unison" in meta

    def test_max_leap_matches_registry(self) -> None:
        meta = _counterpoint_metadata_for_lane("contrary_motion", "melody")
        rule = resolve_rule("contrary")
        assert meta["counterpoint_max_leap"] == str(rule.intervals.max_leap)

    def test_preferred_intervals_are_json(self) -> None:
        meta = _counterpoint_metadata_for_lane("parallel_thirds", "bass")
        intervals = json.loads(meta["counterpoint_preferred_intervals"])
        assert isinstance(intervals, list)
        assert all(isinstance(i, int) for i in intervals)

    def test_scene_lanes_carry_counterpoint_metadata(self) -> None:
        scene = _build_scene("contrary_motion")
        for lane in scene.pattern.lanes:
            assert lane.metadata.get("counterpoint_relation") == "contrary_motion"
            assert lane.metadata.get("counterpoint_rule_id") == "contrary"

    def test_scene_without_counterpoint_has_no_metadata(self) -> None:
        scene = _build_scene("")
        for lane in scene.pattern.lanes:
            assert "counterpoint_relation" not in lane.metadata
            assert "counterpoint_rule_id" not in lane.metadata

    def test_each_production_value_wires_correct_rule(self) -> None:
        for relation, expected_rule_id in _COUNTERPOINT_RELATION_TO_RULE_ID.items():
            scene = _build_scene(relation)
            for lane in scene.pattern.lanes:
                assert lane.metadata["counterpoint_rule_id"] == expected_rule_id, (
                    f"{relation} should wire to {expected_rule_id} "
                    f"but got {lane.metadata['counterpoint_rule_id']}"
                )


# === Acceptance criterion 1: Independent lane contours ===


class TestIndependentLaneContours:
    def test_multi_voice_scene_has_independent_contours(self) -> None:
        scene = _build_scene("contrary_motion")
        violations = validate_scene_counterpoint(scene)
        contour_violations = [v for v in violations if "locked contours" in v]
        assert not contour_violations, f"Expected independent contours: {contour_violations}"

    def test_contour_extraction_returns_scale_degrees(self) -> None:
        steps = [
            TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.7),
            TrackerStep(row=4, length_rows=4, scale_degree=3, velocity=0.6),
            TrackerStep(row=8, length_rows=4, scale_degree=5, velocity=0.7),
        ]
        lane = TrackerLane(name="melody", role="melody", voice="pluck", steps=steps)
        contour = _lane_contour(lane)
        assert contour == [1.0, 3.0, 5.0]

    def test_contour_skips_rest_degrees(self) -> None:
        steps = [
            TrackerStep(row=0, length_rows=4, scale_degree=3, velocity=0.7),
            TrackerStep(row=4, length_rows=4, scale_degree=0, velocity=0.0),
            TrackerStep(row=8, length_rows=4, scale_degree=5, velocity=0.7),
        ]
        lane = TrackerLane(name="melody", role="melody", voice="pluck", steps=steps)
        contour = _lane_contour(lane)
        assert contour == [3.0, 5.0]

    def test_locked_contours_detected(self) -> None:
        melody_steps = [
            TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.7),
            TrackerStep(row=4, length_rows=4, scale_degree=3, velocity=0.7),
            TrackerStep(row=8, length_rows=4, scale_degree=5, velocity=0.7),
        ]
        bass_steps = [
            TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.5),
            TrackerStep(row=4, length_rows=4, scale_degree=3, velocity=0.5),
            TrackerStep(row=8, length_rows=4, scale_degree=5, velocity=0.5),
        ]
        from senseweave.music_tracker import TrackerPattern, TrackerScene, SceneConstraint
        scene = TrackerScene(
            name="Test",
            key="C",
            tempo_bpm=96.0,
            rows_per_beat=4,
            pattern=TrackerPattern(
                rows=12,
                lanes=[
                    TrackerLane(name="melody", role="melody", voice="pluck", steps=melody_steps),
                    TrackerLane(name="foundation", role="bass", voice="gong", steps=bass_steps),
                ],
            ),
            constraints=SceneConstraint(max_polyphony=3, allowed_roles=("melody", "bass")),
        )
        violations = validate_scene_counterpoint(scene)
        assert any("locked contours" in v for v in violations)


# === Acceptance criterion 2: Staggered climaxes ===


class TestStaggeredClimaxes:
    def test_multi_voice_scene_has_staggered_climaxes(self) -> None:
        scene = _build_scene("parallel_thirds")
        violations = validate_scene_counterpoint(scene)
        climax_violations = [v for v in violations if "not staggered" in v]
        assert not climax_violations, f"Expected staggered climaxes: {climax_violations}"

    def test_activity_extraction_normalises_time(self) -> None:
        steps = [
            TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.5),
            TrackerStep(row=4, length_rows=4, scale_degree=3, velocity=0.8),
            TrackerStep(row=8, length_rows=4, scale_degree=5, velocity=0.6),
        ]
        lane = TrackerLane(name="melody", role="melody", voice="pluck", steps=steps)
        activity = _lane_activity(lane, total_rows=12)
        assert len(activity) == 3
        assert activity[0] == (0.0, 0.5)
        assert abs(activity[1][0] - 1 / 3) < 0.01
        assert activity[1][1] == 0.8

    def test_concurrent_peaks_detected(self) -> None:
        from senseweave.music_tracker import TrackerPattern, TrackerScene, SceneConstraint
        melody_steps = [
            TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.5),
            TrackerStep(row=4, length_rows=4, scale_degree=3, velocity=0.9),
        ]
        bass_steps = [
            TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.5),
            TrackerStep(row=4, length_rows=4, scale_degree=3, velocity=0.9),
        ]
        scene = TrackerScene(
            name="Test",
            key="C",
            tempo_bpm=96.0,
            rows_per_beat=4,
            pattern=TrackerPattern(
                rows=8,
                lanes=[
                    TrackerLane(name="melody", role="melody", voice="pluck", steps=melody_steps),
                    TrackerLane(name="foundation", role="bass", voice="gong", steps=bass_steps),
                ],
            ),
            constraints=SceneConstraint(max_polyphony=3, allowed_roles=("melody", "bass")),
        )
        violations = validate_scene_counterpoint(scene)
        assert any("not staggered" in v for v in violations)


# === Acceptance criterion 3: No lane crowding ===


class TestNoLaneCrowding:
    def test_multi_voice_scene_no_crowding(self) -> None:
        scene = _build_scene("oblique_pedal")
        violations = validate_scene_counterpoint(scene)
        crowding_violations = [v for v in violations if "crowding" in v]
        assert not crowding_violations, f"Expected no crowding: {crowding_violations}"

    def test_register_band_extraction(self) -> None:
        steps = [
            TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.7),
            TrackerStep(row=4, length_rows=4, scale_degree=5, velocity=0.6),
        ]
        lane = TrackerLane(name="melody", role="melody", voice="pluck", steps=steps)
        band = _lane_register_band(lane)
        assert band is not None
        assert band.voice == "melody"
        assert band.low_midi < band.high_midi

    def test_register_band_none_for_empty_lane(self) -> None:
        lane = TrackerLane(name="melody", role="melody", voice="pluck", steps=[])
        band = _lane_register_band(lane)
        assert band is None

    def test_bass_register_lower_than_melody(self) -> None:
        bass_steps = [TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.5)]
        melody_steps = [TrackerStep(row=0, length_rows=4, scale_degree=1, velocity=0.7)]
        bass_lane = TrackerLane(name="foundation", role="bass", voice="gong", steps=bass_steps)
        melody_lane = TrackerLane(name="melody", role="melody", voice="pluck", steps=melody_steps)
        bass_band = _lane_register_band(bass_lane)
        melody_band = _lane_register_band(melody_lane)
        assert bass_band is not None
        assert melody_band is not None
        assert bass_band.low_midi < melody_band.low_midi

    def test_crowding_detected_for_overlapping_bands(self) -> None:
        from senseweave.arrangement_engine import register_crowding_detected
        bands = [
            RegisterBand(voice="melody", low_midi=60, high_midi=72),
            RegisterBand(voice="counter", low_midi=60, high_midi=72),
        ]
        assert register_crowding_detected(bands)


# === Integration: full scene with counterpoint relation ===


class TestIntegrationCounterpointScene:
    def test_all_relations_wire_metadata_to_lanes(self) -> None:
        for relation in _COUNTERPOINT_RELATION_TO_RULE_ID:
            scene = _build_scene(relation, name="Development")
            note_lanes = [lane for lane in scene.pattern.lanes if lane.role != "sample"]
            assert len(note_lanes) >= 2, f"Expected multiple lanes for {relation}"
            for lane in note_lanes:
                assert lane.metadata["counterpoint_relation"] == relation
                assert lane.metadata["counterpoint_rule_id"] == _COUNTERPOINT_RELATION_TO_RULE_ID[relation]

    def test_scene_metadata_includes_counterpoint_relation(self) -> None:
        scene = _build_scene("contrary_motion", name="Development")
        assert scene.metadata.get("production_counterpoint_relation") == "contrary_motion"

    def test_validation_returns_list(self) -> None:
        scene = _build_scene("contrary_motion", name="Development")
        violations = validate_scene_counterpoint(scene)
        assert isinstance(violations, list)

    def test_single_lane_scene_skips_counterpoint_validation(self) -> None:
        score = Score(
            phrases=[Phrase(
                notes=[Note(1, 1.0, True), Note(3, 0.5, False)],
                voice="pluck",
                dynamic="mf",
                role="melody",
            )],
            key="C",
            tempo_bpm=96.0,
            mood="calm",
            created_at=0.0,
        )
        scene = build_scene_from_score(
            score,
            name="Afterglow",
            allowed_roles=("melody",),
            rows_per_beat=4,
            max_polyphony=1,
        )
        violations = validate_scene_counterpoint(scene)
        assert violations == []

    def test_no_register_crowding_across_default_role_bands(self) -> None:
        scene = _build_scene("parallel_thirds", name="Theme")
        violations = validate_scene_counterpoint(scene)
        crowding = [v for v in violations if "crowding" in v]
        assert not crowding, f"Default role registers should not crowd: {crowding}"

    def test_contour_validation_runs_on_multi_lane_scene(self) -> None:
        scene = _build_scene("contrary_motion", name="Development")
        violations = validate_scene_counterpoint(scene)
        contour_or_none = [v for v in violations if "locked contours" in v]
        assert isinstance(contour_or_none, list)
