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
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass


# PRD §7.5.2 / CC-083: the entire fatigue feature is gated by
# ``CYPHERCLAW_V2_FATIGUE``, default OFF.
CYPHERCLAW_V2_FATIGUE_ENV = "CYPHERCLAW_V2_FATIGUE"
_FATIGUE_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})


def fatigue_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True iff ``CYPHERCLAW_V2_FATIGUE`` is set to a truthy value.

    Default OFF: an unset, empty, or non-truthy value resolves to False.
    """
    source = os.environ if env is None else env
    raw = source.get(CYPHERCLAW_V2_FATIGUE_ENV)
    if raw is None:
        return False
    return raw.strip().lower() in _FATIGUE_TRUE_VALUES


# PRD §7.5.2 / CC-080: half-life of ~30 seconds for the exponential decay.
FATIGUE_HALF_LIFE_SECONDS = 30.0

# PRD §7.5.2 / CC-081: threshold above which a fatigue multiplier is applied to
# subsequent expression-parameter magnitudes, plus the multiplier's maximum
# reduction (defaults: 0.7 and 0.5 — see PRD "Open Questions / Tuning").
FATIGUE_THRESHOLD = 0.7
FATIGUE_REDUCTION = 0.5


def fatigue_multiplier(
    counter_value: float,
    threshold: float = FATIGUE_THRESHOLD,
    reduction: float = FATIGUE_REDUCTION,
    *,
    env: Mapping[str, str] | None = None,
) -> float:
    """Return the multiplier for expression parameters at ``counter_value``.

    Below or at ``threshold`` the multiplier is ``1.0`` (no reduction). Above
    the threshold it follows the PRD formula
    ``1 - reduction * clamp(counter_value, 0.0, 1.0)``.

    Per CC-083, this returns ``1.0`` (no reduction) when the
    ``CYPHERCLAW_V2_FATIGUE`` environment flag is OFF.
    """
    if not fatigue_enabled(env):
        return 1.0
    if counter_value <= threshold:
        return 1.0
    normalized = min(1.0, max(0.0, float(counter_value)))
    return 1.0 - float(reduction) * normalized


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
