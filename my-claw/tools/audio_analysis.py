"""Pure audio analysis functions for CypherClaw's listening system.

No I/O, no file access, no subprocess calls. Takes sample arrays, returns results.
Stdlib only — no numpy.
"""
from __future__ import annotations

import math
import statistics


def detect_amplitude(samples: list[int] | list[float]) -> tuple[float, float]:
    """Return (rms, peak) normalized to 0.0-1.0 for 16-bit audio."""
    if not samples:
        return 0.0, 0.0
    max_val = 32768.0
    peak = max(abs(s) for s in samples) / max_val
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / max_val
    return rms, peak


def detect_pitch_autocorrelation(
    samples: list[int] | list[float],
    sample_rate: int,
    *,
    min_freq: float = 80.0,
    max_freq: float = 2000.0,
    confidence_threshold: float = 0.3,
) -> tuple[float | None, float]:
    """Detect fundamental pitch via autocorrelation.

    Returns (frequency_hz, confidence) or (None, 0.0) if no pitch found.
    Confidence is the normalized autocorrelation peak (0.0-1.0).
    """
    n = len(samples)
    if n < 2:
        return None, 0.0

    # Check if signal is loud enough
    rms, _ = detect_amplitude(samples)
    if rms < 0.005:
        return None, 0.0

    # Lag range from frequency bounds
    min_lag = max(1, int(sample_rate / max_freq))
    max_lag = min(n // 2, int(sample_rate / min_freq))

    if min_lag >= max_lag:
        return None, 0.0

    # Normalize samples to float
    mean = sum(samples) / n
    centered = [s - mean for s in samples]

    # Autocorrelation at lag 0 for normalization
    energy = sum(s * s for s in centered)
    if energy < 1e-10:
        return None, 0.0

    # Find the autocorrelation peak in the valid lag range
    best_lag = min_lag
    best_corr = -1.0

    for lag in range(min_lag, max_lag):
        corr = 0.0
        for i in range(n - lag):
            corr += centered[i] * centered[i + lag]
        corr /= energy
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    if best_corr < confidence_threshold:
        return None, 0.0

    # Parabolic interpolation for sub-sample accuracy
    if min_lag < best_lag < max_lag - 1:
        # Compute neighbors
        corr_prev = sum(
            centered[i] * centered[i + best_lag - 1] for i in range(n - best_lag)
        ) / energy
        corr_next = sum(
            centered[i] * centered[i + best_lag + 1] for i in range(n - best_lag - 1)
        ) / energy

        denom = 2.0 * (2.0 * best_corr - corr_prev - corr_next)
        if abs(denom) > 1e-10:
            shift = (corr_prev - corr_next) / denom
            refined_lag = best_lag + shift
        else:
            refined_lag = float(best_lag)
    else:
        refined_lag = float(best_lag)

    freq = sample_rate / refined_lag
    confidence = max(0.0, min(1.0, best_corr))
    return freq, confidence


def detect_onset(
    current_rms: float,
    previous_rms: float,
    *,
    onset_threshold_ratio: float = 3.0,
    release_threshold: float = 0.005,
) -> str:
    """Classify the transition between two amplitude windows.

    Returns 'onset', 'sustain', 'release', or 'silence'.
    """
    is_loud = current_rms > release_threshold
    was_loud = previous_rms > release_threshold

    if is_loud and not was_loud:
        return "onset"
    if is_loud and was_loud:
        if previous_rms > 0 and current_rms / previous_rms > onset_threshold_ratio:
            return "onset"
        return "sustain"
    if not is_loud and was_loud:
        return "release"
    return "silence"


def detect_click_transients(
    samples: list[int] | list[float],
    sample_rate: int,
    *,
    median_radius: int = 4,
    context_window_ms: float = 5.0,
    guard_samples: int = 3,
    min_residual: float = 0.15,
    min_ratio: float = 10.0,
    max_width_samples: int = 4,
    refractory_ms: float = 8.0,
    max_click_rate_hz: float = 10.0,
) -> dict:
    """Detect sparse click/pop transients in a mono waveform.

    The detector looks for samples that deviate sharply from the local median,
    then rejects dense periodic discontinuities such as hard-edged waveforms.
    """
    if not samples or sample_rate <= 0:
        return {
            "count": 0,
            "events": [],
            "max_residual": 0.0,
            "max_ratio": 0.0,
            "suppressed_as_periodic": False,
        }

    norm = [
        (float(s) / 32768.0) if abs(float(s)) > 1.5 else float(s)
        for s in samples
    ]

    if len(norm) <= (median_radius * 2) + 1:
        return {
            "count": 0,
            "events": [],
            "max_residual": 0.0,
            "max_ratio": 0.0,
            "suppressed_as_periodic": False,
        }

    residuals = [0.0] * len(norm)
    for i in range(median_radius, len(norm) - median_radius):
        neighborhood = norm[i - median_radius : i] + norm[i + 1 : i + median_radius + 1]
        median = statistics.median(neighborhood)
        residuals[i] = abs(norm[i] - median)

    sq_prefix = [0.0]
    for residual in residuals:
        sq_prefix.append(sq_prefix[-1] + (residual * residual))

    def _window_energy(start: int, end: int) -> tuple[float, int]:
        start = max(0, start)
        end = min(len(residuals), end)
        if end <= start:
            return 0.0, 0
        return sq_prefix[end] - sq_prefix[start], end - start

    context_radius = max(median_radius + 1, int(sample_rate * context_window_ms / 1000.0))
    refractory_samples = max(1, int(sample_rate * refractory_ms / 1000.0))
    events = []

    i = context_radius
    limit = len(norm) - context_radius
    while i < limit:
        residual = residuals[i]
        if residual < min_residual:
            i += 1
            continue

        if residual < max(residuals[i - 1], residuals[i + 1]):
            i += 1
            continue

        left_energy, left_count = _window_energy(i - context_radius, i - guard_samples)
        right_energy, right_count = _window_energy(i + guard_samples + 1, i + context_radius + 1)
        context_count = left_count + right_count
        if context_count <= 0:
            i += 1
            continue

        context_rms = math.sqrt((left_energy + right_energy) / context_count)
        ratio = residual / max(context_rms, 1e-12)
        if ratio < min_ratio:
            i += 1
            continue

        half_height = residual * 0.5
        width = 1
        left = i - 1
        while left >= 0 and residuals[left] >= half_height:
            width += 1
            left -= 1
        right = i + 1
        while right < len(residuals) and residuals[right] >= half_height:
            width += 1
            right += 1
        if width > max_width_samples:
            i += 1
            continue

        events.append(
            {
                "sample_index": i,
                "time_seconds": i / sample_rate,
                "sample_peak": abs(norm[i]),
                "residual": residual,
                "context_rms": context_rms,
                "ratio": ratio,
                "width_samples": width,
            }
        )
        i += refractory_samples

    duration_seconds = len(norm) / sample_rate
    click_rate = (len(events) / duration_seconds) if duration_seconds > 0 else 0.0
    if click_rate > max_click_rate_hz:
        return {
            "count": 0,
            "events": [],
            "max_residual": 0.0,
            "max_ratio": 0.0,
            "suppressed_as_periodic": True,
        }

    return {
        "count": len(events),
        "events": events,
        "max_residual": max((event["residual"] for event in events), default=0.0),
        "max_ratio": max((event["ratio"] for event in events), default=0.0),
        "suppressed_as_periodic": False,
    }


def classify_audio_content(
    samples: list[int] | list[float],
    sample_rate: int,
) -> dict:
    """Classify audio as speech-like, tonal, transient, or silence.

    Speech: high ZCR + high amplitude variance (dynamic).
    Tonal: low ZCR + low amplitude variance (steady, like Theramini).
    Transient: high peak-to-RMS ratio.
    Silence: RMS below threshold.
    """
    rms, peak = detect_amplitude(samples)

    if rms < 0.003:
        return {"type": "silence", "zcr": 0.0, "amp_variance": 0.0, "confidence": 0.9}

    # Zero-crossing rate
    crossings = 0
    for i in range(1, len(samples)):
        if (samples[i] >= 0) != (samples[i - 1] >= 0):
            crossings += 1
    zcr = crossings / len(samples) if samples else 0.0

    # Amplitude variance (split into windows, measure RMS variance)
    window_size = sample_rate // 10  # 100ms windows
    window_rms_values = []
    for i in range(0, len(samples) - window_size, window_size):
        chunk = samples[i : i + window_size]
        w_rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) / 32768.0
        window_rms_values.append(w_rms)

    if len(window_rms_values) > 1:
        mean_rms = sum(window_rms_values) / len(window_rms_values)
        amp_variance = math.sqrt(
            sum((r - mean_rms) ** 2 for r in window_rms_values)
            / len(window_rms_values)
        )
    else:
        amp_variance = 0.0

    # Peak-to-RMS ratio for transient detection
    crest = peak / rms if rms > 0 else 0.0

    # Classify
    if crest > 8.0:
        return {"type": "transient", "zcr": zcr, "amp_variance": amp_variance, "confidence": 0.7}

    if zcr > 0.05 and amp_variance > 0.005:
        conf = min(1.0, zcr * 10 + amp_variance * 50)
        return {"type": "speech", "zcr": zcr, "amp_variance": amp_variance, "confidence": conf}

    if zcr < 0.03 and amp_variance < 0.005:
        return {"type": "tonal", "zcr": zcr, "amp_variance": amp_variance, "confidence": 0.8}

    # Ambiguous — default to tonal (safer: avoids Whisper hallucinations)
    return {"type": "tonal", "zcr": zcr, "amp_variance": amp_variance, "confidence": 0.4}


