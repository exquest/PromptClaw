"""Tests for the sw_master_smooth SuperCollider stub and boot-time seeding.

These tests pin two server-side commitments that the
`master_bus_s_new_args` Python helper depends on:

1. A `.scd` source stub for `sw_master_smooth` exists and declares the new
   `sampler_amp` and `sampler_bypass_comp` controls with their defaults.
2. The boot scripts (`start_audio.sh`, `restart_composer.sh`) seed the
   master node by calling `master_bus_s_new_args()` so the OSC arg list
   stays in lockstep with `DEFAULT_MASTER_BUS_VALUES`.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from cypherclaw.space_reverb import VOICE_REVERB_PROFILES

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

REPO_ROOT = Path(__file__).resolve().parents[1]
SCD_PATH = REPO_ROOT / "my-claw" / "tools" / "senseweave" / "synthesis" / "master_smooth.scd"
START_AUDIO_PATH = REPO_ROOT / "my-claw" / "scripts" / "start_audio.sh"
RESTART_COMPOSER_PATH = REPO_ROOT / "my-claw" / "scripts" / "restart_composer.sh"


def _scd_declared_defaults(text: str) -> dict[str, float]:
    """Parse `name = number` pairs from the SynthDef arg block.

    Tolerates both `|name = value, ...|` and `arg name = value;` forms by
    matching `<identifier> = <number>` tokens inside the SynthDef body.
    """
    defaults: dict[str, float] = {}
    for match in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(-?\d+(?:\.\d+)?)", text):
        name, value = match.group(1), match.group(2)
        if name in defaults:
            continue
        defaults[name] = float(value)
    return defaults


def test_master_smooth_scd_declares_sampler_controls() -> None:
    assert SCD_PATH.exists(), f"missing SuperCollider stub: {SCD_PATH}"
    text = SCD_PATH.read_text(encoding="utf-8")

    assert "SynthDef(\\sw_master_smooth" in text or "SynthDef(\"sw_master_smooth\"" in text, (
        "stub must declare a SynthDef named sw_master_smooth"
    )

    defaults = _scd_declared_defaults(text)
    for control in ("amp", "drive", "warmth", "reverb", "room", "sampler_amp", "sampler_bypass_comp"):
        assert control in defaults, f"sw_master_smooth stub must declare '{control}' control"

    assert defaults["sampler_amp"] == 1.0, "sampler_amp must default to 1.0 (peak-normalized unity)"
    assert defaults["sampler_bypass_comp"] == 1.0, (
        "sampler_bypass_comp must default to 1.0 (compression bypassed for grain transients)"
    )


def test_boot_scripts_seed_master_via_master_bus_helper() -> None:
    for script in (START_AUDIO_PATH, RESTART_COMPOSER_PATH):
        text = script.read_text(encoding="utf-8")
        assert "master_bus_s_new_args" in text, (
            f"{script.name} must seed the master node via master_bus_s_new_args() "
            "so the boot-time control list stays in sync with DEFAULT_MASTER_BUS_VALUES"
        )
        assert "from senseweave.master_bus import" in text, (
            f"{script.name} must import the helper from senseweave.master_bus"
        )


def test_master_smooth_scd_provisions_seven_voice_fx_buses() -> None:
    """T-042/T-044d: seven FX return buses, one per CypherClaw v2 voice,
    routed into the compressor input so per-voice effects ride the same
    glue compression and reverb tail as the dry mix.
    """
    text = SCD_PATH.read_text(encoding="utf-8")
    voice_names = tuple(VOICE_REVERB_PROFILES)

    defaults = _scd_declared_defaults(text)
    for voice in voice_names:
        control = f"fx_bus_{voice}"
        assert control in defaults, f"sw_master_smooth must declare '{control}' control"

    bus_indices = [int(defaults[f"fx_bus_{v}"]) for v in voice_names]
    assert bus_indices == [
        VOICE_REVERB_PROFILES[voice].fx_bus_id for voice in voice_names
    ]
    assert len(set(bus_indices)) == len(voice_names), (
        f"each voice FX bus must be unique, got {dict(zip(voice_names, bus_indices))}"
    )

    for voice in voice_names:
        pattern = re.compile(rf"In\.ar\(\s*fx_bus_{voice}\b")
        assert pattern.search(text), (
            f"sw_master_smooth must read FX bus '{voice}' via In.ar(fx_bus_{voice}, ...)"
        )

    compander_idx = text.find("Compander.ar")
    assert compander_idx > 0, "sw_master_smooth must invoke Compander.ar"
    pre_comp = text[:compander_idx]
    for voice in voice_names:
        assert f"fx_bus_{voice}" in pre_comp, (
            f"fx_bus_{voice} must be routed BEFORE the master compressor"
        )


def test_boot_scripts_have_no_hardcoded_master_bus_literals() -> None:
    for script in (START_AUDIO_PATH, RESTART_COMPOSER_PATH):
        text = script.read_text(encoding="utf-8")
        for literal in ('"drive",', '"warmth",', '"reverb",', '"room",'):
            assert literal not in text, (
                f"{script.name} still hardcodes {literal!r} master-bus literal; "
                "route through master_bus_s_new_args() instead"
            )
