from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from cypherclaw.render.events import Event
from cypherclaw.render.role_gate import role_is_eligible

LISTENER_JND_MS: Final[float] = 10.0


def _gaussian_jitter(step_index: int, seed: int, sigma: float) -> float:
    if sigma == 0.0:
        return 0.0
    h = hashlib.sha256(struct.pack(">QQ", step_index & 0xFFFFFFFFFFFFFFFF, seed & 0xFFFFFFFFFFFFFFFF)).digest()
    u1 = (int.from_bytes(h[:8], "big") + 1) / (2**64 + 1)
    u2 = (int.from_bytes(h[8:16], "big") + 1) / (2**64 + 1)
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return z * sigma


@dataclass
class MicrotimingRule:
    sigma_melodic_ms: float = 3.0
    seed: int = 0

    rule_id = "R8"

    def __post_init__(self) -> None:
        if self.sigma_melodic_ms > LISTENER_JND_MS:
            raise ValueError(
                f"sigma_melodic_ms={self.sigma_melodic_ms} exceeds JND ({LISTENER_JND_MS} ms)"
            )

    def applies_to(self, role: str, metadata: Mapping[str, object] | None = None) -> bool:
        return role_is_eligible(role, metadata)

    def apply(self, event: Event) -> None:
        if not self.applies_to(event.role, event.metadata):
            event.timing_deviation_ms = 0.0  # type: ignore[attr-defined]
            return
        step_index = int(getattr(event, "step_index", 0) or 0)
        deviation = _gaussian_jitter(step_index, self.seed, self.sigma_melodic_ms)
        event.timing_deviation_ms = deviation  # type: ignore[attr-defined]
