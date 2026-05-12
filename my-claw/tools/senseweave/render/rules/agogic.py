"""R3 agogic accent shaping."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
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

DEFAULT_DURATION_MULTIPLIER = 1.10
DEFAULT_VELOCITY_GAIN_DB = 3.5
MAX_DURATION_MULTIPLIER = 1.15
MAX_VELOCITY_GAIN_DB = 6.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _metadata_float(metadata: Mapping[str, object], key: str) -> float | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def detect_contour_apex(steps: Sequence[TrackerStep]) -> int | None:
    """Return the strongest local up-down contour apex index, if any."""

    if len(steps) < 3:
        return None

    candidates: list[tuple[int, int, int]] = []
    for index in range(1, len(steps) - 1):
        previous_degree = steps[index - 1].scale_degree
        degree = steps[index].scale_degree
        next_degree = steps[index + 1].scale_degree
        if previous_degree < degree and degree > next_degree:
            prominence = min(degree - previous_degree, degree - next_degree)
            candidates.append((degree, prominence, -index))

    if not candidates:
        return None
    _degree, _prominence, negative_index = max(candidates)
    return -negative_index


def detect_harmonic_charge_peak(steps: Sequence[TrackerStep]) -> int | None:
    """Return the unique harmonic-charge peak index, if one is present."""

    charges = [
        (index, charge)
        for index, step in enumerate(steps)
        if (charge := _metadata_float(step.metadata, "harmonic_charge")) is not None
    ]
    if len(charges) < 2:
        return None

    values = [charge for _index, charge in charges]
    peak = max(values)
    if math.isclose(peak, min(values)):
        return None
    if values.count(peak) > 1:
        return None
    return next(index for index, charge in charges if charge == peak)


def _phrase_group_key(step: TrackerStep) -> str:
    for key in ("phrase_id", "phrase_index", "repeat_cycle"):
        value = step.metadata.get(key)
        if value:
            return f"{key}:{value}"
    return "lane"


def _accent_index_for_phrase(steps: Sequence[TrackerStep]) -> int | None:
    charge_index = detect_harmonic_charge_peak(steps)
    if charge_index is not None:
        return charge_index
    return detect_contour_apex(steps)


def _scaled_length(length_rows: int, *, duration_multiplier: float, k: float) -> int:
    multiplier = 1.0 + ((duration_multiplier - 1.0) * k)
    multiplier = _clamp(multiplier, 1.0, MAX_DURATION_MULTIPLIER)
    return max(1, int(round(length_rows * multiplier)))


def _scaled_velocity(velocity: float, *, velocity_gain_db: float, k: float) -> float:
    gain_db = _clamp(velocity_gain_db * k, 0.0, MAX_VELOCITY_GAIN_DB)
    multiplier = 10.0 ** (gain_db / 20.0)
    shaped = velocity * multiplier
    return round(_clamp(shaped, 0.0, 1.0), 3)


def _apply_accent_to_step(
    step: TrackerStep,
    *,
    duration_multiplier: float,
    velocity_gain_db: float,
    k: float,
) -> TrackerStep:
    if _metadata_is_grid_locked(step.metadata):
        return step
    return replace(
        step,
        length_rows=_scaled_length(
            step.length_rows,
            duration_multiplier=duration_multiplier,
            k=k,
        ),
        velocity=_scaled_velocity(
            step.velocity,
            velocity_gain_db=velocity_gain_db,
            k=k,
        ),
    )


@dataclass(frozen=True)
class AgogicAccentRule:
    """Lengthen and emphasize one contour or harmonic apex per phrase."""

    duration_multiplier: float = DEFAULT_DURATION_MULTIPLIER
    velocity_gain_db: float = DEFAULT_VELOCITY_GAIN_DB

    rule_id = "R3"

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
        return apply_agogic_accent(score, k=k, roles=roles, rule=self)


def _apply_to_lane(
    lane: TrackerLane,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: AgogicAccentRule,
) -> TrackerLane:
    normalized_role = lane.role.strip().lower()
    if roles is not None and normalized_role not in {role.strip().lower() for role in roles}:
        return lane
    if not rule.applies_to(lane.role, lane.metadata):
        return lane

    groups: dict[str, list[tuple[int, TrackerStep]]] = {}
    for index, step in enumerate(lane.steps):
        groups.setdefault(_phrase_group_key(step), []).append((index, step))

    accent_indices: set[int] = set()
    for group in groups.values():
        group_steps = [step for _index, step in group]
        group_accent_index = _accent_index_for_phrase(group_steps)
        if group_accent_index is not None:
            accent_indices.add(group[group_accent_index][0])

    if not accent_indices:
        return lane

    return replace(
        lane,
        steps=[
            _apply_accent_to_step(
                step,
                duration_multiplier=rule.duration_multiplier,
                velocity_gain_db=rule.velocity_gain_db,
                k=k,
            )
            if index in accent_indices
            else step
            for index, step in enumerate(lane.steps)
        ],
    )


def _apply_to_pattern(
    pattern: TrackerPattern,
    *,
    k: float,
    roles: frozenset[str] | None,
    rule: AgogicAccentRule,
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
    rule: AgogicAccentRule,
) -> TrackerScene:
    return replace(
        scene,
        pattern=_apply_to_pattern(scene.pattern, k=k, roles=roles, rule=rule),
    )


def apply_agogic_accent(
    score: Any,
    *,
    k: float = 1.0,
    roles: frozenset[str] | None = None,
    rule: AgogicAccentRule | None = None,
) -> Any:
    """Apply R3 agogic accent shaping to tracker scenes or songs."""

    if k == 0.0:
        return score
    active_rule = rule or AgogicAccentRule()
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
