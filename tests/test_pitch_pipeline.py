"""Tests for `pitch_hz` composer-side pitch pipeline (T-035 / CC-042)."""

from __future__ import annotations

import math

import pytest

from cypherclaw.tuning import (
    GamelanSlendro,
    JustIntonation5Limit,
    TwelveTET,
    pitch_hz,
)


CENT_TOLERANCE = 0.1


def _cents_between(actual_hz: float, expected_hz: float) -> float:
    return 1200.0 * math.log2(actual_hz / expected_hz)


def test_degree_zero_octave_zero_returns_tonal_center() -> None:
    for tuning in (TwelveTET(), JustIntonation5Limit(), GamelanSlendro()):
        assert pitch_hz(0, 0, tuning, 261.625565) == pytest.approx(261.625565)


def test_octave_offset_doubles_frequency() -> None:
    tuning = TwelveTET()
    assert pitch_hz(0, 1, tuning, 220.0) == pytest.approx(440.0)
    assert pitch_hz(0, -1, tuning, 220.0) == pytest.approx(110.0)
    assert pitch_hz(0, 2, tuning, 220.0) == pytest.approx(880.0)


def test_twelve_tet_reference_frequencies_within_tolerance() -> None:
    tuning = TwelveTET()
    center = 261.625565  # C4
    # Equal-tempered semitones from C4: D4, E4, G4, A4, C5
    cases: dict[tuple[int, int], float] = {
        (2, 0): 293.664768,
        (4, 0): 329.627557,
        (7, 0): 391.995436,
        (9, 0): 440.0,
        (0, 1): 523.251131,
    }
    for (degree, octave), expected in cases.items():
        actual = pitch_hz(degree, octave, tuning, center)
        assert abs(_cents_between(actual, expected)) < CENT_TOLERANCE


def test_just_intonation_reference_ratios_within_tolerance() -> None:
    tuning = JustIntonation5Limit()
    center = 264.0
    # 5-limit JI ratios from PRD: M3 = 5/4, P4 = 4/3, P5 = 3/2, M6 = 5/3
    cases: dict[tuple[int, int], float] = {
        (4, 0): 264.0 * 5.0 / 4.0,
        (5, 0): 264.0 * 4.0 / 3.0,
        (7, 0): 264.0 * 3.0 / 2.0,
        (9, 0): 264.0 * 5.0 / 3.0,
        (0, 1): 528.0,
    }
    for (degree, octave), expected in cases.items():
        actual = pitch_hz(degree, octave, tuning, center)
        assert abs(_cents_between(actual, expected)) < CENT_TOLERANCE


def test_gamelan_slendro_reference_cents_within_tolerance() -> None:
    tuning = GamelanSlendro()
    center = 300.0
    # Cumulative cents per PRD: 0, 240, 480, 750, 990
    expected_cents = (0.0, 240.0, 480.0, 750.0, 990.0)
    for degree, cents in enumerate(expected_cents):
        expected = center * (2.0 ** (cents / 1200.0))
        actual = pitch_hz(degree, 0, tuning, center)
        assert abs(_cents_between(actual, expected)) < CENT_TOLERANCE


def test_scale_degree_overflow_wraps_into_octave() -> None:
    tuning = TwelveTET()
    # Degree 12 in octave 0 equals degree 0 in octave 1
    assert pitch_hz(12, 0, tuning, 220.0) == pytest.approx(
        pitch_hz(0, 1, tuning, 220.0)
    )
    # Degree -1 in octave 0 equals degree 11 in octave -1
    assert pitch_hz(-1, 0, tuning, 220.0) == pytest.approx(
        pitch_hz(11, -1, tuning, 220.0)
    )


def test_slendro_degree_overflow_uses_five_step_octave() -> None:
    tuning = GamelanSlendro()
    assert pitch_hz(5, 0, tuning, 300.0) == pytest.approx(
        pitch_hz(0, 1, tuning, 300.0)
    )


def test_non_positive_tonal_center_rejected() -> None:
    with pytest.raises(ValueError):
        pitch_hz(0, 0, TwelveTET(), 0.0)
    with pytest.raises(ValueError):
        pitch_hz(0, 0, TwelveTET(), -1.0)
