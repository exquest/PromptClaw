"""Tests for the tuning MorphOperator (T-034 / CC-041)."""

from __future__ import annotations

import pytest

from cypherclaw.tuning import (
    GamelanSlendro,
    JustIntonation5Limit,
    MorphOperator,
    TwelveTET,
)


def test_pitch_table_at_zero_equals_source_table() -> None:
    source = TwelveTET()
    target = JustIntonation5Limit()
    morph = MorphOperator(source=source, target=target, tonal_center_hz=440.0)
    assert morph.pitch_table_at(0.0) == source.pitch_table(440.0)


def test_pitch_table_at_one_equals_target_table() -> None:
    source = TwelveTET()
    target = JustIntonation5Limit()
    morph = MorphOperator(source=source, target=target, tonal_center_hz=440.0)
    assert morph.pitch_table_at(1.0) == target.pitch_table(440.0)


def test_pitch_table_midpoint_is_linear_interpolation() -> None:
    source = TwelveTET()
    target = JustIntonation5Limit()
    center = 440.0
    morph = MorphOperator(source=source, target=target, tonal_center_hz=center)
    mid = morph.pitch_table_at(0.5)
    src_table = source.pitch_table(center)
    tgt_table = target.pitch_table(center)
    for degree in src_table:
        assert mid[degree] == pytest.approx(
            0.5 * src_table[degree] + 0.5 * tgt_table[degree]
        )


def test_pitch_table_at_endpoints_with_mismatched_degree_counts() -> None:
    source = TwelveTET()  # 12 degrees
    target = GamelanSlendro()  # 5 degrees
    morph = MorphOperator(source=source, target=target, tonal_center_hz=261.625565)
    assert morph.pitch_table_at(0.0) == source.pitch_table(261.625565)
    assert morph.pitch_table_at(1.0) == target.pitch_table(261.625565)


def test_pitch_table_at_rejects_out_of_range_t() -> None:
    morph = MorphOperator(
        source=TwelveTET(),
        target=JustIntonation5Limit(),
        tonal_center_hz=440.0,
    )
    with pytest.raises(ValueError):
        morph.pitch_table_at(-0.01)
    with pytest.raises(ValueError):
        morph.pitch_table_at(1.01)
