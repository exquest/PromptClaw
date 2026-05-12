"""Depth-2 lung capacity helpers - locked test surface for frac-0016."""
from __future__ import annotations

import dataclasses
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.music_tracker import (  # noqa: E402
    SceneConstraint,
    TrackerLane,
    TrackerPattern,
    TrackerScene,
    TrackerSong,
    TrackerStep,
)
from senseweave.render.rules.lung_capacity import (  # noqa: E402
    LaneBreathStat,
    LungCapacityReport,
    LungCapacityRule,
    analyze_lung_capacity,
    apply_lung_capacity,
    lane_breath_stat,
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


def _lane(
    steps: list[TrackerStep],
    *,
    name: str = "texture",
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


def _scene(
    lanes: list[TrackerLane],
    *,
    name: str = "fixture",
    metadata: dict[str, str] | None = None,
) -> TrackerScene:
    return TrackerScene(
        name=name,
        key="C",
        tempo_bpm=60.0,
        rows_per_beat=1,
        pattern=TrackerPattern(rows=32, lanes=lanes),
        constraints=SceneConstraint(max_polyphony=1, allowed_roles=("color",)),
        metadata=metadata or {"groove_meter": "4/4"},
    )


def _wind_steps_force_insert() -> list[TrackerStep]:
    return [
        _step(0, 4, phrase_id="p1"),
        _step(4, 3, phrase_id="p2"),
    ]


def _wind_steps_internal_tag() -> list[TrackerStep]:
    return [
        _step(0, 3, phrase_id="p1", velocity=0.8, accent=True),
        _step(3, 3, phrase_id="p1", velocity=0.8),
        _step(6, 2, phrase_id="p1", velocity=0.3),
    ]


def test_lane_breath_stat_counts_inserted_and_tagged_breaths() -> None:
    rule = LungCapacityRule()
    original = _lane(_wind_steps_force_insert())
    scene = _scene([original])

    rendered_scene = apply_lung_capacity(scene, k=1.0, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_breath_stat(original, rendered_lane, rule=rule)

    assert isinstance(stat, LaneBreathStat)
    assert getattr(stat, "__dataclass_params__").frozen
    assert dataclasses.is_dataclass(stat)
    assert stat.lane_name == "texture"
    assert stat.voice == "breath"
    assert stat.role == "color"
    assert stat.capacity_seconds == 6.0
    assert stat.inserted_breath_count == 1
    assert stat.tagged_breath_count == 0
    assert stat.applies is True


def test_lane_breath_stat_counts_tagged_internal_breath() -> None:
    rule = LungCapacityRule(internal_breath_max_velocity=0.4)
    original = _lane(
        _wind_steps_internal_tag(),
        metadata={"lung_capacity_s": "6"},
    )
    scene = _scene([original])

    rendered_scene = apply_lung_capacity(scene, k=1.0, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_breath_stat(original, rendered_lane, rule=rule)

    assert stat.inserted_breath_count == 0
    assert stat.tagged_breath_count == 1
    assert stat.applies is True
    assert stat.capacity_seconds == 6.0


def test_lane_breath_stat_marks_non_wind_lane_as_not_applying() -> None:
    rule = LungCapacityRule()
    original = _lane(_wind_steps_force_insert(), voice="pluck")

    stat = lane_breath_stat(original, original, rule=rule)

    assert stat.applies is False
    assert stat.capacity_seconds is None
    assert stat.inserted_breath_count == 0
    assert stat.tagged_breath_count == 0
    assert stat.voice == "pluck"


def test_analyze_lung_capacity_scene_returns_rendered_and_report() -> None:
    rule = LungCapacityRule()
    wind_lane = _lane(_wind_steps_force_insert(), name="winds", voice="breath")
    pluck_lane = _lane(
        _wind_steps_force_insert(),
        name="strings",
        voice="pluck",
    )
    scene = _scene([wind_lane, pluck_lane])

    rendered, report = analyze_lung_capacity(scene, rule=rule)

    expected_rendered = apply_lung_capacity(scene, rule=rule)
    assert rendered == expected_rendered

    assert isinstance(report, LungCapacityReport)
    assert report.score_kind == "scene"
    assert report.total_inserted == 1
    assert report.total_tagged == 0
    assert len(report.lane_stats) == 2

    winds_stat = report.lane_stats[0]
    assert winds_stat.lane_name == "winds"
    assert winds_stat.applies is True
    assert winds_stat.inserted_breath_count == 1
    assert winds_stat.tagged_breath_count == 0
    assert winds_stat.capacity_seconds == 6.0

    strings_stat = report.lane_stats[1]
    assert strings_stat.lane_name == "strings"
    assert strings_stat.applies is False
    assert strings_stat.capacity_seconds is None
    assert strings_stat.inserted_breath_count == 0
    assert strings_stat.tagged_breath_count == 0


def test_analyze_lung_capacity_song_aggregates_scenes() -> None:
    rule = LungCapacityRule()
    scene_a = _scene(
        [_lane(_wind_steps_force_insert(), name="winds_a")],
        name="scene_a",
    )
    scene_b = _scene(
        [_lane(_wind_steps_force_insert(), name="winds_b")],
        name="scene_b",
    )
    song = TrackerSong(title="capacity_song", scenes=[scene_a, scene_b])

    rendered, report = analyze_lung_capacity(song, rule=rule)

    assert isinstance(rendered, TrackerSong)
    assert report.score_kind == "song"
    assert len(report.lane_stats) == 2
    assert report.lane_stats[0].lane_name == "winds_a"
    assert report.lane_stats[1].lane_name == "winds_b"
    assert report.total_inserted == 2
    assert report.total_tagged == 0


def test_analyze_lung_capacity_handles_unsupported_score() -> None:
    rendered, report = analyze_lung_capacity("not-a-score")

    assert rendered == "not-a-score"
    assert report.score_kind == "unsupported"
    assert report.total_inserted == 0
    assert report.total_tagged == 0
    assert report.lane_stats == ()


def test_summarize_lung_capacity_report_returns_json_safe_summary() -> None:
    rule = LungCapacityRule()
    wind_lane = _lane(_wind_steps_force_insert(), name="winds", voice="breath")
    pluck_lane = _lane(
        _wind_steps_force_insert(),
        name="strings",
        voice="pluck",
    )
    scene = _scene([wind_lane, pluck_lane])

    _, report = analyze_lung_capacity(scene, rule=rule)

    summary = summarize_lung_capacity_report(report)

    assert summary == {
        "score_kind": "scene",
        "total_inserted": 1,
        "total_tagged": 0,
        "lane_count": 2,
        "applied_lane_count": 1,
        "lanes": [
            {
                "lane_name": "winds",
                "voice": "breath",
                "role": "color",
                "capacity_seconds": 6.0,
                "inserted_breath_count": 1,
                "tagged_breath_count": 0,
                "applies": True,
            },
            {
                "lane_name": "strings",
                "voice": "pluck",
                "role": "color",
                "capacity_seconds": None,
                "inserted_breath_count": 0,
                "tagged_breath_count": 0,
                "applies": False,
            },
        ],
    }


def test_lung_capacity_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(
        "my-claw/tools/senseweave/render/rules/lung_capacity.py"
    )
    assert result.depth >= 2, result.reason
