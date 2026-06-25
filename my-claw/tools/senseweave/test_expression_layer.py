"""Expression layer (v2 feature 7) — scene-phase intensity + per-voice attack shaping.

The expression layer rides the EXISTING fire-and-forget voice controls
(amp / attack / release); it adds NO new DSP. Its master scalar is the
scene-phase intensity M (design statement §7.4), derived from the *deployed*
arc phase's own ``dynamic`` marking (pp/p/mp/mf/f) rather than the phase name
— the design statement's §7.4 phase names (Listen/Conversation/Divination/
Procession) do not match the deployed arc (Divination/Emergence/Conversation/
Convergence/Crystallization), and the deployed "Divination" is the quiet
opening, the opposite of §7.4's weighty Divination. Keying on the dynamic
marking realizes §7.4's intensity intent and is immune to the name drift.

Per-voice attack Sharp/Swell follows the §7.3 voice→gesture allocations
(bowed/breath/pad/choir = swell; pluck/tabla/kotekan/etc = sharp). The whole
layer is gated by CYPHERCLAW_V2_EXPRESSION, default OFF: when OFF (or when
phase data is missing) every multiplier is exactly 1.0 so playback is
byte-identical to legacy.
"""
from __future__ import annotations

import pytest

from senseweave.expression_layer import (
    CYPHERCLAW_V2_EXPRESSION_ENV,
    ExpressionProfile,
    attack_shape_for_voice,
    expression_enabled,
    expression_profile,
    scene_phase_intensity,
)


# --- flag gate ------------------------------------------------------------

def test_flag_defaults_off():
    assert expression_enabled({}) is False
    assert expression_enabled({CYPHERCLAW_V2_EXPRESSION_ENV: ""}) is False
    assert expression_enabled({CYPHERCLAW_V2_EXPRESSION_ENV: "off"}) is False


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", " yes ", "on", "Enabled"])
def test_flag_truthy_values(raw):
    assert expression_enabled({CYPHERCLAW_V2_EXPRESSION_ENV: raw}) is True


# --- scene-phase intensity M (§7.4 via dynamic marking) -------------------

def test_intensity_monotonic_in_dynamic():
    m = [scene_phase_intensity(d) for d in ("pp", "p", "mp", "mf", "f")]
    assert m == sorted(m)
    assert len(set(m)) == 5  # strictly increasing


def test_intensity_lands_in_design_77_4_bands():
    # §7.4 intent: vessel-quiet phases low, weighty phases high.
    assert 0.0 <= scene_phase_intensity("pp") <= 0.2
    assert 0.0 <= scene_phase_intensity("p") <= 0.2          # "Listen" band
    assert 0.3 <= scene_phase_intensity("mp") <= 0.6         # "Procession" band
    assert 0.5 <= scene_phase_intensity("mf") <= 0.8         # "Conversation" band
    assert 0.8 <= scene_phase_intensity("f") <= 1.0          # "Divination" band


def test_intensity_unknown_dynamic_is_none():
    # Missing/unknown dynamic must be distinguishable so callers never act on it.
    assert scene_phase_intensity(None) is None
    assert scene_phase_intensity("") is None
    assert scene_phase_intensity("mezzo") is None


# --- attack shape per §7.3 voice allocations ------------------------------

@pytest.mark.parametrize("voice", ["bowed", "breath", "pad", "choir"])
def test_swell_voices(voice):
    assert attack_shape_for_voice(voice) == "swell"


@pytest.mark.parametrize("voice", ["pluck", "tabla_tin", "tabla_ge", "kotekan", "gong", "bell", "metal", "grain"])
def test_sharp_voices(voice):
    assert attack_shape_for_voice(voice) == "sharp"


def test_unknown_voice_defaults_sharp():
    assert attack_shape_for_voice("mystery_synth") == "sharp"


# --- profile: OFF / missing-data identity ---------------------------------

def _is_identity(p: ExpressionProfile) -> bool:
    return (
        p.amp_multiplier == 1.0
        and p.attack_multiplier == 1.0
        and p.release_multiplier == 1.0
    )


def test_profile_flag_off_is_identity():
    p = expression_profile(
        voice_name="bowed", role="melody", phase_dynamic="f",
        env={},  # flag absent
    )
    assert _is_identity(p)


def test_profile_missing_phase_is_identity_even_when_on():
    on = {CYPHERCLAW_V2_EXPRESSION_ENV: "1"}
    for dyn in (None, "", "bogus"):
        p = expression_profile(
            voice_name="bowed", role="melody", phase_dynamic=dyn, env=on,
        )
        assert _is_identity(p), f"dynamic={dyn!r} should be identity"


# --- profile: ON behavior -------------------------------------------------

ON = {CYPHERCLAW_V2_EXPRESSION_ENV: "1"}


def test_amp_grows_with_intensity():
    quiet = expression_profile(voice_name="bowed", role="melody", phase_dynamic="pp", env=ON)
    weighty = expression_profile(voice_name="bowed", role="melody", phase_dynamic="f", env=ON)
    assert quiet.amp_multiplier < 1.0 < weighty.amp_multiplier
    # modest — must not fight the mastering bus
    assert 0.75 <= quiet.amp_multiplier <= 1.0
    assert 1.0 <= weighty.amp_multiplier <= 1.15


def test_swell_voice_lengthens_attack_with_intensity():
    p = expression_profile(voice_name="bowed", role="melody", phase_dynamic="f", env=ON)
    assert p.attack_shape == "swell"
    assert p.attack_multiplier > 1.0


def test_sharp_voice_tightens_attack_with_intensity():
    p = expression_profile(voice_name="pluck", role="melody", phase_dynamic="f", env=ON)
    assert p.attack_shape == "sharp"
    assert p.attack_multiplier < 1.0


def test_all_multipliers_bounded_across_full_range():
    for dyn in ("pp", "p", "mp", "mf", "f"):
        for voice in ("bowed", "breath", "pad", "choir", "pluck", "tabla_tin", "kotekan", "bell"):
            p = expression_profile(voice_name=voice, role="melody", phase_dynamic=dyn, env=ON)
            assert 0.75 <= p.amp_multiplier <= 1.15
            assert 0.5 <= p.attack_multiplier <= 4.0
            assert 0.85 <= p.release_multiplier <= 1.5


def test_intensity_exposed_on_profile():
    p = expression_profile(voice_name="bowed", role="melody", phase_dynamic="mf", env=ON)
    assert p.intensity == pytest.approx(scene_phase_intensity("mf"))
