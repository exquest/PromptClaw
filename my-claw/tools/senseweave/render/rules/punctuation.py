"""R6 punctuation and breath: lengthen terminal notes and insert breath silences."""
from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from ...music_tracker import (
    TrackerLane,
    TrackerPattern,
    TrackerScene,
    TrackerSong,
    TrackerStep,
)
from .metric_accent import _metadata_is_grid_locked, role_is_eligible

DEFAULT_TERMINAL_MULTIPLIER = 1.25
MAX_TERMINAL_MULTIPLIER = 1.40
DEFAULT_BREATH_AFTER_MS = 250.0
BREATH_STDDEV_FACTOR = 0.1
_DEFAULT_TEMPO = 120.0
_DEFAULT_RPB = 4


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _phrase_group_key(step: TrackerStep) -> str:
    for key in ("phrase_id", "phrase_index", "repeat_cycle"):
        value = step.metadata.get(key)
        if value:
            return f"{key}:{value}"
    return "lane"


def _ms_to_rows(ms: float, *, tempo_bpm: float, rows_per_beat: int) -> int:
    ms_per_beat = 60_000.0 / tempo_bpm
    ms_per_row = ms_per_beat / rows_per_beat
    return max(1, int(round(ms / ms_per_row)))


def _rows_to_ms(rows: int, *, tempo_bpm: float, rows_per_beat: int) -> float:
    ms_per_beat = 60_000.0 / tempo_bpm
    ms_per_row = ms_per_beat / rows_per_beat
    return rows * ms_per_row


def _terminal_indices(steps: list[TrackerStep]) -> set[int]:
    groups: dict[str, list[tuple[int, TrackerStep]]] = {}
    for idx, step in enumerate(steps):
        groups.setdefault(_phrase_group_key(step), []).append((idx, step))
    terminals: set[int] = set()
    for group in groups.values():
        if group:
            terminals.add(group[-1][0])
    return terminals


def _apply_to_lane(
    lane: TrackerLane,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: PunctuationRule,
    tempo_bpm: float,
    rows_per_beat: int,
    rng: random.Random,
) -> TrackerLane:
    normalized_role = lane.role.strip().lower()
    if roles is not None and normalized_role not in {r.strip().lower() for r in roles}:
        return lane
    if not rule.applies_to(lane.role, lane.metadata):
        return lane
    if not lane.steps:
        return lane

    terminals = _terminal_indices(lane.steps)
    if not terminals:
        return lane

    new_steps: list[TrackerStep] = []
    for idx, step in enumerate(lane.steps):
        if idx not in terminals or _metadata_is_grid_locked(step.metadata):
            new_steps.append(step)
            continue

        multiplier = 1.0 + (rule.terminal_multiplier - 1.0) * k
        multiplier = _clamp(multiplier, 1.0, MAX_TERMINAL_MULTIPLIER)
        new_length = max(1, int(round(step.length_rows * multiplier)))
        extended = replace(step, length_rows=new_length)
        new_steps.append(extended)

        breath_ms = rng.gauss(rule.breath_after_ms, rule.breath_after_ms * BREATH_STDDEV_FACTOR)
        breath_ms = max(0.0, breath_ms)
        breath_length = _ms_to_rows(breath_ms, tempo_bpm=tempo_bpm, rows_per_beat=rows_per_beat)
        actual_ms = _rows_to_ms(breath_length, tempo_bpm=tempo_bpm, rows_per_beat=rows_per_beat)

        breath_step = TrackerStep(
            row=extended.row + extended.length_rows,
            length_rows=breath_length,
            scale_degree=0,
            velocity=0.0,
            metadata={"breath_r6": "true", "breath_ms": str(round(actual_ms, 1))},
        )
        new_steps.append(breath_step)

    return replace(lane, steps=new_steps)


