"""Audio-rendered novelty checks for SenseWeave render fixtures."""
from __future__ import annotations

import math
import wave
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .pass_ import PerformedPart


@dataclass(frozen=True)
class ProxyAudioRender:
    """Result of rendering deterministic fixture proxy audio."""

    audio_path: Path
    sample_rate: int
    duration_s: float
    symbolic_peak_times_s: tuple[float, ...]


@dataclass(frozen=True)
class AudioNoveltyAnalysis:
    """librosa feature SSM and Foote novelty output for one audio render."""

    sample_rate: int
    self_similarity: np.ndarray
    novelty_curve: np.ndarray
    frame_times_s: np.ndarray
    audio_peak_times_s: tuple[float, ...]


@dataclass(frozen=True)
class NoveltyPeakMatch:
    """Nearest audio novelty peak for one symbolic peak."""

    symbolic_time_s: float
    audio_time_s: float | None
    deviation_s: float | None


@dataclass(frozen=True)
class NoveltyAlignment:
    """Symbolic-vs-audio novelty alignment report."""

    symbolic_peak_times_s: tuple[float, ...]
    audio_peak_times_s: tuple[float, ...]
    matches: tuple[NoveltyPeakMatch, ...]
    unmatched_symbolic_peak_times_s: tuple[float, ...]
    max_deviation_s: float
    tolerance_s: float
    passed: bool


def symbolic_novelty_peak_times(part: PerformedPart) -> tuple[float, ...]:
    """Return CCH-034 symbolic novelty peak times for a render fixture."""

    score = _score_mapping(part)
    duration_s = _duration_seconds(part)
    raw_times = score.get("symbolic_novelty_peak_times_s", score.get("novelty_peak_times_s"))
    if raw_times is not None:
        return _bounded_peak_times(raw_times, duration_s)

    try:
        count = int(score.get("novelty_peaks", 0) or 0)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return ()

    step = duration_s / float(count + 1)
    return tuple(round(step * (index + 1), 3) for index in range(count))


