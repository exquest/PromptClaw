"""Depth-2 duration contrast helpers - locked test surface for frac-0018."""
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
from senseweave.render.rules.duration_contrast import (  # noqa: E402
    DurationContrastReport,
    DurationContrastRule,
    LaneDurationContrastStat,
    analyze_duration_contrast,
    apply_duration_contrast,
    lane_duration_contrast_stat,
    summarize_duration_contrast_report,
)


def _step(
    index: int,
    length: int,
    *,
    velocity: float = 0.5,
    metadata: dict[str, str] | None = None,
) -> TrackerStep:
    return TrackerStep(
        row=index * 16,
        length_rows=length,
        scale_degree=1,
        velocity=velocity,
        metadata=metadata or {},
    )


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
        steps=steps or [_step(0, 4), _step(1, 8), _step(2, 16), _step(3, 32)],
        metadata=metadata or {},
    )


def _scene(
    lanes: list[TrackerLane],
    *,
    name: str = "fixture",
    rows: int = 64,
) -> TrackerScene:
    return TrackerScene(
        name=name,
        key="C",
        tempo_bpm=120.0,
        rows_per_beat=4,
        pattern=TrackerPattern(rows=rows, lanes=lanes),
        constraints=SceneConstraint(max_polyphony=1, allowed_roles=("melody",)),
        metadata={"groove_meter": "4/4"},
    )


def test_lane_duration_contrast_stat_reports_melody_shaping() -> None:
    rule = DurationContrastRule()
    original = _lane("melody")
    scene = _scene([original])

    rendered_scene = apply_duration_contrast(scene, k=1.0, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_duration_contrast_stat(original, rendered_lane, rule=rule)

    assert isinstance(stat, LaneDurationContrastStat)
    assert dataclasses.is_dataclass(stat)
    assert getattr(stat, "__dataclass_params__").frozen
    assert stat.lane_name == "melody"
    assert stat.role == "melody"
    assert stat.step_count == 4
    assert stat.shaped_step_count == 3
    assert stat.mean_multiplier == 1.023
    assert stat.longest_row == 32
    assert stat.shortest_row == 16
    assert stat.applies is True


def test_lane_duration_contrast_stat_marks_non_melodic_lane_as_not_applying() -> None:
    rule = DurationContrastRule()
    original = _lane("ostinato")

    stat = lane_duration_contrast_stat(original, original, rule=rule)

    assert stat.applies is False
    assert stat.shaped_step_count == 0
    assert stat.mean_multiplier == 1.0
    assert stat.lane_name == "ostinato"
    assert stat.role == "ostinato"


def test_lane_duration_contrast_stat_marks_grid_locked_lane_as_not_applying() -> None:
    rule = DurationContrastRule()
    original = _lane("melody", metadata={"grid_locked": "true"})
    scene = _scene([original])

    rendered_scene = apply_duration_contrast(scene, k=1.0, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_duration_contrast_stat(original, rendered_lane, rule=rule)

    assert stat.applies is False
    assert stat.shaped_step_count == 0
    assert stat.mean_multiplier == 1.0


def test_analyze_duration_contrast_scene_returns_rendered_and_report() -> None:
    rule = DurationContrastRule()
    scene = _scene([_lane("melody"), _lane("ostinato")])

    rendered, report = analyze_duration_contrast(scene, rule=rule)

    assert rendered == apply_duration_contrast(scene, rule=rule)
    assert isinstance(report, DurationContrastReport)
    assert report.score_kind == "scene"
    assert report.total_shaped_steps == 3
    assert len(report.lane_stats) == 2
    assert report.lane_stats[0].lane_name == "melody"
    assert report.lane_stats[0].applies is True
    assert report.lane_stats[0].shaped_step_count == 3
    assert report.lane_stats[1].lane_name == "ostinato"
    assert report.lane_stats[1].applies is False
    assert report.lane_stats[1].shaped_step_count == 0


def test_analyze_duration_contrast_song_aggregates_scenes() -> None:
    rule = DurationContrastRule()
    scene_a = _scene([_lane("melody", name="lead_a")], name="scene_a")
    scene_b = _scene([_lane("melody", name="lead_b")], name="scene_b")
    song = TrackerSong(title="duration_song", scenes=[scene_a, scene_b])

    rendered, report = analyze_duration_contrast(song, rule=rule)

    assert isinstance(rendered, TrackerSong)
    assert report.score_kind == "song"
    assert report.total_shaped_steps == 6
    assert tuple(stat.lane_name for stat in report.lane_stats) == (
        "lead_a",
        "lead_b",
    )


def test_analyze_duration_contrast_handles_unsupported_score() -> None:
    rendered, report = analyze_duration_contrast("not-a-score")

    assert rendered == "not-a-score"
    assert report.score_kind == "unsupported"
    assert report.total_shaped_steps == 0
    assert report.lane_stats == ()


def test_summarize_duration_contrast_report_returns_json_safe_summary() -> None:
    rule = DurationContrastRule()
    scene = _scene([_lane("melody"), _lane("ostinato")])

    _, report = analyze_duration_contrast(scene, rule=rule)

    summary = summarize_duration_contrast_report(report)

    assert summary == {
        "score_kind": "scene",
        "total_shaped_steps": 3,
        "lane_count": 2,
        "applied_lane_count": 1,
        "lanes": [
            {
                "lane_name": "melody",
                "role": "melody",
                "step_count": 4,
                "shaped_step_count": 3,
                "mean_multiplier": 1.023,
                "longest_row": 32,
                "shortest_row": 16,
                "applies": True,
            },
            {
                "lane_name": "ostinato",
                "role": "ostinato",
                "step_count": 4,
                "shaped_step_count": 0,
                "mean_multiplier": 1.0,
                "longest_row": 0,
                "shortest_row": 0,
                "applies": False,
            },
        ],
    }


def test_duration_contrast_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(
        "my-claw/tools/senseweave/render/rules/duration_contrast.py"
    )
    assert result.depth >= 2, result.reason
