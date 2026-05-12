"""Tests for sample_capture_daemon.py."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from sample_capture_daemon import (
    ARC_PHASES,
    BUFFER_DURATION_SECONDS,
    JACK_INPUT_PORTS,
    JACK_SOURCE_PORTS,
    MOOD_LABELS,
    PRESENCE_LABELS,
    SAMPLE_RATE,
    SELF_QUOTE_DURATION_SECONDS,
    AcousticFeatures,
    AcousticTagThresholds,
    DetectorThresholds,
    InterestingMomentDetector,
    SampleCaptureDaemon,
    SampleTags,
    analyze_acoustic_features,
    build_sample_tags,
    derive_acoustic_tags,
    extract_context_tags,
    save_capture,
    self_quote,
    time_of_day_from_timestamp,
)


class _FakeInputPort:
    def __init__(self, name: str) -> None:
        self.name = name
        self._frames = np.zeros(0, dtype=np.float32)

    def get_array(self) -> np.ndarray:
        return self._frames

    def set_frames(self, frames: np.ndarray) -> None:
        self._frames = np.asarray(frames, dtype=np.float32)


class _FakeInputPorts:
    def __init__(self) -> None:
        self._ports: dict[str, _FakeInputPort] = {}

    def register(self, name: str) -> _FakeInputPort:
        port = _FakeInputPort(name)
        self._ports[name] = port
        return port


class _FakeJackClient:
    def __init__(self, name: str) -> None:
        self.name = name
        self.inports = _FakeInputPorts()
        self.connections: list[tuple[str, str]] = []
        self.activated = False
        self.closed = False
        self._process_callback: Callable[[int], object] | None = None
        self._xrun_callback: Callable[[float], object] | None = None

    def set_process_callback(self, callback: Callable[[int], object]) -> None:
        self._process_callback = callback

    def set_xrun_callback(self, callback: Callable[[float], object]) -> None:
        self._xrun_callback = callback

    def activate(self) -> None:
        self.activated = True

    def connect(self, source: str, destination: _FakeInputPort) -> None:
        self.connections.append((source, f"{self.name}:{destination.name}"))

    def close(self) -> None:
        self.closed = True

    def push_frames(
        self,
        contact: np.ndarray,
        room: np.ndarray,
        self_frames: np.ndarray | None = None,
    ) -> None:
        self.inports._ports["in_contact"].set_frames(contact)
        self.inports._ports["in_room"].set_frames(room)
        if "in_self" in self.inports._ports:
            self.inports._ports["in_self"].set_frames(
                np.zeros(len(contact), dtype=np.float32) if self_frames is None else self_frames
            )
        assert self._process_callback is not None
        self._process_callback(len(contact))

    def push_self_frames(self, frames: np.ndarray) -> None:
        self.inports._ports["in_contact"].set_frames(np.zeros(len(frames), dtype=np.float32))
        self.inports._ports["in_room"].set_frames(np.zeros(len(frames), dtype=np.float32))
        self.inports._ports["in_self"].set_frames(np.asarray(frames, dtype=np.float32))
        assert self._process_callback is not None
        self._process_callback(len(frames))

    def trigger_xrun(self, delay_usecs: float = 0.0) -> None:
        assert self._xrun_callback is not None
        self._xrun_callback(delay_usecs)


def _start_daemon(
    *,
    sample_rate: int = 4,
    buffer_duration_seconds: int = 3,
) -> tuple[SampleCaptureDaemon, _FakeJackClient]:
    client = _FakeJackClient("cypherclaw-capture")
    daemon = SampleCaptureDaemon(
        sample_rate=sample_rate,
        buffer_duration_seconds=buffer_duration_seconds,
        client_factory=lambda _name: client,
    )
    daemon.start()
    return daemon, client


def test_defaults_match_prd_contract() -> None:
    assert SAMPLE_RATE == 48_000
    assert BUFFER_DURATION_SECONDS == 60


def test_start_registers_and_connects_expected_jack_ports() -> None:
    daemon, client = _start_daemon()

    assert client.activated is True
    assert set(client.inports._ports) == {"in_contact", "in_room", "in_self"}
    assert client.connections == [
        (JACK_SOURCE_PORTS["contact"], "cypherclaw-capture:in_contact"),
        (JACK_SOURCE_PORTS["room"], "cypherclaw-capture:in_room"),
        (JACK_SOURCE_PORTS["self"], "cypherclaw-capture:in_self"),
    ]
    assert daemon.input_port_names == JACK_INPUT_PORTS
    assert JACK_SOURCE_PORTS["self"] == "SuperCollider:out_1"


def test_ring_buffer_retains_latest_rolling_window() -> None:
    daemon, client = _start_daemon()

    for start in range(0, 16, 4):
        client.push_frames(
            np.arange(start, start + 4, dtype=np.float32),
            np.arange(100 + start, 104 + start, dtype=np.float32),
        )

    np.testing.assert_array_equal(
        daemon.get_window("contact", duration_sec=3.0, offset_sec=0.0),
        np.arange(4, 16, dtype=np.float32),
    )
    np.testing.assert_array_equal(
        daemon.get_window("room", duration_sec=3.0, offset_sec=0.0),
        np.arange(104, 116, dtype=np.float32),
    )


def test_get_window_supports_offsets_and_zero_padding() -> None:
    daemon, client = _start_daemon(sample_rate=4, buffer_duration_seconds=8)
    client.push_frames(
        np.arange(20, dtype=np.float32),
        np.arange(200, 220, dtype=np.float32),
    )

    np.testing.assert_array_equal(
        daemon.get_window("contact", duration_sec=1.5, offset_sec=1.0),
        np.arange(10, 16, dtype=np.float32),
    )
    np.testing.assert_array_equal(
        daemon.get_window("room", duration_sec=2.0, offset_sec=4.0),
        np.array([0, 0, 0, 0, 200, 201, 202, 203], dtype=np.float32),
    )


FIXTURE_SAMPLE_RATE = 8000


def _silence(seconds: float, sample_rate: int = FIXTURE_SAMPLE_RATE) -> np.ndarray:
    return np.zeros(int(round(seconds * sample_rate)), dtype=np.float32)


def _hum(
    seconds: float,
    sample_rate: int = FIXTURE_SAMPLE_RATE,
    *,
    base_freq: float = 110.0,
) -> np.ndarray:
    n = int(round(seconds * sample_rate))
    t = np.arange(n, dtype=np.float32) / sample_rate
    rng = np.random.default_rng(7)
    samples = (
        0.08 * np.sin(2 * np.pi * base_freq * t)
        + 0.05 * np.sin(2 * np.pi * (base_freq * 2.0) * t)
        + 0.03 * np.sin(2 * np.pi * (base_freq * 3.0) * t)
        + 0.01 * rng.standard_normal(n).astype(np.float32)
    )
    return samples.astype(np.float32)


def _footsteps(
    seconds: float,
    sample_rate: int = FIXTURE_SAMPLE_RATE,
    *,
    count: int = 5,
) -> np.ndarray:
    n = int(round(seconds * sample_rate))
    samples = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(11)
    burst_len = int(round(0.04 * sample_rate))
    envelope = np.exp(-np.linspace(0.0, 6.0, burst_len, dtype=np.float32))
    spacing = (n - burst_len) / max(1, count + 1)
    for i in range(count):
        start = int(round(spacing * (i + 1)))
        burst = (rng.standard_normal(burst_len).astype(np.float32) * 0.35) * envelope
        samples[start : start + burst_len] += burst
    return samples


def _music(seconds: float, sample_rate: int = FIXTURE_SAMPLE_RATE) -> np.ndarray:
    n = int(round(seconds * sample_rate))
    t = np.arange(n, dtype=np.float32) / sample_rate
    pad = 0.04 * np.sin(2 * np.pi * 220.0 * t) + 0.03 * np.sin(2 * np.pi * 330.0 * t)
    samples = pad.astype(np.float32)
    pluck_period = 0.18
    pluck_dur = int(round(0.06 * sample_rate))
    env = np.exp(-np.linspace(0.0, 7.0, pluck_dur, dtype=np.float32))
    pluck_count = int(seconds / pluck_period)
    for i in range(pluck_count):
        start = int(round(i * pluck_period * sample_rate))
        if start + pluck_dur > n:
            break
        freq = 440.0 + (i * 67.0) % 240.0
        local_t = np.arange(pluck_dur, dtype=np.float32) / sample_rate
        samples[start : start + pluck_dur] += (0.4 * np.sin(2 * np.pi * freq * local_t) * env).astype(
            np.float32
        )
    return samples


def _make_detector(
    *,
    thresholds: DetectorThresholds | None = None,
    sample_rate: int = FIXTURE_SAMPLE_RATE,
    clock: Callable[[], float] | None = None,
) -> InterestingMomentDetector:
    return InterestingMomentDetector(
        source="room",
        sample_rate=sample_rate,
        thresholds=thresholds,
        clock=clock,
    )


def test_detector_thresholds_match_prd_defaults() -> None:
    thresholds = DetectorThresholds()

    assert thresholds.spectral_flux_multiplier == 0.6
    assert thresholds.rms_dbfs_floor == -45.0
    assert thresholds.transient_count_min == 2
    assert thresholds.cooldown_seconds == 30.0
    assert thresholds.window_seconds == 1.0
    assert thresholds.hop_seconds == 0.25
    assert thresholds.min_capture_seconds == 4.0
    assert thresholds.max_capture_seconds == 8.0


def test_detector_thresholds_from_env_overrides() -> None:
    overrides = DetectorThresholds.from_env(
        {
            "SAMPLE_CAPTURE_FLUX_MULTIPLIER": "0.4",
            "SAMPLE_CAPTURE_RMS_DBFS": "-30",
            "SAMPLE_CAPTURE_TRANSIENT_MIN": "3",
            "SAMPLE_CAPTURE_COOLDOWN_SEC": "5",
            "SAMPLE_CAPTURE_MAX_LEN_SEC": "9",
        }
    )

    assert overrides.spectral_flux_multiplier == 0.4
    assert overrides.rms_dbfs_floor == -30.0
    assert overrides.transient_count_min == 3
    assert overrides.cooldown_seconds == 5.0
    assert overrides.max_capture_seconds == 9.0
    assert overrides.window_seconds == DetectorThresholds().window_seconds


def test_detector_silence_does_not_flag() -> None:
    detector = _make_detector(clock=iter([0.0, 0.25, 0.5, 0.75, 1.0]).__next__)

    flagged = [detector.evaluate(_silence(1.0)) for _ in range(5)]

    assert flagged == [None, None, None, None, None]


def test_detector_dishwasher_hum_does_not_flag_due_to_no_transients() -> None:
    detector = _make_detector(clock=iter([0.0, 0.25, 0.5, 0.75, 1.0]).__next__)

    results = [detector.evaluate(_hum(1.0)) for _ in range(5)]

    assert all(r is None for r in results), "steady hum lacks transient density"


def test_detector_footsteps_flag_after_baseline() -> None:
    times = iter([0.0, 0.25, 0.5, 0.75, 1.0]).__next__
    detector = _make_detector(clock=times)
    for _ in range(2):
        detector.evaluate(_silence(1.0))
    detector.evaluate(_hum(1.0))

    flagged = detector.evaluate(_footsteps(1.0))

    assert flagged is not None
    assert flagged.transient_count >= 2
    assert flagged.rms_dbfs > -45.0
    assert 4.0 <= flagged.capture_seconds <= 8.0
    assert flagged.pre_roll_seconds + flagged.post_roll_seconds == pytest.approx(
        flagged.capture_seconds - 1.0
    )


def test_detector_music_flags_and_capture_window_within_bounds() -> None:
    times = iter([0.0, 0.25, 0.5, 0.75, 1.0, 1.25]).__next__
    detector = _make_detector(clock=times)
    for _ in range(3):
        detector.evaluate(_hum(1.0))

    flagged = detector.evaluate(_music(1.0))

    assert flagged is not None
    assert flagged.transient_count >= 2
    assert 4.0 <= flagged.capture_seconds <= 8.0


def test_detector_cooldown_suppresses_back_to_back_flags() -> None:
    times = [0.0, 0.25, 0.5, 0.75, 1.0, 31.0, 31.25]
    detector = _make_detector(clock=iter(times).__next__)
    for _ in range(3):
        detector.evaluate(_silence(1.0))

    first = detector.evaluate(_footsteps(1.0))
    second = detector.evaluate(_footsteps(1.0))
    detector.evaluate(_silence(1.0))
    third = detector.evaluate(_footsteps(1.0))

    assert first is not None
    assert second is None, "second flag inside cooldown should be suppressed"
    assert third is not None, "third flag past cooldown should fire again"


AUDIO_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "audio"
AUDIO_FIXTURE_SAMPLE_RATE = 8000


def _read_fixture_wav(name: str) -> np.ndarray:
    path = AUDIO_FIXTURE_DIR / name
    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1, f"{name} must be mono"
        assert handle.getframerate() == AUDIO_FIXTURE_SAMPLE_RATE, (
            f"{name} must be {AUDIO_FIXTURE_SAMPLE_RATE} Hz"
        )
        assert handle.getsampwidth() == 2, f"{name} must be 16-bit"
        nframes = handle.getnframes()
        raw = handle.readframes(nframes)
    pcm = np.frombuffer(raw, dtype=np.int16)
    return pcm.astype(np.float32) / 32767.0


def test_canned_fixtures_are_one_second_at_eight_kilohertz() -> None:
    for name in (
        "silence.wav",
        "dishwasher.wav",
        "footsteps.wav",
        "music.wav",
        "dogs.wav",
        "transient_cluster.wav",
    ):
        samples = _read_fixture_wav(name)
        assert samples.shape == (AUDIO_FIXTURE_SAMPLE_RATE,), (
            f"{name} should contain exactly 1 second of audio"
        )


@pytest.fixture
def canned_window() -> Callable[[str], np.ndarray]:
    def _loader(name: str) -> np.ndarray:
        if not name.endswith(".wav"):
            name += ".wav"
        return _read_fixture_wav(name)

    return _loader


def test_silence_fixture_does_not_flag_detector(canned_window: Callable[[str], np.ndarray]) -> None:
    detector = _make_detector(clock=iter([0.0, 0.25, 0.5, 0.75, 1.0]).__next__)
    samples = canned_window("silence")

    flagged = [detector.evaluate(samples) for _ in range(5)]

    assert flagged == [None, None, None, None, None]


def test_dishwasher_fixture_does_not_flag_detector(canned_window: Callable[[str], np.ndarray]) -> None:
    detector = _make_detector(clock=iter([0.0, 0.25, 0.5, 0.75, 1.0]).__next__)
    samples = canned_window("dishwasher")

    results = [detector.evaluate(samples) for _ in range(5)]

    assert all(r is None for r in results), "steady hum lacks transient density"


@pytest.mark.parametrize(
    "fixture_name, expected_min_transients",
    [
        ("footsteps", 2),
        ("music", 2),
        ("dogs", 2),
        ("transient_cluster", 4),
    ],
)
def test_detector_branch_smoke_test_flags_on_matching_fixture(
    canned_window: Callable[[str], np.ndarray],
    fixture_name: str,
    expected_min_transients: int,
) -> None:
    times = iter([0.0, 0.25, 0.5, 0.75, 1.0, 1.25]).__next__
    detector = _make_detector(clock=times)
    # Warm up the detector with a steady hum to establish a baseline
    hum_samples = canned_window("dishwasher")
    for _ in range(3):
        detector.evaluate(hum_samples)

    flagged = detector.evaluate(canned_window(fixture_name))

    assert flagged is not None
    assert flagged.transient_count >= expected_min_transients
    assert flagged.rms_dbfs > -45.0


def test_detector_step_pulls_window_from_daemon() -> None:
    daemon, client = _start_daemon(sample_rate=FIXTURE_SAMPLE_RATE, buffer_duration_seconds=2)
    chunk = FIXTURE_SAMPLE_RATE // 4
    for _ in range(4):
        client.push_frames(
            np.zeros(chunk, dtype=np.float32),
            np.zeros(chunk, dtype=np.float32),
        )
    detector = InterestingMomentDetector(
        daemon=daemon,
        source="room",
        thresholds=DetectorThresholds(window_seconds=1.0, transient_count_min=1),
        clock=iter([0.0, 0.25, 0.5, 0.75]).__next__,
    )

    for _ in range(3):
        detector.step()

    footsteps = _footsteps(1.0, FIXTURE_SAMPLE_RATE)
    half = footsteps.size // 2
    client.push_frames(
        np.zeros(half, dtype=np.float32),
        footsteps[:half],
    )
    client.push_frames(
        np.zeros(footsteps.size - half, dtype=np.float32),
        footsteps[half:],
    )

    flagged = detector.step()

    assert flagged is not None
    assert flagged.transient_count >= 1


def test_xrun_logs_warning_and_capture_continues(caplog) -> None:
    daemon, client = _start_daemon(sample_rate=4, buffer_duration_seconds=3)
    caplog.set_level(logging.WARNING)

    client.push_frames(
        np.array([1, 2, 3, 4], dtype=np.float32),
        np.array([11, 12, 13, 14], dtype=np.float32),
    )
    client.trigger_xrun(128.0)
    client.push_frames(
        np.array([5, 6, 7, 8], dtype=np.float32),
        np.array([15, 16, 17, 18], dtype=np.float32),
    )

    assert daemon.xrun_count == 1
    assert "xrun" in caplog.text.lower()
    np.testing.assert_array_equal(
        daemon.get_window("contact", duration_sec=2.0, offset_sec=0.0),
        np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=np.float32),
    )


def test_extract_context_tags_normalizes_full_snapshot() -> None:
    # 2026-04-25 14:30 PDT (≈ 2026-04-25 21:30 UTC) — afternoon bucket
    captured_at = 1777152600.0
    context = {
        "organism": {
            "arc_phase": "Climax",
            "mode": "engaged",
            "mood": {"label": "Content", "valence": 0.42, "arousal": 0.7},
        },
        "room_presence": {
            "someone_here": True,
            "confidence": 0.88,
        },
    }

    tags = extract_context_tags(context, captured_at=captured_at)

    assert isinstance(tags, SampleTags)
    assert tags.arc_phase == "climax"
    assert tags.mood_label == "content"
    assert tags.mood_valence == pytest.approx(0.42)
    assert tags.mood_arousal == pytest.approx(0.7)
    assert tags.presence == "engaged"
    assert tags.presence_confidence == pytest.approx(0.88)
    assert tags.someone_here is True
    assert tags.time_of_day in TIME_OF_DAY_LABELS_LOCAL
    assert tags.captured_at_unix == captured_at
    assert tags.captured_at_iso.endswith("Z") and "T" in tags.captured_at_iso


def test_extract_context_tags_handles_missing_and_invalid_values() -> None:
    captured_at = 1777152600.0

    tags = extract_context_tags(None, captured_at=captured_at)

    assert tags.arc_phase == "unknown"
    assert tags.mood_label == "neutral"
    assert tags.mood_valence == 0.0
    assert tags.mood_arousal == 0.0
    assert tags.presence == "unknown"
    assert tags.presence_confidence == 0.0
    assert tags.someone_here is False
    assert tags.captured_at_unix == captured_at

    bad = {
        "organism": {
            "arc_phase": "intermission",
            "mode": "lurking",
            "mood": {"label": "thrilled", "valence": "n/a", "arousal": float("nan")},
        },
        "room_presence": {"confidence": 5.0, "someone_here": "yes"},
    }
    tags = extract_context_tags(bad, captured_at=captured_at)
    assert tags.arc_phase == "unknown"
    assert tags.presence == "unknown"
    assert tags.mood_label == "neutral"
    assert tags.mood_valence == 0.0
    assert tags.mood_arousal == 0.0
    assert tags.presence_confidence == 1.0  # clamped to [0, 1]
    assert tags.someone_here is True


def test_extract_context_tags_falls_back_to_top_level_keys() -> None:
    context = {
        "arc_phase": "rest",
        "mood": {"label": "melancholy", "valence": -0.5, "arousal": 0.2},
        "presence": {"presence": "solo", "confidence": 0.6, "someone_here": False},
    }

    tags = extract_context_tags(context, captured_at=0.0)

    assert tags.arc_phase == "rest"
    assert tags.mood_label == "melancholy"
    assert tags.mood_valence == pytest.approx(-0.5)
    assert tags.presence == "solo"
    assert tags.presence_confidence == pytest.approx(0.6)
    assert tags.someone_here is False


def test_sample_tags_as_dict_round_trips_all_fields() -> None:
    tags = extract_context_tags(
        {"organism": {"arc_phase": "build"}}, captured_at=1777152600.0
    )
    payload = tags.as_dict()

    expected_keys = {
        "arc_phase",
        "mood_label",
        "mood_valence",
        "mood_arousal",
        "presence",
        "presence_confidence",
        "someone_here",
        "time_of_day",
        "captured_at_iso",
        "captured_at_unix",
        "acoustic_tags",
        "mode",
        "extra_tags",
    }
    assert set(payload) == expected_keys
    assert payload["arc_phase"] == "build"
    assert payload["acoustic_tags"] == []
    assert payload["mode"] == "unknown"
    assert payload["extra_tags"] == {}


def test_time_of_day_buckets_cover_full_day() -> None:
    # Build local-time fixtures for representative hours.
    import datetime as _dt

    base = _dt.datetime(2026, 4, 25, 0, 0, 0)
    hours_to_label = {
        2: "night",
        7: "dawn",
        10: "morning",
        14: "afternoon",
        18: "evening",
        22: "night",
    }
    for hour, label in hours_to_label.items():
        ts = (base.replace(hour=hour)).timestamp()
        assert time_of_day_from_timestamp(ts) == label


def test_known_label_sets_match_documented_schema() -> None:
    assert ARC_PHASES == {"build", "rise", "climax", "resolve", "rest"}
    assert PRESENCE_LABELS == {"solo", "aware", "engaged", "performing"}
    assert MOOD_LABELS == {
        "melancholy",
        "neutral",
        "content",
        "anxious",
        "excited",
    }


TIME_OF_DAY_LABELS_LOCAL = {"night", "dawn", "morning", "afternoon", "evening"}


def test_analyze_acoustic_features_handles_empty_and_silent_input() -> None:
    empty = analyze_acoustic_features(
        np.zeros(0, dtype=np.float32), FIXTURE_SAMPLE_RATE
    )
    assert empty == AcousticFeatures()

    silent = analyze_acoustic_features(_silence(1.0), FIXTURE_SAMPLE_RATE)
    assert silent.spectral_centroid_hz == 0.0
    assert silent.spectral_bandwidth_hz == 0.0
    assert silent.transient_density_hz == 0.0


def test_analyze_acoustic_features_centroid_tracks_dominant_frequency() -> None:
    sample_rate = FIXTURE_SAMPLE_RATE
    n = sample_rate  # 1 second
    t = np.arange(n, dtype=np.float32) / sample_rate
    low = (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    high = (0.5 * np.sin(2 * np.pi * 2200.0 * t)).astype(np.float32)

    low_features = analyze_acoustic_features(low, sample_rate)
    high_features = analyze_acoustic_features(high, sample_rate)

    assert low_features.spectral_centroid_hz == pytest.approx(220.0, rel=0.05)
    assert high_features.spectral_centroid_hz == pytest.approx(2200.0, rel=0.05)
    assert high_features.spectral_centroid_hz > low_features.spectral_centroid_hz


def test_analyze_acoustic_features_bandwidth_widens_with_broadband_noise() -> None:
    sample_rate = FIXTURE_SAMPLE_RATE
    n = sample_rate
    t = np.arange(n, dtype=np.float32) / sample_rate
    tone = (0.5 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32)
    rng = np.random.default_rng(42)
    noise = (0.3 * rng.standard_normal(n)).astype(np.float32)

    tone_features = analyze_acoustic_features(tone, sample_rate)
    noise_features = analyze_acoustic_features(noise, sample_rate)

    assert tone_features.spectral_bandwidth_hz >= 0.0
    assert noise_features.spectral_bandwidth_hz > tone_features.spectral_bandwidth_hz


def test_analyze_acoustic_features_transient_density_is_per_second() -> None:
    sample_rate = FIXTURE_SAMPLE_RATE
    two_sec_footsteps = _footsteps(2.0, sample_rate=sample_rate, count=6)

    features = analyze_acoustic_features(two_sec_footsteps, sample_rate)

    assert features.transient_density_hz > 0.0
    # 6 bursts spread over 2 s should not exceed ~3 transients/sec.
    assert features.transient_density_hz <= 3.5


def test_analyze_acoustic_features_as_dict_exposes_numeric_fields() -> None:
    features = analyze_acoustic_features(_hum(1.0), FIXTURE_SAMPLE_RATE)

    payload = features.as_dict()
    assert set(payload) == {
        "spectral_centroid_hz",
        "spectral_bandwidth_hz",
        "transient_density_hz",
    }
    assert all(isinstance(v, float) for v in payload.values())


def test_derive_acoustic_tags_silent_features_yield_no_tags() -> None:
    assert derive_acoustic_tags(AcousticFeatures()) == ()


def test_derive_acoustic_tags_low_centroid_low_transients_is_warm_and_sustained() -> None:
    features = AcousticFeatures(
        spectral_centroid_hz=300.0,
        spectral_bandwidth_hz=200.0,
        transient_density_hz=0.0,
    )

    assert derive_acoustic_tags(features) == ("warm", "sustained")


def test_derive_acoustic_tags_narrow_high_centroid_is_bright_and_metallic() -> None:
    features = AcousticFeatures(
        spectral_centroid_hz=4000.0,
        spectral_bandwidth_hz=300.0,
        transient_density_hz=0.0,
    )

    tags = derive_acoustic_tags(features)

    assert "bright" in tags
    assert "metallic" in tags
    assert "warm" not in tags
    # canonical order: bright before metallic
    assert tags.index("bright") < tags.index("metallic")


def test_derive_acoustic_tags_broadband_high_centroid_is_bright_not_metallic() -> None:
    features = AcousticFeatures(
        spectral_centroid_hz=3500.0,
        spectral_bandwidth_hz=1500.0,
        transient_density_hz=1.0,
    )

    tags = derive_acoustic_tags(features)

    assert "bright" in tags
    assert "metallic" not in tags


def test_derive_acoustic_tags_high_transient_density_is_percussive_not_sustained() -> None:
    features = AcousticFeatures(
        spectral_centroid_hz=1000.0,
        spectral_bandwidth_hz=800.0,
        transient_density_hz=4.5,
    )

    tags = derive_acoustic_tags(features)

    assert "percussive" in tags
    assert "sustained" not in tags


def test_derive_acoustic_tags_respects_custom_thresholds() -> None:
    features = AcousticFeatures(
        spectral_centroid_hz=500.0,
        spectral_bandwidth_hz=200.0,
        transient_density_hz=0.0,
    )
    strict = AcousticTagThresholds(warm_centroid_max_hz=200.0)

    assert "warm" not in derive_acoustic_tags(features, thresholds=strict)
    assert "warm" in derive_acoustic_tags(features)


def test_build_sample_tags_merges_context_and_acoustic_tags() -> None:
    sample_rate = FIXTURE_SAMPLE_RATE
    n = sample_rate
    t = np.arange(n, dtype=np.float32) / sample_rate
    warm_tone = (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)

    tags = build_sample_tags(
        warm_tone,
        sample_rate,
        context={"organism": {"arc_phase": "rest"}},
        captured_at=1777152600.0,
    )

    assert isinstance(tags, SampleTags)
    assert tags.arc_phase == "rest"
    assert tags.captured_at_unix == 1777152600.0
    assert "warm" in tags.acoustic_tags
    assert "metallic" not in tags.acoustic_tags

    payload = tags.as_dict()
    assert payload["acoustic_tags"] == list(tags.acoustic_tags)
    assert payload["arc_phase"] == "rest"


def test_build_sample_tags_silent_input_yields_empty_acoustic_tags() -> None:
    tags = build_sample_tags(
        _silence(1.0),
        FIXTURE_SAMPLE_RATE,
        context=None,
        captured_at=0.0,
    )

    assert tags.acoustic_tags == ()
    assert tags.arc_phase == "unknown"


def test_save_capture_emits_contextual_and_acoustic_tags_for_room_sample(tmp_path) -> None:
    sample_rate = FIXTURE_SAMPLE_RATE
    n = sample_rate
    t = np.arange(n, dtype=np.float32) / sample_rate
    warm_tone = (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    captured_at = 1777152600.0

    capture = save_capture(
        warm_tone,
        source="room",
        sample_rate=sample_rate,
        capture_root=tmp_path,
        context={
            "organism": {
                "arc_phase": "rest",
                "mode": "engaged",
                "mood": {"label": "content", "valence": 0.42, "arousal": 0.31},
            },
            "room_presence": {"someone_here": True, "confidence": 0.88},
        },
        captured_at=captured_at,
    )

    assert capture.source == "room"
    assert capture.path.exists()
    assert capture.path.parent == tmp_path / "room"
    assert capture.path.name.startswith("room_20260425T213000Z_rest_")
    assert capture.tags.arc_phase == "rest"
    assert capture.tags.mood_label == "content"
    assert capture.tags.presence == "engaged"
    assert capture.tags.someone_here is True
    assert capture.tags.time_of_day == "afternoon"
    assert capture.tags.acoustic_tags == ("warm", "sustained")

    with wave.open(str(capture.path), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == sample_rate
        assert handle.getsampwidth() == 3
        assert handle.getnframes() == n


def test_save_capture_persists_tags_to_sample_index(tmp_path) -> None:
    sample_rate = FIXTURE_SAMPLE_RATE
    n = sample_rate
    t = np.arange(n, dtype=np.float32) / sample_rate
    warm_tone = (0.5 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)

    capture = save_capture(
        warm_tone,
        source="room",
        sample_rate=sample_rate,
        capture_root=tmp_path,
        context={
            "organism": {
                "arc_phase": "rest",
                "mode": "engaged",
                "mood": {"label": "content", "valence": 0.42, "arousal": 0.31},
            },
            "room_presence": {"someone_here": True, "confidence": 0.88},
        },
        captured_at=1777152600.0,
    )

    index_path = tmp_path / "index.sqlite"
    assert index_path.exists()

    with sqlite3.connect(index_path) as con:
        row = con.execute(
            """
            SELECT source, path, arc_phase, mood_label, presence, someone_here,
                   time_of_day, acoustic_tags_json, tags_json
            FROM samples
            WHERE sample_id = ?
            """,
            (capture.sample_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "room"
    assert row[1] == str(capture.path)
    assert row[2] == "rest"
    assert row[3] == "content"
    assert row[4] == "engaged"
    assert row[5] == 1
    assert row[6] == "afternoon"
    assert json.loads(row[7]) == ["warm", "sustained"]

    payload = json.loads(row[8])
    assert payload["arc_phase"] == "rest"
    assert payload["presence"] == "engaged"
    assert payload["acoustic_tags"] == ["warm", "sustained"]


def test_save_capture_indexes_percussive_contact_sample(tmp_path) -> None:
    capture = save_capture(
        _footsteps(1.0),
        source="contact",
        sample_rate=FIXTURE_SAMPLE_RATE,
        capture_root=tmp_path,
        context={
            "arc_phase": "climax",
            "presence": {
                "presence": "performing",
                "confidence": 0.75,
                "someone_here": True,
            },
            "mood": {"label": "excited", "valence": 0.8, "arousal": 0.9},
        },
        captured_at=1777167000.0,
    )

    assert capture.source == "contact"
    assert capture.path.exists()
    assert capture.path.parent == tmp_path / "contact"
    assert capture.tags.arc_phase == "climax"
    assert capture.tags.presence == "performing"
    assert capture.tags.mood_label == "excited"
    assert "percussive" in capture.tags.acoustic_tags
    assert "sustained" not in capture.tags.acoustic_tags

    with sqlite3.connect(tmp_path / "index.sqlite") as con:
        row = con.execute(
            "SELECT source, arc_phase, presence, acoustic_tags_json FROM samples WHERE sample_id = ?",
            (capture.sample_id,),
        ).fetchone()

    assert row == (
        "contact",
        "climax",
        "performing",
        json.dumps(list(capture.tags.acoustic_tags)),
    )


def _peak_dbfs(samples: np.ndarray) -> float:
    import math

    peak = float(np.max(np.abs(samples)))
    return -math.inf if peak <= 0.0 else 20.0 * math.log10(peak)


def _read_wav_samples(path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        sampwidth = handle.getsampwidth()
        nframes = handle.getnframes()
    assert sampwidth == 3
    raw = np.frombuffer(frames, dtype=np.uint8).reshape(nframes, 3)
    # 24-bit signed little-endian → int32
    extended = np.zeros((nframes, 4), dtype=np.uint8)
    extended[:, :3] = raw
    extended[:, 3] = np.where(raw[:, 2] & 0x80, 0xFF, 0x00)
    int32 = extended.view(np.int32).reshape(-1)
    return int32.astype(np.float32) / float((1 << 23) - 1)


def test_save_capture_peak_normalizes_to_minus_one_dbfs(tmp_path) -> None:
    sample_rate = FIXTURE_SAMPLE_RATE
    n = sample_rate
    t = np.arange(n, dtype=np.float32) / sample_rate
    quiet_tone = (0.1 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)  # ≈ -20 dBFS
    src_peak_db = _peak_dbfs(quiet_tone)
    assert src_peak_db < -1.0  # sanity: needs headroom to be normalized

    capture = save_capture(
        quiet_tone,
        source="room",
        sample_rate=sample_rate,
        capture_root=tmp_path,
        captured_at=1777152600.0,
    )

    expected_gain_db = -1.0 - src_peak_db
    assert capture.gain_db == pytest.approx(expected_gain_db, abs=0.01)
    assert capture.gain_db > 0.0

    written = _read_wav_samples(capture.path)
    written_peak_db = _peak_dbfs(written)
    assert written_peak_db == pytest.approx(-1.0, abs=0.05)


def test_save_capture_preserves_raw_when_peak_below_minus_thirty_dbfs(tmp_path) -> None:
    sample_rate = FIXTURE_SAMPLE_RATE
    n = sample_rate
    t = np.arange(n, dtype=np.float32) / sample_rate
    very_quiet = (0.01 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)  # -40 dBFS
    src_peak_db = _peak_dbfs(very_quiet)
    assert src_peak_db < -30.0

    capture = save_capture(
        very_quiet,
        source="room",
        sample_rate=sample_rate,
        capture_root=tmp_path,
        captured_at=1777152600.0,
    )

    assert capture.gain_db == 0.0

    written = _read_wav_samples(capture.path)
    written_peak_db = _peak_dbfs(written)
    # raw preserved (modulo 24-bit quantization noise)
    assert written_peak_db == pytest.approx(src_peak_db, abs=0.5)


def test_save_capture_silence_yields_zero_gain(tmp_path) -> None:
    capture = save_capture(
        _silence(0.5),
        source="room",
        sample_rate=FIXTURE_SAMPLE_RATE,
        capture_root=tmp_path,
        captured_at=1777152600.0,
    )

    assert capture.gain_db == 0.0


def test_save_capture_writes_gain_db_to_sample_index(tmp_path) -> None:
    sample_rate = FIXTURE_SAMPLE_RATE
    n = sample_rate
    t = np.arange(n, dtype=np.float32) / sample_rate
    quiet_tone = (0.1 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)

    capture = save_capture(
        quiet_tone,
        source="room",
        sample_rate=sample_rate,
        capture_root=tmp_path,
        captured_at=1777152600.0,
    )

    with sqlite3.connect(tmp_path / "index.sqlite") as con:
        row = con.execute(
            "SELECT gain_db FROM samples WHERE sample_id = ?",
            (capture.sample_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == pytest.approx(capture.gain_db, abs=1e-6)
    assert row[0] > 0.0


# ---------------------------------------------------------------------------
# Self-quotation loop
# ---------------------------------------------------------------------------


SELF_QUOTE_RATE = 8


def _self_listener_burst(peak_offset_seconds: float, *, total_seconds: float = 12.0) -> np.ndarray:
    """Mock self-listener stream with a clear peak ``peak_offset_seconds`` from end."""
    n = int(round(total_seconds * SELF_QUOTE_RATE))
    samples = (0.05 * np.ones(n, dtype=np.float32))
    peak_idx = max(0, n - 1 - int(round(peak_offset_seconds * SELF_QUOTE_RATE)))
    samples[peak_idx] = 0.9
    return samples


def _start_self_daemon() -> tuple[SampleCaptureDaemon, _FakeJackClient]:
    return _start_daemon(sample_rate=SELF_QUOTE_RATE, buffer_duration_seconds=16)


def _passing_score_summary(**overrides) -> dict:
    payload = {
        "arc_payoff": 0.85,
        "click_count": 0,
        "mode": "solo",
        "arc_phase": "rest",
        "mood": "content",
        "song_id": "song-42",
    }
    payload.update(overrides)
    return payload


def test_self_quote_triggers_only_when_gate_passes(tmp_path) -> None:
    daemon, client = _start_self_daemon()
    client.push_self_frames(_self_listener_burst(peak_offset_seconds=4.0))

    # Below arc_payoff threshold → no capture.
    assert (
        self_quote(
            _passing_score_summary(arc_payoff=0.6),
            daemon=daemon,
            capture_root=tmp_path,
            captured_at=1777152600.0,
        )
        is None
    )
    # Clicks recorded → no capture.
    assert (
        self_quote(
            _passing_score_summary(click_count=1),
            daemon=daemon,
            capture_root=tmp_path,
            captured_at=1777152600.0,
        )
        is None
    )
    # Working-ambience mode → no capture.
    assert (
        self_quote(
            _passing_score_summary(mode="working_ambience"),
            daemon=daemon,
            capture_root=tmp_path,
            captured_at=1777152600.0,
        )
        is None
    )
    # No file should have been written by any of the gated calls.
    assert not (tmp_path / "self").exists()

    # All gate conditions met → capture lands in samples/self/.
    capture = self_quote(
        _passing_score_summary(),
        daemon=daemon,
        capture_root=tmp_path,
        captured_at=1777152600.0,
    )
    assert capture is not None
    assert capture.source == "self"
    assert capture.path.parent == tmp_path / "self"
    assert capture.path.exists()


def test_self_quote_capture_window_is_centered_on_peak(tmp_path) -> None:
    daemon, client = _start_self_daemon()
    # Peak placed 4s back from "now" — a 4-second window centered there
    # should span [peak-2s, peak+2s] (offset_sec ≈ 2.0).
    client.push_self_frames(_self_listener_burst(peak_offset_seconds=4.0))

    capture = self_quote(
        _passing_score_summary(),
        daemon=daemon,
        capture_root=tmp_path,
        captured_at=1777152600.0,
    )

    assert capture is not None
    assert capture.frame_count == int(SELF_QUOTE_DURATION_SECONDS * SELF_QUOTE_RATE)
    # Read window directly from the daemon at the centering offset and
    # confirm the loud peak sits near the middle of the window.
    raw_window = daemon.get_window("self", SELF_QUOTE_DURATION_SECONDS, offset_sec=2.0)
    peak_idx = int(np.argmax(np.abs(raw_window)))
    middle = raw_window.size // 2
    assert abs(peak_idx - middle) <= 1


def test_self_quote_propagates_tags_to_index(tmp_path) -> None:
    daemon, client = _start_self_daemon()
    client.push_self_frames(_self_listener_burst(peak_offset_seconds=4.0))

    capture = self_quote(
        _passing_score_summary(arc_phase="rest", mood="content", mode="solo", song_id=42),
        daemon=daemon,
        capture_root=tmp_path,
        captured_at=1777152600.0,
    )

    assert capture is not None
    assert capture.tags.arc_phase == "rest"
    assert capture.tags.mood_label == "content"
    assert capture.tags.mode == "solo"
    assert dict(capture.tags.extra_tags) == {"self_quote_source_song_id": "42"}

    with sqlite3.connect(tmp_path / "index.sqlite") as con:
        row = con.execute(
            "SELECT tags_json FROM samples WHERE sample_id = ?",
            (capture.sample_id,),
        ).fetchone()

    assert row is not None
    payload = json.loads(row[0])
    assert payload["arc_phase"] == "rest"
    assert payload["mood_label"] == "content"
    assert payload["mode"] == "solo"
    assert payload["extra_tags"] == {"self_quote_source_song_id": "42"}
