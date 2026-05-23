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

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any


AFFECTIVE_STATE_BUS_INDEX = 100
AFFECTIVE_STATE_BUS_CHANNELS = 1
AFFECTIVE_STATE_BUS_MIN = 0.0
AFFECTIVE_STATE_BUS_MAX = 1.0
AFFECTIVE_STATE_BUS_DECAY_SECONDS = 5.0

# Per PRD §7.5.2: each voice writes a rolling-window estimate of its own
# expression intensity, averaged over the last ~2 seconds.
AFFECTIVE_STATE_BUS_WINDOW_SECONDS = 2.0

# Per PRD §7.5.2: "weighted sum of (vibrato depth, tremolo depth, dynamics,
# pitch-bend extent) normalized to [0,1]". The PRD doesn't pin specific
# weights; equal contribution is the documented baseline.
AFFECTIVE_STATE_BUS_INTENSITY_WEIGHTS: dict[str, float] = {
    "vibrato_depth": 0.25,
    "tremolo_depth": 0.25,
    "dynamics": 0.25,
    "pitch_bend_extent": 0.25,
}


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


def affective_state_bus_decay(
    initial: float,
    elapsed_seconds: float,
    tau: float = AFFECTIVE_STATE_BUS_DECAY_SECONDS,
) -> float:
    """Exponential slow-decay toward 0 with time constant ``tau`` seconds.

    Returns ``initial * exp(-elapsed / tau)`` clamped to the bus range.
    ``elapsed_seconds <= 0`` returns the clamped initial value unchanged
    (no time has passed). Negative or zero ``tau`` is rejected.
    """
    if tau <= 0:
        raise ValueError("tau must be positive")
    clamped_initial = _clamp_affect(initial)
    if elapsed_seconds <= 0:
        return clamped_initial
    return _clamp_affect(clamped_initial * math.exp(-float(elapsed_seconds) / float(tau)))


def voice_expression_intensity(
    vibrato_depth: float = 0.0,
    tremolo_depth: float = 0.0,
    dynamics: float = 0.0,
    pitch_bend_extent: float = 0.0,
) -> float:
    """Weighted sum of the four expression channels, clamped to [0, 1]."""
    components = {
        "vibrato_depth": vibrato_depth,
        "tremolo_depth": tremolo_depth,
        "dynamics": dynamics,
        "pitch_bend_extent": pitch_bend_extent,
    }
    total = sum(
        AFFECTIVE_STATE_BUS_INTENSITY_WEIGHTS[name] * _clamp_affect(value)
        for name, value in components.items()
    )
    return _clamp_affect(total)


@dataclass
class _VoiceWindow:
    samples: deque[tuple[float, float]] = field(default_factory=deque)

    def add(self, value: float, now: float) -> None:
        self.samples.append((float(now), _clamp_affect(value)))

    def prune(self, now: float, window_seconds: float) -> None:
        cutoff = float(now) - window_seconds
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

    def mean(self) -> float:
        if not self.samples:
            return 0.0
        return sum(v for _, v in self.samples) / len(self.samples)


class AffectiveStateBusWriter:
    """Per-voice rolling-window writer for the shared affective_state_bus.

    Each voice contributes intensity samples via :meth:`update`. On
    :meth:`flush`, the writer prunes samples older than the configured
    window (default ~2s), computes each voice's mean, and emits one
    ``/c_set`` per active voice to the shared bus. Voices are emitted in
    ascending order so the bus settles at the max-pooled value — the
    semantics required by PRD §7.5.2 / CC-071. The trace therefore shows
    one OSC write per active voice each tick, all within [0, 1].
    """

    def __init__(
        self,
        window_seconds: float = AFFECTIVE_STATE_BUS_WINDOW_SECONDS,
        decay_tau_seconds: float = AFFECTIVE_STATE_BUS_DECAY_SECONDS,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if decay_tau_seconds <= 0:
            raise ValueError("decay_tau_seconds must be positive")
        self.window_seconds = float(window_seconds)
        self.decay_tau_seconds = float(decay_tau_seconds)
        self._voices: dict[str, _VoiceWindow] = {}
        self._last_bus_value: float = 0.0
        self._last_bus_time: float | None = None

    def update(self, voice_id: str, intensity: float, *, now: float) -> float:
        """Record ``intensity`` (clamped to [0,1]) for ``voice_id`` at ``now``."""
        window = self._voices.setdefault(voice_id, _VoiceWindow())
        clamped = _clamp_affect(intensity)
        window.add(clamped, now)
        return clamped

    def voice_window_mean(self, voice_id: str, *, now: float) -> float:
        """Return the rolling-window mean for ``voice_id`` at ``now``."""
        window = self._voices.get(voice_id)
        if window is None:
            return 0.0
        window.prune(now, self.window_seconds)
        return window.mean()

    def seed(self, client: Any, value: float, *, now: float) -> float:
        """Seed the bus and bookkeeping state to ``value`` at ``now``.

        Provided so callers can start a decay test (or boot the runtime)
        from a known bus value without having to fake contributor history.
        """
        seeded = seed_affective_state_bus(client, value)
        self._last_bus_value = seeded
        self._last_bus_time = float(now)
        return seeded

    def flush(self, client: Any, *, now: float) -> float:
        """Write per-voice means to the bus; return the bus value after the tick.

        With active contributors: sends one ``/c_set`` per voice with
        samples in the current window, ordered by mean ascending so the
        bus ends at the max value. Voices whose windows are empty after
        pruning are dropped from the trace.

        With no active contributors: emits a single ``/c_set`` with the
        exponentially-decayed value (time constant
        :attr:`decay_tau_seconds`) computed from the last bus value and
        the elapsed time. This is the slow-decay-toward-0 behavior
        required by PRD §7.5.2.
        """
        active: list[tuple[str, float]] = []
        for voice_id, window in self._voices.items():
            window.prune(now, self.window_seconds)
            if not window.samples:
                continue
            active.append((voice_id, window.mean()))
        active.sort(key=lambda item: (item[1], item[0]))
        if active:
            max_pooled = 0.0
            for _, mean in active:
                client.send_message("/c_set", [AFFECTIVE_STATE_BUS_INDEX, mean])
                if mean > max_pooled:
                    max_pooled = mean
            self._last_bus_value = max_pooled
            self._last_bus_time = float(now)
            return max_pooled
        if self._last_bus_time is None or self._last_bus_value <= AFFECTIVE_STATE_BUS_MIN:
            self._last_bus_time = float(now)
            return self._last_bus_value
        elapsed = float(now) - self._last_bus_time
        decayed = affective_state_bus_decay(
            self._last_bus_value, elapsed, self.decay_tau_seconds
        )
        client.send_message("/c_set", [AFFECTIVE_STATE_BUS_INDEX, decayed])
        self._last_bus_value = decayed
        self._last_bus_time = float(now)
        return decayed
