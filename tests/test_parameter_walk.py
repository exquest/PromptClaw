"""Tests for within-family parameter walks (T-050)."""

from __future__ import annotations

import math

import pytest

from cypherclaw.instrument_morph import (
    ParameterWalkFrame,
    ParameterWalkSpec,
    generate_parameter_walk,
    parameter_walk_depth_band,
)


def test_osc_trace_stays_within_expected_depth_band() -> None:
    specs = (
        ParameterWalkSpec(name="filter_cutoff", center=2000.0, depth_fraction=0.10, rate_hz=0.25),
        ParameterWalkSpec(name="fm_index", center=4.0, depth_fraction=0.075, rate_hz=0.15, phase=0.25),
        ParameterWalkSpec(name="osc_detune", center=12.0, depth_fraction=0.05, rate_hz=0.1),
    )

    frames = generate_parameter_walk(specs, duration=8.0, sample_rate=40.0)

    assert frames, "expected a non-empty trace"
    for spec in specs:
        low, high = parameter_walk_depth_band(spec)
        for frame in frames:
            value = frame.parameters[spec.name]
            assert low - 1e-9 <= value <= high + 1e-9, (
                f"{spec.name} out of band at t={frame.time}: {value} not in [{low}, {high}]"
            )


def test_trace_is_continuous_between_adjacent_samples() -> None:
    spec = ParameterWalkSpec(
        name="filter_cutoff", center=2000.0, depth_fraction=0.10, rate_hz=0.25
    )

    sample_rate = 40.0
    frames = generate_parameter_walk((spec,), duration=8.0, sample_rate=sample_rate)

    swing = spec.depth_fraction * abs(spec.center)
    max_step = 2.0 * math.pi * spec.rate_hz * swing / sample_rate
    tolerance = max_step * 1.01 + 1e-9

    deltas = [
        abs(b.parameters[spec.name] - a.parameters[spec.name])
        for a, b in zip(frames, frames[1:])
    ]
    assert deltas, "expected at least one delta between samples"
    assert max(deltas) <= tolerance


def test_trace_timestamps_are_monotonic_and_bounded() -> None:
    spec = ParameterWalkSpec(name="p", center=1.0, depth_fraction=0.1, rate_hz=1.0)

    frames = generate_parameter_walk((spec,), duration=2.0, sample_rate=10.0)

    times = [frame.time for frame in frames]
    assert times[0] == pytest.approx(0.0)
    assert times[-1] == pytest.approx(2.0)
    for earlier, later in zip(times, times[1:]):
        assert later >= earlier
    assert all(isinstance(f, ParameterWalkFrame) for f in frames)


def test_zero_depth_produces_constant_center_value() -> None:
    spec = ParameterWalkSpec(name="p", center=7.5, depth_fraction=0.0, rate_hz=0.5)

    frames = generate_parameter_walk((spec,), duration=1.0, sample_rate=20.0)

    for frame in frames:
        assert frame.parameters["p"] == pytest.approx(7.5)


def test_phase_offset_shifts_starting_value() -> None:
    base = ParameterWalkSpec(name="p", center=10.0, depth_fraction=0.1, rate_hz=1.0)
    shifted = ParameterWalkSpec(
        name="p", center=10.0, depth_fraction=0.1, rate_hz=1.0, phase=0.25
    )

    base_frames = generate_parameter_walk((base,), duration=0.5, sample_rate=100.0)
    shifted_frames = generate_parameter_walk((shifted,), duration=0.5, sample_rate=100.0)

    assert base_frames[0].parameters["p"] == pytest.approx(10.0)
    assert shifted_frames[0].parameters["p"] == pytest.approx(11.0)


def test_duplicate_parameter_names_are_rejected() -> None:
    specs = (
        ParameterWalkSpec(name="p", center=1.0, depth_fraction=0.1, rate_hz=0.5),
        ParameterWalkSpec(name="p", center=2.0, depth_fraction=0.1, rate_hz=0.5),
    )
    with pytest.raises(ValueError):
        generate_parameter_walk(specs, duration=1.0, sample_rate=10.0)


def test_empty_spec_sequence_is_rejected() -> None:
    with pytest.raises(ValueError):
        generate_parameter_walk((), duration=1.0, sample_rate=10.0)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_duration_is_rejected(bad: float) -> None:
    spec = ParameterWalkSpec(name="p", center=1.0, depth_fraction=0.1, rate_hz=0.5)
    with pytest.raises(ValueError):
        generate_parameter_walk((spec,), duration=bad, sample_rate=10.0)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_sample_rate_is_rejected(bad: float) -> None:
    spec = ParameterWalkSpec(name="p", center=1.0, depth_fraction=0.1, rate_hz=0.5)
    with pytest.raises(ValueError):
        generate_parameter_walk((spec,), duration=1.0, sample_rate=bad)


@pytest.mark.parametrize("bad_depth", [-0.01, 1.5, float("nan")])
def test_invalid_depth_fraction_is_rejected(bad_depth: float) -> None:
    with pytest.raises(ValueError):
        ParameterWalkSpec(
            name="p", center=1.0, depth_fraction=bad_depth, rate_hz=0.5
        )
        generate_parameter_walk(
            (ParameterWalkSpec(name="p", center=1.0, depth_fraction=bad_depth, rate_hz=0.5),),
            duration=1.0,
            sample_rate=10.0,
        )


@pytest.mark.parametrize("bad_rate", [0.0, -0.1, float("nan"), float("inf")])
def test_invalid_rate_hz_is_rejected(bad_rate: float) -> None:
    with pytest.raises(ValueError):
        generate_parameter_walk(
            (ParameterWalkSpec(name="p", center=1.0, depth_fraction=0.1, rate_hz=bad_rate),),
            duration=1.0,
            sample_rate=10.0,
        )
