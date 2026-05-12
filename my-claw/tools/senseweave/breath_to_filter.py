"""Breath-to-Filter — maps house breathing rhythm to audio/visual filter parameters.

CypherClaw's house has a heartbeat (contact mic on the case).  The RMS
envelope of that signal rises and falls like breathing.  This module
extracts that rhythm and maps it to:

  - Audio filter sweep (cutoff, resonance, wet/dry mix)
  - Visual breathing animation (scale pulse, brightness offset)

All analysis is stdlib-only: no numpy, no scipy.  We use simple
zero-crossing and autocorrelation on the RMS envelope.
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum number of RMS samples needed to estimate breath rate
_MIN_SAMPLES = 16

# Breath rate limits (cycles per minute)
_MIN_BPM = 1.0
_MAX_BPM = 30.0

# Filter parameter ranges
_CUTOFF_MIN = 200.0    # Hz
_CUTOFF_MAX = 2000.0   # Hz
_RESONANCE_MAX = 0.5

# Visual parameter ranges
_SCALE_AMPLITUDE = 0.008   # +/- around 1.0
_BRIGHTNESS_AMPLITUDE = 5  # +/- integer offset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _detrend(values: list[float]) -> list[float]:
    """Remove the mean from a signal (simple detrending)."""
    m = _mean(values)
    return [v - m for v in values]


def _autocorrelation(signal: list[float], max_lag: int) -> list[float]:
    """Compute normalised autocorrelation for lags 0..max_lag.

    Returns a list of length max_lag+1.  Index 0 is always 1.0
    (or 0.0 if signal is all zeros).
    """
    n = len(signal)
    if n == 0:
        return [0.0] * (max_lag + 1)

    # Energy at lag 0
    energy = sum(s * s for s in signal)
    if energy == 0.0:
        return [0.0] * (max_lag + 1)

    result = []
    for lag in range(max_lag + 1):
        if lag >= n:
            result.append(0.0)
            continue
        acc = 0.0
        for i in range(n - lag):
            acc += signal[i] * signal[i + lag]
        result.append(acc / energy)
    return result


# ---------------------------------------------------------------------------
# estimate_breath_rate
# ---------------------------------------------------------------------------


def estimate_breath_rate(rms_history: list[float], sample_interval: float) -> float:
    """Estimate breathing rate from RMS envelope.

    Parameters
    ----------
    rms_history : list[float]
        RMS values sampled at regular intervals.
    sample_interval : float
        Seconds between consecutive samples.

    Returns
    -------
    float
        Estimated breath rate in cycles per minute.
        Returns 0.0 if no periodic pattern is found.
    """
    if len(rms_history) < _MIN_SAMPLES:
        return 0.0

    detrended = _detrend(rms_history)

    # Check if signal has any variation
    peak = max(abs(v) for v in detrended)
    if peak < 1e-9:
        return 0.0

    # Autocorrelation — look for first peak after lag 0
    # Max lag covers the slowest breath we'd detect (_MIN_BPM)
    max_period_samples = int(60.0 / (_MIN_BPM * sample_interval))
    max_lag = min(max_period_samples, len(detrended) // 2)

    if max_lag < 2:
        return 0.0

    acorr = _autocorrelation(detrended, max_lag)

    # Find the first significant peak after the initial descent from lag 0.
    # This avoids locking onto harmonics/subharmonics — the first peak
    # corresponds to the fundamental period.
    min_period_samples = max(2, int(60.0 / (_MAX_BPM * sample_interval)))

    # Step 1: walk past initial descent — find where acorr first dips
    #         below a threshold (entered the first trough).
    past_descent = min_period_samples
    for lag in range(min_period_samples, max_lag):
        if acorr[lag] < acorr[lag - 1]:
            past_descent = lag
            continue
        # acorr started rising again — we're past the trough
        break

    # Step 2: from there, find the first local maximum
    best_lag = 0
    best_val = -1.0
    rising = False
    for lag in range(past_descent, max_lag + 1):
        if acorr[lag] > acorr[lag - 1]:
            rising = True
        if rising and acorr[lag] < acorr[lag - 1]:
            # We just passed a peak at lag-1
            best_lag = lag - 1
            best_val = acorr[lag - 1]
            break

    # Edge case: still rising at max_lag
    if best_lag == 0 and rising and max_lag > past_descent:
        best_lag = max_lag
        best_val = acorr[max_lag]

    # Require a reasonably strong autocorrelation peak
    if best_lag == 0 or best_val < 0.15:
        return 0.0

    period_s = best_lag * sample_interval
    if period_s <= 0:
        return 0.0

    bpm = 60.0 / period_s
    return _clamp(bpm, _MIN_BPM, _MAX_BPM)


# ---------------------------------------------------------------------------
# breath_phase
# ---------------------------------------------------------------------------


def breath_phase(rms_history: list[float]) -> float:
    """Return current phase in the breath cycle.

    Uses zero-crossings of the detrended RMS to estimate phase:
      0.0 = inhale start (rising through zero)
      0.5 = exhale start (falling through zero)
      1.0 = next cycle start

    Returns 0.0 if no pattern is detectable.
    """
    if len(rms_history) < 4:
        return 0.0

    detrended = _detrend(rms_history)

    # Check for any variation
    peak = max(abs(v) for v in detrended)
    if peak < 1e-9:
        return 0.0

    # Find zero crossings
    crossings: list[tuple[int, str]] = []  # (index, "up" | "down")
    for i in range(1, len(detrended)):
        if detrended[i - 1] <= 0 < detrended[i]:
            crossings.append((i, "up"))
        elif detrended[i - 1] > 0 >= detrended[i]:
            crossings.append((i, "down"))

    if len(crossings) < 2:
        # Not enough crossings — estimate from last value's sign
        if detrended[-1] > 0:
            return 0.25  # somewhere in inhale
        else:
            return 0.75  # somewhere in exhale

    # Use the last two crossings to estimate phase of the final sample
    last_crossing_idx, last_crossing_dir = crossings[-1]
    prev_crossing_idx, _ = crossings[-2]

    # Half-cycle length from last two crossings
    half_cycle = last_crossing_idx - prev_crossing_idx
    if half_cycle <= 0:
        half_cycle = 1

    # How far are we past the last crossing?
    samples_past = len(detrended) - 1 - last_crossing_idx
    fraction_past = samples_past / (half_cycle * 2)  # fraction of full cycle

    if last_crossing_dir == "up":
        # Last crossing was rising (inhale start = 0.0)
        phase = 0.0 + fraction_past
    else:
        # Last crossing was falling (exhale start = 0.5)
        phase = 0.5 + fraction_past

    return _clamp(phase % 1.0, 0.0, 1.0)


# ---------------------------------------------------------------------------
# breath_to_filter_params
# ---------------------------------------------------------------------------


def breath_to_filter_params(phase: float, rate: float) -> dict:
    """Map breath phase and rate to audio filter parameters.

    Parameters
    ----------
    phase : float
        Current breath phase (0.0 to 1.0).
    rate : float
        Breathing rate in cycles per minute (0.0 = undetected).

    Returns
    -------
    dict with keys:
        cutoff_hz  : float  200-2000 Hz, sweeps with breath phase
        resonance  : float  0.0-0.5, peaks at breath extremes
        mix        : float  0.0-1.0, how much filter to apply
    """
    if rate <= 0.0:
        return {
            "cutoff_hz": (_CUTOFF_MIN + _CUTOFF_MAX) / 2.0,
            "resonance": 0.0,
            "mix": 0.0,
        }

    # Cutoff sweeps sinusoidally with phase.
    # phase 0.25 (peak inhale) = max cutoff, phase 0.75 (peak exhale) = min cutoff
    # Use cosine so that phase=0.25 -> cos(0) = 1.0 (max)
    cutoff_norm = 0.5 + 0.5 * math.cos(2 * math.pi * (phase - 0.25))
    cutoff_hz = _CUTOFF_MIN + cutoff_norm * (_CUTOFF_MAX - _CUTOFF_MIN)
    cutoff_hz = _clamp(cutoff_hz, _CUTOFF_MIN, _CUTOFF_MAX)

    # Resonance peaks at breath extremes (phase 0.0/0.5/1.0 = zero crossings)
    # Use |cos(2*pi*phase)| so peaks are at 0.0 and 0.5
    resonance = _RESONANCE_MAX * abs(math.cos(2 * math.pi * phase))
    resonance = _clamp(resonance, 0.0, _RESONANCE_MAX)

    # Mix: proportional to rate, saturates around 15 BPM
    mix = _clamp(rate / 15.0, 0.0, 1.0)

    return {
        "cutoff_hz": round(cutoff_hz, 1),
        "resonance": round(resonance, 4),
        "mix": round(mix, 3),
    }


# ---------------------------------------------------------------------------
# breath_to_visual_params
# ---------------------------------------------------------------------------


def breath_to_visual_params(phase: float, rate: float) -> dict:
    """Map breath phase and rate to visual parameters for the face display.

    Parameters
    ----------
    phase : float
        Current breath phase (0.0 to 1.0).
    rate : float
        Breathing rate in cycles per minute (0.0 = undetected).

    Returns
    -------
    dict with keys:
        scale_factor      : float  1.0 +/- 0.008 (subtle breathing)
        brightness_offset : int    -5 to +5 (subtle brightness pulse)
    """
    if rate <= 0.0:
        return {
            "scale_factor": 1.0,
            "brightness_offset": 0,
        }

    # Scale oscillates sinusoidally with breath phase
    # phase 0.25 (peak inhale) = max scale, phase 0.75 = min scale
    breath_wave = math.cos(2 * math.pi * (phase - 0.25))
    scale_factor = 1.0 + _SCALE_AMPLITUDE * breath_wave
    scale_factor = _clamp(scale_factor, 1.0 - _SCALE_AMPLITUDE, 1.0 + _SCALE_AMPLITUDE)

    # Brightness follows the same wave
    brightness_offset = round(_BRIGHTNESS_AMPLITUDE * breath_wave)
    brightness_offset = int(_clamp(brightness_offset, -_BRIGHTNESS_AMPLITUDE, _BRIGHTNESS_AMPLITUDE))

    return {
        "scale_factor": round(scale_factor, 6),
        "brightness_offset": brightness_offset,
    }
