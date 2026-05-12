"""R10 Silence Budget: per-voice rest accumulators enforced at phrase boundaries."""
from __future__ import annotations

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
from .metric_accent import role_is_eligible

DEFAULT_TARGET_DENSITY = 0.7
DEFAULT_THRESHOLD = 4.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _note_density(steps: list[TrackerStep]) -> float:
    if not steps:
        return 0.0
    total = sum(s.length_rows for s in steps)
    if total == 0:
        return 0.0
    sounding = sum(s.length_rows for s in steps if s.velocity > 0.0)
    return sounding / total


def _duration_rows(steps: list[TrackerStep]) -> float:
    return float(sum(s.length_rows for s in steps))


def _ordered_phrases(
    steps: list[TrackerStep],
) -> list[tuple[str, list[int]]]:
    seen: dict[str, list[int]] = {}
    order: list[str] = []
    for idx, step in enumerate(steps):
        pid = step.metadata.get("phrase_id")
        if pid is None:
            continue
        if pid not in seen:
            seen[pid] = []
            order.append(pid)
        seen[pid].append(idx)
    return [(pid, seen[pid]) for pid in order]


def _find_breath_between(
    steps: list[TrackerStep], after_idx: int, before_idx: int,
) -> int | None:
    for idx in range(after_idx + 1, before_idx):
        if steps[idx].metadata.get("breath_r6") == "true":
            return idx
    return None


def _apply_to_lane(
    lane: TrackerLane,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: SilenceBudgetRule,
) -> TrackerLane:
    normalized_role = lane.role.strip().lower()
    if roles is not None and normalized_role not in {r.strip().lower() for r in roles}:
        return lane
    if not rule.applies_to(lane.role, lane.metadata):
        return lane
    if not lane.steps:
        return lane

    phrases = _ordered_phrases(lane.steps)
    if len(phrases) < 2:
        return lane

    rest_budget = 0.0
    breath_ext_indices: set[int] = set()
    tacet_indices: set[int] = set()

    for i, (pid, indices) in enumerate(phrases):
        phrase_steps = [lane.steps[j] for j in indices]

        restraint = 0.0
        if phrase_steps and "restraint" in phrase_steps[0].metadata:
            try:
                restraint = float(phrase_steps[0].metadata["restraint"])
            except (ValueError, TypeError):
                pass
        elif lane.metadata and "restraint" in lane.metadata:
            try:
                restraint = float(lane.metadata["restraint"]) # type: ignore[arg-type]
            except (ValueError, TypeError):
                pass
        restraint = max(0.0, min(1.0, restraint))

        actual = _note_density(phrase_steps)
        dt = _duration_rows(phrase_steps)
        rest_budget += (rule.target_density - actual) * dt * k

        threshold = rule.threshold * (1.0 + restraint)

        if rest_budget >= threshold and i + 1 < len(phrases):
            last_idx = max(indices)
            next_first_idx = min(phrases[i + 1][1])
            breath_idx = _find_breath_between(lane.steps, last_idx, next_first_idx)

            if breath_idx is not None:
                breath_ext_indices.add(breath_idx)
            else:
                tacet_indices.update(phrases[i + 1][1])

            rest_budget = 0.0

    if not breath_ext_indices and not tacet_indices:
        return lane

    new_steps: list[TrackerStep] = []
    for idx, step in enumerate(lane.steps):
        if idx in breath_ext_indices:
            new_steps.append(replace(
                step,
                length_rows=step.length_rows * 2,
                metadata={**step.metadata, "silence_budget_breath_ext": "true"},
            ))
        elif idx in tacet_indices:
            new_steps.append(replace(
                step,
                velocity=0.0,
                metadata={**step.metadata, "silence_budget_tacet": "true"},
            ))
        else:
            new_steps.append(step)

    return replace(lane, steps=new_steps)


@dataclass(frozen=True)
class SilenceBudgetRule:
    """R10: per-voice rest accumulators enforced at phrase boundaries."""

    target_density: float = DEFAULT_TARGET_DENSITY
    threshold: float = DEFAULT_THRESHOLD

    rule_id = "R10"

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
        return apply_silence_budget(score, k=k, seeds=seeds, roles=roles, rule=self)


def _apply_to_pattern(
    pattern: TrackerPattern,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: SilenceBudgetRule,
) -> TrackerPattern:
    return replace(
        pattern,
        lanes=[
            _apply_to_lane(lane, k=k, roles=roles, rule=rule)
            for lane in pattern.lanes
        ],
    )


def _apply_to_scene(
    scene: TrackerScene,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: SilenceBudgetRule,
) -> TrackerScene:
    return replace(
        scene,
        pattern=_apply_to_pattern(scene.pattern, k=k, roles=roles, rule=rule),
    )


