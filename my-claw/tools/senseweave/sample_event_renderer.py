"""Render short room-derived sample events for CypherClaw."""
from __future__ import annotations

import math
import random
import wave
from array import array
from pathlib import Path
from typing import Any


TARGET_SAMPLE_RATE = 16000


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def read_wav_mono(path: str | Path) -> tuple[list[int], int]:
    wav_path = Path(path)
    with wave.open(str(wav_path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frame_count = handle.getnframes()
        raw = handle.readframes(frame_count)
    if sample_width == 2:
        samples = array("h")
    elif sample_width == 4:
        samples = array("i")
    else:
        raise ValueError(f"unsupported sample width: {sample_width}")
    samples.frombytes(raw)
    if channels == 1:
        return list(samples), sample_rate
    mono: list[int] = []
    for index in range(0, len(samples), channels):
        frame = samples[index : index + channels]
        mono.append(int(sum(frame) / len(frame)))
    return mono, sample_rate


def write_wav_mono(path: str | Path, samples: list[int], sample_rate: int = TARGET_SAMPLE_RATE) -> None:
    wav_path = Path(path)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    payload = array("h", [int(_clamp(sample, -32767, 32767)) for sample in samples]).tobytes()
    with wave.open(str(wav_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(payload)


def _to_float(samples: list[int]) -> list[float]:
    return [sample / 32768.0 for sample in samples]


def _from_float(samples: list[float]) -> list[int]:
    return [int(_clamp(sample, -1.0, 1.0) * 32767.0) for sample in samples]


def _resample_linear(samples: list[float], ratio: float) -> list[float]:
    if not samples:
        return []
    if ratio <= 0:
        ratio = 1.0
    output_length = max(1, int(len(samples) / ratio))
    out: list[float] = []
    for index in range(output_length):
        source_pos = index * ratio
        lower = int(source_pos)
        upper = min(lower + 1, len(samples) - 1)
        frac = source_pos - lower
        out.append(samples[lower] * (1.0 - frac) + samples[upper] * frac)
    return out


def _fade(samples: list[float]) -> list[float]:
    length = len(samples)
    if length <= 2:
        return samples
    out = samples[:]
    for index, value in enumerate(samples):
        phase = index / (length - 1)
        envelope = math.sin(math.pi * phase) ** 1.5
        out[index] = value * envelope
    return out


def _lowpass(samples: list[float], sample_rate: int, cutoff_hz: float) -> list[float]:
    if cutoff_hz <= 0:
        return samples
    alpha = math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)
    out: list[float] = []
    prev = 0.0
    for sample in samples:
        prev = (1.0 - alpha) * sample + alpha * prev
        out.append(prev)
    return out


def _choose_segment(source: list[float], length: int, rng: random.Random) -> list[float]:
    if not source:
        return [0.0] * length
    if len(source) <= length:
        repeats = (length // len(source)) + 1
        tiled = (source * repeats)[:length]
        return tiled
    start = rng.randint(0, len(source) - length)
    return source[start : start + length]


def _mix_into(target: list[float], segment: list[float], start_index: int, gain: float) -> None:
    if gain == 0.0:
        return
    for offset, value in enumerate(segment):
        index = start_index + offset
        if 0 <= index < len(target):
            target[index] += value * gain


def _activity_duration(activity: dict[str, Any], default_s: float) -> float:
    value = float(activity.get("render_duration_s", default_s) or default_s)
    return max(0.5, value)


def _activity_peak_target(activity: dict[str, Any], default_peak: float) -> float:
    override = float(activity.get("peak_target", 0.0) or 0.0)
    if override > 0.0:
        return _clamp(override, 0.08, 0.24)
    return _clamp(default_peak, 0.08, 0.24)


def _bounded_event_count(activity: dict[str, Any], raw_count: int, *, default_limit: int, minimum: int) -> int:
    limit = int(activity.get("max_event_count", default_limit) or default_limit)
    limit = max(1, min(64, limit))
    bounded_minimum = minimum if limit >= minimum else 1
    return min(limit, max(bounded_minimum, raw_count))


def _render_grain_cloud(source: list[float], activity: dict[str, Any], rng: random.Random) -> tuple[list[float], int]:
    profile = str(activity.get("scene_profile", "") or "")
    duration_s = _activity_duration(activity, 2.4 + float(activity.get("wet_mix", 0.0) or 0.0) * 1.8)
    output = [0.0] * int(TARGET_SAMPLE_RATE * duration_s)
    grain_density = float(activity.get("grain_density_hz", 0.0) or 0.0)
    count_scale = 1.0
    grain_ms_low, grain_ms_high = 40, 140
    gain_low, gain_high = 0.08, 0.22
    if profile == "development_grains":
        count_scale = 1.35
        grain_ms_low, grain_ms_high = 55, 180
        gain_low, gain_high = 0.1, 0.24
    elif profile == "emergence_motion":
        count_scale = 1.15
        grain_ms_low, grain_ms_high = 50, 160
    grain_count = _bounded_event_count(
        activity,
        int(grain_density * duration_s * 0.55 * count_scale),
        default_limit=24,
        minimum=6,
    )
    for _ in range(grain_count):
        grain_ms = rng.randint(grain_ms_low, grain_ms_high)
        segment = _choose_segment(source, int(TARGET_SAMPLE_RATE * grain_ms / 1000.0), rng)
        ratio = rng.uniform(0.55, 1.05)
        segment = _fade(_resample_linear(segment, ratio))
        if rng.random() < float(activity.get("reverse_probability", 0.0) or 0.0):
            segment = list(reversed(segment))
        start = rng.randint(0, max(0, len(output) - len(segment)))
        gain = rng.uniform(gain_low, gain_high)
        _mix_into(output, segment, start, gain)
    return output, grain_count


def _render_slice_accents(source: list[float], activity: dict[str, Any], rng: random.Random) -> tuple[list[float], int]:
    profile = str(activity.get("scene_profile", "") or "")
    duration_s = _activity_duration(activity, 2.0)
    output = [0.0] * int(TARGET_SAMPLE_RATE * duration_s)
    slice_count = _bounded_event_count(
        activity,
        int(3 + float(activity.get("wet_mix", 0.0) or 0.0) * 8),
        default_limit=7,
        minimum=3,
    )
    if profile == "theme_accents":
        slice_count = max(slice_count, 4)
    for index in range(slice_count):
        seg_ms = rng.randint(120, 260)
        segment = _choose_segment(source, int(TARGET_SAMPLE_RATE * seg_ms / 1000.0), rng)
        segment = _fade(_resample_linear(segment, rng.uniform(0.7, 1.0)))
        if rng.random() < float(activity.get("reverse_probability", 0.0) or 0.0):
            segment = list(reversed(segment))
        if profile == "theme_accents":
            progress = (index / max(1, slice_count)) ** 0.85
        else:
            progress = index / max(1, slice_count - 1)
        start = int(progress * max(0, len(output) - len(segment)))
        _mix_into(output, segment, start, 0.14 + index * 0.02)
    return output, slice_count


def _render_window_echo(source: list[float], activity: dict[str, Any], rng: random.Random) -> tuple[list[float], int]:
    profile = str(activity.get("scene_profile", "") or "")
    duration_s = _activity_duration(activity, 2.8)
    output = [0.0] * int(TARGET_SAMPLE_RATE * duration_s)
    segment = _fade(_resample_linear(_choose_segment(source, int(TARGET_SAMPLE_RATE * 0.35), rng), 0.82))
    gains = (0.22, 0.14, 0.09, 0.05)
    spacing_s = 0.48
    if profile == "conversation_echo":
        gains = (0.24, 0.16, 0.1, 0.06)
        spacing_s = 0.44
    elif profile == "recap_echo":
        gains = (0.18, 0.12, 0.08, 0.05)
        spacing_s = 0.56
    for index, gain in enumerate(gains):
        start = int(index * TARGET_SAMPLE_RATE * spacing_s)
        _mix_into(output, segment, start, gain)
    return output, len(gains)


def _render_bed(source: list[float], activity: dict[str, Any], rng: random.Random) -> tuple[list[float], int]:
    mode = str(activity.get("activity_mode", "texture_bed"))
    profile = str(activity.get("scene_profile", "") or "")
    duration_s = _activity_duration(activity, 4.0 if mode == "freeze_bed" else 3.2)
    output = [0.0] * int(TARGET_SAMPLE_RATE * duration_s)
    segment = _choose_segment(source, int(TARGET_SAMPLE_RATE * 0.5), rng)
    ratio = 0.45 if mode == "freeze_bed" else 0.65
    ratio /= max(1.0, float(activity.get("stretch_ratio", 1.0) or 1.0))
    if profile == "afterglow_residue":
        ratio *= 0.85
    elif profile == "divination_bed":
        ratio *= 0.92
    segment = _fade(_resample_linear(segment, max(0.25, ratio)))
    gain = 0.12
    step_divisor = 3
    if profile == "afterglow_residue":
        gain = 0.08
        step_divisor = 2
    elif profile == "divination_bed":
        gain = 0.1
        step_divisor = 3
    step = max(1, len(segment) // step_divisor)
    event_count = 0
    for start in range(0, len(output), step):
        _mix_into(output, segment, start, gain)
        event_count += 1
    return output, event_count


def render_sample_event(
    *,
    source_path: str | Path,
    output_path: str | Path,
    activity: dict[str, Any],
    seed: int | None = None,
) -> dict[str, float | str]:
    source_samples, source_rate = read_wav_mono(source_path)
    source = _to_float(source_samples)
    if source_rate != TARGET_SAMPLE_RATE:
        source = _resample_linear(source, source_rate / TARGET_SAMPLE_RATE)
    rng = random.Random(seed if seed is not None else hash((str(source_path), activity.get("activity_mode", ""))))
    mode = str(activity.get("activity_mode", "texture_bed"))
    if mode == "grain_cloud":
        output, event_count = _render_grain_cloud(source, activity, rng)
    elif mode == "slice_accents":
        output, event_count = _render_slice_accents(source, activity, rng)
    elif mode == "window_echo":
        output, event_count = _render_window_echo(source, activity, rng)
    else:
        output, event_count = _render_bed(source, activity, rng)

    cutoff = float(activity.get("lowpass_hz", 0.0) or 0.0)
    if cutoff <= 0.0 and mode in {"grain_cloud", "slice_accents", "window_echo"}:
        cutoff = 3600.0
    output = _lowpass(output, TARGET_SAMPLE_RATE, cutoff)

    peak = max(max(abs(sample) for sample in output), 1e-6)
    target_peak = _activity_peak_target(
        activity,
        0.12 + float(activity.get("wet_mix", 0.0) or 0.0) * 0.22,
    )
    output = [sample * (target_peak / peak) for sample in output]
    integer_output = _from_float(output)
    write_wav_mono(output_path, integer_output, TARGET_SAMPLE_RATE)
    return {
        "mode": mode,
        "duration_s": round(len(integer_output) / TARGET_SAMPLE_RATE, 3),
        "peak": round(max(abs(sample) for sample in output), 5),
        "event_count": event_count,
        "source_path": str(source_path),
        "output_path": str(output_path),
    }
