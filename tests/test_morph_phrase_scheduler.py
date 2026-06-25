"""Tests for the morph-phrase scheduler (CC-050/051, T-047e).

The morph_voice synthdef crossfades source A (saw) <-> source B (pulse) via a
continuous ``morph_x`` in [0, 1]. The composer turns that static control into a
musical gesture by streaming ``morph_x`` along a trajectory across a scene. This
pins the pure trajectory math: shape (rise/fall/arch), curve law, depth scaling,
and row->progress mapping. No OSC, no I/O.
"""
from __future__ import annotations

import pytest

from cypherclaw.instrument_morph import MorphInterpolationCurve
from cypherclaw.instrument_morph.phrase_scheduler import (
    MorphSweepShape,
    normalize_morph_sweep_shape,
    phrase_morph_x,
    phrase_morph_x_for_row,
)


def test_rise_goes_from_source_a_to_source_b() -> None:
    assert phrase_morph_x(0.0, shape=MorphSweepShape.RISE) == pytest.approx(0.0)
    assert phrase_morph_x(1.0, shape=MorphSweepShape.RISE) == pytest.approx(1.0)
    # Monotonic non-decreasing across the phrase under the linear law.
    prev = -1.0
    for i in range(11):
        v = phrase_morph_x(i / 10.0, shape=MorphSweepShape.RISE)
        assert v >= prev
        prev = v


def test_fall_goes_from_source_b_to_source_a() -> None:
    assert phrase_morph_x(0.0, shape=MorphSweepShape.FALL) == pytest.approx(1.0)
    assert phrase_morph_x(1.0, shape=MorphSweepShape.FALL) == pytest.approx(0.0)


def test_arch_begins_and_ends_on_source_a_and_peaks_at_middle() -> None:
    assert phrase_morph_x(0.0, shape=MorphSweepShape.ARCH) == pytest.approx(0.0)
    assert phrase_morph_x(1.0, shape=MorphSweepShape.ARCH) == pytest.approx(0.0)
    assert phrase_morph_x(0.5, shape=MorphSweepShape.ARCH) == pytest.approx(1.0)
    # Symmetric around the midpoint.
    assert phrase_morph_x(0.25, shape=MorphSweepShape.ARCH) == pytest.approx(
        phrase_morph_x(0.75, shape=MorphSweepShape.ARCH)
    )


def test_arch_is_the_default_shape() -> None:
    assert phrase_morph_x(0.5) == pytest.approx(phrase_morph_x(0.5, shape=MorphSweepShape.ARCH))
    assert phrase_morph_x(0.0) == pytest.approx(0.0)
    assert phrase_morph_x(1.0) == pytest.approx(0.0)


def test_depth_scales_the_peak() -> None:
    assert phrase_morph_x(0.5, shape=MorphSweepShape.ARCH, depth=0.6) == pytest.approx(0.6)
    assert phrase_morph_x(1.0, shape=MorphSweepShape.RISE, depth=0.4) == pytest.approx(0.4)
    # Depth 0 collapses the gesture to pure source A everywhere.
    for i in range(11):
        assert phrase_morph_x(i / 10.0, depth=0.0) == pytest.approx(0.0)


@pytest.mark.parametrize(
    "curve",
    [MorphInterpolationCurve.LINEAR, MorphInterpolationCurve.EXPONENTIAL, MorphInterpolationCurve.SIGMOID],
)
def test_output_stays_in_unit_range_for_all_shapes_and_curves(curve) -> None:
    for shape in MorphSweepShape:
        for i in range(21):
            v = phrase_morph_x(i / 20.0, shape=shape, curve=curve, depth=0.85)
            assert 0.0 <= v <= 1.0


@pytest.mark.parametrize(
    "curve",
    [MorphInterpolationCurve.LINEAR, MorphInterpolationCurve.EXPONENTIAL, MorphInterpolationCurve.SIGMOID],
)
def test_rise_endpoints_hit_exactly_under_every_curve(curve) -> None:
    assert phrase_morph_x(0.0, shape=MorphSweepShape.RISE, curve=curve) == pytest.approx(0.0)
    assert phrase_morph_x(1.0, shape=MorphSweepShape.RISE, curve=curve) == pytest.approx(1.0)


def test_row_mapping_spans_first_to_last_row() -> None:
    rows = 16
    assert phrase_morph_x_for_row(0, rows, shape=MorphSweepShape.RISE) == pytest.approx(0.0)
    assert phrase_morph_x_for_row(rows - 1, rows, shape=MorphSweepShape.RISE) == pytest.approx(1.0)
    # Middle row peaks the arch.
    assert phrase_morph_x_for_row((rows - 1) // 2, rows, shape=MorphSweepShape.ARCH) > 0.9


def test_row_mapping_handles_degenerate_row_counts() -> None:
    # A single-row (or zero-row) scene has no span: progress pins to 0.0.
    assert phrase_morph_x_for_row(0, 1, shape=MorphSweepShape.RISE) == pytest.approx(0.0)
    assert phrase_morph_x_for_row(0, 0, shape=MorphSweepShape.RISE) == pytest.approx(0.0)


def test_row_mapping_clamps_out_of_range_rows() -> None:
    rows = 8
    assert phrase_morph_x_for_row(-3, rows, shape=MorphSweepShape.RISE) == pytest.approx(0.0)
    assert phrase_morph_x_for_row(99, rows, shape=MorphSweepShape.RISE) == pytest.approx(1.0)


def test_normalize_shape_accepts_strings_and_rejects_garbage() -> None:
    assert normalize_morph_sweep_shape("arch") is MorphSweepShape.ARCH
    assert normalize_morph_sweep_shape("RISE") is MorphSweepShape.RISE
    assert normalize_morph_sweep_shape(MorphSweepShape.FALL) is MorphSweepShape.FALL
    with pytest.raises(ValueError):
        normalize_morph_sweep_shape("zigzag")


@pytest.mark.parametrize("bad", [-0.01, 1.01, float("nan"), float("inf")])
def test_progress_out_of_unit_range_is_rejected(bad) -> None:
    with pytest.raises((ValueError, TypeError)):
        phrase_morph_x(bad)


@pytest.mark.parametrize("bad", [-0.5, 1.5])
def test_depth_out_of_unit_range_is_rejected(bad) -> None:
    with pytest.raises(ValueError):
        phrase_morph_x(0.5, depth=bad)
