"""CypherClaw v2 expression layer (PRD feature 7 / design statement §7).

This layer adds expressive shaping to the live composer by riding the
*existing* fire-and-forget voice controls (``amp`` / ``attack`` / ``release``)
— it introduces NO new SuperCollider DSP. Its master scalar is the
scene-phase intensity ``M`` (§7.4): a value in ``[0, 1]`` that scales
amplitude and (later) modulation depth by the current arc phase's energy.

Naming note (a deliberate, surfaced reinterpretation — see §"Authority and
Conflict Resolution" in the design statement): §7.4 keys ``M`` on phase names
*Listen / Conversation / Divination / Procession*, but the deployed arc
(``senseweave.procedural_arc``) uses *Divination / Emergence / Conversation /
Convergence / Crystallization*, and its "Divination" is the quiet opening
("listen before speaking", dynamic ``p``) — the opposite of §7.4's weighty
Divination. Rather than map by drifted names, we derive ``M`` from each
deployed phase's own ``dynamic`` marking (pp/p/mp/mf/f). That realizes §7.4's
*intensity intent* and is immune to the naming mismatch.

Per-voice attack Sharp/Swell follows the §7.3 voice→gesture allocations.
(§7.1's "default Sharp for bowed/pads" conflicts with §7.3's "bowed forbids
sharp attack"; §7.3 is the per-voice "physical alignment" table CypherClaw
called non-negotiable, so it wins — conflict surfaced, not silently resolved.)

The whole layer is gated by ``CYPHERCLAW_V2_EXPRESSION`` (default OFF). When
OFF — or when phase data is missing — every multiplier is exactly ``1.0`` so
playback is byte-identical to legacy. Continuous modulators (vibrato/tremolo/
granulation) need new synthdefs and are a deliberately deferred later slice;
they are NOT part of this module.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


CYPHERCLAW_V2_EXPRESSION_ENV = "CYPHERCLAW_V2_EXPRESSION"
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})

# §7.4 intensity by dynamic marking. Chosen to land inside the design's M
# bands: pp/p in the "Listen" band (0.0–0.2), mp in "Procession" (0.3–0.6),
# mf in "Conversation" (0.5–0.8), f in "Divination" (0.8–1.0).
_DYNAMIC_INTENSITY: dict[str, float] = {
    "pp": 0.10,
    "p": 0.20,
    "mp": 0.42,
    "mf": 0.68,
    "f": 0.90,
    "ff": 1.00,
}

# §7.3 voice→gesture allocations: voices whose primary gesture is a sustained
# swell rather than a percussive onset.
_SWELL_VOICES = frozenset({"bowed", "breath", "pad", "choir"})


def expression_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True iff ``CYPHERCLAW_V2_EXPRESSION`` is set to a truthy value."""
    source = os.environ if env is None else env
    raw = source.get(CYPHERCLAW_V2_EXPRESSION_ENV)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY_VALUES


def scene_phase_intensity(dynamic: str | None) -> float | None:
    """Map a deployed arc phase's ``dynamic`` marking to §7.4 intensity ``M``.

    Returns ``None`` for an unknown/empty/missing dynamic so callers never act
    on absent phase data.
    """
    if not dynamic:
        return None
    return _DYNAMIC_INTENSITY.get(dynamic.strip().lower())


def attack_shape_for_voice(voice_name: str) -> str:
    """Return ``"swell"`` or ``"sharp"`` per the §7.3 voice allocations."""
    return "swell" if voice_name in _SWELL_VOICES else "sharp"


@dataclass(frozen=True)
class ExpressionProfile:
    """Per-note expressive multipliers applied to existing voice controls."""

    amp_multiplier: float = 1.0
    attack_multiplier: float = 1.0
    release_multiplier: float = 1.0
    attack_shape: str = "sharp"
    intensity: float = 0.0

    @classmethod
    def identity(cls, *, attack_shape: str = "sharp") -> "ExpressionProfile":
        return cls(attack_shape=attack_shape)


def expression_profile(
    *,
    voice_name: str,
    role: str = "",
    phase_dynamic: str | None,
    env: Mapping[str, str] | None = None,
) -> ExpressionProfile:
    """Compute the expressive profile for one note.

    Identity (all multipliers ``1.0``) when the flag is OFF or the phase
    dynamic is missing/unknown. Otherwise:
    - amplitude scales gently with ``M`` (modest, so it does not fight the
      mastering bus): ``0.85 .. 1.10`` across ``M = 0 .. 1``;
    - swell voices lengthen their attack with ``M`` (up to ~3x); sharp voices
      tighten it (down to ~0.65x);
    - release lengthens slightly with ``M`` for weight (up to ~1.3x).
    """
    shape = attack_shape_for_voice(voice_name)

    if not expression_enabled(env):
        return ExpressionProfile.identity(attack_shape=shape)

    intensity = scene_phase_intensity(phase_dynamic)
    if intensity is None:
        return ExpressionProfile.identity(attack_shape=shape)

    m = max(0.0, min(1.0, intensity))

    # Gentle, mastering-safe amplitude bias: M=0 -> 0.85, M=0.5 -> ~0.975, M=1 -> 1.10.
    amp_mult = 0.85 + 0.25 * m

    if shape == "swell":
        # Sustained voices breathe in: longer attack as intensity rises.
        attack_mult = 1.0 + 2.0 * m
    else:
        # Percussive voices sharpen as intensity rises.
        attack_mult = 1.0 - 0.35 * m

    # A touch more sustain weight at higher intensity.
    release_mult = 1.0 + 0.3 * m

    return ExpressionProfile(
        amp_multiplier=round(amp_mult, 4),
        attack_multiplier=round(attack_mult, 4),
        release_multiplier=round(release_mult, 4),
        attack_shape=shape,
        intensity=round(m, 4),
    )


__all__ = [
    "CYPHERCLAW_V2_EXPRESSION_ENV",
    "ExpressionProfile",
    "attack_shape_for_voice",
    "expression_enabled",
    "expression_profile",
    "scene_phase_intensity",
]
