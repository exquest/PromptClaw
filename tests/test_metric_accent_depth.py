"""Depth-2 metric accent helpers - locked test surface for frac-0017."""
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
from senseweave.render.rules.metric_accent import (  # noqa: E402
    LaneMetricAccentStat,
    MetricAccentReport,
    MetricAccentRule,
    analyze_metric_accent,
    apply_metric_accent,
    lane_metric_accent_stat,
    summarize_metric_accent_report,
)


def _steps(count: int = 16, *, velocity: float = 0.5) -> list[TrackerStep]:
    return [
        TrackerStep(row=row, length_rows=1, scale_degree=1, velocity=velocity)
        for row in range(count)
    ]


def _lane(
    role: str,
    *,
    name: str | None = None,
    steps: list[TrackerStep] | None = None,
    metadata: dict[str, str] | None = None,
) -> TrackerLane:
    return TrackerLane(
        name=name or role,
        role=role,
        voice="pluck",
        steps=steps or _steps(),
        metadata=metadata or {},
    )


def _scene(
    lanes: list[TrackerLane],
    *,
    meter: str = "4/4",
    name: str = "fixture",
    rows: int = 16,
) -> TrackerScene:
    return TrackerScene(
        name=name,
        key="C",
        tempo_bpm=120.0,
        rows_per_beat=4,
        pattern=TrackerPattern(rows=rows, lanes=lanes),
        constraints=SceneConstraint(max_polyphony=1, allowed_roles=("melody",)),
        metadata={"groove_meter": meter},
    )


def test_lane_metric_accent_stat_reports_melody_shaping() -> None:
    rule = MetricAccentRule()
    original = _lane("melody")
    scene = _scene([original])

    rendered_scene = apply_metric_accent(scene, k=1.0, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_metric_accent_stat(
        original,
        rendered_lane,
        meter="4/4",
        rule=rule,
    )

    assert isinstance(stat, LaneMetricAccentStat)
    assert dataclasses.is_dataclass(stat)
    assert getattr(stat, "__dataclass_params__").frozen
    assert stat.lane_name == "melody"
    assert stat.role == "melody"
    assert stat.meter == "4/4"
    assert stat.step_count == 16
    assert stat.shaped_step_count == 15
    assert stat.mean_multiplier == 0.866
    assert stat.strongest_row == 0
    assert stat.applies is True


def test_lane_metric_accent_stat_marks_non_melodic_lane_as_not_applying() -> None:
    rule = MetricAccentRule()
    original = _lane("ostinato")

    stat = lane_metric_accent_stat(
        original,
        original,
        meter="4/4",
        rule=rule,
    )

    assert stat.applies is False
    assert stat.shaped_step_count == 0
    assert stat.mean_multiplier == 1.0
    assert stat.lane_name == "ostinato"
    assert stat.role == "ostinato"


def test_lane_metric_accent_stat_marks_grid_locked_lane_as_not_applying() -> None:
    rule = MetricAccentRule()
    original = _lane("melody", metadata={"grid_locked": "true"})
    scene = _scene([original])

    rendered_scene = apply_metric_accent(scene, k=1.0, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_metric_accent_stat(
        original,
        rendered_lane,
        meter="4/4",
        rule=rule,
    )

    assert stat.applies is False
    assert stat.shaped_step_count == 0
    assert stat.mean_multiplier == 1.0
    assert stat.strongest_row == 0


def test_analyze_metric_accent_scene_returns_rendered_and_report() -> None:
    rule = MetricAccentRule()
    scene = _scene([_lane("melody"), _lane("ostinato")])

    rendered, report = analyze_metric_accent(scene, rule=rule)

    assert rendered == apply_metric_accent(scene, rule=rule)
    assert isinstance(report, MetricAccentReport)
    assert report.score_kind == "scene"
    assert report.total_shaped_steps == 15
    assert len(report.lane_stats) == 2
    assert report.lane_stats[0].lane_name == "melody"
    assert report.lane_stats[0].applies is True
    assert report.lane_stats[0].shaped_step_count == 15
    assert report.lane_stats[1].lane_name == "ostinato"
    assert report.lane_stats[1].applies is False
    assert report.lane_stats[1].shaped_step_count == 0


def test_analyze_metric_accent_song_aggregates_scene_meters() -> None:
    rule = MetricAccentRule()
    scene_a = _scene(
        [_lane("melody", name="triple", steps=_steps(12))],
        meter="3/4",
        name="scene_a",
        rows=12,
    )
    scene_b = _scene(
        [_lane("melody", name="compound", steps=_steps(12))],
        meter="6/8",
        name="scene_b",
        rows=12,
    )
    song = TrackerSong(title="metric_song", scenes=[scene_a, scene_b])

    rendered, report = analyze_metric_accent(song, rule=rule)

    assert isinstance(rendered, TrackerSong)
    assert report.score_kind == "song"
    assert report.total_shaped_steps == 22
    assert tuple(stat.lane_name for stat in report.lane_stats) == (
        "triple",
        "compound",
    )
    assert tuple(stat.meter for stat in report.lane_stats) == ("3/4", "6/8")


def test_analyze_metric_accent_handles_unsupported_score() -> None:
    rendered, report = analyze_metric_accent("not-a-score")

    assert rendered == "not-a-score"
    assert report.score_kind == "unsupported"
    assert report.total_shaped_steps == 0
    assert report.lane_stats == ()


def test_summarize_metric_accent_report_returns_json_safe_summary() -> None:
    rule = MetricAccentRule()
    scene = _scene([_lane("melody"), _lane("ostinato")])

    _, report = analyze_metric_accent(scene, rule=rule)

    summary = summarize_metric_accent_report(report)

    assert summary == {
        "score_kind": "scene",
        "total_shaped_steps": 15,
        "lane_count": 2,
        "applied_lane_count": 1,
        "lanes": [
            {
                "lane_name": "melody",
                "role": "melody",
                "meter": "4/4",
                "step_count": 16,
                "shaped_step_count": 15,
                "mean_multiplier": 0.866,
                "strongest_row": 0,
                "applies": True,
            },
            {
                "lane_name": "ostinato",
                "role": "ostinato",
                "meter": "4/4",
                "step_count": 16,
                "shaped_step_count": 0,
                "mean_multiplier": 1.0,
                "strongest_row": 0,
                "applies": False,
            },
        ],
    }


def test_metric_accent_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(
        "my-claw/tools/senseweave/render/rules/metric_accent.py"
    )
    assert result.depth >= 2, result.reason
