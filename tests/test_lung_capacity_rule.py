from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.music_tracker import (
    SceneConstraint,
    TrackerLane,
    TrackerPattern,
    TrackerScene,
    TrackerSong,
    TrackerStep,
)
from senseweave.render.rules.lung_capacity import (
    DEFAULT_LUNG_CAPACITY_SECONDS,
    LungCapacityRule,
    analyze_lung_capacity,
    apply_lung_capacity,
    lung_capacity_seconds_for_voice,
    summarize_lung_capacity_report,
)


def _step(
    row: int,
    length: int,
    *,
    phrase_id: str,
    velocity: float = 0.8,
    accent: bool = False,
) -> TrackerStep:
    return TrackerStep(
        row=row,
        length_rows=length,
        scale_degree=1,
        velocity=velocity,
        accent=accent,
        metadata={"phrase_id": phrase_id},
    )


def _breath(row: int, length: int) -> TrackerStep:
    return TrackerStep(
        row=row,
        length_rows=length,
        scale_degree=0,
        velocity=0.0,
        metadata={"breath_r6": "true"},
    )


def _scene(
    steps: list[TrackerStep],
    *,
    voice: str = "breath",
    lane_metadata: dict[str, str] | None = None,
) -> TrackerScene:
    lane = TrackerLane(
        name="texture",
        role="color",
        voice=voice,
        steps=steps,
        metadata=lane_metadata or {},
    )
    return TrackerScene(
        name="fixture",
        key="C",
        tempo_bpm=60.0,
        rows_per_beat=1,
        pattern=TrackerPattern(rows=32, lanes=[lane]),
        constraints=SceneConstraint(max_polyphony=1, allowed_roles=("color",)),
        metadata={"groove_meter": "4/4"},
    )


def _lung_breaths(scene: TrackerScene) -> list[TrackerStep]:
    return [
        step
        for step in scene.pattern.lanes[0].steps
        if step.metadata.get("breath_lung_capacity") == "true"
    ]


def test_wind_and_voice_default_to_six_second_capacity() -> None:
    assert lung_capacity_seconds_for_voice("breath", {}) == DEFAULT_LUNG_CAPACITY_SECONDS
    assert lung_capacity_seconds_for_voice("choir", {}) == DEFAULT_LUNG_CAPACITY_SECONDS


def test_non_wind_voice_defaults_to_no_lung_capacity() -> None:
    assert lung_capacity_seconds_for_voice("pluck", {}) is None


def test_lung_capacity_override_is_clamped_to_four_to_eight_seconds() -> None:
    assert lung_capacity_seconds_for_voice("pluck", {"lung_capacity_s": "2"}) == 4.0
    assert lung_capacity_seconds_for_voice("breath", {"lung_capacity_s": "10"}) == 8.0
    assert lung_capacity_seconds_for_voice("choir", {"lung_capacity_s": "null"}) is None


def test_exceeding_capacity_forces_breath_at_next_phrase_boundary() -> None:
    scene = _scene([
        _step(0, 4, phrase_id="p1"),
        _step(4, 3, phrase_id="p2"),
    ])

    rendered = LungCapacityRule().apply(scene, k=1.0, seeds=None, roles=None)

    breaths = _lung_breaths(rendered)
    assert len(breaths) == 1
    assert breaths[0].row == 7
    assert breaths[0].metadata["lung_capacity_s"] == "6.0"


def test_existing_breath_at_boundary_is_reused() -> None:
    scene = _scene([
        _step(0, 4, phrase_id="p1"),
        _step(4, 3, phrase_id="p2"),
        _breath(7, 1),
    ])

    rendered = LungCapacityRule().apply(scene, k=1.0, seeds=None, roles=None)
    out = rendered.pattern.lanes[0].steps

    breaths = _lung_breaths(rendered)
    assert len(out) == 3
    assert len(breaths) == 1
    assert breaths[0].metadata["breath_r6"] == "true"


def test_non_lung_voice_is_unchanged() -> None:
    steps = [
        _step(0, 4, phrase_id="p1"),
        _step(4, 3, phrase_id="p2"),
    ]
    scene = _scene(steps, voice="pluck")

    rendered = LungCapacityRule().apply(scene, k=1.0, seeds=None, roles=None)

    assert rendered.pattern.lanes[0].steps == steps


def test_weak_step_can_become_earlier_breath_when_density_tolerates() -> None:
    scene = _scene(
        [
            _step(0, 3, phrase_id="p1", velocity=0.8, accent=True),
            _step(3, 3, phrase_id="p1", velocity=0.8),
            _step(6, 2, phrase_id="p1", velocity=0.3),
        ],
        lane_metadata={"lung_capacity_s": "6"},
    )

    rendered = LungCapacityRule(internal_breath_max_velocity=0.4).apply(
        scene, k=1.0, seeds=None, roles=None,
    )
    out = rendered.pattern.lanes[0].steps

    assert len(out) == 3
    assert out[2].velocity == 0.0
    assert out[2].scale_degree == 0
    assert out[2].metadata["breath_lung_capacity"] == "true"


# === End-to-end depth-2 coverage (frac-0087) ===


def _lane(
    name: str,
    steps: list[TrackerStep],
    *,
    voice: str = "breath",
    role: str = "color",
    metadata: dict[str, str] | None = None,
) -> TrackerLane:
    return TrackerLane(
        name=name,
        role=role,
        voice=voice,
        steps=steps,
        metadata=metadata or {},
    )


