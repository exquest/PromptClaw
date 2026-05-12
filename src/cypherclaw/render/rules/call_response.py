"""R11 Call-Response Gating: follower phrase intent complements leader's realized performance."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cypherclaw.render.events import Event
from cypherclaw.render.role_gate import role_is_eligible


_CR_ROLE_KEYS = ("call_response_role", "cr_role", "ensemble_role")
_FOLLOWER_VALUES = frozenset({"follower", "follow", "response", "support"})
_LEADER_VALUES = frozenset({"leader", "lead", "call"})
_SKIP_VALUES = frozenset({"solo", "tacet", "silent"})


@dataclass
class PerformedPart:
    """Snapshot of the leader voice's realized phrase shape at a given position."""

    contour_apex: float = 0.0
    amp_curve: float = 1.0
    is_building: bool = False
    is_pausing: bool = False


def _call_response_role(metadata: Mapping[str, object] | None) -> str | None:
    if not metadata:
        return None
    for key in _CR_ROLE_KEYS:
        value = metadata.get(key)
        if value is not None:
            text = str(value).strip().lower()
            if text in _FOLLOWER_VALUES:
                return "follower"
            if text in _LEADER_VALUES:
                return "leader"
            if text in _SKIP_VALUES:
                return text
    return None


@dataclass
class CallResponseRule:
    """R11: follower phrase intent complements leader's realized performance."""

    complement_strength: float = 0.5

    rule_id = "R11"

    def applies_to(
        self, role: str, metadata: Mapping[str, object] | None = None
    ) -> bool:
        if not role_is_eligible(role, metadata):
            return False
        return _call_response_role(metadata) == "follower"

    def apply(
        self, event: Event, leader_part: PerformedPart | None = None
    ) -> None:
        if leader_part is None:
            return
        if not self.applies_to(event.role, event.metadata):
            return

        k = self.complement_strength

        if leader_part.is_building:
            self._descend_from_apex(event, leader_part, k)
        elif leader_part.is_pausing:
            self._fill(event, leader_part, k)
        else:
            self._complement(event, leader_part, k)

    def _descend_from_apex(
        self, event: Event, leader: PerformedPart, k: float
    ) -> None:
        event.amp_mult *= 1.0 - k * leader.amp_curve * 0.6
        event.contour_apex = (
            event.contour_apex * (1.0 - k)
            + (1.0 - leader.contour_apex) * k
        )
        event.tempo_mult *= 1.0 + k * 0.02

    def _fill(
        self, event: Event, leader: PerformedPart, k: float
    ) -> None:
        event.amp_mult *= 1.0 + k * 0.5
        event.contour_apex += k * (1.0 - leader.amp_curve) * 0.4
        event.tempo_mult *= 1.0 - k * 0.02

    def _complement(
        self, event: Event, leader: PerformedPart, k: float
    ) -> None:
        complement = 1.0 - leader.amp_curve
        event.amp_mult *= 1.0 + k * (complement - 0.5) * 0.4
        event.contour_apex = (
            event.contour_apex * (1.0 - k * 0.3)
            + (1.0 - leader.contour_apex) * k * 0.3
        )
