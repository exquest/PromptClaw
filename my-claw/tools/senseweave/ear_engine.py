"""Lightweight musical self-analysis for tracker output and captured audio."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from .synthesis.continuous_learner import PlayedNote

_EPSILON = 1e-12


@dataclass(frozen=True)
class _EarEvent:
    frequency_hz: float
    duration_s: float
    amplitude: float
    accent: bool
    start_s: float


@dataclass(frozen=True)
class EqualLoudnessHint:
    """Suggested level adjustment for a frequency band at moderate listening levels."""

    band_low_hz: float
    band_high_hz: float
    compensation_db: float


@dataclass(frozen=True)
class CriticalListeningReport:
    """Full psychoacoustic evaluation of a musical passage."""

    spectral_balance: float
    dynamic_contour: float
    spatial_distribution: float
    timbral_quality: float
    rhythmic_activity: float
    harmonic_tension: float
    masking_risk: float
    equal_loudness_hints: tuple[EqualLoudnessHint, ...]


@dataclass(frozen=True)
class ProductionCorrection:
    """Actionable adjustment recommendations from critical listening."""

    density: float
    register: float
    eq_tilt: float
    dynamics: float
    palette: float


def _midi_number(freq: float) -> float:
    return 69.0 + 12.0 * math.log2(max(freq, 1e-6) / 440.0)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _round_metrics(metrics: Mapping[str, float]) -> dict[str, float]:
    rounded: dict[str, float] = {}
    for key, value in metrics.items():
        if key.endswith("_hz") or key == "pitch_hz":
            rounded[key] = round(float(value), 2)
        else:
            rounded[key] = round(float(value), 3)
    return rounded


def _get_value(source: object, *names: str, default: object = None) -> object:
    if isinstance(source, Mapping):
        for name in names:
            if name in source:
                return source[name]
    for name in names:
        if hasattr(source, name):
            return getattr(source, name)
    return default


def _float_value(source: object, *names: str, default: float = 0.0) -> float:
    value = _get_value(source, *names, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_value(source: object, *names: str, default: bool = False) -> bool:
    value = _get_value(source, *names, default=default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "accent"}
    return bool(value)


def _frequency_events_from_tracker(tracker_events: Sequence[object]) -> list[_EarEvent]:
    if not tracker_events:
        return []

    positive_durations = [
        _float_value(event, "duration_seconds", "duration_s", "duration", default=0.0)
        for event in tracker_events
    ]
    row_duration = min((duration for duration in positive_durations if duration > 0.0), default=0.25)
    events: list[_EarEvent] = []
    for index, event in enumerate(tracker_events):
        frequency = _float_value(event, "frequency_hz", "freq", "pitch_hz", default=0.0)
        if frequency <= 0.0:
            continue
        duration = max(
            0.001,
            _float_value(event, "duration_seconds", "duration_s", "duration", default=row_duration),
        )
        explicit_start = _get_value(event, "start_seconds", "time_seconds", "timestamp", default=None)
        if explicit_start is None:
            row = _float_value(event, "row", default=float(index))
            start = row * row_duration
        else:
            start = _float_value(event, "start_seconds", "time_seconds", "timestamp", default=float(index) * row_duration)
        events.append(
            _EarEvent(
                frequency_hz=frequency,
                duration_s=duration,
                amplitude=max(0.0, _float_value(event, "amplitude", "velocity", default=1.0)),
                accent=_bool_value(event, "accent"),
                start_s=start,
            )
        )
    return sorted(events, key=lambda event: (event.start_s, event.frequency_hz))


def _frequency_events_from_notes(notes: Sequence[PlayedNote]) -> list[_EarEvent]:
    events: list[_EarEvent] = []
    start = 0.0
    for note in notes:
        duration = max(0.001, float(note.duration or 0.0))
        if note.freq > 0.0:
            events.append(
                _EarEvent(
                    frequency_hz=float(note.freq),
                    duration_s=duration,
                    amplitude=1.0,
                    accent=bool(note.accent),
                    start_s=start,
                )
            )
        start += duration
    return events


def _onset_density(events: Sequence[_EarEvent]) -> float:
    if not events:
        return 0.0
    starts = {round(event.start_s, 3) for event in events}
    start = min(event.start_s for event in events)
    end = max(event.start_s + event.duration_s for event in events)
    duration = max(0.001, end - start)
    return len(starts) / duration


def _spectral_flatness(values: Sequence[float]) -> float:
    positives = [max(0.0, float(value)) for value in values]
    if not positives or sum(positives) <= _EPSILON:
        return 0.0
    arithmetic = sum(positives) / len(positives)
    geometric = math.exp(sum(math.log(value + _EPSILON) for value in positives) / len(positives))
    return _clamp(geometric / max(arithmetic, _EPSILON))


def _tracker_spectral_metrics(events: Sequence[_EarEvent]) -> dict[str, float]:
    if not events:
        return {
            "spectral_centroid_hz": 0.0,
            "spectral_flatness": 0.0,
            "roughness": 0.0,
        }

    weight_total = sum(max(event.amplitude, 0.001) for event in events)
    centroid = sum(event.frequency_hz * max(event.amplitude, 0.001) for event in events) / max(weight_total, _EPSILON)

    bins = [0.0] * 18
    for event in events:
        midi = _midi_number(event.frequency_hz)
        index = int(_clamp((midi - 24.0) / 4.0, 0.0, len(bins) - 1))
        bins[index] += max(event.amplitude, 0.001)

    roughness = _roughness_from_events(events)
    return {
        "spectral_centroid_hz": centroid,
        "spectral_flatness": _spectral_flatness(bins),
        "roughness": roughness,
    }


def _roughness_from_events(events: Sequence[_EarEvent]) -> float:
    weighted = 0.0
    possible = 0.0
    for index, left in enumerate(events):
        for right in events[index + 1 :]:
            if abs(left.start_s - right.start_s) > max(0.05, min(left.duration_s, right.duration_s) * 0.5):
                continue
            interval = abs(_midi_number(left.frequency_hz) - _midi_number(right.frequency_hz)) % 12.0
            distance_to_dissonance = min(
                abs(interval - target)
                for target in (1.0, 2.0, 6.0, 10.0, 11.0)
            )
            dissonance = _clamp(1.0 - (distance_to_dissonance / 1.5))
            pair_weight = math.sqrt(max(left.amplitude, 0.001) * max(right.amplitude, 0.001))
            weighted += dissonance * pair_weight
            possible += pair_weight
    return _clamp(weighted / max(possible, _EPSILON))


def _shape_repetition_score(intervals: Sequence[float]) -> float:
    if len(intervals) < 4:
        return 0.0
    shapes = [tuple(round(interval) for interval in intervals[index : index + 3]) for index in range(len(intervals) - 2)]
    if not shapes:
        return 0.0
    unique = len(set(shapes))
    return _clamp(1.0 - (unique / len(shapes)))


def _hook_clarity(
    *,
    intervals: Sequence[float],
    notes_count: int,
    accented_count: int,
    leap_ratio: float,
    repetition_score: float,
    cadence_strength: float,
) -> float:
    if notes_count < 2:
        return 0.0
    interval_variety = len({round(interval) for interval in intervals}) / max(1, len(intervals))
    variety_balance = 1.0 - abs(interval_variety - 0.45)
    accent_ratio = accented_count / max(1, notes_count)
    singability = 1.0 - max(0.0, leap_ratio - 0.35)
    return _clamp(
        0.18
        + repetition_score * 0.26
        + variety_balance * 0.22
        + min(0.18, accent_ratio * 0.7)
        + singability * 0.08
        + cadence_strength * 0.08
    )


def _cadence_strength(midis: Sequence[float], events: Sequence[_EarEvent]) -> float:
    if len(midis) < 2:
        return 0.0
    end_interval = abs(midis[-1] - midis[0])
    final_duration = events[-1].duration_s if events else 0.0
    avg_duration = sum(event.duration_s for event in events) / max(1, len(events))
    duration_bonus = 0.08 if final_duration >= avg_duration * 1.25 else 0.0
    accent_bonus = 0.08 if events and events[-1].accent else 0.0
    return _clamp(1.0 - min(end_interval, 12.0) / 12.0 + duration_bonus + accent_bonus)


def feedback_scores(metrics: Mapping[str, float]) -> dict[str, float]:
    """Convert raw ear metrics into corrective composition scores."""

    interval_variety = float(metrics.get("interval_variety", 0.0) or 0.0)
    pitch_range = float(metrics.get("pitch_range_semitones", metrics.get("register_spread", 0.0)) or 0.0)
    onset_density = float(metrics.get("onset_density", 0.0) or 0.0)
    repetition = float(metrics.get("repetition_score", 0.0) or 0.0)
    centroid = float(metrics.get("spectral_centroid_hz", 0.0) or 0.0)
    flatness = float(metrics.get("spectral_flatness", 0.0) or 0.0)
    roughness = float(metrics.get("roughness", 0.0) or 0.0)
    hook = float(metrics.get("hook_clarity", 0.0) or 0.0)
    cadence = float(metrics.get("cadence_strength", 0.0) or 0.0)
    development = float(metrics.get("development_score", 0.0) or 0.0)

    static_score = _clamp(
        (1.0 - interval_variety) * 0.28
        + (1.0 - min(pitch_range / 12.0, 1.0)) * 0.24
        + (1.0 - min(onset_density / 2.0, 1.0)) * 0.24
        + repetition * 0.24
    )
    harsh_score = _clamp(
        _clamp((centroid - 2400.0) / 2600.0) * 0.42
        + flatness * 0.24
        + roughness * 0.34
    )
    muddy_score = _clamp(_clamp((1100.0 - centroid) / 1100.0) * 0.82 + (1.0 - flatness) * 0.1)
    underdeveloped_score = _clamp((1.0 - development) * 0.52 + (1.0 - hook) * 0.28 + (1.0 - cadence) * 0.2)
    return _round_metrics(
        {
            "static_score": static_score,
            "harsh_score": harsh_score,
            "muddy_score": muddy_score,
            "underdeveloped_score": underdeveloped_score,
        }
    )


def _analyze_events(events: Sequence[_EarEvent], spectral_metrics: Mapping[str, float] | None = None) -> dict[str, float]:
    freqs = [event.frequency_hz for event in events if event.frequency_hz > 0.0]
    if len(freqs) < 2:
        base = {
            "pitch_hz": freqs[0] if freqs else 0.0,
            "pitch_mean_midi": _midi_number(freqs[0]) if freqs else 0.0,
            "pitch_range_semitones": 0.0,
            "interval_variety": 0.0,
            "mean_interval_semitones": 0.0,
            "register_spread": 0.0,
            "leap_ratio": 0.0,
            "onset_density": _onset_density(events),
            "cadence_strength": 0.0,
            "hook_clarity": 0.0,
            "repetition_score": 0.0,
            "development_score": 0.0,
        }
        base.update(spectral_metrics or _tracker_spectral_metrics(events))
        base.update(feedback_scores(base))
        return _round_metrics(base)

    midis = [_midi_number(freq) for freq in freqs]
    intervals = [abs(midis[i] - midis[i - 1]) for i in range(1, len(midis))]
    rounded_intervals = {round(interval) for interval in intervals}
    interval_variety = min(1.0, len(rounded_intervals) / max(1.0, len(intervals)))
    pitch_range = max(midis) - min(midis)
    leap_ratio = sum(1 for interval in intervals if interval >= 4.5) / max(1, len(intervals))
    cadence_strength = _cadence_strength(midis, events)
    repetition_score = _shape_repetition_score(intervals)
    development_score = _clamp(
        interval_variety * 0.36
        + min(pitch_range / 18.0, 1.0) * 0.22
        + (1.0 - repetition_score) * 0.24
        + min(_onset_density(events) / 4.0, 1.0) * 0.18
    )
    hook_clarity = _hook_clarity(
        intervals=intervals,
        notes_count=len(events),
        accented_count=sum(1 for event in events if event.accent),
        leap_ratio=leap_ratio,
        repetition_score=repetition_score,
        cadence_strength=cadence_strength,
    )
    base = {
        "pitch_hz": sum(freqs) / len(freqs),
        "pitch_mean_midi": sum(midis) / len(midis),
        "pitch_range_semitones": pitch_range,
        "interval_variety": interval_variety,
        "mean_interval_semitones": sum(intervals) / max(1, len(intervals)),
        "register_spread": pitch_range,
        "leap_ratio": leap_ratio,
        "onset_density": _onset_density(events),
        "cadence_strength": cadence_strength,
        "hook_clarity": hook_clarity,
        "repetition_score": repetition_score,
        "development_score": development_score,
    }
    base.update(spectral_metrics or _tracker_spectral_metrics(events))
    base.update(feedback_scores(base))
    return _round_metrics(base)


def analyze_played_notes(notes: Sequence[PlayedNote]) -> dict[str, float]:
    """Summarize melodic, rhythmic, spectral, and corrective scores from notes."""

    return _analyze_events(_frequency_events_from_notes(notes))


def analyze_tracker_output(tracker_events: Sequence[object]) -> dict[str, float]:
    """Analyze scheduled tracker events or event-like dictionaries."""

    return _analyze_events(_frequency_events_from_tracker(tracker_events))


def _normalize_samples(samples: Sequence[int] | Sequence[float]) -> list[float]:
    if not samples:
        return []
    peak = max(abs(float(sample)) for sample in samples)
    scale = 32768.0 if peak > 1.5 else 1.0
    return [float(sample) / scale for sample in samples]


def _detect_pitch_autocorrelation(
    samples: Sequence[float],
    sample_rate: int,
    *,
    min_freq: float = 80.0,
    max_freq: float = 2000.0,
) -> tuple[float, float]:
    if sample_rate <= 0 or len(samples) < 4:
        return 0.0, 0.0
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    if rms < 0.003:
        return 0.0, 0.0
    min_lag = max(1, int(sample_rate / max_freq))
    max_lag = min(len(samples) // 2, int(sample_rate / min_freq))
    if min_lag >= max_lag:
        return 0.0, 0.0

    mean = sum(samples) / len(samples)
    centered = [sample - mean for sample in samples]
    energy = sum(sample * sample for sample in centered)
    if energy <= _EPSILON:
        return 0.0, 0.0

    best_lag = min_lag
    best_corr = 0.0
    for lag in range(min_lag, max_lag + 1):
        corr = sum(centered[index] * centered[index + lag] for index in range(len(centered) - lag)) / energy
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    if best_corr < 0.25:
        return 0.0, 0.0
    return sample_rate / max(float(best_lag), _EPSILON), _clamp(best_corr)


def _pitch_track_events(samples: Sequence[float], sample_rate: int) -> list[_EarEvent]:
    frame_size = max(256, int(sample_rate * 0.12))
    hop_size = max(128, frame_size // 2)
    events: list[_EarEvent] = []
    if sample_rate <= 0 or len(samples) < frame_size:
        pitch, confidence = _detect_pitch_autocorrelation(samples, sample_rate)
        if pitch > 0.0:
            return [_EarEvent(pitch, len(samples) / max(float(sample_rate), 1.0), confidence, False, 0.0)]
        return []

    for start in range(0, len(samples) - frame_size + 1, hop_size):
        frame = samples[start : start + frame_size]
        pitch, confidence = _detect_pitch_autocorrelation(frame, sample_rate)
        if pitch <= 0.0:
            continue
        events.append(
            _EarEvent(
                frequency_hz=pitch,
                duration_s=frame_size / sample_rate,
                amplitude=confidence,
                accent=False,
                start_s=start / sample_rate,
            )
        )
    return events


def _estimate_audio_onset_density(samples: Sequence[float], sample_rate: int) -> float:
    if sample_rate <= 0 or len(samples) < 512:
        return 0.0
    frame_size = 256
    hop_size = 128
    energies: list[float] = []
    for start in range(0, len(samples) - frame_size + 1, hop_size):
        frame = samples[start : start + frame_size]
        energies.append(math.sqrt(sum(sample * sample for sample in frame) / len(frame)))
    if len(energies) < 2:
        return 0.0
    mean_energy = sum(energies) / len(energies)
    threshold = max(0.01, mean_energy * 1.35)
    onsets = 0
    previous = energies[0]
    for energy in energies[1:]:
        if energy >= threshold and previous < threshold and energy > previous * 1.1:
            onsets += 1
        previous = energy
    return onsets / max(len(samples) / sample_rate, _EPSILON)


def _audio_spectrum(samples: Sequence[float], sample_rate: int) -> list[tuple[float, float]]:
    if sample_rate <= 0 or len(samples) < 16:
        return []
    size = 1
    limit = min(len(samples), 2048)
    while size * 2 <= limit:
        size *= 2
    if size < 16:
        return []
    start = max(0, (len(samples) - size) // 2)
    frame = list(samples[start : start + size])
    windowed = [
        sample * (0.5 - 0.5 * math.cos(2.0 * math.pi * index / max(1, size - 1)))
        for index, sample in enumerate(frame)
    ]
    spectrum: list[tuple[float, float]] = []
    for bin_index in range(1, size // 2):
        angle_base = -2.0 * math.pi * bin_index / size
        real = 0.0
        imag = 0.0
        for index, sample in enumerate(windowed):
            angle = angle_base * index
            real += sample * math.cos(angle)
            imag += sample * math.sin(angle)
        magnitude = math.sqrt(real * real + imag * imag)
        spectrum.append((bin_index * sample_rate / size, magnitude))
    return spectrum


def _audio_spectral_metrics(samples: Sequence[float], sample_rate: int) -> dict[str, float]:
    spectrum = _audio_spectrum(samples, sample_rate)
    if not spectrum:
        return {
            "spectral_centroid_hz": 0.0,
            "spectral_flatness": 0.0,
            "roughness": 0.0,
        }
    total = sum(magnitude for _freq, magnitude in spectrum)
    if total <= _EPSILON:
        return {
            "spectral_centroid_hz": 0.0,
            "spectral_flatness": 0.0,
            "roughness": 0.0,
        }
    centroid = sum(freq * magnitude for freq, magnitude in spectrum) / total
    magnitudes = [magnitude for _freq, magnitude in spectrum]
    roughness = sum(abs(right - left) for left, right in zip(magnitudes, magnitudes[1:])) / max(total, _EPSILON)
    return {
        "spectral_centroid_hz": centroid,
        "spectral_flatness": _spectral_flatness(magnitudes),
        "roughness": _clamp(roughness),
    }


def analyze_captured_audio(samples: Sequence[int] | Sequence[float], sample_rate: int) -> dict[str, float]:
    """Analyze a captured mono waveform using stdlib-only DSP estimates."""

    normalized = _normalize_samples(samples)
    spectral = _audio_spectral_metrics(normalized, sample_rate)
    events = _pitch_track_events(normalized, sample_rate)
    if not events:
        pitch, confidence = _detect_pitch_autocorrelation(normalized, sample_rate)
        if pitch > 0.0:
            events = [_EarEvent(pitch, len(normalized) / max(float(sample_rate), 1.0), confidence, False, 0.0)]
    metrics = _analyze_events(events, spectral)
    pitch, confidence = _detect_pitch_autocorrelation(normalized, sample_rate)
    metrics["pitch_hz"] = round(pitch, 2)
    metrics["pitch_confidence"] = round(confidence, 3)
    metrics["onset_density"] = round(_estimate_audio_onset_density(normalized, sample_rate), 3)
    metrics.update(feedback_scores(metrics))
    return _round_metrics(metrics)


# --- Critical listening & psychoacoustic evaluation ---

# ISO 226 equal-loudness approximate compensation at ~70 phon.
# (band_low_hz, band_high_hz, suggested_compensation_db)
_EQUAL_LOUDNESS_BANDS: tuple[tuple[float, float, float], ...] = (
    (20.0, 80.0, 6.0),
    (80.0, 200.0, 3.0),
    (200.0, 500.0, 1.0),
    (500.0, 2000.0, 0.0),
    (2000.0, 5000.0, -1.0),
    (5000.0, 10000.0, 0.0),
    (10000.0, 20000.0, 3.0),
)


def _spectral_balance_from_events(events: Sequence[_EarEvent]) -> float:
    """Measure how evenly energy distributes across low/mid/high bands."""
    if not events:
        return 0.0
    # low: <48 MIDI (~130Hz), mid: 48-72 (~130-523Hz), high: >72 (>523Hz)
    bands = [0.0, 0.0, 0.0]
    for event in events:
        midi = _midi_number(event.frequency_hz)
        energy = max(event.amplitude, 0.001) * event.duration_s
        if midi < 48.0:
            bands[0] += energy
        elif midi < 72.0:
            bands[1] += energy
        else:
            bands[2] += energy
    total = sum(bands)
    if total <= _EPSILON:
        return 0.0
    proportions = [b / total for b in bands]
    ideal = 1.0 / 3.0
    deviation = sum(abs(p - ideal) for p in proportions) / 2.0
    return _clamp(1.0 - deviation)


def _dynamic_contour_from_events(events: Sequence[_EarEvent]) -> float:
    """Measure amplitude variation across time windows."""
    if len(events) < 2:
        return 0.0
    start = min(e.start_s for e in events)
    end = max(e.start_s + e.duration_s for e in events)
    duration = end - start
    if duration < 0.01:
        return 0.0
    n_windows = min(8, max(2, len(events) // 2))
    window_size = duration / n_windows
    window_energies = [0.0] * n_windows
    for event in events:
        idx = int((event.start_s - start) / window_size)
        idx = min(idx, n_windows - 1)
        window_energies[idx] += event.amplitude * event.duration_s
    mean_energy = sum(window_energies) / n_windows
    if mean_energy <= _EPSILON:
        return 0.0
    variance = sum((e - mean_energy) ** 2 for e in window_energies) / n_windows
    cv = math.sqrt(variance) / mean_energy
    return _clamp(min(cv / 1.5, 1.0))


def _spatial_distribution_from_events(events: Sequence[_EarEvent]) -> float:
    """Estimate spatial diversity from frequency spread and voice count."""
    if not events:
        return 0.0
    active_bands: set[int] = set()
    midis: list[float] = []
    for event in events:
        midi = _midi_number(event.frequency_hz)
        midis.append(midi)
        active_bands.add(int(midi / 12.0))
    midi_range = max(midis) - min(midis)
    band_diversity = min(len(active_bands) / 5.0, 1.0)
    range_score = min(midi_range / 36.0, 1.0)
    return _clamp(band_diversity * 0.6 + range_score * 0.4)


def _timbral_quality_from_metrics(
    spectral_flatness: float,
    spectral_centroid_hz: float,
    roughness: float,
) -> float:
    """Rate timbral quality: complex and bright, but not harsh or noisy."""
    flatness_score = 1.0 - abs(spectral_flatness - 0.35) * 2.0
    centroid_score = 1.0 - _clamp(
        abs(math.log2(max(spectral_centroid_hz, 100.0) / 800.0)) / 2.0
    )
    roughness_penalty = roughness * 0.5
    return _clamp(
        flatness_score * 0.35 + centroid_score * 0.45 + (1.0 - roughness_penalty) * 0.2
    )


def _masking_risk_from_events(events: Sequence[_EarEvent]) -> float:
    """Detect frequency proximity between simultaneous events (masking risk)."""
    if len(events) < 2:
        return 0.0
    masked_pairs = 0.0
    total_pairs = 0
    for i, left in enumerate(events):
        for right in events[i + 1 :]:
            left_end = left.start_s + left.duration_s
            right_end = right.start_s + right.duration_s
            overlap = min(left_end, right_end) - max(left.start_s, right.start_s)
            if overlap <= 0:
                continue
            total_pairs += 1
            midi_diff = abs(
                _midi_number(left.frequency_hz) - _midi_number(right.frequency_hz)
            )
            if midi_diff < 3.5:
                pair_weight = min(left.amplitude, right.amplitude) / max(
                    left.amplitude, right.amplitude, _EPSILON
                )
                masked_pairs += pair_weight
    if total_pairs == 0:
        return 0.0
    return _clamp(masked_pairs / total_pairs)


def _equal_loudness_hints() -> tuple[EqualLoudnessHint, ...]:
    """Return ISO 226-approximate compensation hints for ~70 phon listening."""
    return tuple(
        EqualLoudnessHint(low, high, comp) for low, high, comp in _EQUAL_LOUDNESS_BANDS
    )


def _critical_listening(
    events: Sequence[_EarEvent],
    spectral_metrics: Mapping[str, float] | None = None,
) -> CriticalListeningReport:
    spec = spectral_metrics or _tracker_spectral_metrics(events)
    return CriticalListeningReport(
        spectral_balance=round(_spectral_balance_from_events(events), 3),
        dynamic_contour=round(_dynamic_contour_from_events(events), 3),
        spatial_distribution=round(_spatial_distribution_from_events(events), 3),
        timbral_quality=round(
            _timbral_quality_from_metrics(
                spec.get("spectral_flatness", 0.0),
                spec.get("spectral_centroid_hz", 0.0),
                spec.get("roughness", 0.0),
            ),
            3,
        ),
        rhythmic_activity=round(_clamp(min(_onset_density(events) / 6.0, 1.0)), 3),
        harmonic_tension=round(float(spec.get("roughness", 0.0)), 3),
        masking_risk=round(_masking_risk_from_events(events), 3),
        equal_loudness_hints=_equal_loudness_hints(),
    )


def critical_listening_notes(notes: Sequence[PlayedNote]) -> CriticalListeningReport:
    """Psychoacoustic evaluation of played notes."""
    return _critical_listening(_frequency_events_from_notes(notes))


def critical_listening_tracker(
    tracker_events: Sequence[object],
) -> CriticalListeningReport:
    """Psychoacoustic evaluation of tracker events."""
    return _critical_listening(_frequency_events_from_tracker(tracker_events))


def production_corrections(report: CriticalListeningReport) -> ProductionCorrection:
    """Map critical listening metrics to actionable production corrections.

    Returns corrections in [-1, 1] for density, register, eq_tilt,
    dynamics, and palette.
    """
    density = _clamp(
        (0.5 - report.rhythmic_activity) * 1.0 + report.masking_risk * -0.5,
        -1.0,
        1.0,
    )

    register = 0.0
    if report.timbral_quality < 0.4 and report.harmonic_tension > 0.5:
        register = -0.4
    elif report.timbral_quality < 0.4 and report.harmonic_tension < 0.3:
        register = 0.4
    register = _clamp(
        register + (0.5 - report.spectral_balance) * 0.3, -1.0, 1.0
    )

    eq_tilt = _clamp((0.5 - report.timbral_quality) * 1.5, -1.0, 1.0)
    dynamics = _clamp((0.45 - report.dynamic_contour) * 1.8, -1.0, 1.0)
    palette = _clamp((0.5 - report.spatial_distribution) * 1.6, -1.0, 1.0)

    return ProductionCorrection(
        density=round(density, 3),
        register=round(register, 3),
        eq_tilt=round(eq_tilt, 3),
        dynamics=round(dynamics, 3),
        palette=round(palette, 3),
    )