_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_MAJOR_SCALE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]

_KEY_SCALES: dict[str, list[str]] = {}
for _i, _root in enumerate(_NOTE_NAMES):
    _scale = []
    for _semi in _MAJOR_SCALE_SEMITONES:
        _scale.append(_NOTE_NAMES[(_i + _semi) % 12])
    _KEY_SCALES[_root] = _scale


def pitch_to_note_name(frequency_hz: float) -> str:
    """Convert frequency to note name, e.g. 440.0 -> 'A4'."""
    if frequency_hz <= 0:
        return "?"
    midi = 69 + 12 * math.log2(frequency_hz / 440.0)
    note_idx = round(midi) % 12
    octave = (round(midi) // 12) - 1
    return f"{_NOTE_NAMES[note_idx]}{octave}"


def pitch_to_nearest_key(frequency_hz: float) -> tuple[str, list[str]]:
    """Given a detected pitch, find the nearest major scale root.

    Returns (root_note, scale_notes).
    E.g., 440.0 -> ('A', ['A', 'B', 'C#', 'D', 'E', 'F#', 'G#'])
    """
    if frequency_hz <= 0:
        return "C", _KEY_SCALES["C"]

    midi = 69 + 12 * math.log2(frequency_hz / 440.0)
    note_idx = round(midi) % 12
    root = _NOTE_NAMES[note_idx]
    return root, _KEY_SCALES[root]


def extract_spectral_peaks(
    samples: list[int] | list[float],
    sample_rate: int,
    *,
    max_peaks: int = 4,
    min_freq: float = 20.0,
    max_freq: float = 12000.0,
) -> list[float]:
    """Extract prominent spectral peaks using a pure Python radix-2 FFT approach."""
    if not samples:
        return []
    
    n = 1024
    if len(samples) > n:
        start = (len(samples) - n) // 2
        window = samples[start:start + n]
    else:
        window = list(samples)
        n = len(window)
    
    p = 1
    while p < n: p *= 2
    if p != n:
        window.extend([0.0] * (p - n))
        n = p

    def reverse_bits(val: int, width: int) -> int:
        res = 0
        for _ in range(width):
            res = (res << 1) | (val & 1)
            val >>= 1
        return res
        
    width = n.bit_length() - 1
    x_real = [float(s) for s in window]
    x_imag = [0.0] * n
    
    # Bit-reversal permutation
    for i in range(n):
        rev = reverse_bits(i, width)
        if i < rev:
            x_real[i], x_real[rev] = x_real[rev], x_real[i]
        
    # Cooley-Tukey Radix-2
    step = 1
    while step < n:
        half_step = step
        step <<= 1
        theta_step = -2.0 * math.pi / step
        for i in range(half_step):
            theta = i * theta_step
            wr = math.cos(theta)
            wi = math.sin(theta)
            for j in range(i, n, step):
                k = j + half_step
                tr = wr * x_real[k] - wi * x_imag[k]
                ti = wr * x_imag[k] + wi * x_real[k]
                x_real[k] = x_real[j] - tr
                x_imag[k] = x_imag[j] - ti
                x_real[j] += tr
                x_imag[j] += ti

    magnitudes = []
    for i in range(n // 2):
        mag = math.sqrt(x_real[i]**2 + x_imag[i]**2)
        freq = i * sample_rate / n
        if min_freq <= freq <= max_freq:
            magnitudes.append((freq, mag))
            
    peaks = []
    for i in range(1, len(magnitudes) - 1):
        if magnitudes[i][1] > magnitudes[i-1][1] and magnitudes[i][1] > magnitudes[i+1][1]:
            peaks.append(magnitudes[i])
            
    peaks.sort(key=lambda x: x[1], reverse=True)
    return [p[0] for p in peaks[:max_peaks]]