def _multi_lane_scene(lanes: list[TrackerLane], *, name: str = "fixture") -> TrackerScene:
    return TrackerScene(
        name=name,
        key="C",
        tempo_bpm=60.0,
        rows_per_beat=1,
        pattern=TrackerPattern(rows=32, lanes=lanes),
        constraints=SceneConstraint(max_polyphony=1, allowed_roles=("color",)),
        metadata={"groove_meter": "4/4"},
    )


class LungCapacityRuleEndToEndTests:
    """Drive the R11 lung-capacity public surface through one full path."""

    __test__ = True

    def test_scene_analysis_reports_inserted_tagged_and_skipped_lanes(self) -> None:
        insert_lane = _lane(
            "wind_insert",
            [
                _step(0, 4, phrase_id="p1"),
                _step(4, 3, phrase_id="p2"),
            ],
            voice="breath",
        )
        tag_lane = _lane(
            "wind_tag",
            [
                _step(0, 3, phrase_id="p1", velocity=0.8, accent=True),
                _step(3, 3, phrase_id="p1", velocity=0.8),
                _step(6, 2, phrase_id="p1", velocity=0.3),
            ],
            voice="choir",
            metadata={"lung_capacity_s": "6"},
        )
        skipped_lane = _lane(
            "pluck_skip",
            [
                _step(0, 4, phrase_id="p1"),
                _step(4, 3, phrase_id="p2"),
            ],
            voice="pluck",
        )
        scene = _multi_lane_scene([insert_lane, tag_lane, skipped_lane])
        rule = LungCapacityRule(internal_breath_max_velocity=0.4)

        rendered, report = analyze_lung_capacity(scene, rule=rule)
        direct_rendered = rule.apply(
            scene,
            k=1.0,
            seeds={"R11": 99},
            roles=frozenset({"color"}),
        )

        assert rendered == apply_lung_capacity(scene, rule=rule)
        assert direct_rendered == rendered
        assert report.score_kind == "scene"
        assert report.total_inserted == 1
        assert report.total_tagged == 1
        assert len(report.lane_stats) == 3

        inserted_breath = rendered.pattern.lanes[0].steps[2]
        assert inserted_breath.row == 7
        assert inserted_breath.velocity == 0.0
        assert inserted_breath.metadata == {
            "breath_lung_capacity": "true",
            "lung_capacity_s": "6.0",
        }

        tagged_breath = rendered.pattern.lanes[1].steps[2]
        assert tagged_breath.row == 6
        assert tagged_breath.velocity == 0.0
        assert tagged_breath.scale_degree == 0
        assert tagged_breath.metadata["breath_lung_capacity"] == "true"
        assert tagged_breath.metadata["phrase_id"] == "p1"

        assert rendered.pattern.lanes[2].steps == skipped_lane.steps

        wind_insert, wind_tag, pluck_skip = report.lane_stats
        assert wind_insert.lane_name == "wind_insert"
        assert wind_insert.capacity_seconds == 6.0
        assert wind_insert.inserted_breath_count == 1
        assert wind_insert.tagged_breath_count == 0
        assert wind_insert.applies is True

        assert wind_tag.lane_name == "wind_tag"
        assert wind_tag.capacity_seconds == 6.0
        assert wind_tag.inserted_breath_count == 0
        assert wind_tag.tagged_breath_count == 1
        assert wind_tag.applies is True

        assert pluck_skip.lane_name == "pluck_skip"
        assert pluck_skip.capacity_seconds is None
        assert pluck_skip.inserted_breath_count == 0
        assert pluck_skip.tagged_breath_count == 0
        assert pluck_skip.applies is False

        summary = summarize_lung_capacity_report(report)
        assert summary == {
            "score_kind": "scene",
            "total_inserted": 1,
            "total_tagged": 1,
            "lane_count": 3,
            "applied_lane_count": 2,
            "lanes": [
                {
                    "lane_name": "wind_insert",
                    "voice": "breath",
                    "role": "color",
                    "capacity_seconds": 6.0,
                    "inserted_breath_count": 1,
                    "tagged_breath_count": 0,
                    "applies": True,
                },
                {
                    "lane_name": "wind_tag",
                    "voice": "choir",
                    "role": "color",
                    "capacity_seconds": 6.0,
                    "inserted_breath_count": 0,
                    "tagged_breath_count": 1,
                    "applies": True,
                },
                {
                    "lane_name": "pluck_skip",
                    "voice": "pluck",
                    "role": "color",
                    "capacity_seconds": None,
                    "inserted_breath_count": 0,
                    "tagged_breath_count": 0,
                    "applies": False,
                },
            ],
        }
        assert json.loads(json.dumps(summary, sort_keys=True)) == summary

    def test_song_analysis_aggregates_multiple_scenes(self) -> None:
        scene_a = _multi_lane_scene(
            [
                _lane(
                    "winds_a",
                    [
                        _step(0, 4, phrase_id="p1"),
                        _step(4, 3, phrase_id="p2"),
                    ],
                )
            ],
            name="scene_a",
        )
        scene_b = _multi_lane_scene(
            [
                _lane(
                    "winds_b",
                    [
                        _step(0, 4, phrase_id="p1"),
                        _step(4, 3, phrase_id="p2"),
                    ],
                )
            ],
            name="scene_b",
        )
        song = TrackerSong(title="lung_capacity_song", scenes=[scene_a, scene_b])

        rendered, report = analyze_lung_capacity(song, rule=LungCapacityRule())

        assert isinstance(rendered, TrackerSong)
        assert report.score_kind == "song"
        assert report.total_inserted == 2
        assert report.total_tagged == 0
        assert tuple(stat.lane_name for stat in report.lane_stats) == (
            "winds_a",
            "winds_b",
        )
        assert all(stat.applies for stat in report.lane_stats)
