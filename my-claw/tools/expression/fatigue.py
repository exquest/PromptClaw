"""Per-voice cumulative expression fatigue counter with exponential decay.

Per the CypherClaw v2 PRD (§7.5.2 / CC-080..084), each voice accumulates an
expression "load" (vibrato depth + tremolo depth + pitch-bend extent +
gesture-intensity-weight) per note. The counter decays exponentially with a
half-life of ~30 seconds so that long silences and soft passages let the
voice "recover."

This module owns the decay envelope and the per-voice bookkeeping that
later tasks build on: the threshold-based fatigue multiplier (CC-081),
the recovery behavior (CC-082), and the ``CYPHERCLAW_V2_FATIGUE`` env-gate
(CC-083). Counter state is in-process only — composer restarts produce
fresh, rested voices, as the PRD requires.
"""
from __future__ import annotations

from dataclasses import dataclass


# PRD §7.5.2 / CC-080: half-life of ~30 seconds for the exponential decay.
FATIGUE_HALF_LIFE_SECONDS = 30.0


def fatigue_decay_factor(
    elapsed_seconds: float,
    half_life_seconds: float = FATIGUE_HALF_LIFE_SECONDS,
) -> float:
    """Return ``0.5 ** (elapsed / half_life)`` for ``elapsed_seconds >= 0``.

    Negative elapsed time clamps to 0 (no decay). ``half_life_seconds`` must
    be positive; zero or negative values are rejected because the decay
    envelope is undefined there.
    """
    if half_life_seconds <= 0:
        raise ValueError("half_life_seconds must be positive")
    if elapsed_seconds <= 0:
        return 1.0
    return 0.5 ** (float(elapsed_seconds) / float(half_life_seconds))


@dataclass
class _VoiceFatigue:
    value: float = 0.0
    last_update: float = 0.0


class FatigueCounter:
    """Per-voice expression fatigue with exponential decay.

    Each call to :meth:`add_note` decays the voice's current load by the
    time elapsed since its last update, then adds the new note's load.
    :meth:`value` returns the decayed load at a given time without
    mutating state — useful for read-only checks (e.g. the T-008
    threshold gate).
    """

    def __init__(self, half_life_seconds: float = FATIGUE_HALF_LIFE_SECONDS) -> None:
        if half_life_seconds <= 0:
            raise ValueError("half_life_seconds must be positive")
        self.half_life_seconds = float(half_life_seconds)
        self._voices: dict[str, _VoiceFatigue] = {}

    def _decayed(self, voice_id: str, now: float) -> float:
        state = self._voices.get(voice_id)
        if state is None:
            return 0.0
        elapsed = float(now) - state.last_update
        return state.value * fatigue_decay_factor(elapsed, self.half_life_seconds)

    def add_note(self, voice_id: str, load: float, *, now: float) -> float:
        """Decay the voice's load to ``now``, add ``load``, return the new value.

        ``load`` is clipped at 0 — a single note cannot reduce fatigue.
        """
        decayed = self._decayed(voice_id, now)
        new_value = decayed + max(0.0, float(load))
        self._voices[voice_id] = _VoiceFatigue(value=new_value, last_update=float(now))
        return new_value

    def value(self, voice_id: str, *, now: float) -> float:
        """Return the decayed counter for ``voice_id`` at ``now`` (non-mutating)."""
        return self._decayed(voice_id, now)

    def reset(self, voice_id: str | None = None) -> None:
        """Clear one voice's state, or all voices when ``voice_id`` is None."""
        if voice_id is None:
            self._voices.clear()
        else:
            self._voices.pop(voice_id, None)