@dataclass(frozen=True)
class PunctuationRule:
    """R6: lengthen terminal notes and insert breath silences at phrase boundaries."""

    terminal_multiplier: float = DEFAULT_TERMINAL_MULTIPLIER
    breath_after_ms: float = DEFAULT_BREATH_AFTER_MS

    rule_id = "R6"

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
        return apply_punctuation(score, k=k, seeds=seeds, roles=roles, rule=self)


@dataclass(frozen=True)
class LanePunctuationStat:
    """Per-lane punctuation outcome from one apply pass."""

    lane_name: str
    role: str
    step_count: int
    terminal_note_count: int
    extended_terminal_count: int
    inserted_breath_count: int
    mean_terminal_multiplier: float
    mean_breath_ms: float
    applies: bool


@dataclass(frozen=True)
class PunctuationReport:
    """Aggregate punctuation outcome for one score."""

    score_kind: str
    total_extended_terminals: int
    total_inserted_breaths: int
    lane_stats: tuple[LanePunctuationStat, ...]


def _make_rng(seeds: Mapping[str, int] | None) -> random.Random:
    seed = (seeds or {}).get("R6", 42)
    return random.Random(seed)


def _apply_to_pattern(
    pattern: TrackerPattern,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: PunctuationRule,
    tempo_bpm: float,
    rows_per_beat: int,
    rng: random.Random,
) -> TrackerPattern:
    return replace(
        pattern,
        lanes=[
            _apply_to_lane(
                lane, k=k, roles=roles, rule=rule,
                tempo_bpm=tempo_bpm, rows_per_beat=rows_per_beat, rng=rng,
            )
            for lane in pattern.lanes
        ],
    )


def _apply_to_scene(
    scene: TrackerScene,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: PunctuationRule,
    rng: random.Random,
) -> TrackerScene:
    return replace(
        scene,
        pattern=_apply_to_pattern(
            scene.pattern, k=k, roles=roles, rule=rule,
            tempo_bpm=scene.tempo_bpm, rows_per_beat=scene.rows_per_beat, rng=rng,
        ),
    )


def apply_punctuation(
    score: Any,
    *,
    k: float = 1.0,
    seeds: Mapping[str, int] | None = None,
    roles: frozenset[str] | None = None,
    rule: PunctuationRule | None = None,
) -> Any:
    """Apply R6 punctuation + breath to tracker scenes or songs."""

    if k == 0.0:
        return score
    active_rule = rule or PunctuationRule()
    shaped_k = _clamp(k, 0.0, 1.0)
    if shaped_k == 0.0:
        return score
    rng = _make_rng(seeds)
    if isinstance(score, TrackerScene):
        return _apply_to_scene(score, k=shaped_k, roles=roles, rule=active_rule, rng=rng)
    if isinstance(score, TrackerSong):
        return replace(
            score,
            scenes=[
                _apply_to_scene(scene, k=shaped_k, roles=roles, rule=active_rule, rng=rng)
                for scene in score.scenes
            ],
        )
    if isinstance(score, TrackerPattern):
        return _apply_to_pattern(
            score, k=shaped_k, roles=roles, rule=active_rule,
            tempo_bpm=_DEFAULT_TEMPO, rows_per_beat=_DEFAULT_RPB, rng=rng,
        )
    return score


def _is_punctuation_breath(step: TrackerStep) -> bool:
    return step.metadata.get("breath_r6") == "true"


def _inserted_breath_steps(
    original: TrackerLane,
    rendered: TrackerLane,
) -> list[TrackerStep]:
    original_breath_keys = {
        (step.row, step.length_rows, str(step.metadata.get("breath_ms", "")))
        for step in original.steps
        if _is_punctuation_breath(step)
    }
    inserted: list[TrackerStep] = []
    for step in rendered.steps:
        if not _is_punctuation_breath(step):
            continue
        key = (step.row, step.length_rows, str(step.metadata.get("breath_ms", "")))
        if key not in original_breath_keys:
            inserted.append(step)
    return inserted


