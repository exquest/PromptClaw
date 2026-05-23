"""Tests for composer-side instrument morph curve interpolation (T-048b)."""

from __future__ import annotations

import math

import pytest

from cypherclaw.instrument_morph import (
    MorphInterpolationCurve,
    build_morph_parameter_frames,
    interpolate_voice_parameters,
    morph_curve_position,
)


def _normalized_exponential(position: float) -> float:
    strength = 4.0
    return (math.exp(strength * position) - 1.0) / (math.exp(strength) - 1.0)


def _normalized_sigmoid(position: float) -> float:
    strength = 12.0
    low = 1.0 / (1.0 + math.exp(strength * 0.5))
    high = 1.0 / (1.0 + math.exp(-strength * 0.5))
    raw = 1.0 / (1.0 + math.exp(-strength * (position - 0.5)))
    return (raw - low) / (high - low)


def test_morph_curve_position_shapes_are_deterministic() -> None:
    for curve in MorphInterpolationCurve:
        assert morph_curve_position(0.0, curve) == 0.0
        assert morph_curve_position(1.0, curve) == 1.0

    assert morph_curve_position(0.25, "linear") == pytest.approx(0.25)
    assert morph_curve_position(0.75, "linear") == pytest.approx(0.75)

    exponential_midpoint = morph_curve_position(0.5, "exponential")
    assert exponential_midpoint == pytest.approx(_normalized_exponential(0.5))
    assert 0.0 < exponential_midpoint < 0.5

    sigmoid_quarter = morph_curve_position(0.25, "sigmoid")
    sigmoid_midpoint = morph_curve_position(0.5, "sigmoid")
    sigmoid_three_quarter = morph_curve_position(0.75, "sigmoid")

    assert sigmoid_quarter == pytest.approx(_normalized_sigmoid(0.25))
    assert sigmoid_midpoint == pytest.approx(0.5)
    assert sigmoid_three_quarter == pytest.approx(_normalized_sigmoid(0.75))
    assert sigmoid_quarter + sigmoid_three_quarter == pytest.approx(1.0)
    assert sigmoid_quarter < 0.25
    assert sigmoid_three_quarter > 0.75


def test_interpolate_voice_parameters_uses_curve_values_and_exact_endpoints() -> None:
    source = {"brightness": 0.2, "drive": 0.1}
    target = {"brightness": 0.8, "drive": 0.5}

    assert interpolate_voice_parameters(source, target, 0.0, "exponential") == source
    assert interpolate_voice_parameters(source, target, 1.0, "sigmoid") == target

    linear = interpolate_voice_parameters(source, target, 0.25, "linear")
    assert linear == {
        "brightness": pytest.approx(0.35),
        "drive": pytest.approx(0.2),
    }

    curve_value = _normalized_exponential(0.5)
    exponential = interpolate_voice_parameters(source, target, 0.5, "exponential")
    assert exponential == {
        "brightness": pytest.approx(0.2 + (0.8 - 0.2) * curve_value),
        "drive": pytest.approx(0.1 + (0.5 - 0.1) * curve_value),
    }


def test_interpolate_voice_parameters_preserves_one_sided_parameters() -> None:
    result = interpolate_voice_parameters(
        {"brightness": 0.2, "source_only": 9.0},
        {"brightness": 0.8, "target_only": 3.0},
        0.5,
        "linear",
    )

    assert list(result) == ["brightness", "source_only", "target_only"]
    assert result == {
        "brightness": pytest.approx(0.5),
        "source_only": 9.0,
        "target_only": 3.0,
    }


def test_build_morph_parameter_frames_returns_endpoint_inclusive_trajectory() -> None:
    frames = build_morph_parameter_frames(
        {"brightness": 0.2},
        {"brightness": 0.8},
        frame_count=5,
        curve="linear",
    )

    assert len(frames) == 5
    assert [frame.position for frame in frames] == pytest.approx(
        [0.0, 0.25, 0.5, 0.75, 1.0]
    )
    assert [frame.curve_position for frame in frames] == pytest.approx(
        [0.0, 0.25, 0.5, 0.75, 1.0]
    )
    assert frames[0].parameters == {"brightness": 0.2}
    assert frames[-1].parameters == {"brightness": 0.8}
    assert frames[2].parameters == {"brightness": pytest.approx(0.5)}


@pytest.mark.parametrize("position", [-0.01, 1.01, math.inf, math.nan])
def test_morph_interpolation_rejects_invalid_inputs(position: float) -> None:
    with pytest.raises(ValueError):
        morph_curve_position(position, "linear")

    with pytest.raises(ValueError):
        morph_curve_position(0.5, "bouncy")

    with pytest.raises(ValueError):
        build_morph_parameter_frames(
            {"brightness": 0.2},
            {"brightness": 0.8},
            frame_count=1,
            curve="linear",
        )

    with pytest.raises(TypeError):
        interpolate_voice_parameters(
            {"brightness": "bright"},
            {"brightness": 0.8},
            0.5,
            "linear",
        )
