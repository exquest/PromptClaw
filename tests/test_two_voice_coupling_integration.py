"""Integration test for cross-voice vibrato coupling (T-006b).

This module implements the 'Drive the coupling' phase of the T-006 integration
test series. It uses the fixture from T-006a to demonstrate that high
intensity in Voice A successfully propagates through the AffectiveStateBus
and scales Voice B's vibrato depth.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.dirname(__file__))

import pytest

from senseweave.affective_state_bus import (
    AFFECTIVE_STATE_BUS_INDEX,
    AFFECTIVE_STATE_BUS_WINDOW_SECONDS,
    voice_expression_intensity,
)
from senseweave.synthesis.senseweave_voice import (
    coupling_multiplier_from_bus_value,
)
from test_two_voice_coupling_fixture import (
    VOICE_A_ID,
    TwoVoiceCouplingFixture,
    two_voice_coupling_fixture,  # noqa: F401  # pytest fixture
)


# T-006c: Defined minimum delta for a 'measurable shift'
MIN_COUPLING_DELTA = 0.01

# T-006c: Coupling sign — positive bus values must drive voice B's depth
# upward, so the post-coupling shift is expected to be > 0.
COUPLING_SIGN = 1.0


class _SuperColliderDouble:
    """In-memory stand-in for scsynth that mirrors `/c_set` writes.

    The writer flushes to ``send_message`` and a downstream voice reads
    via ``read_control_bus``. Holding both in a single object means the
    drive loop exercises the same value path that production uses, instead
    of pre-baking the reader's return value.
    """

    def __init__(self) -> None:
        self.send_message = MagicMock(side_effect=self._on_send)
        self._bus_values: dict[int, float] = {}

    def _on_send(self, address: str, args: list) -> None:
        if address == "/c_set" and len(args) >= 2:
            self._bus_values[int(args[0])] = float(args[1])

    def read_control_bus(self, bus_index: int) -> float:
        return self._bus_values.get(int(bus_index), 0.0)


class TestTwoVoiceCouplingDrive:
    def test_coupling_propagation_from_voice_a_to_voice_b(
        self,
        two_voice_coupling_fixture: TwoVoiceCouplingFixture,  # noqa: F811
    ) -> None:
        """Verify Voice A's intensity propagates and scales Voice B's depth."""
        fixture = two_voice_coupling_fixture
        
        # 1. Calculate expected intensity for Voice A
        intensity_a = voice_expression_intensity(
            vibrato_depth=fixture.voice_a_vibrato_depth
        )
        
        # 2. Update the bus with Voice A's intensity at t=0
        fixture.bus_writer.update(VOICE_A_ID, intensity_a, now=0.0)
        
        # 3. Flush to the 'SuperCollider' (mocked OSC)
        fixture.bus_writer.flush(fixture.bus_osc, now=0.0)
        
        # Verify OSC message was sent to the correct bus
        fixture.bus_osc.send_message.assert_called_with(
            "/c_set", [AFFECTIVE_STATE_BUS_INDEX, intensity_a]
        )
        
        # 4. Setup Voice B to read from the bus
        reader = MagicMock()
        reader.read_control_bus.return_value = intensity_a
        
        # Enable coupling for this test
        env = {"CYPHERCLAW_V2_COUPLING": "1"}
        
        # 5. Voice B triggers a note, which should pick up the coupling multiplier
        modulator_depths = {"vib_depth": fixture.voice_b_vibrato_depth}
        
        # Capture the note_on call args to see the scaled depth
        fixture.voice_b.note_on_with_affective_coupling(
            freq=440.0,
            control_bus_reader=reader,
            modulator_depths=modulator_depths,
            env=env
        )
        
        # 6. Verify Voice B's note-on used the scaled depth
        expected_multiplier = coupling_multiplier_from_bus_value(intensity_a)
        expected_scaled_depth = fixture.voice_b_vibrato_depth * expected_multiplier
        
        # Check the OSC call for Voice B's note
        fixture.osc_b.send_message.assert_called_once()
        args = fixture.osc_b.send_message.call_args[0][1]
        
        # Find vib_depth in args
        depth_index = args.index("vib_depth")
        actual_scaled_depth = args[depth_index + 1]
        
        # T-006c: Explicit assertions for delta and direction
        shift = actual_scaled_depth - fixture.pre_coupling_vibrato_depth

        # Measurable-shift magnitude exceeds the defined minimum delta.
        assert abs(shift) > MIN_COUPLING_DELTA

        # Shift direction matches the coupling sign (positive).
        assert shift * COUPLING_SIGN > 0

        # Final check against exact expected value
        assert actual_scaled_depth == pytest.approx(expected_scaled_depth)

    def test_drive_coupling_over_multiple_ticks_propagates_to_voice_b(
        self,
        two_voice_coupling_fixture: TwoVoiceCouplingFixture,  # noqa: F811
    ) -> None:
        """Advance the render loop enough ticks for coupling to propagate.

        Voice A samples its high-vibrato intensity into the bus writer
        across the full 2s rolling window, the writer flushes once per
        tick into the shared SuperCollider double, and only then does
        Voice B trigger a note that reads the bus. The depth captured
        from Voice B's `/s_new` is the post-coupling measurement.
        """
        fixture = two_voice_coupling_fixture
        supercollider = _SuperColliderDouble()

        intensity_a = voice_expression_intensity(
            vibrato_depth=fixture.voice_a_vibrato_depth,
        )

        tick_dt = 0.1
        tick_count = int(AFFECTIVE_STATE_BUS_WINDOW_SECONDS / tick_dt) + 2
        bus_trace: list[float] = []
        for tick in range(tick_count):
            now = tick * tick_dt
            fixture.bus_writer.update(VOICE_A_ID, intensity_a, now=now)
            bus_trace.append(fixture.bus_writer.flush(supercollider, now=now))

        assert bus_trace[-1] == pytest.approx(intensity_a)
        assert supercollider.read_control_bus(AFFECTIVE_STATE_BUS_INDEX) == pytest.approx(
            intensity_a
        )

        env = {"CYPHERCLAW_V2_COUPLING": "1"}
        fixture.voice_b.note_on_with_affective_coupling(
            freq=440.0,
            control_bus_reader=supercollider,
            modulator_depths={"vib_depth": fixture.voice_b_vibrato_depth},
            env=env,
        )

        fixture.osc_b.send_message.assert_called_once()
        s_new_args = fixture.osc_b.send_message.call_args[0][1]
        post_coupling_depth = s_new_args[s_new_args.index("vib_depth") + 1]

        expected_multiplier = coupling_multiplier_from_bus_value(intensity_a)
        assert post_coupling_depth == pytest.approx(
            fixture.voice_b_vibrato_depth * expected_multiplier
        )

        # T-006c: post-coupling depth differs from pre-coupling baseline by
        # more than the minimum measurable delta, and the shift direction
        # matches the coupling sign.
        shift = post_coupling_depth - fixture.pre_coupling_vibrato_depth
        assert abs(shift) > MIN_COUPLING_DELTA
        assert shift * COUPLING_SIGN > 0

    def test_coupling_decay_over_time(
        self,
        two_voice_coupling_fixture: TwoVoiceCouplingFixture,  # noqa: F811
    ) -> None:
        """Verify that coupling strength decays when Voice A stops contributing."""
        fixture = two_voice_coupling_fixture
        
        # 1. Seed the bus with high intensity
        intensity_a = 0.8
        fixture.bus_writer.update(VOICE_A_ID, intensity_a, now=0.0)
        fixture.bus_writer.flush(fixture.bus_osc, now=0.0)
        
        # 2. Wait 5 seconds (the decay time constant tau)
        # At t=5.0, value should be 0.8 * exp(-5/5) = 0.8 * exp(-1) approx 0.294
        now = 5.0
        decayed_value = fixture.bus_writer.flush(fixture.bus_osc, now=now)
        
        import math
        expected_decayed = intensity_a * math.exp(-1.0)
        assert decayed_value == pytest.approx(expected_decayed)
        
        # Verify OSC update sent the decayed value
        fixture.bus_osc.send_message.assert_called_with(
            "/c_set", [AFFECTIVE_STATE_BUS_INDEX, pytest.approx(expected_decayed)]
        )