def lane_punctuation_stat(
    original: TrackerLane,
    rendered: TrackerLane,
    *,
    rule: PunctuationRule,
) -> LanePunctuationStat:
    """Compare *original* and *rendered* lanes and report R6 shaping."""

    terminal_indices = _terminal_indices(original.steps)
    rendered_notes = [
        step for step in rendered.steps if not _is_punctuation_breath(step)
    ]
    extended_terminal_count = 0
    ratios: list[float] = []

    for idx in sorted(terminal_indices):
        if idx >= len(original.steps) or idx >= len(rendered_notes):
            continue
        original_step = original.steps[idx]
        rendered_step = rendered_notes[idx]
        if rendered_step.length_rows != original_step.length_rows:
            extended_terminal_count += 1
        if original_step.length_rows > 0:
            ratios.append(rendered_step.length_rows / original_step.length_rows)

    inserted_breaths = _inserted_breath_steps(original, rendered)
    breath_ms_values: list[float] = []
    for step in inserted_breaths:
        try:
            breath_ms_values.append(float(step.metadata.get("breath_ms", 0.0)))
        except (TypeError, ValueError):
            continue

    mean_terminal_multiplier = (
        round(sum(ratios) / len(ratios), 3) if ratios else 1.0
    )
    mean_breath_ms = (
        round(sum(breath_ms_values) / len(breath_ms_values), 1)
        if breath_ms_values else 0.0
    )

    return LanePunctuationStat(
        lane_name=rendered.name,
        role=rendered.role,
        step_count=len(rendered.steps),
        terminal_note_count=len(terminal_indices),
        extended_terminal_count=extended_terminal_count,
        inserted_breath_count=len(inserted_breaths),
        mean_terminal_multiplier=mean_terminal_multiplier,
        mean_breath_ms=mean_breath_ms,
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
            pairs.extend(zip(original_scene.pattern.lanes, rendered_scene.pattern.lanes))
        return pairs
    if kind == "pattern":
        return list(zip(score.lanes, rendered.lanes))
    return []


def analyze_punctuation(
    score: Any,
    *,
    k: float = 1.0,
    seeds: Mapping[str, int] | None = None,
    roles: frozenset[str] | None = None,
    rule: PunctuationRule | None = None,
) -> tuple[Any, PunctuationReport]:
    """Apply punctuation to *score* and return rendered score + report."""

    active_rule = rule or PunctuationRule()
    rendered = apply_punctuation(
        score,
        k=k,
        seeds=seeds,
        roles=roles,
        rule=active_rule,
    )
    kind = _score_kind(score)
    if kind == "unsupported":
        return rendered, PunctuationReport(
            score_kind="unsupported",
            total_extended_terminals=0,
            total_inserted_breaths=0,
            lane_stats=(),
        )

    stats: list[LanePunctuationStat] = []
    total_extended_terminals = 0
    total_inserted_breaths = 0
    for original_lane, rendered_lane in _lane_pairs(score, rendered, kind):
        stat = lane_punctuation_stat(
            original_lane,
            rendered_lane,
            rule=active_rule,
        )
        stats.append(stat)
        total_extended_terminals += stat.extended_terminal_count
        total_inserted_breaths += stat.inserted_breath_count

    return rendered, PunctuationReport(
        score_kind=kind,
        total_extended_terminals=total_extended_terminals,
        total_inserted_breaths=total_inserted_breaths,
        lane_stats=tuple(stats),
    )


def summarize_punctuation_report(
    report: PunctuationReport,
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
                "terminal_note_count": stat.terminal_note_count,
                "extended_terminal_count": stat.extended_terminal_count,
                "inserted_breath_count": stat.inserted_breath_count,
                "mean_terminal_multiplier": stat.mean_terminal_multiplier,
                "mean_breath_ms": stat.mean_breath_ms,
                "applies": stat.applies,
            }
        )
    return {
        "score_kind": report.score_kind,
        "total_extended_terminals": report.total_extended_terminals,
        "total_inserted_breaths": report.total_inserted_breaths,
        "lane_count": len(report.lane_stats),
        "applied_lane_count": applied_count,
        "lanes": lanes,
    }
