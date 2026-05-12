from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from cypherclaw.render.events import Event
from cypherclaw.render.role_gate import role_is_eligible


@dataclass
class FinalRitRule:
    alpha: float = 0.35
    onset_position: float = 0.75

    rule_id = "R5"

    def applies_to(self, role: str, metadata: Mapping[str, object] | None = None) -> bool:
        return role_is_eligible(role, metadata)

    def apply(self, event: Event) -> None:
        if not self.applies_to(event.role, event.metadata):
            return
        phrase = event.phrase
        if not _is_cadential(event, phrase):
            return

        x_start = self.onset_position
        x_end = 1.0
        x = event.normalized_phrase_position
        if x < x_start or x_start >= x_end:
            return

        progress = min(1.0, max(0.0, (x - x_start) / (x_end - x_start)))
        event.tempo_mult *= math.sqrt(max(0.0, 1.0 - self.alpha * progress))


def _is_cadential(event: Event, phrase: object | None) -> bool:
    if event.is_cadential:
        return True
    if getattr(phrase, "is_cadential", False) is True:
        return True
    metadata = getattr(phrase, "metadata", None)
    return isinstance(metadata, Mapping) and str(metadata.get("is_cadential", "")).lower() == "true"
