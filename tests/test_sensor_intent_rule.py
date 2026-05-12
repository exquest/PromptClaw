from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.render.rules.sensor_intent import (
    INTENTION_BASELINE,
    INTENTION_KEYS,
    SENSOR_CHANNELS,
    SENSOR_INTENTION_WEIGHTS,
    SensorIntentFilter,
    SensorIntentRule,
    aggregate_sensor_intent_stream,
    aggregate_sensor_intentions,
)


def _pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    centered_left = [value - left_mean for value in left]
    centered_right = [value - right_mean for value in right]
    numerator = sum(a * b for a, b in zip(centered_left, centered_right))
    left_denominator = math.sqrt(sum(value * value for value in centered_left))
    right_denominator = math.sqrt(sum(value * value for value in centered_right))
    if left_denominator == 0.0 or right_denominator == 0.0:
        return 0.0
    return numerator / (left_denominator * right_denominator)


def test_first_sample_uses_weight_matrix_for_aggregate_intentions() -> None:
    frame = {
        "theramini": {"playing": True},
        "room": {"activity": "active", "transient": True},
        "speech": {"detected": True},
        "garden": {"brightness": 0.9},
    }

    intentions = aggregate_sensor_intentions([frame])

    expected = {
        key: round(
            min(
                1.0,
                max(
                    0.0,
                    INTENTION_BASELINE[key]
                    + sum(
                        SENSOR_INTENTION_WEIGHTS[sensor][key]
                        for sensor in SENSOR_CHANNELS
                    ),
                ),
            ),
            3,
        )
        for key in INTENTION_KEYS
    }
    assert intentions == expected


def test_iir_smoothing_and_hysteresis_hold_then_release() -> None:
    sensor_filter = SensorIntentFilter(alpha=0.1)
    active_frame = {
        "theramini": {"playing": True},
        "room": {"activity": "active", "transient": True},
        "speech": {"detected": True},
        "garden": {"brightness": 0.9},
    }
    quiet_frame = {
        "theramini": {"playing": False},
        "room": {"activity": "quiet", "transient": False},
        "speech": {"detected": False},
        "garden": {"brightness": 0.0},
    }

    active = sensor_filter.update(active_frame)
    held = sensor_filter.update(quiet_frame)

    assert held == active

    released = held
    for _ in range(10):
        released = sensor_filter.update(quiet_frame)

    assert released["global_energy"] < held["global_energy"]
    assert released["global_brightness"] < held["global_brightness"]
    assert released["global_restraint"] > held["global_restraint"]


def test_rule_outputs_only_aggregate_intentions_from_sensor_stream() -> None:
    result = SensorIntentRule().apply(
        {
            "sensor_stream": [
                {
                    "theramini": {"playing": True},
                    "room": {"activity": "moderate", "transient": False},
                    "speech": {"detected": False},
                    "garden": {"brightness": 0.7},
                }
            ],
            "cutoff_hz": 12_000,
            "wet_mix": 0.8,
        },
        k=1.0,
        seeds=None,
        roles=None,
    )

    assert set(result) == {"aggregate_intentions"}
    assert set(result["aggregate_intentions"]) == set(INTENTION_KEYS)


def test_recorded_stream_does_not_expose_single_sensor_driver() -> None:
    recorded_stream: list[dict[str, float]] = []
    for index in range(72):
        recorded_stream.append(
            {
                "theramini_active": 1.0 if index % 11 in {0, 1, 2, 3, 4, 5} else 0.0,
                "room_activity": 1.0 if index % 13 in {2, 3, 4, 8, 9, 10} else 0.0,
                "room_transient": 1.0 if index % 17 in {0, 8} else 0.0,
                "speech_detected": 1.0 if index % 19 in {5, 6, 7, 14, 15} else 0.0,
                "outdoor_brightness": 1.0 if index % 23 in {4, 5, 6, 7, 17, 18, 19} else 0.0,
            }
        )

    rendered_stream = aggregate_sensor_intent_stream(recorded_stream)

    assert all(set(frame) == {"aggregate_intentions"} for frame in rendered_stream)
    sensor_columns = {
        sensor: [frame[sensor] for frame in recorded_stream]
        for sensor in SENSOR_CHANNELS
    }
    intention_columns = {
        key: [frame["aggregate_intentions"][key] for frame in rendered_stream]
        for key in INTENTION_KEYS
    }

    strongest = max(
        abs(_pearson(sensor_values, intention_values))
        for sensor_values in sensor_columns.values()
        for intention_values in intention_columns.values()
    )
    assert strongest <= 0.85
