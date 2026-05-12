"""Tests for breath_to_filter.py — house breathing rhythm to audio/visual filter parameters."""
from __future__ import annotations

import json
import math
import os
import sys


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


# ---------------------------------------------------------------------------
# End-to-end coverage — depth-2 pipeline tests
# ---------------------------------------------------------------------------


class TestBreathToFilterEndToEnd:
    """Drive the full breath analysis pipeline across complete synthetic
    RMS histories, exercising the public API end-to-end through breath
    rate estimation, phase extraction, and filter/visual parameter
    derivation. These tests use looped and table-driven assertions to
    exercise real listening paths rather than single-call checks.
    """

    def test_full_pipeline_across_breath_rates(self) -> None:
        """Sine breath signals at known BPMs should round-trip through
        the full estimate→phase→filter→visual pipeline with valid
        params at every step."""
        cases = [(3.0, 1.5), (6.0, 1.5), (12.0, 2.0)]
        for expected_bpm, tolerance in cases:
            history = _sine_rms(cycles=expected_bpm, num_samples=600)
            rate = estimate_breath_rate(history, sample_interval=0.1)
            phase = breath_phase(history)
            fp = breath_to_filter_params(phase=phase, rate=rate)
            vp = breath_to_visual_params(phase=phase, rate=rate)

            assert abs(rate - expected_bpm) < tolerance, expected_bpm
            assert 0.0 <= phase <= 1.0
            assert 200.0 <= fp["cutoff_hz"] <= 2000.0
            assert 0.0 <= fp["resonance"] <= 0.5
            assert 0.0 < fp["mix"] <= 1.0
            assert 1.0 - 0.008 <= vp["scale_factor"] <= 1.0 + 0.008
            assert -5 <= vp["brightness_offset"] <= 5

    def test_full_pipeline_handles_flat_signal(self) -> None:
        """A flat RMS history yields zero rate and the documented neutral
        filter/visual contract end-to-end."""
        history = _flat_rms(num_samples=600, value=0.12)
        rate = estimate_breath_rate(history, sample_interval=0.1)
        phase = breath_phase(history)
        fp = breath_to_filter_params(phase=phase, rate=rate)
        vp = breath_to_visual_params(phase=phase, rate=rate)

        assert rate == 0.0
        assert phase == 0.0
        assert fp["mix"] == 0.0
        assert fp["resonance"] == 0.0
        assert fp["cutoff_hz"] == round((200.0 + 2000.0) / 2.0, 1)
        assert vp["scale_factor"] == 1.0
        assert vp["brightness_offset"] == 0

    def test_full_pipeline_handles_empty_history(self) -> None:
        """Empty histories must not raise and must produce neutral output."""
        for history in ([], [0.1], [0.1, 0.2]):
            rate = estimate_breath_rate(history, sample_interval=0.1)
            phase = breath_phase(history)
            fp = breath_to_filter_params(phase=phase, rate=rate)
            vp = breath_to_visual_params(phase=phase, rate=rate)
            assert rate == 0.0
            assert phase == 0.0
            assert fp["mix"] == 0.0
            assert vp["scale_factor"] == 1.0
            assert vp["brightness_offset"] == 0

    def test_phase_sweep_filter_contracts(self) -> None:
        """Across a phase table, cutoff peaks at inhale (0.25), troughs at
        exhale (0.75); resonance peaks at extremes (0.0/0.5) and
        approaches zero at quarter-cycle points."""
        sweep = [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0]
        cutoffs: list[float] = []
        resonances: list[float] = []
        for phase in sweep:
            fp = breath_to_filter_params(phase=phase, rate=6.0)
            assert 200.0 <= fp["cutoff_hz"] <= 2000.0
            assert 0.0 <= fp["resonance"] <= 0.5
            cutoffs.append(fp["cutoff_hz"])
            resonances.append(fp["resonance"])

        # phase 0.25 (index 2) is the maximum cutoff in the sweep
        assert cutoffs[2] == max(cutoffs)
        # phase 0.75 (index 6) is the minimum cutoff in the sweep
        assert cutoffs[6] == min(cutoffs)
        # phases 0.0 and 0.5 are resonance peaks; 0.25/0.75 are minima
        assert resonances[0] >= resonances[1]
        assert resonances[4] >= resonances[3]
        assert resonances[2] < resonances[0]
        assert resonances[6] < resonances[4]

    def test_phase_sweep_visual_contracts(self) -> None:
        """Visual scale and brightness mirror the breath wave: max at
        inhale (0.25) and min at exhale (0.75)."""
        sweep = [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0]
        scales: list[float] = []
        brights: list[float] = []
        for phase in sweep:
            vp = breath_to_visual_params(phase=phase, rate=6.0)
            assert 1.0 - 0.008 <= vp["scale_factor"] <= 1.0 + 0.008
            assert -5 <= vp["brightness_offset"] <= 5
            scales.append(vp["scale_factor"])
            brights.append(vp["brightness_offset"])

        assert scales[2] == max(scales)
        assert scales[6] == min(scales)
        assert brights[2] == max(brights)
        assert brights[6] == min(brights)

    def test_mix_saturation_curve(self) -> None:
        """Mix is monotone non-decreasing as rate climbs and saturates at
        1.0 above the documented 15 BPM saturation point."""
        rates = [0.0, 1.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0, 24.0, 30.0]
        previous = -1.0
        for rate in rates:
            fp = breath_to_filter_params(phase=0.5, rate=rate)
            mix = fp["mix"]
            assert mix >= previous, (rate, mix, previous)
            assert 0.0 <= mix <= 1.0
            if rate == 0.0:
                assert mix == 0.0
            if rate >= 15.0:
                assert mix == 1.0
            previous = mix

    def test_zero_rate_neutralises_filter_and_visual(self) -> None:
        """A zero rate at any phase returns the documented neutral
        contract for both filter and visual outputs."""
        for phase in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
            fp = breath_to_filter_params(phase=phase, rate=0.0)
            vp = breath_to_visual_params(phase=phase, rate=0.0)
            assert fp["mix"] == 0.0
            assert fp["resonance"] == 0.0
            assert vp["scale_factor"] == 1.0
            assert vp["brightness_offset"] == 0

    def test_filter_outputs_are_json_safe(self) -> None:
        """All filter param dicts can round-trip through JSON without
        loss for a sweep of phases at a representative rate."""
        sweep = [0.0, 0.25, 0.5, 0.75, 1.0]
        encoded_dicts: list[dict] = []
        for phase in sweep:
            fp = breath_to_filter_params(phase=phase, rate=6.0)
            blob = json.dumps(fp, sort_keys=True)
            decoded = json.loads(blob)
            assert decoded["cutoff_hz"] == fp["cutoff_hz"]
            assert decoded["resonance"] == fp["resonance"]
            assert decoded["mix"] == fp["mix"]
            encoded_dicts.append(decoded)
        assert len(encoded_dicts) == len(sweep)

    def test_visual_outputs_are_json_safe(self) -> None:
        """Visual param dicts must serialise across a phase sweep without
        loss, including the integer brightness_offset field."""
        sweep = [0.0, 0.25, 0.5, 0.75, 1.0]
        encoded_dicts: list[dict] = []
        for phase in sweep:
            vp = breath_to_visual_params(phase=phase, rate=6.0)
            blob = json.dumps(vp, sort_keys=True)
            decoded = json.loads(blob)
            assert decoded["scale_factor"] == vp["scale_factor"]
            assert decoded["brightness_offset"] == vp["brightness_offset"]
            encoded_dicts.append(decoded)
        assert len(encoded_dicts) == len(sweep)

    def test_pipeline_outputs_feed_diagnostics(self) -> None:
        """Full pipeline produces a JSON-safe diagnostic record per
        signal type (sine breath, flat silence, noisy)."""
        signals = {
            "calm": _sine_rms(cycles=6, num_samples=600),
            "fast": _sine_rms(cycles=12, num_samples=600),
            "flat": _flat_rms(num_samples=600, value=0.1),
            "noisy": _noisy_rms(num_samples=600),
        }
        diagnostics: dict[str, dict] = {}
        for name, history in signals.items():
            rate = estimate_breath_rate(history, sample_interval=0.1)
            phase = breath_phase(history)
            diagnostics[name] = {
                "rate_bpm": rate,
                "phase": phase,
                "filter": breath_to_filter_params(phase=phase, rate=rate),
                "visual": breath_to_visual_params(phase=phase, rate=rate),
            }
        encoded = json.dumps(diagnostics, sort_keys=True)
        assert "\"calm\"" in encoded
        assert diagnostics["flat"]["rate_bpm"] == 0.0
        assert diagnostics["flat"]["filter"]["mix"] == 0.0
        assert diagnostics["flat"]["visual"]["scale_factor"] == 1.0
        assert diagnostics["calm"]["filter"]["mix"] > 0.0
        assert diagnostics["fast"]["filter"]["mix"] >= diagnostics["calm"]["filter"]["mix"]

    def test_breath_rate_detected_within_tolerance_per_bpm(self) -> None:
        """Sweep multiple synthetic BPMs and assert rate detection stays
        within the documented tolerance for each."""
        cases = [(3.0, 1.5), (4.0, 1.5), (6.0, 1.5), (8.0, 1.5), (12.0, 2.0)]
        detected: list[tuple[float, float]] = []
        for expected_bpm, tolerance in cases:
            history = _sine_rms(cycles=expected_bpm, num_samples=600)
            rate = estimate_breath_rate(history, sample_interval=0.1)
            assert abs(rate - expected_bpm) < tolerance, (expected_bpm, rate)
            detected.append((expected_bpm, rate))
        assert len(detected) == len(cases)
        for expected_bpm, rate in detected:
            assert rate > 0.0, expected_bpm

    def test_phase_within_unit_interval_for_all_signal_types(self) -> None:
        """Phase must always fall in [0, 1] regardless of signal shape."""
        signal_factories = [
            lambda: _sine_rms(cycles=6, num_samples=600),
            lambda: _sine_rms(cycles=3, num_samples=600),
            lambda: _flat_rms(num_samples=600),
            lambda: _noisy_rms(num_samples=600),
            lambda: _sine_rms(cycles=0.5, num_samples=20),
        ]
        for factory in signal_factories:
            history = factory()
            phase = breath_phase(history)
            assert 0.0 <= phase <= 1.0
            assert isinstance(phase, float)

    def test_filter_cutoff_decreases_from_inhale_to_exhale(self) -> None:
        """Across multiple rates, the inhale phase always opens the
        filter wider than the exhale phase."""
        for rate in (3.0, 6.0, 9.0, 12.0, 15.0):
            inhale = breath_to_filter_params(phase=0.25, rate=rate)
            exhale = breath_to_filter_params(phase=0.75, rate=rate)
            assert inhale["cutoff_hz"] > exhale["cutoff_hz"], rate
            assert inhale["mix"] == exhale["mix"]

    def test_visual_scale_decreases_from_inhale_to_exhale(self) -> None:
        """Visual scale_factor mirrors the filter cutoff: bigger at
        inhale, smaller at exhale, across multiple rates."""
        for rate in (3.0, 6.0, 9.0, 12.0, 15.0):
            inhale = breath_to_visual_params(phase=0.25, rate=rate)
            exhale = breath_to_visual_params(phase=0.75, rate=rate)
            assert inhale["scale_factor"] > exhale["scale_factor"], rate
            assert inhale["brightness_offset"] >= exhale["brightness_offset"]

    def test_pipeline_is_deterministic(self) -> None:
        """Running the same RMS history through the pipeline twice must
        produce identical rate, phase, filter, and visual params."""
        histories = [
            _sine_rms(cycles=6, num_samples=600),
            _sine_rms(cycles=12, num_samples=600),
            _flat_rms(num_samples=600),
        ]
        for history in histories:
            rate_a = estimate_breath_rate(history, sample_interval=0.1)
            phase_a = breath_phase(history)
            fp_a = breath_to_filter_params(phase=phase_a, rate=rate_a)
            vp_a = breath_to_visual_params(phase=phase_a, rate=rate_a)

            rate_b = estimate_breath_rate(history, sample_interval=0.1)
            phase_b = breath_phase(history)
            fp_b = breath_to_filter_params(phase=phase_b, rate=rate_b)
            vp_b = breath_to_visual_params(phase=phase_b, rate=rate_b)

            assert rate_a == rate_b
            assert phase_a == phase_b
            assert fp_a == fp_b
            assert vp_a == vp_b

    def test_resonance_peaks_at_extremes_table(self) -> None:
        """Table-driven check that resonance is highest at breath extremes
        (phase 0.0 and 0.5) and approaches zero at quarter-cycle phases."""
        extremes = [0.0, 0.5, 1.0]
        midpoints = [0.25, 0.75]
        peak_resonances: list[float] = []
        mid_resonances: list[float] = []
        for phase in extremes:
            fp = breath_to_filter_params(phase=phase, rate=6.0)
            peak_resonances.append(fp["resonance"])
        for phase in midpoints:
            fp = breath_to_filter_params(phase=phase, rate=6.0)
            mid_resonances.append(fp["resonance"])
        assert min(peak_resonances) >= max(mid_resonances)
        for value in mid_resonances:
            assert value < 0.05

    def test_full_cycle_phase_progression_advances(self) -> None:
        """Sampling the same sine breath at successively longer windows
        produces phase values that span the [0, 1] interval as the
        observation window covers more of the cycle."""
        full = _sine_rms(cycles=1, num_samples=200)
        observed: list[float] = []
        for end in (50, 100, 150, 200):
            window = full[:end]
            observed.append(breath_phase(window))
        # Distinct phases across a full cycle's progression
        assert len(set(round(p, 3) for p in observed)) >= 2
        for value in observed:
            assert 0.0 <= value <= 1.0

    def test_filter_cutoff_value_matches_expected_curve(self) -> None:
        """Spot-check the documented cosine cutoff curve at known phases
        within the published tolerance."""
        expected_extremes = {
            0.25: 2000.0,  # inhale peak
            0.75: 200.0,   # exhale trough
        }
        observed: dict[float, float] = {}
        for phase, expected in expected_extremes.items():
            fp = breath_to_filter_params(phase=phase, rate=6.0)
            observed[phase] = fp["cutoff_hz"]
            assert abs(fp["cutoff_hz"] - expected) < 1.0
        assert observed[0.25] > observed[0.75]
        assert observed[0.25] - observed[0.75] > 1500.0