def render_proxy_audio(
    part: PerformedPart,
    audio_path: str | Path,
    *,
    sample_rate: int = 16000,
    duration_s: float | None = None,
    flatten_expression: bool = False,
) -> ProxyAudioRender:
    """Render deterministic 5-minute proxy audio for a fixture piece."""

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    rendered_duration_s = float(duration_s) if duration_s is not None else _duration_seconds(part)
    if rendered_duration_s <= 0.0 or not math.isfinite(rendered_duration_s):
        raise ValueError("duration_s must be a positive finite number")

    path = Path(audio_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    peak_times = symbolic_novelty_peak_times(part)
    total_frames = int(round(rendered_duration_s * sample_rate))
    score = _score_mapping(part)
    pitches = _float_sequence(score.get("pitches"), default=(60.0, 64.0, 67.0, 72.0))
    velocities = _float_sequence(score.get("velocities"), default=(64.0, 78.0, 52.0, 84.0))

    if flatten_expression:
        samples = _synthesize_segment(
            total_frames,
            sample_rate=sample_rate,
            midi_pitch=pitches[0],
            velocity=64.0,
            segment_index=0,
        )
    else:
        samples = np.zeros(total_frames, dtype=np.float32)
        edges_s = (0.0, *peak_times, rendered_duration_s)
        edges = tuple(int(round(edge * sample_rate)) for edge in edges_s)
        for segment_index, (start, stop) in enumerate(zip(edges, edges[1:])):
            start = max(0, min(total_frames, start))
            stop = max(start, min(total_frames, stop))
            if stop <= start:
                continue
            segment = _synthesize_segment(
                stop - start,
                sample_rate=sample_rate,
                midi_pitch=pitches[segment_index % len(pitches)],
                velocity=velocities[segment_index % len(velocities)],
                segment_index=segment_index,
            )
            samples[start:stop] = segment

    _write_wav(path, samples, sample_rate)
    return ProxyAudioRender(
        audio_path=path,
        sample_rate=sample_rate,
        duration_s=round(total_frames / sample_rate, 6),
        symbolic_peak_times_s=peak_times,
    )


def extract_audio_novelty(
    audio_path: str | Path,
    *,
    hop_length: int = 2048,
    n_mels: int = 32,
    kernel_size: int = 32,
) -> AudioNoveltyAnalysis:
    """Extract librosa SSM and Foote novelty from rendered audio."""

    try:
        import librosa
    except ImportError as exc:  # pragma: no cover - exercised when dependency is absent
        raise RuntimeError("librosa is required for audio novelty extraction") from exc

    if hop_length <= 0:
        raise ValueError("hop_length must be positive")
    if n_mels <= 0:
        raise ValueError("n_mels must be positive")

    y, sample_rate = librosa.load(str(audio_path), sr=None, mono=True)
    if y.size == 0:
        raise ValueError("audio file contains no samples")

    n_fft = max(512, min(4096, hop_length * 2))
    mel = librosa.feature.melspectrogram(
        y=y,
        sr=sample_rate,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=n_mels,
        power=2.0,
    )
    features = librosa.power_to_db(mel, ref=np.max).astype(np.float32)
    features = _normalize_feature_columns(features)
    self_similarity = np.matmul(features.T, features).astype(np.float32)
    novelty_curve = _foote_novelty(self_similarity, kernel_size=kernel_size)
    frame_times = librosa.times_like(novelty_curve, sr=sample_rate, hop_length=hop_length)
    peak_times = _pick_audio_peaks(novelty_curve, frame_times)

    return AudioNoveltyAnalysis(
        sample_rate=int(sample_rate),
        self_similarity=self_similarity,
        novelty_curve=novelty_curve,
        frame_times_s=frame_times,
        audio_peak_times_s=peak_times,
    )


def check_audio_symbolic_novelty_alignment(
    part: PerformedPart,
    audio_path: str | Path,
    *,
    tolerance_s: float = 0.5,
    hop_length: int = 2048,
    n_mels: int = 32,
    kernel_size: int = 32,
) -> NoveltyAlignment:
    """Verify symbolic novelty peaks have matching audio novelty peaks."""

    if tolerance_s < 0.0:
        raise ValueError("tolerance_s must be non-negative")

    symbolic_peaks = symbolic_novelty_peak_times(part)
    analysis = extract_audio_novelty(
        audio_path,
        hop_length=hop_length,
        n_mels=n_mels,
        kernel_size=kernel_size,
    )
    return align_novelty_peaks(
        symbolic_peaks,
        analysis.audio_peak_times_s,
        tolerance_s=tolerance_s,
    )


def align_novelty_peaks(
    symbolic_peak_times_s: Sequence[float],
    audio_peak_times_s: Sequence[float],
    *,
    tolerance_s: float = 0.5,
) -> NoveltyAlignment:
    """Match symbolic novelty peak times to nearest audio novelty peak times."""

    symbolic = tuple(float(value) for value in symbolic_peak_times_s)
    audio = tuple(float(value) for value in audio_peak_times_s)
    matches: list[NoveltyPeakMatch] = []
    unmatched: list[float] = []
    deviations: list[float] = []

    for symbolic_time in symbolic:
        if not audio:
            matches.append(NoveltyPeakMatch(symbolic_time, None, None))
            unmatched.append(symbolic_time)
            continue
        nearest = min(audio, key=lambda audio_time: abs(audio_time - symbolic_time))
        deviation = abs(nearest - symbolic_time)
        deviations.append(deviation)
        if deviation <= tolerance_s:
            matches.append(NoveltyPeakMatch(symbolic_time, nearest, deviation))
        else:
            matches.append(NoveltyPeakMatch(symbolic_time, nearest, deviation))
            unmatched.append(symbolic_time)

    max_deviation = max(deviations) if deviations else 0.0
    return NoveltyAlignment(
        symbolic_peak_times_s=symbolic,
        audio_peak_times_s=audio,
        matches=tuple(matches),
        unmatched_symbolic_peak_times_s=tuple(unmatched),
        max_deviation_s=max_deviation,
        tolerance_s=tolerance_s,
        passed=not unmatched,
    )


def _score_mapping(part: PerformedPart) -> Mapping[str, Any]:
    return part.score if isinstance(part.score, Mapping) else {}


def _duration_seconds(part: PerformedPart) -> float:
    score = _score_mapping(part)
    for key in ("duration_sec", "duration_s", "planned_duration_s"):
        try:
            value = float(score.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0.0 and math.isfinite(value):
            return value
    return 300.0


def _bounded_peak_times(raw_times: object, duration_s: float) -> tuple[float, ...]:
    values = _float_sequence(raw_times, default=())
    bounded = [
        round(value, 3)
        for value in values
        if 0.0 < value < duration_s and math.isfinite(value)
    ]
    return tuple(dict.fromkeys(bounded))


def _float_sequence(raw: object, *, default: Sequence[float]) -> tuple[float, ...]:
    if raw is None:
        return tuple(float(value) for value in default)
    if isinstance(raw, str):
        chunks: Sequence[object] = raw.replace(",", " ").split()
    elif isinstance(raw, Sequence):
        chunks = raw
    else:
        return tuple(float(value) for value in default)

    values: list[float] = []
    for item in chunks:
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return tuple(values) if values else tuple(float(value) for value in default)


def _midi_to_frequency(midi_pitch: float) -> float:
    return 440.0 * (2.0 ** ((midi_pitch - 69.0) / 12.0))


def _synthesize_segment(
    frame_count: int,
    *,
    sample_rate: int,
    midi_pitch: float,
    velocity: float,
    segment_index: int,
) -> np.ndarray:
    if frame_count <= 0:
        return np.zeros(0, dtype=np.float32)

    t = np.arange(frame_count, dtype=np.float32) / float(sample_rate)
    frequency = _midi_to_frequency(midi_pitch)
    velocity_scale = max(0.0, min(1.0, velocity / 127.0 if velocity > 1.0 else velocity))
    amplitude = 0.16 + velocity_scale * 0.28
    vibrato = 1.0 + 0.004 * np.sin(2.0 * np.pi * (4.0 + segment_index) * t)
    phase = 2.0 * np.pi * frequency * vibrato * t

    harmonic_gain = 0.12 + 0.08 * (segment_index % 3)
    sub_gain = 0.06 if segment_index % 2 else 0.0
    wave_data = (
        np.sin(phase)
        + harmonic_gain * np.sin(phase * (2.0 + (segment_index % 2)))
        + sub_gain * np.sin(phase * 0.5)
    )

    envelope = np.ones(frame_count, dtype=np.float32)
    fade = min(frame_count // 2, max(1, int(sample_rate * 0.025)))
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        envelope[:fade] *= ramp
        envelope[-fade:] *= ramp[::-1]

    return (wave_data * envelope * amplitude).astype(np.float32)


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    normalized = samples if peak <= 0.95 else samples * (0.95 / peak)
    pcm = np.clip(normalized, -0.95, 0.95)
    payload = (pcm * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(payload)


def _normalize_feature_columns(features: np.ndarray) -> np.ndarray:
    minimum = np.min(features, axis=1, keepdims=True)
    spread = np.ptp(features, axis=1, keepdims=True)
    scaled = (features - minimum) / np.maximum(spread, 1e-6)
    norms = np.linalg.norm(scaled, axis=0, keepdims=True)
    return (scaled / np.maximum(norms, 1e-6)).astype(np.float32)


def _foote_novelty(self_similarity: np.ndarray, *, kernel_size: int) -> np.ndarray:
    frame_count = int(self_similarity.shape[0])
    if frame_count == 0:
        return np.zeros(0, dtype=np.float32)

    size = max(4, int(kernel_size))
    if size % 2:
        size += 1
    size = min(size, frame_count if frame_count % 2 == 0 else frame_count - 1)
    if size < 4:
        return np.zeros(frame_count, dtype=np.float32)

    half = size // 2
    axis = np.arange(size, dtype=np.float32) - (size / 2.0) + 0.5
    gaussian = np.exp(-(axis[:, None] ** 2 + axis[None, :] ** 2) / (2.0 * (half / 2.0) ** 2))
    checker = np.sign(axis[:, None] * axis[None, :])
    kernel = (gaussian * checker).astype(np.float32)
    kernel -= float(kernel.mean())

    novelty = np.zeros(frame_count, dtype=np.float32)
    for center in range(half, frame_count - half):
        window = self_similarity[center - half : center + half, center - half : center + half]
        novelty[center] = float(np.sum(window * kernel))

    novelty = np.maximum(novelty, 0.0)
    peak = float(np.max(novelty)) if novelty.size else 0.0
    if peak > 0.0:
        novelty = novelty / peak
    return novelty.astype(np.float32)


def _pick_audio_peaks(
    novelty_curve: np.ndarray,
    frame_times_s: np.ndarray,
    *,
    threshold: float = 0.2,
    min_separation_s: float = 10.0,
    edge_guard_s: float = 15.0,
) -> tuple[float, ...]:
    if novelty_curve.size < 3 or float(np.max(novelty_curve)) <= 0.0:
        return ()

    frame_step = float(np.median(np.diff(frame_times_s))) if frame_times_s.size > 1 else 1.0
    wait_frames = max(1, int(round(min_separation_s / max(frame_step, 1e-6))))
    adaptive_threshold = max(threshold, float(np.mean(novelty_curve) + np.std(novelty_curve)))
    candidates: list[int] = []
    duration_s = float(frame_times_s[-1]) if frame_times_s.size else 0.0
    for index in range(1, len(novelty_curve) - 1):
        frame_time = float(frame_times_s[index])
        if frame_time < edge_guard_s or frame_time > duration_s - edge_guard_s:
            continue
        value = float(novelty_curve[index])
        if value < adaptive_threshold:
            continue
        if value >= float(novelty_curve[index - 1]) and value > float(novelty_curve[index + 1]):
            candidates.append(index)

    selected: list[int] = []
    for index in sorted(candidates, key=lambda item: float(novelty_curve[item]), reverse=True):
        if all(abs(index - existing) >= wait_frames for existing in selected):
            selected.append(index)

    return tuple(round(float(frame_times_s[index]), 3) for index in sorted(selected))


__all__ = [
    "AudioNoveltyAnalysis",
    "NoveltyAlignment",
    "NoveltyPeakMatch",
    "ProxyAudioRender",
    "align_novelty_peaks",
    "check_audio_symbolic_novelty_alignment",
    "extract_audio_novelty",
    "render_proxy_audio",
    "symbolic_novelty_peak_times",
]
