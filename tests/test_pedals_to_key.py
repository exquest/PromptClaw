"""Tests for pedals_to_key.py — sustain/expression pedal to harmony mapping."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave"))

from pedals_to_key import (
    pedal_to_harmonic_shift,
    expression_to_dynamics,
    key_shift_from_pedal_pattern,
)


# === pedal_to_harmonic_shift ===


class TestPedalToHarmonicShift:
    def test_sustain_on_holds_chord(self):
        result = pedal_to_harmonic_shift(sustain=True, expression=64)
        assert result["hold_chord"] is True

    def test_sustain_off_no_hold(self):
        result = pedal_to_harmonic_shift(sustain=False, expression=64)
        assert result["hold_chord"] is False

    def test_low_expression_low_tension(self):
        result = pedal_to_harmonic_shift(sustain=False, expression=0)
        assert result["tension"] < 0.1
        assert result["suggest_extensions"] is False

    def test_high_expression_high_tension(self):
        result = pedal_to_harmonic_shift(sustain=False, expression=127)
        assert result["tension"] > 0.9
        assert result["suggest_extensions"] is True

    def test_mid_expression_mid_tension(self):
        result = pedal_to_harmonic_shift(sustain=True, expression=64)
        assert 0.4 <= result["tension"] <= 0.6

    def test_tension_range_always_valid(self):
        for exp in (0, 32, 64, 96, 127):
            result = pedal_to_harmonic_shift(sustain=False, expression=exp)
            assert 0.0 <= result["tension"] <= 1.0

    def test_returns_expected_keys(self):
        result = pedal_to_harmonic_shift(sustain=True, expression=100)
        assert "hold_chord" in result
        assert "tension" in result
        assert "suggest_extensions" in result

    def test_extension_threshold_boundary(self):
        # Expression at midpoint: should not suggest extensions
        result = pedal_to_harmonic_shift(sustain=False, expression=63)
        assert result["suggest_extensions"] is False

        # Expression just above threshold: should suggest extensions
        result = pedal_to_harmonic_shift(sustain=False, expression=96)
        assert result["suggest_extensions"] is True

    def test_clamps_expression_below_zero(self):
        # Negative expression treated as 0
        result = pedal_to_harmonic_shift(sustain=False, expression=-5)
        assert result["tension"] == 0.0

    def test_clamps_expression_above_127(self):
        # Over-max expression treated as 127
        result = pedal_to_harmonic_shift(sustain=False, expression=200)
        assert result["tension"] == 1.0


# === expression_to_dynamics ===


class TestExpressionToDynamics:
    def test_zero_expression_quiet_dim(self):
        result = expression_to_dynamics(0)
        assert result["volume_factor"] <= 0.31
        assert result["brightness"] <= 0.01

    def test_max_expression_loud_bright(self):
        result = expression_to_dynamics(127)
        assert result["volume_factor"] >= 0.99
        assert result["brightness"] >= 0.99

    def test_mid_expression_mid_values(self):
        result = expression_to_dynamics(64)
        assert 0.5 <= result["volume_factor"] <= 0.8
        assert 0.4 <= result["brightness"] <= 0.6

    def test_returns_expected_keys(self):
        result = expression_to_dynamics(50)
        assert "volume_factor" in result
        assert "brightness" in result

    def test_volume_factor_range(self):
        for v in (0, 32, 64, 96, 127):
            result = expression_to_dynamics(v)
            assert 0.3 <= result["volume_factor"] <= 1.0

    def test_brightness_range(self):
        for v in (0, 32, 64, 96, 127):
            result = expression_to_dynamics(v)
            assert 0.0 <= result["brightness"] <= 1.0

    def test_monotonic_volume(self):
        """Volume should increase as expression increases."""
        values = [expression_to_dynamics(v)["volume_factor"] for v in range(0, 128, 8)]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_monotonic_brightness(self):
        """Brightness should increase as expression increases."""
        values = [expression_to_dynamics(v)["brightness"] for v in range(0, 128, 8)]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_clamps_negative(self):
        result = expression_to_dynamics(-10)
        assert result["volume_factor"] >= 0.3
        assert result["brightness"] >= 0.0

    def test_clamps_over_max(self):
        result = expression_to_dynamics(200)
        assert result["volume_factor"] <= 1.0
        assert result["brightness"] <= 1.0


# === key_shift_from_pedal_pattern ===


class TestKeyShiftFromPedalPattern:
    def test_empty_events_returns_none(self):
        assert key_shift_from_pedal_pattern([]) is None

    def test_single_event_returns_none(self):
        assert key_shift_from_pedal_pattern([(0.0, True)]) is None

    def test_rapid_on_off_on_modulate(self):
        # Rapid on-off-on within a short window => modulate
        events = [
            (0.0, True),
            (0.15, False),
            (0.3, True),
        ]
        assert key_shift_from_pedal_pattern(events) == "modulate"

    def test_long_hold_pedal_point(self):
        # Single long hold => pedal_point
        events = [
            (0.0, True),
            (3.0, True),  # still held after 3 seconds
        ]
        assert key_shift_from_pedal_pattern(events) == "pedal_point"

    def test_slow_on_off_returns_none(self):
        # Slow, deliberate pedal use — no special pattern
        events = [
            (0.0, True),
            (2.0, False),
        ]
        result = key_shift_from_pedal_pattern(events)
        assert result is None

    def test_returns_valid_values(self):
        # Whatever events, result must be one of the valid values
        events = [(0.0, True), (0.1, False), (0.2, True)]
        result = key_shift_from_pedal_pattern(events)
        assert result in ("modulate", "pedal_point", None)

    def test_rapid_pattern_timing_matters(self):
        # On-off-on but spread too far apart => not modulate
        events = [
            (0.0, True),
            (1.5, False),
            (3.0, True),
        ]
        result = key_shift_from_pedal_pattern(events)
        assert result != "modulate"

    def test_very_long_hold(self):
        # Very long hold = pedal_point
        events = [
            (0.0, True),
            (10.0, True),
        ]
        assert key_shift_from_pedal_pattern(events) == "pedal_point"
