"""Tests for the TuningSystem abstract base and concrete classes (T-033)."""

from __future__ import annotations

import math

import pytest

from cypherclaw.tuning import (
    GamelanSlendro,
    JustIntonation5Limit,
    TuningSystem,
    TwelveTET,
    tuning_for_name,
)


CONCRETE_TUNINGS: tuple[type[TuningSystem], ...] = (
    TwelveTET,
    JustIntonation5Limit,
    GamelanSlendro,
)


def test_module_imports_concrete_tunings() -> None:
    for cls in CONCRETE_TUNINGS:
        assert issubclass(cls, TuningSystem)


def test_abstract_base_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        TuningSystem()  # type: ignore[abstract]


@pytest.mark.parametrize("cls", CONCRETE_TUNINGS)
def test_pitch_table_returns_full_octave(cls: type[TuningSystem]) -> None:
    tuning = cls()
    table = tuning.pitch_table(440.0)
    assert isinstance(table, dict)
    assert len(table) == tuning.degrees_per_octave
    assert set(table.keys()) == set(range(tuning.degrees_per_octave))
    for hz in table.values():
        assert hz > 0.0


@pytest.mark.parametrize("cls", CONCRETE_TUNINGS)
def test_pitch_table_degree_zero_is_tonal_center(cls: type[TuningSystem]) -> None:
    assert cls().pitch_table(261.625565)[0] == pytest.approx(261.625565)


def test_twelve_tet_octave_ratio_matches_equal_temperament() -> None:
    table = TwelveTET().pitch_table(440.0)
    assert table[7] == pytest.approx(440.0 * (2.0 ** (7 / 12.0)))
    assert table[12 - 1] == pytest.approx(440.0 * (2.0 ** (11 / 12.0)))


def test_just_intonation_perfect_fifth_is_three_halves() -> None:
    table = JustIntonation5Limit().pitch_table(220.0)
    assert table[7] == pytest.approx(220.0 * 1.5)


def test_gamelan_slendro_step_cents() -> None:
    table = GamelanSlendro().pitch_table(300.0)
    expected_cents = (0.0, 240.0, 480.0, 750.0, 990.0)
    for degree, cents in enumerate(expected_cents):
        ratio = 2.0 ** (cents / 1200.0)
        assert table[degree] == pytest.approx(300.0 * ratio)


@pytest.mark.parametrize("cls", CONCRETE_TUNINGS)
def test_non_positive_tonal_center_rejected(cls: type[TuningSystem]) -> None:
    with pytest.raises(ValueError):
        cls().pitch_table(0.0)
    with pytest.raises(ValueError):
        cls().pitch_table(-1.0)


@pytest.mark.parametrize("cls", CONCRETE_TUNINGS)
def test_pitch_table_scales_with_tonal_center(cls: type[TuningSystem]) -> None:
    a = cls().pitch_table(100.0)
    b = cls().pitch_table(200.0)
    for degree, hz_a in a.items():
        assert b[degree] == pytest.approx(2.0 * hz_a)
    for hz in a.values():
        assert math.isfinite(hz)


@pytest.mark.parametrize(
    "legacy_name",
    ["12-TET", "12-tet", "12 TET", "12tet", "Twelve_TET", "equal-temperament"],
)
def test_tuning_for_name_accepts_legacy_12_tet_aliases(legacy_name: str) -> None:
    tuning = tuning_for_name(legacy_name)
    assert isinstance(tuning, TwelveTET)
    assert tuning.pitch_table(440.0) == TwelveTET().pitch_table(440.0)


def test_tuning_for_name_resolves_canonical_names() -> None:
    assert isinstance(tuning_for_name("twelve_tet"), TwelveTET)
    assert isinstance(tuning_for_name("just_intonation_5_limit"), JustIntonation5Limit)
    assert isinstance(tuning_for_name("gamelan_slendro"), GamelanSlendro)


def test_tuning_for_name_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        tuning_for_name("pythagorean")
