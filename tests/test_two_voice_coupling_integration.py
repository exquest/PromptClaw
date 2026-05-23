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
    voice_expression_intensity,
)
from senseweave.synthesis.senseweave_voice import (
    SenseweaveVoice,
    coupling_multiplier_from_bus_value,
)
from test_two_voice_coupling_fixture import (
    VOICE_A_ID,
    VOICE_A_VIBRATO_DEPTH,
    VOICE_B_VIBRATO_DEPTH,
    TwoVoiceCouplingFixture,
    two_voice_coupling_fixture,
)


# T-006c: Defined minimum delta for a 'measurable shift'
MIN_COUPLING_DELTA = 0.01


class TestTwoVoiceCouplingDrive:
    def test_coupling_propagation_from_voice_a_to_voice_b(
        self,
        two_voice_coupling_fixture: TwoVoiceCouplingFixture,
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
        shift = actual_scaled_depth - fixture.voice_b_vibrato_depth
        
        # Assert post-coupling depth differs by more than minimum delta
        assert abs(shift) > MIN_COUPLING_DELTA
        
        # Assert shift direction is positive (coupling sign matches)
        assert shift > 0
        
        # Final check against exact expected value
        assert actual_scaled_depth == pytest.approx(expected_scaled_depth)

    def test_coupling_decay_over_time(
        self,
        two_voice_coupling_fixture: TwoVoiceCouplingFixture,
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
