"""Depth-2 silence budget helpers - locked test surface for frac-0020."""
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
from senseweave.render.rules.silence_budget import (  # noqa: E402
    LaneSilenceBudgetStat,
    SilenceBudgetReport,
    SilenceBudgetRule,
    analyze_silence_budget,
    apply_silence_budget,
    lane_silence_budget_stat,
    summarize_silence_budget_report,
)


def _step(
    row: int,
    length: int,
    *,
    phrase_id: str = "p1",
    velocity: float = 0.8,
) -> TrackerStep:
    return TrackerStep(
        row=row,
        length_rows=length,
        scale_degree=1,
        velocity=velocity,
        metadata={"phrase_id": phrase_id},
    )


def _breath(row: int, length: int) -> TrackerStep:
    return TrackerStep(
        row=row,
        length_rows=length,
        scale_degree=0,
        velocity=0.0,
        metadata={"breath_r6": "true", "breath_ms": "250.0"},
    )


def _tacet_lane(role: str = "melody", *, name: str | None = None) -> TrackerLane:
    return TrackerLane(
        name=name or role,
        role=role,
        voice="pluck",
        steps=[
            _step(0, 4, phrase_id="p1", velocity=0.0),
            _step(4, 4, phrase_id="p1", velocity=0.0),
            _step(8, 4, phrase_id="p1", velocity=0.0),
            _step(12, 4, phrase_id="p2", velocity=0.8),
            _step(16, 4, phrase_id="p2", velocity=0.8),
        ],
        metadata={},
    )


def _breath_lane(role: str = "melody", *, name: str | None = None) -> TrackerLane:
    return TrackerLane(
        name=name or role,
        role=role,
        voice="pluck",
        steps=[
            _step(0, 4, phrase_id="p1", velocity=0.0),
            _step(4, 4, phrase_id="p1", velocity=0.0),
            _breath(8, 2),
            _step(10, 4, phrase_id="p2", velocity=0.8),
            _step(14, 4, phrase_id="p2", velocity=0.8),
        ],
        metadata={},
    )


def _scene(lanes: list[TrackerLane], *, name: str = "fixture") -> TrackerScene:
    return TrackerScene(
        name=name,
        key="C",
        tempo_bpm=120.0,
        rows_per_beat=4,
        pattern=TrackerPattern(rows=64, lanes=lanes),
        constraints=SceneConstraint(max_polyphony=1, allowed_roles=("melody",)),
        metadata={"groove_meter": "4/4"},
    )


