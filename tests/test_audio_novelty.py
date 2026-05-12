"""Tests for audio-rendered SSM and Foote novelty cross-checks."""
from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.render.audio_novelty import (  # noqa: E402
    check_audio_symbolic_novelty_alignment,
    extract_audio_novelty,
    render_proxy_audio,
    symbolic_novelty_peak_times,
)
from senseweave.render.pass_ import PerformedPart  # noqa: E402
from senseweave.render.metrics import compute_metrics  # noqa: E402


SAMPLE_RATE = 8000
SYMBOLIC_PEAKS = (60.0, 150.0, 240.0)


def _fixture_part() -> PerformedPart:
    return PerformedPart(
        score={
            "duration_sec": 300.0,
            "intent_tags": ["development"],
            "velocities": [55.0, 75.0, 45.0, 80.0, 65.0, 70.0, 50.0],
            "iois": [1.0, 1.05, 0.95, 1.0, 1.1, 0.9, 1.0],
            "pitches": [60, 64, 67, 71, 62, 65, 69],
            "tempo_curve": [118.0, 120.0, 122.0, 121.0, 119.0],
            "novelty_peaks": len(SYMBOLIC_PEAKS),
            "symbolic_novelty_peak_times_s": list(SYMBOLIC_PEAKS),
            "silence_ms": 220.0,
            "rests_ms": [80.0, 240.0, 120.0],
            "section_gs": [0.82, 0.91, 0.94],
            "role": "melody",
        },
        applied_rules=("R1", "R2", "R6"),
        quantities={"R1": 1.0, "R2": 1.0, "R6": 0.7},
    )


def test_proxy_renderer_writes_five_minute_wav(tmp_path: Path) -> None:
    part = _fixture_part()
    audio_path = tmp_path / "fixture.wav"

    rendered = render_proxy_audio(part, audio_path, sample_rate=SAMPLE_RATE)

    assert rendered.audio_path == audio_path
    assert rendered.sample_rate == SAMPLE_RATE
    assert rendered.duration_s == 300.0
    assert rendered.symbolic_peak_times_s == SYMBOLIC_PEAKS

    with wave.open(str(audio_path), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == SAMPLE_RATE
        assert handle.getnframes() == SAMPLE_RATE * 300
        handle.setpos(SAMPLE_RATE * 60)
        assert handle.readframes(256) != b"\x00\x00" * 256


def test_librosa_ssm_and_foote_novelty_are_extracted(tmp_path: Path) -> None:
    audio_path = tmp_path / "fixture.wav"
    render_proxy_audio(_fixture_part(), audio_path, sample_rate=SAMPLE_RATE)

    analysis = extract_audio_novelty(
        audio_path,
        hop_length=2048,
        n_mels=24,
        kernel_size=16,
    )

    assert analysis.sample_rate == SAMPLE_RATE
    assert analysis.self_similarity.shape[0] == analysis.self_similarity.shape[1]
    assert analysis.self_similarity.shape[0] == len(analysis.novelty_curve)
    assert len(analysis.frame_times_s) == len(analysis.novelty_curve)
    assert float(analysis.novelty_curve.max()) > 0.25
    assert analysis.audio_peak_times_s


def test_symbolic_and_audio_novelty_peaks_align_within_500ms(tmp_path: Path) -> None:
    part = _fixture_part()
    audio_path = tmp_path / "fixture.wav"
    render_proxy_audio(part, audio_path, sample_rate=SAMPLE_RATE)

    report = check_audio_symbolic_novelty_alignment(
        part,
        audio_path,
        tolerance_s=0.5,
        hop_length=2048,
        n_mels=24,
        kernel_size=16,
    )

    assert symbolic_novelty_peak_times(part) == SYMBOLIC_PEAKS
    assert report.passed is True
    assert report.unmatched_symbolic_peak_times_s == ()
    assert len(report.matches) == len(SYMBOLIC_PEAKS)
    assert report.max_deviation_s <= 0.5
    for match in report.matches:
        assert match.audio_time_s is not None
        assert match.deviation_s is not None
        assert match.deviation_s <= 0.5


def test_flattened_audio_fails_even_when_symbolic_metrics_pass(tmp_path: Path) -> None:
    part = _fixture_part()
    metrics = compute_metrics(part)
    assert metrics["novelty_peaks"] == len(SYMBOLIC_PEAKS)
    assert 12 <= metrics["velocity_sigma"] <= 22

    audio_path = tmp_path / "flattened.wav"
    render_proxy_audio(
        part,
        audio_path,
        sample_rate=SAMPLE_RATE,
        flatten_expression=True,
    )

    report = check_audio_symbolic_novelty_alignment(
        part,
        audio_path,
        tolerance_s=0.5,
        hop_length=2048,
        n_mels=24,
        kernel_size=16,
    )

    assert report.passed is False
    assert report.audio_peak_times_s == ()
    assert report.unmatched_symbolic_peak_times_s == SYMBOLIC_PEAKS
