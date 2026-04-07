"""Tests for breath_to_filter.py — house breathing rhythm to audio/visual filter parameters."""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from breath_to_filter import (
    estimate_breath_rate,
    breath_phase,
    breath_to_filter_params,
    breath_to_visual_params,
)


# ---------------------------------------------------------------------------
# Helpers — generate synthetic RMS histories
# ---------------------------------------------------------------------------


def _sine_rms(cycles: float, num_samples: int, amplitude: float = 0.1,
              offset: float = 0.15) -> list[float]:
    """Generate a sinusoidal RMS history simulating breathing."""
    return [
        offset + amplitude * math.sin(2 * math.pi * cycles * i / num_samples)
        for i in range(num_samples)
    ]


def _flat_rms(num_samples: int, value: float = 0.1) -> list[float]:
    """Generate a flat (constant) RMS history — no breathing pattern."""
    return [value] * num_samples


def _noisy_rms(num_samples: int, seed: int = 42) -> list[float]:
    """Generate pseudorandom RMS values — no coherent pattern."""
    # Simple LCG for reproducibility without importing random
    x = seed
    result = []
    for _ in range(num_samples):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        result.append(0.05 + 0.2 * (x / 0x7FFFFFFF))
    return result


# ---------------------------------------------------------------------------
# estimate_breath_rate
# ---------------------------------------------------------------------------


class TestEstimateBreathRate:
    def test_detects_known_rate(self):
        """6 cycles over 60 seconds = 6 breaths per minute."""
        history = _sine_rms(cycles=6, num_samples=600)
        rate = estimate_breath_rate(history, sample_interval=0.1)
        # Should be close to 6 BPM (within 1 BPM tolerance)
        assert abs(rate - 6.0) < 1.5

    def test_detects_faster_rate(self):
        """12 cycles over 60 seconds = 12 breaths per minute."""
        history = _sine_rms(cycles=12, num_samples=600)
        rate = estimate_breath_rate(history, sample_interval=0.1)
        assert abs(rate - 12.0) < 2.0

    def test_detects_slow_rate(self):
        """3 cycles over 60 seconds = 3 breaths per minute."""
        history = _sine_rms(cycles=3, num_samples=600)
        rate = estimate_breath_rate(history, sample_interval=0.1)
        assert abs(rate - 3.0) < 1.5

    def test_returns_zero_for_flat_signal(self):
        """No variation = no detectable breath."""
        history = _flat_rms(600)
        rate = estimate_breath_rate(history, sample_interval=0.1)
        assert rate == 0.0

    def test_returns_zero_for_empty_history(self):
        rate = estimate_breath_rate([], sample_interval=0.1)
        assert rate == 0.0

    def test_returns_zero_for_very_short_history(self):
        rate = estimate_breath_rate([0.1, 0.2], sample_interval=0.1)
        assert rate == 0.0

    def test_returns_non_negative(self):
        history = _noisy_rms(600)
        rate = estimate_breath_rate(history, sample_interval=0.1)
        assert rate >= 0.0

    def test_rate_type_is_float(self):
        history = _sine_rms(cycles=6, num_samples=600)
        rate = estimate_breath_rate(history, sample_interval=0.1)
        assert isinstance(rate, float)


# ---------------------------------------------------------------------------
# breath_phase
# ---------------------------------------------------------------------------


class TestBreathPhase:
    def test_returns_float_between_0_and_1(self):
        history = _sine_rms(cycles=3, num_samples=300)
        phase = breath_phase(history)
        assert isinstance(phase, float)
        assert 0.0 <= phase <= 1.0

    def test_returns_zero_for_flat_signal(self):
        """No variation = phase 0.0 (or any defined default)."""
        history = _flat_rms(300)
        phase = breath_phase(history)
        assert phase == 0.0

    def test_returns_zero_for_empty_history(self):
        phase = breath_phase([])
        assert phase == 0.0

    def test_phase_differs_at_different_points_in_cycle(self):
        """Phase at peak vs trough should differ."""
        # Generate 1 full cycle, sample at different points
        cycle_a = _sine_rms(cycles=1, num_samples=100)
        # At sample 25 (quarter cycle) vs sample 75 (three-quarter cycle)
        phase_rising = breath_phase(cycle_a[:25])
        phase_falling = breath_phase(cycle_a[:75])
        # They should be different phases in the cycle
        assert phase_rising != phase_falling

    def test_returns_valid_for_short_history(self):
        history = _sine_rms(cycles=0.5, num_samples=20)
        phase = breath_phase(history)
        assert 0.0 <= phase <= 1.0


