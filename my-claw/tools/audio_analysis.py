"""Pure audio analysis functions for CypherClaw's listening system.

No I/O, no file access, no subprocess calls. Takes sample arrays, returns results.
Stdlib only — no numpy.
"""
from __future__ import annotations

import math


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
