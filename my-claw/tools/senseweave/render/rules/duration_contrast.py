"""R4 duration contrast: exaggerate short-vs-long note durations."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from statistics import median
from typing import Any

from ...music_tracker import (
    TrackerLane,
    TrackerPattern,
    TrackerScene,
    TrackerSong,
    TrackerStep,
)
from .metric_accent import _metadata_is_grid_locked, role_is_eligible

MIN_MULTIPLIER = 0.90
MAX_MULTIPLIER = 1.10


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _duration_multiplier(length_rows: int, median_length: float, k: float) -> float:
    if median_length <= 0 or length_rows <= 0:
        return 1.0
    ratio = length_rows / median_length
    adjustment = k * math.log(ratio)
    return _clamp(1.0 + adjustment, MIN_MULTIPLIER, MAX_MULTIPLIER)


def _apply_contrast_to_lane(
    lane: TrackerLane,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: DurationContrastRule,
) -> TrackerLane:
    normalized_role = lane.role.strip().lower()
    if roles is not None and normalized_role not in {r.strip().lower() for r in roles}:
        return lane
    if not rule.applies_to(lane.role, lane.metadata):
        return lane

    durations = [step.length_rows for step in lane.steps if step.length_rows > 0]
    if len(durations) < 2:
        return lane
    median_dur = median(durations)

    return replace(
        lane,
        steps=[
            _apply_contrast_to_step(step, median_length=median_dur, k=k)
            for step in lane.steps
        ],
    )


def _apply_contrast_to_step(
    step: TrackerStep,
    *,
    median_length: float,
    k: float,
) -> TrackerStep:
    if _metadata_is_grid_locked(step.metadata):
        return step
    multiplier = _duration_multiplier(step.length_rows, median_length, k)
    new_length = max(1, int(round(step.length_rows * multiplier)))
    if new_length == step.length_rows:
        return step
    return replace(step, length_rows=new_length)


class DurationContrastRule:
    """Exaggerate short-vs-long note durations via log-scaled contrast."""

    rule_id = "R4"

    def applies_to(self, role: str, metadata: Mapping[str, object] | None = None) -> bool:
        return role_is_eligible(role, metadata)

    def apply(
        self,
        score: Any,
        *,
        k: float,
        seeds: Mapping[str, int] | None,
        roles: frozenset[str] | None,
    ) -> Any:
        del seeds
        return apply_duration_contrast(score, k=k, roles=roles, rule=self)


def _apply_to_pattern(
    pattern: TrackerPattern,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: DurationContrastRule,
) -> TrackerPattern:
    return replace(
        pattern,
        lanes=[
            _apply_contrast_to_lane(lane, k=k, roles=roles, rule=rule)
            for lane in pattern.lanes
        ],
    )


def _apply_to_scene(
    scene: TrackerScene,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: DurationContrastRule,
) -> TrackerScene:
    return replace(
        scene,
        pattern=_apply_to_pattern(scene.pattern, k=k, roles=roles, rule=rule),
    )


def apply_duration_contrast(
    score: Any,
    *,
    k: float = 1.0,
    roles: frozenset[str] | None = None,
    rule: DurationContrastRule | None = None,
) -> Any:
    """Apply R4 duration contrast shaping to tracker scenes or songs."""

    if k == 0.0:
        return score
    active_rule = rule or DurationContrastRule()
    shaped_k = _clamp(k, 0.0, 1.0)
    if shaped_k == 0.0:
        return score
    if isinstance(score, TrackerScene):
        return _apply_to_scene(score, k=shaped_k, roles=roles, rule=active_rule)
    if isinstance(score, TrackerSong):
        return replace(
            score,
            scenes=[
                _apply_to_scene(scene, k=shaped_k, roles=roles, rule=active_rule)
                for scene in score.scenes
            ],
        )
    if isinstance(score, TrackerPattern):
        return _apply_to_pattern(score, k=shaped_k, roles=roles, rule=active_rule)
    return score


@dataclass(frozen=True)
class LaneDurationContrastStat:
    """Per-lane duration-contrast outcome from one apply pass."""

    lane_name: str
    role: str
    step_count: int
    shaped_step_count: int
    mean_multiplier: float
    longest_row: int | None
    shortest_row: int | None
    applies: bool


@dataclass(frozen=True)
class DurationContrastReport:
    """Aggregate duration-contrast outcome for one score."""

    score_kind: str
    total_shaped_steps: int
    lane_stats: tuple[LaneDurationContrastStat, ...]


def lane_duration_contrast_stat(
    original: TrackerLane,
    rendered: TrackerLane,
    *,
    rule: DurationContrastRule,
) -> LaneDurationContrastStat:
    """Compare *original* and *rendered* lanes and report R4 shaping."""

    shaped_step_count = 0
    ratios: list[float] = []
    longest: tuple[float, int] | None = None
    shortest: tuple[float, int] | None = None

    for original_step, rendered_step in zip(original.steps, rendered.steps):
        if rendered_step.length_rows != original_step.length_rows:
            shaped_step_count += 1
        if original_step.length_rows <= 0:
            continue
        ratio = rendered_step.length_rows / original_step.length_rows
        ratios.append(ratio)
        if longest is None or ratio > longest[0]:
            longest = (ratio, rendered_step.row)
        if shortest is None or ratio < shortest[0]:
            shortest = (ratio, rendered_step.row)

    mean_multiplier = round(sum(ratios) / len(ratios), 3) if ratios else 1.0

    return LaneDurationContrastStat(
        lane_name=rendered.name,
        role=rendered.role,
        step_count=len(rendered.steps),
        shaped_step_count=shaped_step_count,
        mean_multiplier=mean_multiplier,
        longest_row=longest[1] if longest is not None else None,
        shortest_row=shortest[1] if shortest is not None else None,
        applies=rule.applies_to(rendered.role, rendered.metadata),
    )


def _score_kind(score: Any) -> str:
    if isinstance(score, TrackerScene):
        return "scene"
    if isinstance(score, TrackerSong):
        return "song"
    if isinstance(score, TrackerPattern):
        return "pattern"
    return "unsupported"


def _lane_pairs(
    score: Any,
    rendered: Any,
    kind: str,
) -> list[tuple[TrackerLane, TrackerLane]]:
    if kind == "scene":
        return list(zip(score.pattern.lanes, rendered.pattern.lanes))
    if kind == "song":
        pairs: list[tuple[TrackerLane, TrackerLane]] = []
        for original_scene, rendered_scene in zip(score.scenes, rendered.scenes):
            pairs.extend(
                zip(original_scene.pattern.lanes, rendered_scene.pattern.lanes)
            )
        return pairs
    if kind == "pattern":
        return list(zip(score.lanes, rendered.lanes))
    return []


def analyze_duration_contrast(
    score: Any,
    *,
    k: float = 1.0,
    seeds: Mapping[str, int] | None = None,
    roles: frozenset[str] | None = None,
    rule: DurationContrastRule | None = None,
) -> tuple[Any, DurationContrastReport]:
    """Apply duration contrast to *score* and return rendered score + report."""

    del seeds
    active_rule = rule or DurationContrastRule()
    rendered = apply_duration_contrast(score, k=k, roles=roles, rule=active_rule)
    kind = _score_kind(score)
    if kind == "unsupported":
        return rendered, DurationContrastReport(
            score_kind="unsupported",
            total_shaped_steps=0,
            lane_stats=(),
        )

    stats: list[LaneDurationContrastStat] = []
    total_shaped_steps = 0
    for original_lane, rendered_lane in _lane_pairs(score, rendered, kind):
        stat = lane_duration_contrast_stat(
            original_lane,
            rendered_lane,
            rule=active_rule,
        )
        stats.append(stat)
        total_shaped_steps += stat.shaped_step_count

    return rendered, DurationContrastReport(
        score_kind=kind,
        total_shaped_steps=total_shaped_steps,
        lane_stats=tuple(stats),
    )


def summarize_duration_contrast_report(
    report: DurationContrastReport,
) -> dict[str, object]:
    """Return a JSON-safe operator summary of *report*."""

    lanes: list[dict[str, object]] = []
    applied_count = 0
    for stat in report.lane_stats:
        if stat.applies:
            applied_count += 1
        lanes.append(
            {
                "lane_name": stat.lane_name,
                "role": stat.role,
                "step_count": stat.step_count,
                "shaped_step_count": stat.shaped_step_count,
                "mean_multiplier": stat.mean_multiplier,
                "longest_row": stat.longest_row,
                "shortest_row": stat.shortest_row,
                "applies": stat.applies,
            }
        )
    return {
        "score_kind": report.score_kind,
        "total_shaped_steps": report.total_shaped_steps,
        "lane_count": len(report.lane_stats),
        "applied_lane_count": applied_count,
        "lanes": lanes,
    }
