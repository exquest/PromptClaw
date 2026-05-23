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

    The skeleton uses a linear crossfade: gain_a = 1 - morph_x, gain_b = morph_x.
    Pin both the inversion and the direct use so the contract can't drift.
    """
    assert re.search(r"1\.0\s*-\s*morph_x", scd_source), (
        "source A gain must be (1.0 - morph_x) so morph_x=0 plays A at unity"
    )
    # source B is gated directly by morph_x (after clip).
    assert re.search(r"morph_x\.clip\(\s*0\.0\s*,\s*1\.0\s*\)", scd_source), (
        "morph_x must be clipped to [0.0, 1.0] before use as source B gain"
    )
