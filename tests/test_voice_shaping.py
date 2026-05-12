"""Tests for high-note playback shaping."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.voice_shaping import shaping_for_note


def test_low_notes_are_not_softened() -> None:
    shape = shaping_for_note("pluck", 440.0)

    assert shape.pitch_multiplier == 1.0
    assert shape.amp_multiplier == 1.0
    assert shape.brightness_multiplier == 1.0
    assert shape.detune_add == 0.0


def test_high_pluck_notes_are_softened_and_detuned() -> None:
    shape = shaping_for_note("pluck", 1760.0)

    assert shape.pitch_multiplier == 0.25
    assert shape.amp_multiplier < 1.0
    assert shape.brightness_multiplier < 1.0
    assert shape.detune_add > 0.0
    assert shape.verb_add > 0.0
    assert shape.highpass_hz > 0.0
    assert shape.saturation_mix > 0.0


def test_high_nonpluck_notes_get_gentle_saturation_without_brightness_knob() -> None:
    shape = shaping_for_note("choir", 1568.0)

    assert shape.pitch_multiplier == 0.25
    assert shape.amp_multiplier < 1.0
    assert shape.release_multiplier < 1.0
    assert shape.verb_add > 0.0
    assert shape.brightness_multiplier == 1.0
    assert shape.highpass_hz > 0.0
    assert shape.saturation_mix > 0.0


def test_upper_midrange_notes_now_fold_down_one_octave() -> None:
    shape = shaping_for_note("pluck", 1174.66)

    assert shape.pitch_multiplier == 0.5
    assert shape.highpass_hz > 0.0
