"""Provision the shared `affective_state_bus` SuperCollider control bus.

Per the CypherClaw v2 PRD (§7.5.2 / CC-070..073), a single SuperCollider
control bus holds a float in [0.0, 1.0] — the ensemble's current
"affective state." Each voice writes its rolling-window expression
intensity (max-pooled across voices) and reads the bus to scale its own
modulator depths via ``(1 + coupling_strength * affect)``. The bus
slow-decays toward 0 with a ~5s time constant in the absence of
contributors.

This module owns the bus *index* — the contract between the Python OSC
client and the SuperCollider server. T-002 builds the per-voice writer
wiring on top, T-003 the reader-side coupling, and T-004 the slow-decay
synth. The companion source stub
``synthesis/affective_state_bus.scd`` mirrors these constants on the
server side; tests pin the two in lockstep.
"""
from __future__ import annotations

from typing import Any


AFFECTIVE_STATE_BUS_INDEX = 100
AFFECTIVE_STATE_BUS_CHANNELS = 1
AFFECTIVE_STATE_BUS_MIN = 0.0
AFFECTIVE_STATE_BUS_MAX = 1.0
AFFECTIVE_STATE_BUS_DECAY_SECONDS = 5.0


def _clamp_affect(value: float) -> float:
    return max(AFFECTIVE_STATE_BUS_MIN, min(AFFECTIVE_STATE_BUS_MAX, float(value)))


def affective_state_bus_c_set_args(value: float = 0.0) -> list[float | int]:
    """Return `/c_set` args that seed the bus to ``value`` (clamped to [0,1])."""
    return [AFFECTIVE_STATE_BUS_INDEX, _clamp_affect(value)]


def seed_affective_state_bus(client: Any, value: float = 0.0) -> float:
    """Seed the bus on ``client`` (an OSC sender). Returns the seeded value."""
    args = affective_state_bus_c_set_args(value)
    client.send_message("/c_set", args)
    return float(args[1])
