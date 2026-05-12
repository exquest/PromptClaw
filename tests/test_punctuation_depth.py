"""Depth-2 punctuation helpers - locked test surface for frac-0019."""
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
from senseweave.render.rules.punctuation import (  # noqa: E402
    LanePunctuationStat,
    PunctuationReport,
    PunctuationRule,
    analyze_punctuation,
    apply_punctuation,
    lane_punctuation_stat,
    summarize_punctuation_report,
)


def _step(
    row: int,
    length: int,
    *,
    phrase_id: str = "p1",
    metadata: dict[str, str] | None = None,
) -> TrackerStep:
    step_metadata = {"phrase_id": phrase_id}
    if metadata:
        step_metadata.update(metadata)
    return TrackerStep(
        row=row,
        length_rows=length,
        scale_degree=1,
        velocity=0.5,
        metadata=step_metadata,
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
        steps=steps or [_step(0, 4), _step(4, 4), _step(8, 4)],
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


def test_lane_punctuation_stat_reports_melody_breaths() -> None:
    rule = PunctuationRule()
    original = _lane("melody")
    scene = _scene([original])

    rendered_scene = apply_punctuation(scene, k=1.0, seeds={"R6": 99}, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_punctuation_stat(original, rendered_lane, rule=rule)

    assert isinstance(stat, LanePunctuationStat)
    assert dataclasses.is_dataclass(stat)
    assert getattr(stat, "__dataclass_params__").frozen
    assert stat.lane_name == "melody"
    assert stat.role == "melody"
    assert stat.step_count == 4
    assert stat.terminal_note_count == 1
    assert stat.extended_terminal_count == 1
    assert stat.inserted_breath_count == 1
    assert stat.mean_terminal_multiplier == 1.25
    assert stat.mean_breath_ms == 250.0
    assert stat.applies is True


def test_lane_punctuation_stat_marks_non_melodic_lane_as_not_applying() -> None:
    rule = PunctuationRule()
    original = _lane("ostinato")

    stat = lane_punctuation_stat(original, original, rule=rule)

    assert stat.applies is False
    assert stat.extended_terminal_count == 0
    assert stat.inserted_breath_count == 0
    assert stat.mean_terminal_multiplier == 1.0
    assert stat.mean_breath_ms == 0.0
    assert stat.lane_name == "ostinato"
    assert stat.role == "ostinato"


def test_lane_punctuation_stat_marks_grid_locked_lane_as_not_applying() -> None:
    rule = PunctuationRule()
    original = _lane("melody", metadata={"grid_locked": "true"})
    scene = _scene([original])

    rendered_scene = apply_punctuation(scene, k=1.0, seeds={"R6": 99}, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_punctuation_stat(original, rendered_lane, rule=rule)

    assert stat.applies is False
    assert stat.extended_terminal_count == 0
    assert stat.inserted_breath_count == 0
    assert stat.mean_terminal_multiplier == 1.0


def test_analyze_punctuation_scene_returns_rendered_and_report() -> None:
    rule = PunctuationRule()
    scene = _scene([_lane("melody"), _lane("ostinato")])

    rendered, report = analyze_punctuation(scene, seeds={"R6": 99}, rule=rule)

    assert rendered == apply_punctuation(scene, seeds={"R6": 99}, rule=rule)
    assert isinstance(report, PunctuationReport)
    assert report.score_kind == "scene"
    assert report.total_extended_terminals == 1
    assert report.total_inserted_breaths == 1
    assert len(report.lane_stats) == 2
    assert report.lane_stats[0].lane_name == "melody"
    assert report.lane_stats[0].applies is True
    assert report.lane_stats[0].extended_terminal_count == 1
    assert report.lane_stats[1].lane_name == "ostinato"
    assert report.lane_stats[1].applies is False
    assert report.lane_stats[1].inserted_breath_count == 0


def test_analyze_punctuation_song_aggregates_scenes() -> None:
    rule = PunctuationRule()
    scene_a = _scene([_lane("melody", name="lead_a")], name="scene_a")
    scene_b = _scene([_lane("melody", name="lead_b")], name="scene_b")
    song = TrackerSong(title="punctuation_song", scenes=[scene_a, scene_b])

    rendered, report = analyze_punctuation(song, seeds={"R6": 99}, rule=rule)

    assert isinstance(rendered, TrackerSong)
    assert report.score_kind == "song"
    assert report.total_extended_terminals == 2
    assert report.total_inserted_breaths == 2
    assert tuple(stat.lane_name for stat in report.lane_stats) == (
        "lead_a",
        "lead_b",
    )


def test_analyze_punctuation_pattern_reports_pattern_kind() -> None:
    rule = PunctuationRule()
    pattern = TrackerPattern(rows=64, lanes=[_lane("melody", name="pattern_lead")])

    rendered, report = analyze_punctuation(pattern, seeds={"R6": 99}, rule=rule)

    assert isinstance(rendered, TrackerPattern)
    assert report.score_kind == "pattern"
    assert report.total_extended_terminals == 1
    assert report.total_inserted_breaths == 1
    assert report.lane_stats[0].lane_name == "pattern_lead"


def test_analyze_punctuation_handles_unsupported_score() -> None:
    rendered, report = analyze_punctuation("not-a-score")

    assert rendered == "not-a-score"
    assert report.score_kind == "unsupported"
    assert report.total_extended_terminals == 0
    assert report.total_inserted_breaths == 0
    assert report.lane_stats == ()


def test_summarize_punctuation_report_returns_json_safe_summary() -> None:
    rule = PunctuationRule()
    scene = _scene([_lane("melody"), _lane("ostinato")])

    _, report = analyze_punctuation(scene, seeds={"R6": 99}, rule=rule)

    summary = summarize_punctuation_report(report)

    assert summary == {
        "score_kind": "scene",
        "total_extended_terminals": 1,
        "total_inserted_breaths": 1,
        "lane_count": 2,
        "applied_lane_count": 1,
        "lanes": [
            {
                "lane_name": "melody",
                "role": "melody",
                "step_count": 4,
                "terminal_note_count": 1,
                "extended_terminal_count": 1,
                "inserted_breath_count": 1,
                "mean_terminal_multiplier": 1.25,
                "mean_breath_ms": 250.0,
                "applies": True,
            },
            {
                "lane_name": "ostinato",
                "role": "ostinato",
                "step_count": 3,
                "terminal_note_count": 1,
                "extended_terminal_count": 0,
                "inserted_breath_count": 0,
                "mean_terminal_multiplier": 1.0,
                "mean_breath_ms": 0.0,
                "applies": False,
            },
        ],
    }


def test_punctuation_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(
        "my-claw/tools/senseweave/render/rules/punctuation.py"
    )
    assert result.depth >= 2, result.reason