def test_lane_silence_budget_stat_reports_tacet_lane() -> None:
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    original = _tacet_lane()
    scene = _scene([original])

    rendered_scene = apply_silence_budget(scene, k=1.0, seeds=None, roles=None, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_silence_budget_stat(original, rendered_lane, rule=rule)

    assert isinstance(stat, LaneSilenceBudgetStat)
    assert dataclasses.is_dataclass(stat)
    assert getattr(stat, "__dataclass_params__").frozen
    assert stat.lane_name == "melody"
    assert stat.role == "melody"
    assert stat.step_count == 5
    assert stat.phrase_count == 2
    assert stat.breath_extension_count == 0
    assert stat.tacet_step_count == 2
    assert stat.tacet_phrase_count == 1
    assert stat.applies is True


def test_lane_silence_budget_stat_reports_breath_extension() -> None:
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    original = _breath_lane()
    scene = _scene([original])

    rendered_scene = apply_silence_budget(scene, k=1.0, seeds=None, roles=None, rule=rule)
    rendered_lane = rendered_scene.pattern.lanes[0]

    stat = lane_silence_budget_stat(original, rendered_lane, rule=rule)

    assert stat.lane_name == "melody"
    assert stat.role == "melody"
    assert stat.step_count == 5
    assert stat.phrase_count == 2
    assert stat.breath_extension_count == 1
    assert stat.tacet_step_count == 0
    assert stat.tacet_phrase_count == 0
    assert stat.applies is True


def test_lane_silence_budget_stat_marks_non_melodic_lane_as_not_applying() -> None:
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    original = _tacet_lane(role="ostinato")

    stat = lane_silence_budget_stat(original, original, rule=rule)

    assert stat.applies is False
    assert stat.breath_extension_count == 0
    assert stat.tacet_step_count == 0
    assert stat.tacet_phrase_count == 0
    assert stat.lane_name == "ostinato"
    assert stat.role == "ostinato"
    assert stat.phrase_count == 2


def test_analyze_silence_budget_scene_returns_rendered_and_report() -> None:
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    scene = _scene([_tacet_lane(), _tacet_lane(role="ostinato", name="ost")])

    rendered, report = analyze_silence_budget(scene, rule=rule)

    assert rendered == apply_silence_budget(scene, rule=rule)
    assert isinstance(report, SilenceBudgetReport)
    assert report.score_kind == "scene"
    assert report.total_breath_extensions == 0
    assert report.total_tacet_steps == 2
    assert len(report.lane_stats) == 2
    assert report.lane_stats[0].lane_name == "melody"
    assert report.lane_stats[0].applies is True
    assert report.lane_stats[0].tacet_step_count == 2
    assert report.lane_stats[1].lane_name == "ost"
    assert report.lane_stats[1].applies is False
    assert report.lane_stats[1].tacet_step_count == 0


def test_analyze_silence_budget_song_aggregates_scenes() -> None:
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    scene_a = _scene([_tacet_lane(name="lead_a")], name="scene_a")
    scene_b = _scene([_tacet_lane(name="lead_b")], name="scene_b")
    song = TrackerSong(title="silence_song", scenes=[scene_a, scene_b])

    rendered, report = analyze_silence_budget(song, rule=rule)

    assert isinstance(rendered, TrackerSong)
    assert report.score_kind == "song"
    assert report.total_breath_extensions == 0
    assert report.total_tacet_steps == 4
    assert tuple(stat.lane_name for stat in report.lane_stats) == (
        "lead_a",
        "lead_b",
    )


def test_analyze_silence_budget_pattern_reports_pattern_kind() -> None:
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    pattern = TrackerPattern(rows=64, lanes=[_tacet_lane(name="pattern_lead")])

    rendered, report = analyze_silence_budget(pattern, rule=rule)

    assert isinstance(rendered, TrackerPattern)
    assert report.score_kind == "pattern"
    assert report.total_breath_extensions == 0
    assert report.total_tacet_steps == 2
    assert report.lane_stats[0].lane_name == "pattern_lead"


def test_analyze_silence_budget_handles_unsupported_score() -> None:
    rendered, report = analyze_silence_budget("not-a-score")

    assert rendered == "not-a-score"
    assert report.score_kind == "unsupported"
    assert report.total_breath_extensions == 0
    assert report.total_tacet_steps == 0
    assert report.lane_stats == ()


def test_summarize_silence_budget_report_returns_json_safe_summary() -> None:
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    scene = _scene([_tacet_lane(), _tacet_lane(role="ostinato", name="ost")])

    _, report = analyze_silence_budget(scene, rule=rule)

    summary = summarize_silence_budget_report(report)

    assert summary == {
        "score_kind": "scene",
        "total_breath_extensions": 0,
        "total_tacet_steps": 2,
        "lane_count": 2,
        "applied_lane_count": 1,
        "lanes": [
            {
                "lane_name": "melody",
                "role": "melody",
                "step_count": 5,
                "phrase_count": 2,
                "breath_extension_count": 0,
                "tacet_step_count": 2,
                "tacet_phrase_count": 1,
                "applies": True,
            },
            {
                "lane_name": "ost",
                "role": "ostinato",
                "step_count": 5,
                "phrase_count": 2,
                "breath_extension_count": 0,
                "tacet_step_count": 0,
                "tacet_phrase_count": 0,
                "applies": False,
            },
        ],
    }


def test_silence_budget_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(
        "my-claw/tools/senseweave/render/rules/silence_budget.py"
    )
    assert result.depth >= 2, result.reason