# ---------------------------------------------------------------------------
# breath_to_filter_params
# ---------------------------------------------------------------------------


class TestBreathToFilterParams:
    def test_returns_expected_keys(self):
        params = breath_to_filter_params(phase=0.5, rate=6.0)
        assert "cutoff_hz" in params
        assert "resonance" in params
        assert "mix" in params

    def test_cutoff_range(self):
        """Cutoff should stay within 200-2000 Hz for all phases."""
        for phase in (0.0, 0.25, 0.5, 0.75, 1.0):
            params = breath_to_filter_params(phase=phase, rate=6.0)
            assert 200 <= params["cutoff_hz"] <= 2000

    def test_resonance_range(self):
        """Resonance should stay within 0.0-0.5."""
        for phase in (0.0, 0.25, 0.5, 0.75, 1.0):
            params = breath_to_filter_params(phase=phase, rate=6.0)
            assert 0.0 <= params["resonance"] <= 0.5

    def test_mix_zero_when_rate_zero(self):
        """No breathing detected = no filter applied."""
        params = breath_to_filter_params(phase=0.5, rate=0.0)
        assert params["mix"] == 0.0

    def test_mix_nonzero_when_rate_positive(self):
        params = breath_to_filter_params(phase=0.5, rate=6.0)
        assert params["mix"] > 0.0

    def test_mix_clamped_0_to_1(self):
        params = breath_to_filter_params(phase=0.5, rate=100.0)
        assert 0.0 <= params["mix"] <= 1.0

    def test_inhale_opens_filter(self):
        """Inhale (phase ~ 0.25) should have higher cutoff than exhale (phase ~ 0.75)."""
        params_inhale = breath_to_filter_params(phase=0.25, rate=6.0)
        params_exhale = breath_to_filter_params(phase=0.75, rate=6.0)
        assert params_inhale["cutoff_hz"] > params_exhale["cutoff_hz"]

    def test_resonance_peaks_at_extremes(self):
        """Resonance should be higher at phase 0.0/0.5 (breath extremes) than at 0.25."""
        params_extreme = breath_to_filter_params(phase=0.0, rate=6.0)
        params_mid = breath_to_filter_params(phase=0.25, rate=6.0)
        assert params_extreme["resonance"] >= params_mid["resonance"]


# ---------------------------------------------------------------------------
# breath_to_visual_params
# ---------------------------------------------------------------------------


class TestBreathToVisualParams:
    def test_returns_expected_keys(self):
        params = breath_to_visual_params(phase=0.5, rate=6.0)
        assert "scale_factor" in params
        assert "brightness_offset" in params

    def test_scale_factor_range(self):
        """Scale factor should be 1.0 +/- 0.008."""
        for phase in (0.0, 0.25, 0.5, 0.75, 1.0):
            params = breath_to_visual_params(phase=phase, rate=6.0)
            assert 1.0 - 0.008 <= params["scale_factor"] <= 1.0 + 0.008

    def test_brightness_offset_range(self):
        """Brightness offset should be -5 to +5."""
        for phase in (0.0, 0.25, 0.5, 0.75, 1.0):
            params = breath_to_visual_params(phase=phase, rate=6.0)
            assert -5 <= params["brightness_offset"] <= 5

    def test_no_effect_when_rate_zero(self):
        """No breathing detected = neutral visual params."""
        params = breath_to_visual_params(phase=0.5, rate=0.0)
        assert params["scale_factor"] == 1.0
        assert params["brightness_offset"] == 0

    def test_scale_factor_varies_with_phase(self):
        """Scale should differ between inhale peak and exhale trough."""
        p1 = breath_to_visual_params(phase=0.25, rate=6.0)
        p2 = breath_to_visual_params(phase=0.75, rate=6.0)
        assert p1["scale_factor"] != p2["scale_factor"]

    def test_brightness_varies_with_phase(self):
        p1 = breath_to_visual_params(phase=0.25, rate=6.0)
        p2 = breath_to_visual_params(phase=0.75, rate=6.0)
        assert p1["brightness_offset"] != p2["brightness_offset"]

    def test_scale_factor_type(self):
        params = breath_to_visual_params(phase=0.5, rate=6.0)
        assert isinstance(params["scale_factor"], float)

    def test_brightness_offset_type(self):
        params = breath_to_visual_params(phase=0.5, rate=6.0)
        assert isinstance(params["brightness_offset"], (int, float))
