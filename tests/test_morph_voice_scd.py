"""Static tests for the morph_voice SynthDef source (T-047a, CC-050).

The compiled `.scsyndef` is produced by sclang on the CypherClaw deploy
host; this dev box has no SuperCollider toolchain. These tests validate
the SCD source declaratively — name, argument list, default values,
parallel-source UGens, and the morph_x crossfade contract — so that
regressions surface in CI without sclang.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCD_PATH = (
    REPO_ROOT
    / "my-claw"
    / "tools"
    / "senseweave"
    / "synthesis"
    / "voices"
    / "morph_voice.scd"
)


@pytest.fixture(scope="module")
def scd_source() -> str:
    assert SCD_PATH.is_file(), f"morph_voice.scd missing at {SCD_PATH}"
    return SCD_PATH.read_text(encoding="utf-8")


def _arg_block(source: str) -> str:
    match = re.search(r"\|\s*([^|]+?)\s*\|", source, flags=re.DOTALL)
    assert match, "could not locate SynthDef argument list"
    return match.group(1)


def _arg_default(arg_block: str, name: str) -> float:
    pattern = rf"\b{re.escape(name)}\s*=\s*(-?\d+(?:\.\d+)?)"
    match = re.search(pattern, arg_block)
    assert match, f"argument {name!r} missing or has no default"
    return float(match.group(1))


def test_synthdef_name_is_morph_voice(scd_source: str) -> None:
    assert re.search(r"SynthDef\(\\morph_voice\b", scd_source), (
        "SynthDef must be named \\morph_voice"
    )


def test_writes_def_file_to_synthdefs(scd_source: str) -> None:
    assert re.search(r"\.writeDefFile\(\s*\"\.\./synthdefs/?\"\s*\)", scd_source), (
        "compiled .scsyndef must land in synthesis/synthdefs/ "
        "(via ../synthdefs/ from the voices/synthesis source tree)"
    )


def test_declares_morph_x_control_defaulting_to_source_a(scd_source: str) -> None:
    args = _arg_block(scd_source)
    assert _arg_default(args, "morph_x") == 0.0, (
        "morph_x must default to 0.0 so a freshly spawned synth plays source A only"
    )


def test_declares_common_voice_controls(scd_source: str) -> None:
    args = _arg_block(scd_source)
    for control in ("freq", "amp", "attack", "release", "out_bus"):
        _arg_default(args, control)


def test_has_two_parallel_source_voices(scd_source: str) -> None:
    """Source A = Saw, Source B = Pulse, both running in parallel."""
    assert re.search(r"\bSaw\.ar\b", scd_source), "source A must use Saw.ar"
    assert re.search(r"\bPulse\.ar\b", scd_source), "source B must use Pulse.ar"


def test_morph_x_crossfades_source_a_and_source_b(scd_source: str) -> None:
    """morph_x=0 -> source A only; morph_x=1 -> source B only.

    The linear branch must be present: gain_a = 1 - x, gain_b = x.
    Pin both the inversion and the clip so the contract can't drift.
    """
    assert re.search(r"1\.0\s*-\s*\b(?:x|morph_x\w*)\b", scd_source), (
        "linear source A gain must be (1.0 - x) so morph_x=0 plays A at unity"
    )
    # morph_x must be clipped to [0.0, 1.0] before use.
    assert re.search(r"morph_x\.clip\(\s*0\.0\s*,\s*1\.0\s*\)", scd_source), (
        "morph_x must be clipped to [0.0, 1.0] before use as a gain"
    )


def test_declares_morph_curve_selecting_equal_power_by_default(scd_source: str) -> None:
    """`morph_curve` selects the crossfade law (0=linear, 1=equal-power).

    Default is equal-power because it preserves perceived loudness across
    the morph; the linear branch is retained for tests and special cases.
    """
    args = _arg_block(scd_source)
    assert _arg_default(args, "morph_curve") == 1.0, (
        "morph_curve must default to 1 (equal-power) — the musical default"
    )


def test_equal_power_branch_uses_quarter_cosine_pair(scd_source: str) -> None:
    """Equal-power crossfade uses cos(x*pi/2) and sin(x*pi/2).

    That pair satisfies gain_a^2 + gain_b^2 == 1 and hits unity at the
    endpoints, so morph_x=0/1 still produces source A/B at full level.
    """
    assert re.search(r"cos\(\s*\w+\s*\*\s*0\.5pi\s*\)", scd_source), (
        "equal-power source A gain must be cos(x * 0.5pi)"
    )
    assert re.search(r"sin\(\s*\w+\s*\*\s*0\.5pi\s*\)", scd_source), (
        "equal-power source B gain must be sin(x * 0.5pi)"
    )


def test_morph_curve_selects_between_linear_and_equal_power(scd_source: str) -> None:
    """Both gains are dispatched via Select.kr(morph_curve, ...).

    Using Select.kr keeps the choice a per-synth control rather than a
    compile-time constant, so the same SynthDef can render either law.
    """
    select_calls = re.findall(r"Select\.kr\(\s*morph_curve[^)]*\)", scd_source)
    assert len(select_calls) >= 2, (
        "both gain_a and gain_b must be selected by morph_curve via Select.kr"
    )


def test_summed_to_output_bus(scd_source: str) -> None:
    """The two scaled sources are summed before being written to out_bus."""
    assert re.search(
        r"\(\s*source_a\s*\*\s*gain_a\s*\)\s*\+\s*\(\s*source_b\s*\*\s*gain_b\s*\)",
        scd_source,
    ), "scaled sources must be summed: (source_a * gain_a) + (source_b * gain_b)"
    assert re.search(r"Out\.ar\(\s*out_bus\s*,", scd_source), (
        "summed signal must be written to out_bus via Out.ar"
    )


def test_declares_position_control(scd_source: str) -> None:
    """`position` controls stereo placement; defaults to centred (0.0)."""
    args = _arg_block(scd_source)
    assert _arg_default(args, "position") == 0.0, (
        "position must default to 0.0 (centred)"
    )
    assert re.search(
        r"Pan2\.ar\(\s*sig\s*,\s*position\.clip\(\s*-1\.0\s*,\s*1\.0\s*\)\s*\)",
        scd_source,
    ), "Pan2.ar must place the signal using position.clip(-1.0, 1.0)"


def test_declares_fx_bus_routing_controls(scd_source: str) -> None:
    """Per the voice routing contract: declare fx_bus_id and fx_send.

    fx_bus_id defaults to 22 (the morph voice's per-voice FX return bus);
    fx_send defaults to 0.2 (a quiet baseline send level).
    """
    args = _arg_block(scd_source)
    assert _arg_default(args, "fx_bus_id") == 22.0, (
        "fx_bus_id must default to 22 (morph voice FX return bus)"
    )
    assert _arg_default(args, "fx_send") == 0.2, (
        "fx_send must default to 0.2"
    )


def test_writes_parallel_fx_send_to_fx_bus(scd_source: str) -> None:
    """A parallel send scaled by fx_send is written to fx_bus_id.

    Matches the routing contract used by sw_pluck and the other voices:
    `Out.ar(fx_bus_id, sig * fx_send.clip(0.0, 1.0))`.
    """
    assert re.search(
        r"\bsig\s*\*\s*fx_send\.clip\(\s*0\.0\s*,\s*1\.0\s*\)",
        scd_source,
    ), "FX send must be sig * fx_send.clip(0.0, 1.0)"
    assert re.search(r"Out\.ar\(\s*fx_bus_id\s*,", scd_source), (
        "parallel send must be written to fx_bus_id via Out.ar"
    )
