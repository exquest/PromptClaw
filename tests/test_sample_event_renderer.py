"""Tests for EMSD sample-event rendering."""
from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.sample_event_renderer import TARGET_SAMPLE_RATE, render_sample_event, read_wav_mono


def _write_impulse_wav(path: Path, *, frames: int = 16000, pulse_every: int = 1200) -> None:
    samples = []
    for index in range(frames):
        value = 18000 if index % pulse_every == 0 else 0
        samples.append(int(value))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(TARGET_SAMPLE_RATE)
        handle.writeframes(b"".join(int(sample).to_bytes(2, "little", signed=True) for sample in samples))


def test_render_sample_event_creates_nonempty_grain_cloud(tmp_path: Path) -> None:
    source = tmp_path / "room.wav"
    output = tmp_path / "event.wav"
    _write_impulse_wav(source, frames=TARGET_SAMPLE_RATE * 2)

    meta = render_sample_event(
        source_path=source,
        output_path=output,
        activity={
            "activity_mode": "grain_cloud",
            "wet_mix": 0.42,
            "grain_density_hz": 8.0,
            "stretch_ratio": 1.0,
            "lowpass_hz": 0.0,
            "reverse_probability": 0.24,
            "sample_density": 0.55,
            "buffer_seconds": 14.0,
        },
        seed=7,
    )

    samples, sample_rate = read_wav_mono(output)
    assert sample_rate == TARGET_SAMPLE_RATE
    assert output.exists()
    assert len(samples) > TARGET_SAMPLE_RATE
    assert max(abs(sample) for sample in samples) > 0
    assert meta["peak"] > 0.0
    assert meta["duration_s"] > 1.0
    assert meta["source_path"] == str(source)
    assert meta["output_path"] == str(output)


def test_render_sample_event_applies_lowpass_wash_shape(tmp_path: Path) -> None:
    source = tmp_path / "room.wav"
    output = tmp_path / "wash.wav"
    _write_impulse_wav(source, frames=TARGET_SAMPLE_RATE)

    meta = render_sample_event(
        source_path=source,
        output_path=output,
        activity={
            "activity_mode": "lowpass_wash",
            "wet_mix": 0.28,
            "grain_density_hz": 0.0,
            "stretch_ratio": 1.8,
            "lowpass_hz": 1800.0,
            "reverse_probability": 0.0,
            "sample_density": 0.22,
            "buffer_seconds": 18.0,
        },
        seed=3,
    )

    samples, _ = read_wav_mono(output)
    assert len(samples) > TARGET_SAMPLE_RATE
    assert max(abs(sample) for sample in samples) > 0
    assert meta["mode"] == "lowpass_wash"


def test_render_sample_event_honors_afterglow_profile_duration_and_level(tmp_path: Path) -> None:
    source = tmp_path / "room.wav"
    output = tmp_path / "afterglow.wav"
    _write_impulse_wav(source, frames=TARGET_SAMPLE_RATE * 2)

    meta = render_sample_event(
        source_path=source,
        output_path=output,
        activity={
            "activity_mode": "freeze_bed",
            "scene_profile": "afterglow_residue",
            "render_duration_s": 5.0,
            "peak_target": 0.11,
            "wet_mix": 0.2,
            "grain_density_hz": 0.0,
            "stretch_ratio": 1.8,
            "lowpass_hz": 1600.0,
            "reverse_probability": 0.0,
            "sample_density": 0.18,
            "buffer_seconds": 18.0,
        },
        seed=9,
    )

    samples, _ = read_wav_mono(output)
    assert meta["mode"] == "freeze_bed"
    assert meta["duration_s"] >= 4.9
    assert max(abs(sample) for sample in samples) <= int(0.12 * 32767)


def test_render_sample_event_honors_development_grain_profile(tmp_path: Path) -> None:
    source = tmp_path / "room.wav"
    output = tmp_path / "development.wav"
    _write_impulse_wav(source, frames=TARGET_SAMPLE_RATE * 2)

    meta = render_sample_event(
        source_path=source,
        output_path=output,
        activity={
            "activity_mode": "grain_cloud",
            "scene_profile": "development_grains",
            "render_duration_s": 2.9,
            "peak_target": 0.2,
            "wet_mix": 0.36,
            "grain_density_hz": 8.5,
            "stretch_ratio": 1.0,
            "lowpass_hz": 2800.0,
            "reverse_probability": 0.18,
            "sample_density": 0.34,
            "buffer_seconds": 12.0,
        },
        seed=5,
    )

    samples, _ = read_wav_mono(output)
    assert meta["mode"] == "grain_cloud"
    assert meta["duration_s"] >= 2.8
    assert max(abs(sample) for sample in samples) > int(0.15 * 32767)


def test_render_sample_event_bounds_density_with_explicit_event_limit(tmp_path: Path) -> None:
    source = tmp_path / "room.wav"
    output = tmp_path / "bounded.wav"
    _write_impulse_wav(source, frames=TARGET_SAMPLE_RATE * 3)

    meta = render_sample_event(
        source_path=source,
        output_path=output,
        activity={
            "activity_mode": "grain_cloud",
            "scene_profile": "development_grains",
            "render_duration_s": 6.0,
            "peak_target": 0.2,
            "wet_mix": 0.8,
            "grain_density_hz": 120.0,
            "max_event_count": 9,
            "stretch_ratio": 1.0,
            "lowpass_hz": 2800.0,
            "reverse_probability": 0.4,
            "sample_density": 1.0,
            "buffer_seconds": 18.0,
        },
        seed=11,
    )

    assert meta["mode"] == "grain_cloud"
    assert meta["event_count"] <= 9
    assert meta["duration_s"] == 6.0