def apply_silence_budget(
    score: Any,
    *,
    k: float = 1.0,
    seeds: Mapping[str, int] | None = None,
    roles: frozenset[str] | None = None,
    rule: SilenceBudgetRule | None = None,
) -> Any:
    """Apply R10 silence budget to tracker scenes or songs."""
    if k == 0.0:
        return score
    active_rule = rule or SilenceBudgetRule()
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
class LaneSilenceBudgetStat:
    """Per-lane silence-budget outcome from one apply pass."""

    lane_name: str
    role: str
    step_count: int
    phrase_count: int
    breath_extension_count: int
    tacet_step_count: int
    tacet_phrase_count: int
    applies: bool


@dataclass(frozen=True)
class SilenceBudgetReport:
    """Aggregate silence-budget outcome for one score."""

    score_kind: str
    total_breath_extensions: int
    total_tacet_steps: int
    lane_stats: tuple[LaneSilenceBudgetStat, ...]


def _is_breath_extension(step: TrackerStep) -> bool:
    return step.metadata.get("silence_budget_breath_ext") == "true"


def _is_tacet_step(step: TrackerStep) -> bool:
    return step.metadata.get("silence_budget_tacet") == "true"


def _phrase_count(steps: list[TrackerStep]) -> int:
    seen: set[str] = set()
    for step in steps:
        pid = step.metadata.get("phrase_id")
        if isinstance(pid, str) and pid:
            seen.add(pid)
    return len(seen)


def lane_silence_budget_stat(
    original: TrackerLane,
    rendered: TrackerLane,
    *,
    rule: SilenceBudgetRule,
) -> LaneSilenceBudgetStat:
    """Compare *original* and *rendered* lanes and report R10 shaping."""

    breath_extension_count = 0
    tacet_step_count = 0
    tacet_phrase_ids: set[str] = set()
    for step in rendered.steps:
        if _is_breath_extension(step):
            breath_extension_count += 1
        if _is_tacet_step(step):
            tacet_step_count += 1
            pid = step.metadata.get("phrase_id")
            if isinstance(pid, str) and pid:
                tacet_phrase_ids.add(pid)

    return LaneSilenceBudgetStat(
        lane_name=rendered.name,
        role=rendered.role,
        step_count=len(rendered.steps),
        phrase_count=_phrase_count(original.steps),
        breath_extension_count=breath_extension_count,
        tacet_step_count=tacet_step_count,
        tacet_phrase_count=len(tacet_phrase_ids),
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


def analyze_silence_budget(
    score: Any,
    *,
    k: float = 1.0,
    seeds: Mapping[str, int] | None = None,
    roles: frozenset[str] | None = None,
    rule: SilenceBudgetRule | None = None,
) -> tuple[Any, SilenceBudgetReport]:
    """Apply silence budget to *score* and return rendered score + report."""

    active_rule = rule or SilenceBudgetRule()
    rendered = apply_silence_budget(
        score,
        k=k,
        seeds=seeds,
        roles=roles,
        rule=active_rule,
    )
    kind = _score_kind(score)
    if kind == "unsupported":
        return rendered, SilenceBudgetReport(
            score_kind="unsupported",
            total_breath_extensions=0,
            total_tacet_steps=0,
            lane_stats=(),
        )

    stats: list[LaneSilenceBudgetStat] = []
    total_breath_extensions = 0
    total_tacet_steps = 0
    for original_lane, rendered_lane in _lane_pairs(score, rendered, kind):
        stat = lane_silence_budget_stat(
            original_lane,
            rendered_lane,
            rule=active_rule,
        )
        stats.append(stat)
        total_breath_extensions += stat.breath_extension_count
        total_tacet_steps += stat.tacet_step_count

    return rendered, SilenceBudgetReport(
        score_kind=kind,
        total_breath_extensions=total_breath_extensions,
        total_tacet_steps=total_tacet_steps,
        lane_stats=tuple(stats),
    )


def summarize_silence_budget_report(
    report: SilenceBudgetReport,
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
                "phrase_count": stat.phrase_count,
                "breath_extension_count": stat.breath_extension_count,
                "tacet_step_count": stat.tacet_step_count,
                "tacet_phrase_count": stat.tacet_phrase_count,
                "applies": stat.applies,
            }
        )
    return {
        "score_kind": report.score_kind,
        "total_breath_extensions": report.total_breath_extensions,
        "total_tacet_steps": report.total_tacet_steps,
        "lane_count": len(report.lane_stats),
        "applied_lane_count": applied_count,
        "lanes": lanes,
    }
