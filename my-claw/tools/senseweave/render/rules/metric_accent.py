"""R1 metric accent velocity shaping."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from cypherclaw.render.role_gate import (
    GRID_LOCKED_ROLES,
    MELODIC_ACCENT_ROLES,
    metadata_is_grid_locked as _metadata_is_grid_locked,
    role_is_eligible,
)

from ...music_tracker import (
    TrackerLane,
    TrackerPattern,
    TrackerScene,
    TrackerSong,
    TrackerStep,
)

METRIC_ACCENT_4_4: tuple[float, ...] = (
    1.00, 0.82, 0.92, 0.80,
    0.95, 0.80, 0.90, 0.78,
    0.97, 0.80, 0.91, 0.78,
    0.94, 0.80, 0.90, 0.78,
)


def _steps_per_bar(meter: str) -> int:
    if meter == "free":
        return len(METRIC_ACCENT_4_4)

    parts = meter.split("/", 1)
    if len(parts) != 2:
        return len(METRIC_ACCENT_4_4)

    try:
        numerator = int(parts[0])
        denominator = int(parts[1])
    except ValueError:
        return len(METRIC_ACCENT_4_4)

    if numerator <= 0:
        return len(METRIC_ACCENT_4_4)
    if denominator == 8:
        return numerator * 2
    return numerator * 4


def metric_accent_table(meter: str) -> tuple[float, ...]:
    """Return a metric accent table at sixteenth-note resolution for *meter*."""

    steps = _steps_per_bar(meter)
    if steps == len(METRIC_ACCENT_4_4):
        return METRIC_ACCENT_4_4
    return tuple(METRIC_ACCENT_4_4[index % len(METRIC_ACCENT_4_4)] for index in range(steps))


def _meter_for_scene(scene: TrackerScene) -> str:
    return scene.metadata.get("groove_meter") or scene.metadata.get("meter") or "4/4"


def _bar_rows(scene: TrackerScene) -> int:
    meter = _meter_for_scene(scene)
    return _steps_per_bar(meter) * max(1, scene.rows_per_beat) // 4


def _table_index_for_row(row: int, *, bar_rows: int, table_size: int) -> int:
    if bar_rows <= 0:
        return 0
    position = row % bar_rows
    return min(table_size - 1, int(position * table_size / bar_rows))


def _scaled_velocity(velocity: float, multiplier: float, k: float) -> float:
    shaped = velocity * (1.0 + ((multiplier - 1.0) * max(0.0, k)))
    return round(max(0.0, min(1.0, shaped)), 3)


class MetricAccentRule:
    """Apply meter-position velocity multipliers to humanized melodic voices."""

    rule_id = "R1"

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
        return apply_metric_accent(score, k=k, roles=roles, rule=self)


@dataclass(frozen=True)
class LaneMetricAccentStat:
    """Per-lane metric-accent outcome from one apply pass."""

    lane_name: str
    role: str
    meter: str
    step_count: int
    shaped_step_count: int
    mean_multiplier: float
    strongest_row: int | None
    applies: bool


@dataclass(frozen=True)
class MetricAccentReport:
    """Aggregate metric-accent outcome for one score."""

    score_kind: str
    total_shaped_steps: int
    lane_stats: tuple[LaneMetricAccentStat, ...]


def _apply_to_step(
    step: TrackerStep,
    *,
    table: tuple[float, ...],
    bar_rows: int,
    k: float,
) -> TrackerStep:
    if _metadata_is_grid_locked(step.metadata):
        return step
    index = _table_index_for_row(step.row, bar_rows=bar_rows, table_size=len(table))
    return replace(step, velocity=_scaled_velocity(step.velocity, table[index], k))


def _apply_to_lane(
    lane: TrackerLane,
    *,
    table: tuple[float, ...],
    bar_rows: int,
    k: float,
    roles: frozenset[str] | None,
    rule: MetricAccentRule,
) -> TrackerLane:
    normalized_role = lane.role.strip().lower()
    if roles is not None and normalized_role not in {role.strip().lower() for role in roles}:
        return lane
    if not rule.applies_to(lane.role, lane.metadata):
        return lane
    return replace(
        lane,
        steps=[
            _apply_to_step(step, table=table, bar_rows=bar_rows, k=k)
            for step in lane.steps
        ],
    )


def _apply_to_scene(
    scene: TrackerScene,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: MetricAccentRule,
) -> TrackerScene:
    table = metric_accent_table(_meter_for_scene(scene))
    bar_rows = max(1, _bar_rows(scene))
    return replace(
        scene,
        pattern=replace(
            scene.pattern,
            lanes=[
                _apply_to_lane(
                    lane,
                    table=table,
                    bar_rows=bar_rows,
                    k=k,
                    roles=roles,
                    rule=rule,
                )
                for lane in scene.pattern.lanes
            ],
        ),
    )


def _apply_to_pattern(
    pattern: TrackerPattern,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: MetricAccentRule,
) -> TrackerPattern:
    table = metric_accent_table("4/4")
    return replace(
        pattern,
        lanes=[
            _apply_to_lane(
                lane,
                table=table,
                bar_rows=len(table),
                k=k,
                roles=roles,
                rule=rule,
            )
            for lane in pattern.lanes
        ],
    )


def apply_metric_accent(
    score: Any,
    *,
    k: float = 1.0,
    roles: frozenset[str] | None = None,
    rule: MetricAccentRule | None = None,
) -> Any:
    """Apply R1 metric accent shaping to tracker scenes or songs."""

    if k == 0.0:
        return score
    active_rule = rule or MetricAccentRule()
    if isinstance(score, TrackerScene):
        return _apply_to_scene(score, k=k, roles=roles, rule=active_rule)
    if isinstance(score, TrackerSong):
        return replace(
            score,
            scenes=[
                _apply_to_scene(scene, k=k, roles=roles, rule=active_rule)
                for scene in score.scenes
            ],
        )
    if isinstance(score, TrackerPattern):
        return _apply_to_pattern(score, k=k, roles=roles, rule=active_rule)
    return score


def lane_metric_accent_stat(
    original: TrackerLane,
    rendered: TrackerLane,
    *,
    meter: str,
    rule: MetricAccentRule,
) -> LaneMetricAccentStat:
    """Compare *original* and *rendered* lanes and report R1 shaping."""

    shaped_step_count = 0
    ratios: list[float] = []
    strongest: tuple[float, int] | None = None

    for original_step, rendered_step in zip(original.steps, rendered.steps):
        if rendered_step.velocity != original_step.velocity:
            shaped_step_count += 1
        if original_step.velocity <= 0.0:
            continue
        ratio = rendered_step.velocity / original_step.velocity
        ratios.append(ratio)
        if strongest is None or ratio > strongest[0]:
            strongest = (ratio, rendered_step.row)

    mean_multiplier = round(sum(ratios) / len(ratios), 3) if ratios else 1.0

    return LaneMetricAccentStat(
        lane_name=rendered.name,
        role=rendered.role,
        meter=meter,
        step_count=len(rendered.steps),
        shaped_step_count=shaped_step_count,
        mean_multiplier=mean_multiplier,
        strongest_row=strongest[1] if strongest is not None else None,
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
) -> list[tuple[TrackerLane, TrackerLane, str]]:
    if kind == "scene":
        meter = _meter_for_scene(score)
        return [
            (original_lane, rendered_lane, meter)
            for original_lane, rendered_lane in zip(
                score.pattern.lanes,
                rendered.pattern.lanes,
            )
        ]
    if kind == "song":
        pairs: list[tuple[TrackerLane, TrackerLane, str]] = []
        for original_scene, rendered_scene in zip(score.scenes, rendered.scenes):
            meter = _meter_for_scene(original_scene)
            pairs.extend(
                (original_lane, rendered_lane, meter)
                for original_lane, rendered_lane in zip(
                    original_scene.pattern.lanes,
                    rendered_scene.pattern.lanes,
                )
            )
        return pairs
    if kind == "pattern":
        return [
            (original_lane, rendered_lane, "4/4")
            for original_lane, rendered_lane in zip(score.lanes, rendered.lanes)
        ]
    return []


def analyze_metric_accent(
    score: Any,
    *,
    k: float = 1.0,
    seeds: Mapping[str, int] | None = None,
    roles: frozenset[str] | None = None,
    rule: MetricAccentRule | None = None,
) -> tuple[Any, MetricAccentReport]:
    """Apply metric accent to *score* and return rendered score + report."""

    del seeds
    active_rule = rule or MetricAccentRule()
    rendered = apply_metric_accent(score, k=k, roles=roles, rule=active_rule)
    kind = _score_kind(score)
    if kind == "unsupported":
        return rendered, MetricAccentReport(
            score_kind="unsupported",
            total_shaped_steps=0,
            lane_stats=(),
        )

    stats: list[LaneMetricAccentStat] = []
    total_shaped_steps = 0
    for original_lane, rendered_lane, meter in _lane_pairs(score, rendered, kind):
        stat = lane_metric_accent_stat(
            original_lane,
            rendered_lane,
            meter=meter,
            rule=active_rule,
        )
        stats.append(stat)
        total_shaped_steps += stat.shaped_step_count

    return rendered, MetricAccentReport(
        score_kind=kind,
        total_shaped_steps=total_shaped_steps,
        lane_stats=tuple(stats),
    )


def summarize_metric_accent_report(
    report: MetricAccentReport,
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
                "meter": stat.meter,
                "step_count": stat.step_count,
                "shaped_step_count": stat.shaped_step_count,
                "mean_multiplier": stat.mean_multiplier,
                "strongest_row": stat.strongest_row,
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
