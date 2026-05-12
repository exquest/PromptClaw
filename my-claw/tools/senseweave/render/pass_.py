"""Ordered render-pass framework for the SenseWeave render layer.

Rule execution order is fixed and canonical:
R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8 → R9 → R10 → R11 → R12

Rules not in RULE_ORDER are appended after R12 in registration order.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

RULE_ORDER: tuple[str, ...] = (
    "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12",
)

_RULE_ORDER_INDEX: dict[str, int] = {rid: i for i, rid in enumerate(RULE_ORDER)}


@runtime_checkable
class RenderRule(Protocol):
    @property
    def rule_id(self) -> str: ...

    def apply(
        self,
        score: Any,
        *,
        k: float,
        seeds: Mapping[str, int] | None,
        roles: frozenset[str] | None,
    ) -> Any: ...


@dataclass(frozen=True)
class PerformedPart:
    score: Any
    applied_rules: tuple[str, ...]
    quantities: dict[str, float]
    metadata: dict[str, str] = field(default_factory=dict)


def _rule_id(rule: object) -> str:
    for attr in ("rule_id", "id"):
        value = getattr(rule, attr, None)
        if isinstance(value, str) and value:
            return value
    raise TypeError("render rule must define a non-empty string rule_id or id")


def _roles_allowed_by_rule(rule: object, roles: frozenset[str] | None) -> frozenset[str] | None:
    if roles is None:
        return None
    applies_to = getattr(rule, "applies_to", None)
    if not callable(applies_to):
        return roles
    return frozenset(role for role in roles if applies_to(role))


class RenderPass:
    """Ordered rule stack with per-rule enable flags, quantities, and role gating."""

    __slots__ = ("_rules", "_enabled", "_quantities", "_role_gates")

    def __init__(
        self,
        rules: Sequence[Any],
        enabled_flags: Mapping[str, bool] | None = None,
        quantities: Mapping[str, float] | None = None,
        *,
        role_gates: Mapping[str, frozenset[str]] | None = None,
    ) -> None:
        enabled = dict(enabled_flags or {})
        quants = dict(quantities or {})
        gates = dict(role_gates or {})

        by_id: dict[str, Any] = {}
        insertion: list[tuple[str, Any]] = []
        for rule in rules:
            rid = _rule_id(rule)
            if rid in by_id:
                raise ValueError(f"duplicate rule id: {rid}")
            by_id[rid] = rule
            insertion.append((rid, rule))

        ordered: list[tuple[str, Any]] = []
        canonical = set(RULE_ORDER)
        for slot in RULE_ORDER:
            if slot in by_id:
                ordered.append((slot, by_id[slot]))
        for rid, rule in insertion:
            if rid not in canonical:
                ordered.append((rid, rule))

        self._rules: tuple[tuple[str, Any], ...] = tuple(ordered)
        self._enabled: dict[str, bool] = enabled
        self._quantities: dict[str, float] = quants
        self._role_gates: dict[str, frozenset[str]] = gates

    @property
    def rule_order(self) -> tuple[str, ...]:
        return tuple(rid for rid, _rule in self._rules)

    def effective_k(self, rule_id: str) -> float:
        if not self._enabled.get(rule_id, True):
            return 0.0
        return self._quantities.get(rule_id, 1.0)

    def apply(
        self,
        score_tree: Any,
        seeds: Mapping[str, int] | None = None,
        *,
        quantity_overrides: Mapping[str, float] | None = None,
    ) -> PerformedPart:
        overrides = quantity_overrides or {}
        score = score_tree
        applied: list[str] = []
        effective: dict[str, float] = {}

        for rid, rule in self._rules:
            k = overrides[rid] if rid in overrides else self.effective_k(rid)
            effective[rid] = k
            if k == 0.0:
                continue
            roles = self._role_gates.get(rid)
            roles = _roles_allowed_by_rule(rule, roles)
            if roles == frozenset():
                continue
            score = rule.apply(score, k=k, seeds=seeds, roles=roles)
            applied.append(rid)

        return PerformedPart(
            score=score,
            applied_rules=tuple(applied),
            quantities=effective,
        )
