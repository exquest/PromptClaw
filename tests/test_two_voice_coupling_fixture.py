"""Two-voice cross-coupling test fixture (T-006a).

This module is the shared scaffolding for the T-006 sub-task series that
exercises cross-voice affective coupling. The PRD (§7.5.2 / CC-070..074)
specifies a high-intensity voice pushing the shared affective_state_bus,
which then scales a baseline voice's modulator depths via
``1 + coupling_strength * bus_value``.

Voice A is configured with vibrato well above any plausible coupling
threshold; voice B starts at a quiet baseline. ``pre_coupling_vibrato_depth``
records voice B's depth before the bus has any chance to push it, so later
sub-tasks can verify how much B drifts once coupling activates.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

import pytest

from senseweave.affective_state_bus import (
    AFFECTIVE_STATE_BUS_INTENSITY_WEIGHTS,
    AffectiveStateBusWriter,
    voice_expression_intensity,
)
from senseweave.synthesis.senseweave_voice import SenseweaveVoice


# Vibrato depth chosen so voice A's expression intensity (weighted by
# AFFECTIVE_STATE_BUS_INTENSITY_WEIGHTS["vibrato_depth"] = 0.25) already
# exceeds any plausible coupling threshold once paired with a matching
# rate — rate is tracked separately for downstream sub-tasks that drive
# the LFO directly.
VOICE_A_VIBRATO_DEPTH = 0.9
VOICE_A_VIBRATO_RATE_HZ = 6.5

# Voice B's baseline: low, steady vibrato that any coupling event will
# visibly modulate. Kept above 0 so multiplicative coupling has something
# to scale.
VOICE_B_VIBRATO_DEPTH = 0.1
VOICE_B_VIBRATO_RATE_HZ = 4.0

VOICE_A_ID = "voice_a"
VOICE_B_ID = "voice_b"


@dataclass(frozen=True)
class TwoVoiceCouplingFixture:
    """Resolved two-voice fixture for cross-coupling sub-tasks."""

    voice_a: SenseweaveVoice
    voice_b: SenseweaveVoice
    voice_a_vibrato_depth: float
    voice_a_vibrato_rate_hz: float
    voice_b_vibrato_depth: float
    voice_b_vibrato_rate_hz: float
    pre_coupling_vibrato_depth: float
    bus_writer: AffectiveStateBusWriter
    osc_a: MagicMock
    osc_b: MagicMock
    bus_osc: MagicMock


def build_two_voice_coupling_fixture() -> TwoVoiceCouplingFixture:
    """Build the standard two-voice cross-coupling fixture.

    Voice A is loud and expressive (vibrato above the coupling threshold);
    voice B starts quiet so its drift is easy to measure. The bus writer
    is constructed with ``enabled=True`` so downstream sub-tasks can drive
    coupling without re-toggling the CYPHERCLAW_V2_COUPLING env var.
    """
    osc_a = MagicMock()
    osc_b = MagicMock()
    bus_osc = MagicMock()

    voice_a = SenseweaveVoice(osc=osc_a)
    voice_b = SenseweaveVoice(osc=osc_b)

    bus_writer = AffectiveStateBusWriter(enabled=True)

    return TwoVoiceCouplingFixture(
        voice_a=voice_a,
        voice_b=voice_b,
        voice_a_vibrato_depth=VOICE_A_VIBRATO_DEPTH,
        voice_a_vibrato_rate_hz=VOICE_A_VIBRATO_RATE_HZ,
        voice_b_vibrato_depth=VOICE_B_VIBRATO_DEPTH,
        voice_b_vibrato_rate_hz=VOICE_B_VIBRATO_RATE_HZ,
        pre_coupling_vibrato_depth=VOICE_B_VIBRATO_DEPTH,
        bus_writer=bus_writer,
        osc_a=osc_a,
        osc_b=osc_b,
        bus_osc=bus_osc,
    )


@pytest.fixture
def two_voice_coupling_fixture() -> TwoVoiceCouplingFixture:
    """Pytest entry point for the two-voice cross-coupling fixture."""
    return build_two_voice_coupling_fixture()


class TestTwoVoiceCouplingFixture:
    def test_builds_two_distinct_voice_instances(self) -> None:
        fixture = build_two_voice_coupling_fixture()

        assert isinstance(fixture.voice_a, SenseweaveVoice)
        assert isinstance(fixture.voice_b, SenseweaveVoice)
        assert fixture.voice_a is not fixture.voice_b
        assert fixture.osc_a is not fixture.osc_b

    def test_voice_a_vibrato_is_above_voice_b_baseline(self) -> None:
        fixture = build_two_voice_coupling_fixture()

        assert fixture.voice_a_vibrato_depth > fixture.voice_b_vibrato_depth
        assert fixture.voice_a_vibrato_rate_hz > fixture.voice_b_vibrato_rate_hz

    def test_voice_a_intensity_exceeds_voice_b_intensity(self) -> None:
        fixture = build_two_voice_coupling_fixture()

        intensity_a = voice_expression_intensity(
            vibrato_depth=fixture.voice_a_vibrato_depth,
        )
        intensity_b = voice_expression_intensity(
            vibrato_depth=fixture.voice_b_vibrato_depth,
        )
        vibrato_weight = AFFECTIVE_STATE_BUS_INTENSITY_WEIGHTS["vibrato_depth"]

        assert intensity_a == pytest.approx(
            fixture.voice_a_vibrato_depth * vibrato_weight
        )
        assert intensity_b == pytest.approx(
            fixture.voice_b_vibrato_depth * vibrato_weight
        )
        assert intensity_a > intensity_b

    def test_pre_coupling_measurement_matches_voice_b_initial_depth(self) -> None:
        fixture = build_two_voice_coupling_fixture()

        assert fixture.pre_coupling_vibrato_depth == fixture.voice_b_vibrato_depth
        assert fixture.pre_coupling_vibrato_depth == VOICE_B_VIBRATO_DEPTH

    def test_bus_writer_is_enabled_and_idle(self) -> None:
        fixture = build_two_voice_coupling_fixture()

        assert fixture.bus_writer.enabled is True
        assert fixture.bus_writer.voice_window_mean(VOICE_A_ID, now=0.0) == 0.0
        assert fixture.bus_writer.voice_window_mean(VOICE_B_ID, now=0.0) == 0.0
        fixture.bus_osc.send_message.assert_not_called()

    def test_voices_have_not_emitted_osc_traffic_at_setup(self) -> None:
        fixture = build_two_voice_coupling_fixture()

        fixture.osc_a.send_message.assert_not_called()
        fixture.osc_b.send_message.assert_not_called()
        assert fixture.voice_a.active_count == 0
        assert fixture.voice_b.active_count == 0

    def test_pytest_fixture_returns_two_voice_coupling_fixture(
        self,
        two_voice_coupling_fixture: TwoVoiceCouplingFixture,
    ) -> None:
        assert isinstance(two_voice_coupling_fixture, TwoVoiceCouplingFixture)
        assert (
            two_voice_coupling_fixture.pre_coupling_vibrato_depth
            == VOICE_B_VIBRATO_DEPTH
        )
