"""Generate deterministic WAV fixtures for sample-capture detector branches.

Each fixture is one second of mono 16-bit PCM at 8 kHz. Synthesis uses fixed
seeds so the bytes on disk are reproducible. Run from anywhere:

    python tests/fixtures/audio/generate.py

Edit a generator and rerun this script to refresh its fixture; the
``test_detector_*`` tests in ``test_sample_capture_daemon.py`` will then
exercise the new audio.
"""
from __future__ import annotations

import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np

SAMPLE_RATE = 8000
DURATION_SECONDS = 1.0
FIXTURE_DIR = Path(__file__).resolve().parent

SEED_DISHWASHER = 7
SEED_FOOTSTEPS = 11
SEED_DOGS = 17
SEED_TRANSIENT_CLUSTER = 23


def _frame_count(duration: float = DURATION_SECONDS) -> int:
    return int(round(duration * SAMPLE_RATE))


def silence() -> np.ndarray:
    return np.zeros(_frame_count(), dtype=np.float32)


def dishwasher_hum() -> np.ndarray:
    n = _frame_count()
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    rng = np.random.default_rng(SEED_DISHWASHER)
    base_freq = 110.0
    samples = (
        0.08 * np.sin(2 * np.pi * base_freq * t)
        + 0.05 * np.sin(2 * np.pi * (base_freq * 2.0) * t)
        + 0.03 * np.sin(2 * np.pi * (base_freq * 3.0) * t)
        + 0.01 * rng.standard_normal(n).astype(np.float32)
    )
    return samples.astype(np.float32)


def footsteps(count: int = 5) -> np.ndarray:
    n = _frame_count()
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(SEED_FOOTSTEPS)
    burst_len = int(round(0.04 * SAMPLE_RATE))
    envelope = np.exp(-np.linspace(0.0, 6.0, burst_len, dtype=np.float32))
    spacing = (n - burst_len) / max(1, count + 1)
    for i in range(count):
        start = int(round(spacing * (i + 1)))
        burst = (rng.standard_normal(burst_len).astype(np.float32) * 0.35) * envelope
        out[start : start + burst_len] += burst
    return out


def music() -> np.ndarray:
    n = _frame_count()
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    pad = 0.04 * np.sin(2 * np.pi * 220.0 * t) + 0.03 * np.sin(2 * np.pi * 330.0 * t)
    samples = pad.astype(np.float32)
    pluck_period = 0.18
    pluck_dur = int(round(0.06 * SAMPLE_RATE))
    env = np.exp(-np.linspace(0.0, 7.0, pluck_dur, dtype=np.float32))
    pluck_count = int(DURATION_SECONDS / pluck_period)
    for i in range(pluck_count):
        start = int(round(i * pluck_period * SAMPLE_RATE))
        if start + pluck_dur > n:
            break
        freq = 440.0 + (i * 67.0) % 240.0
        local_t = np.arange(pluck_dur, dtype=np.float32) / SAMPLE_RATE
        samples[start : start + pluck_dur] += (
            0.4 * np.sin(2 * np.pi * freq * local_t) * env
        ).astype(np.float32)
    return samples


def dogs(count: int = 3) -> np.ndarray:
    n = _frame_count()
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(SEED_DOGS)
    bark_len = int(round(0.15 * SAMPLE_RATE))
    envelope = np.exp(-np.linspace(0.0, 5.0, bark_len, dtype=np.float32))
    spacing = (n - bark_len) / max(1, count + 1)
    local_t = np.arange(bark_len, dtype=np.float32) / SAMPLE_RATE
    for i in range(count):
        start = int(round(spacing * (i + 1)))
        fundamental = 280.0 + 50.0 * i
        tone = (
            0.45 * np.sin(2 * np.pi * fundamental * local_t)
            + 0.20 * np.sin(2 * np.pi * (fundamental * 2.0) * local_t)
            + 0.10 * np.sin(2 * np.pi * (fundamental * 3.0) * local_t)
        )
        noise = rng.standard_normal(bark_len).astype(np.float32) * 0.15
        out[start : start + bark_len] += ((tone + noise) * envelope).astype(np.float32)
    return out


def transient_cluster(count: int = 6) -> np.ndarray:
    n = _frame_count()
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(SEED_TRANSIENT_CLUSTER)
    burst_len = int(round(0.012 * SAMPLE_RATE))
    envelope = np.exp(-np.linspace(0.0, 8.0, burst_len, dtype=np.float32))
    cluster_start = int(round(0.30 * SAMPLE_RATE))
    spacing = int(round(0.06 * SAMPLE_RATE))
    for i in range(count):
        start = cluster_start + i * spacing
        if start + burst_len > n:
            break
        burst = (rng.standard_normal(burst_len).astype(np.float32) * 0.45) * envelope
        out[start : start + burst_len] += burst
    return out


FIXTURES: dict[str, Callable[[], np.ndarray]] = {
    "silence.wav": silence,
    "dishwasher.wav": dishwasher_hum,
    "footsteps.wav": footsteps,
    "music.wav": music,
    "dogs.wav": dogs,
    "transient_cluster.wav": transient_cluster,
}


def write_wav(path: Path, samples: np.ndarray) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * np.float32(32767.0)).astype(np.int16)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm.tobytes())


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for filename, generator in FIXTURES.items():
        write_wav(FIXTURE_DIR / filename, generator())


if __name__ == "__main__":
    main()
