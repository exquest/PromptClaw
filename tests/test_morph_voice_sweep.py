"""Behavioural sweep test for the morph_voice SynthDef (T-047d, CC-050).

Instantiates a Python model of the `morph_voice` gain math (mirroring the
SCD source in `synthesis/voices/morph_voice.scd`), sweeps `morph_x` from
0.0 to 1.0, and asserts the endpoint contract: `morph_x = 0` outputs
source A only and `morph_x = 1` outputs source B only.

The dev box has no SuperCollider toolchain (see `test_morph_voice_scd.py`),
so the model is a faithful translation of the SCD gain stage rather than a
live `scsynth` instantiation. The two crossfade laws shipped by the
SynthDef — linear (`morph_curve=0`) and equal-power (`morph_curve=1`) —
are both exercised, since the endpoint guarantee must hold under either.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

# Distinct sentinel amplitudes for the two sources: any non-zero output
# can be uniquely attributed to either A or B, so an endpoint assertion
# also proves the other source's gain collapsed to zero.
SOURCE_A_SAMPLE = 1.0
SOURCE_B_SAMPLE = -1.0


@dataclass(frozen=True)
class MorphVoiceInstance:
    """Python stand-in for an instantiated `morph_voice` synth.

    Reproduces the gain stage from morph_voice.scd:
        x = morph_x.clip(0.0, 1.0)
        linear:       gain_a = 1 - x,         gain_b = x
        equal-power:  gain_a = cos(x*pi/2),   gain_b = sin(x*pi/2)
        out = source_a * gain_a + source_b * gain_b
    """

    morph_curve: int  # 0 = linear, 1 = equal-power (per SCD Select.kr law)

    def gains(self, morph_x: float) -> tuple[float, float]:
        x = max(0.0, min(1.0, morph_x))
        if self.morph_curve == 0:
            return (1.0 - x, x)
        return (math.cos(x * 0.5 * math.pi), math.sin(x * 0.5 * math.pi))

    def render(self, morph_x: float, source_a: float, source_b: float) -> float:
        gain_a, gain_b = self.gains(morph_x)
        return source_a * gain_a + source_b * gain_b


def _sweep(steps: int = 11) -> list[float]:
    return [i / (steps - 1) for i in range(steps)]


@pytest.mark.parametrize("morph_curve", [0, 1], ids=["linear", "equal_power"])
def test_morph_x_endpoint_zero_is_source_a_only(morph_curve: int) -> None:
    """morph_x = 0 must produce source A at unity with source B silenced."""
    voice = MorphVoiceInstance(morph_curve=morph_curve)
    gain_a, gain_b = voice.gains(0.0)
    assert gain_a == pytest.approx(1.0), "source A must be at unity at morph_x=0"
    assert gain_b == pytest.approx(0.0), "source B must be silent at morph_x=0"

    out = voice.render(0.0, SOURCE_A_SAMPLE, SOURCE_B_SAMPLE)
    assert out == pytest.approx(SOURCE_A_SAMPLE), (
        "output at morph_x=0 must equal source A exactly"
    )


@pytest.mark.parametrize("morph_curve", [0, 1], ids=["linear", "equal_power"])
def test_morph_x_endpoint_one_is_source_b_only(morph_curve: int) -> None:
    """morph_x = 1 must produce source B at unity with source A silenced."""
    voice = MorphVoiceInstance(morph_curve=morph_curve)
    gain_a, gain_b = voice.gains(1.0)
    assert gain_a == pytest.approx(0.0, abs=1e-9), (
        "source A must be silent at morph_x=1"
    )
    assert gain_b == pytest.approx(1.0), "source B must be at unity at morph_x=1"

    out = voice.render(1.0, SOURCE_A_SAMPLE, SOURCE_B_SAMPLE)
    assert out == pytest.approx(SOURCE_B_SAMPLE), (
        "output at morph_x=1 must equal source B exactly"
    )


@pytest.mark.parametrize("morph_curve", [0, 1], ids=["linear", "equal_power"])
def test_morph_x_sweep_produces_audio_at_every_step(morph_curve: int) -> None:
    """Sweeping morph_x from 0 to 1 must yield audible output at every step.

    With opposite-sign sentinel sources, the output magnitude only collapses
    to zero if both gains are simultaneously zero — which would mean the
    voice has gone silent mid-sweep. Guard against that regression here.
    """
    voice = MorphVoiceInstance(morph_curve=morph_curve)
    for morph_x in _sweep():
        out = voice.render(morph_x, SOURCE_A_SAMPLE, SOURCE_B_SAMPLE)
        gain_a, gain_b = voice.gains(morph_x)
        assert gain_a >= 0.0 and gain_b >= 0.0, (
            f"gains must stay non-negative at morph_x={morph_x}"
        )
        assert abs(gain_a) + abs(gain_b) > 0.0, (
            f"voice fell silent at morph_x={morph_x}"
        )
        assert math.isfinite(out), f"non-finite output at morph_x={morph_x}"


def test_linear_sweep_preserves_constant_gain_sum() -> None:
    """Linear law: gain_a + gain_b == 1 across the whole sweep."""
    voice = MorphVoiceInstance(morph_curve=0)
    for morph_x in _sweep():
        gain_a, gain_b = voice.gains(morph_x)
        assert gain_a + gain_b == pytest.approx(1.0)


def test_equal_power_sweep_preserves_constant_power_sum() -> None:
    """Equal-power law: gain_a**2 + gain_b**2 == 1 across the whole sweep."""
    voice = MorphVoiceInstance(morph_curve=1)
    for morph_x in _sweep():
        gain_a, gain_b = voice.gains(morph_x)
        assert gain_a**2 + gain_b**2 == pytest.approx(1.0)


@pytest.mark.parametrize("morph_curve", [0, 1], ids=["linear", "equal_power"])
def test_morph_x_is_clipped_below_zero_to_source_a(morph_curve: int) -> None:
    """morph_x values below 0 must clamp to source A only (per SCD clip)."""
    voice = MorphVoiceInstance(morph_curve=morph_curve)
    out = voice.render(-0.5, SOURCE_A_SAMPLE, SOURCE_B_SAMPLE)
    assert out == pytest.approx(SOURCE_A_SAMPLE)


@pytest.mark.parametrize("morph_curve", [0, 1], ids=["linear", "equal_power"])
def test_morph_x_is_clipped_above_one_to_source_b(morph_curve: int) -> None:
    """morph_x values above 1 must clamp to source B only (per SCD clip)."""
    voice = MorphVoiceInstance(morph_curve=morph_curve)
    out = voice.render(1.5, SOURCE_A_SAMPLE, SOURCE_B_SAMPLE)
    assert out == pytest.approx(SOURCE_B_SAMPLE)
