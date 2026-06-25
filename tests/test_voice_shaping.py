"""Tests for high-note playback shaping."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.voice_shaping import (
    MAX_PLUCK_UNISON_DETUNE,
    STABLE_PLUCK_UNISON_DETUNE,
    VoiceShape,
    pluck_playback_detune,
    shaping_for_note,
)


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


# --- Stable pluck unison detune (END-WORK #87: kill the "out of tune" read) ---
# The composer used to apply a per-note RANDOM pluck detune (_rnd.uniform(
# 0.001, 0.006)) — a different pitch offset every note, which Marissa + Anthony
# heard as "out of tune". pluck_playback_detune replaces that with a small
# STABLE unison width plus the deterministic per-context adds.


def test_pluck_playback_detune_is_a_small_stable_unison_for_low_notes() -> None:
    shape = shaping_for_note("pluck", 440.0)  # low note -> VoiceShape() default
    detune = pluck_playback_detune(shape)
    assert detune == pytest.approx(STABLE_PLUCK_UNISON_DETUNE)
    assert 0.0 < detune <= 0.003  # present (warmth) but gentle


def test_pluck_playback_detune_is_deterministic_no_randomness() -> None:
    shape = shaping_for_note("pluck", 440.0)
    values = {pluck_playback_detune(shape, 0.004) for _ in range(64)}
    assert len(values) == 1  # identical every call — no per-note pitch drift


def test_pluck_playback_detune_adds_deterministic_context_terms() -> None:
    shape = shaping_for_note("pluck", 1760.0)  # high note -> detune_add > 0
    assert shape.detune_add > 0.0
    detune = pluck_playback_detune(shape, 0.002)
    assert detune == pytest.approx(
        min(STABLE_PLUCK_UNISON_DETUNE + shape.detune_add + 0.002, MAX_PLUCK_UNISON_DETUNE),
        abs=1e-4,
    )
    assert detune > STABLE_PLUCK_UNISON_DETUNE  # high notes get a touch more width


def test_pluck_playback_detune_is_capped_and_never_negative() -> None:
    shape = shaping_for_note("pluck", 1760.0)
    # A large stacked context cannot exceed the cap...
    assert pluck_playback_detune(shape, 0.05) == pytest.approx(MAX_PLUCK_UNISON_DETUNE)
    # ...and a negative context add cannot pull it below the stable base.
    assert pluck_playback_detune(VoiceShape(), -0.01) == pytest.approx(STABLE_PLUCK_UNISON_DETUNE)


def test_stable_pluck_detune_is_below_the_old_random_ceiling() -> None:
    # Regression guard: the new stable base must be well under the old random
    # max (0.006) so it reads as warmth, not as a wide/loose tuning.
    assert STABLE_PLUCK_UNISON_DETUNE < 0.006
