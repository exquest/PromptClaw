"""Tests for the shared `affective_state_bus` control-bus provisioning."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.affective_state_bus import (
    AFFECTIVE_STATE_BUS_CHANNELS,
    AFFECTIVE_STATE_BUS_DECAY_SECONDS,
    AFFECTIVE_STATE_BUS_INDEX,
    AFFECTIVE_STATE_BUS_MAX,
    AFFECTIVE_STATE_BUS_MIN,
    affective_state_bus_c_set_args,
    seed_affective_state_bus,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCD_PATH = (
    REPO_ROOT
    / "my-claw"
    / "tools"
    / "senseweave"
    / "synthesis"
    / "affective_state_bus.scd"
)


class _RecordingOSC:
    def __init__(self) -> None:
        self.messages: list[tuple[str, list]] = []

    def send_message(self, address: str, args: list) -> None:
        self.messages.append((address, list(args)))


def test_bus_constants_are_stable_and_within_prd_contract() -> None:
    assert isinstance(AFFECTIVE_STATE_BUS_INDEX, int)
    assert AFFECTIVE_STATE_BUS_INDEX >= 0
    assert AFFECTIVE_STATE_BUS_CHANNELS == 1
    assert AFFECTIVE_STATE_BUS_MIN == 0.0
    assert AFFECTIVE_STATE_BUS_MAX == 1.0
    assert AFFECTIVE_STATE_BUS_DECAY_SECONDS == 5.0


def test_c_set_args_clamps_to_bus_range() -> None:
    assert affective_state_bus_c_set_args(0.0) == [AFFECTIVE_STATE_BUS_INDEX, 0.0]
    assert affective_state_bus_c_set_args(0.42) == [AFFECTIVE_STATE_BUS_INDEX, 0.42]
    assert affective_state_bus_c_set_args(2.0) == [AFFECTIVE_STATE_BUS_INDEX, 1.0]
    assert affective_state_bus_c_set_args(-1.0) == [AFFECTIVE_STATE_BUS_INDEX, 0.0]


def test_seed_sends_c_set_and_returns_seeded_value() -> None:
    osc = _RecordingOSC()
    value = seed_affective_state_bus(osc, 0.3)
    assert value == 0.3
    assert osc.messages == [("/c_set", [AFFECTIVE_STATE_BUS_INDEX, 0.3])]


def test_seed_clamps_out_of_range_value_before_sending() -> None:
    osc = _RecordingOSC()
    value = seed_affective_state_bus(osc, 1.7)
    assert value == 1.0
    assert osc.messages == [("/c_set", [AFFECTIVE_STATE_BUS_INDEX, 1.0])]


def test_affective_state_bus_scd_exists_and_provisions_bus() -> None:
    assert SCD_PATH.exists(), f"missing SuperCollider stub: {SCD_PATH}"
    text = SCD_PATH.read_text(encoding="utf-8")

    # The bus index, channel count, and range must agree with the Python helper.
    index_match = re.search(r"~affectiveStateBusIndex\s*=\s*(\d+)", text)
    assert index_match is not None, "stub must declare ~affectiveStateBusIndex"
    assert int(index_match.group(1)) == AFFECTIVE_STATE_BUS_INDEX

    channels_match = re.search(r"~affectiveStateBusChannels\s*=\s*(\d+)", text)
    assert channels_match is not None, "stub must declare ~affectiveStateBusChannels"
    assert int(channels_match.group(1)) == AFFECTIVE_STATE_BUS_CHANNELS


def test_affective_state_bus_scd_demonstrates_reader_side_wiring() -> None:
    text = SCD_PATH.read_text(encoding="utf-8")

    # Reader-side wiring per voice: In.kr from the shared bus, clipped.
    assert "In.kr(~affectiveStateBusIndex" in text, (
        "stub must demonstrate the reader-side wiring via In.kr on the shared bus"
    )

    # Per-voice coupling multiplier from PRD §7.5.2 (CC-072).
    assert "SynthDef(\\sw_affective_state_reader" in text, (
        "stub must declare the reference reader SynthDef so voice synthdefs "
        "have a per-voice wiring template"
    )
    assert "coupling_strength" in text
    assert "nominal_depth" in text
    assert "1.0 + (coupling * affect)" in text or "1 + (coupling * affect)" in text, (
        "stub must apply the (1 + coupling * affect) multiplier from CC-072"
    )
