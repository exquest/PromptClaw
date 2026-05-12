"""Tests for ear_engine.py -- musical self-analysis metrics."""
from __future__ import annotations

import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.ear_engine import (
    CriticalListeningReport,
    analyze_captured_audio,
    analyze_played_notes,
    analyze_tracker_output,
    critical_listening_notes,
    critical_listening_tracker,
    feedback_scores,
    production_corrections,
)
from senseweave.synthesis.continuous_learner import PlayedNote


def _note(freq: float, duration: float, accent: bool = False) -> PlayedNote:
    return PlayedNote(
        freq=freq,
        duration=duration,
        accent=accent,
        voice="pluck",
        timestamp=time.time(),
    )


def test_analyze_played_notes_reports_variety_and_spread() -> None:
    report = analyze_played_notes(
        [_note(220.0, 1.0), _note(330.0, 0.5), _note(440.0, 1.5, True), _note(330.0, 0.75)]
    )

    assert report["interval_variety"] > 0
    assert report["register_spread"] > 0
    assert 0.0 <= report["hook_clarity"] <= 1.0


def test_stepwise_phrase_is_less_leap_heavy() -> None:
    stepwise = analyze_played_notes(
        [_note(220.0, 0.5), _note(233.0, 0.5), _note(247.0, 0.5), _note(262.0, 1.0)]
    )
    leaping = analyze_played_notes(
        [_note(220.0, 0.5), _note(440.0, 0.5), _note(277.0, 0.5), _note(523.0, 1.0)]
    )

    assert stepwise["leap_ratio"] < leaping["leap_ratio"]


def test_analyze_tracker_output_reports_full_feedback_metrics() -> None:
    report = analyze_tracker_output(
        [
            {
                "frequency_hz": 220.0,
                "duration_seconds": 0.25,
                "time_seconds": 0.0,
                "amplitude": 0.2,
                "accent": True,
            },
            {
                "frequency_hz": 277.18,
                "duration_seconds": 0.25,
                "time_seconds": 0.25,
                "amplitude": 0.16,
            },
            {
                "frequency_hz": 329.63,
                "duration_seconds": 0.5,
                "time_seconds": 0.5,
                "amplitude": 0.18,
            },
            {
                "frequency_hz": 277.18,
                "duration_seconds": 0.25,
                "time_seconds": 1.0,
                "amplitude": 0.16,
            },
            {
                "frequency_hz": 220.0,
                "duration_seconds": 0.75,
                "time_seconds": 1.25,
                "amplitude": 0.2,
                "accent": True,
            },
        ]
    )

    assert report["pitch_mean_midi"] > 0.0
    assert report["mean_interval_semitones"] > 0.0
    assert report["onset_density"] > 1.0
    assert report["spectral_centroid_hz"] > 200.0
    assert 0.0 <= report["spectral_flatness"] <= 1.0
    assert 0.0 <= report["roughness"] <= 1.0
    assert "repetition_score" in report
    assert "development_score" in report
    assert set(feedback_scores(report)) == {
        "static_score",
        "harsh_score",
        "muddy_score",
        "underdeveloped_score",
    }


def test_analyze_captured_audio_uses_synthetic_audio_features() -> None:
    sample_rate = 8000
    duration_s = 0.5
    sine = [
        0.4 * math.sin(2.0 * math.pi * 440.0 * index / sample_rate)
        for index in range(int(sample_rate * duration_s))
    ]
    rng = random.Random(7)
    noise = [rng.uniform(-0.4, 0.4) for _ in sine]

    tonal = analyze_captured_audio(sine, sample_rate)
    noisy = analyze_captured_audio(noise, sample_rate)

    assert abs(tonal["pitch_hz"] - 440.0) < 12.0
    assert tonal["spectral_centroid_hz"] > 300.0
    assert noisy["spectral_flatness"] > tonal["spectral_flatness"]
    assert 0.0 <= noisy["roughness"] <= 1.0


# --- Critical listening & production corrections ---


def test_critical_listening_balanced_phrase() -> None:
    """A phrase spanning registers produces balanced spectral metrics."""
    events = [
        {"frequency_hz": 110.0, "duration_seconds": 0.5, "time_seconds": 0.0, "amplitude": 0.5},
        {"frequency_hz": 330.0, "duration_seconds": 0.5, "time_seconds": 0.5, "amplitude": 0.5},
        {"frequency_hz": 880.0, "duration_seconds": 0.5, "time_seconds": 1.0, "amplitude": 0.5},
    ]
    report = critical_listening_tracker(events)
    assert report.spectral_balance > 0.5
    assert report.masking_risk < 0.3
    assert 0.0 <= report.rhythmic_activity <= 1.0
    assert 0.0 <= report.timbral_quality <= 1.0
    assert 0.0 <= report.harmonic_tension <= 1.0
    assert len(report.equal_loudness_hints) == 7
    assert report.equal_loudness_hints[0].band_low_hz == 20.0
    assert report.equal_loudness_hints[0].compensation_db == 6.0


def test_critical_listening_crowded_register() -> None:
    """Events crowded in one register have high masking risk."""
    events = [
        {"frequency_hz": 440.0, "duration_seconds": 1.0, "time_seconds": 0.0, "amplitude": 0.8},
        {"frequency_hz": 466.0, "duration_seconds": 1.0, "time_seconds": 0.0, "amplitude": 0.7},
        {"frequency_hz": 494.0, "duration_seconds": 1.0, "time_seconds": 0.0, "amplitude": 0.6},
    ]
    report = critical_listening_tracker(events)
    assert report.masking_risk > 0.5
    assert report.spectral_balance < 0.5


def test_critical_listening_notes_api() -> None:
    """critical_listening_notes accepts PlayedNote objects."""
    notes = [
        _note(220.0, 0.5),
        _note(440.0, 0.5, True),
        _note(880.0, 1.0),
    ]
    report = critical_listening_notes(notes)
    assert report.spectral_balance > 0.3
    assert 0.0 <= report.dynamic_contour <= 1.0
    assert report.spatial_distribution > 0.0


def test_critical_listening_dynamic_contour() -> None:
    """Events with amplitude variation produce higher dynamic contour."""
    steady = [
        {"frequency_hz": 440.0, "duration_seconds": 0.5, "time_seconds": i * 0.5, "amplitude": 0.5}
        for i in range(8)
    ]
    varied = [
        {"frequency_hz": 440.0, "duration_seconds": 0.5, "time_seconds": i * 0.5,
         "amplitude": 0.9 if i % 4 == 0 else 0.1}
        for i in range(8)
    ]
    steady_report = critical_listening_tracker(steady)
    varied_report = critical_listening_tracker(varied)
    assert varied_report.dynamic_contour > steady_report.dynamic_contour


def test_production_corrections_crowded_thins_density() -> None:
    """High masking and activity should recommend thinning."""
    events = [
        {"frequency_hz": 440.0, "duration_seconds": 0.2, "time_seconds": i * 0.15, "amplitude": 0.8}
        for i in range(20)
    ]
    report = critical_listening_tracker(events)
    corrections = production_corrections(report)
    assert corrections.density < 0.0


def test_production_corrections_sparse_adds_density() -> None:
    """Low activity should recommend adding density."""
    report = CriticalListeningReport(
        spectral_balance=0.8,
        dynamic_contour=0.2,
        spatial_distribution=0.6,
        timbral_quality=0.7,
        rhythmic_activity=0.1,
        harmonic_tension=0.2,
        masking_risk=0.0,
        equal_loudness_hints=(),
    )
    corrections = production_corrections(report)
    assert corrections.density > 0.0


def test_production_corrections_flat_dynamics_suggests_expansion() -> None:
    """Low dynamic contour should recommend expanding dynamics."""
    report = CriticalListeningReport(
        spectral_balance=0.6,
        dynamic_contour=0.1,
        spatial_distribution=0.5,
        timbral_quality=0.5,
        rhythmic_activity=0.4,
        harmonic_tension=0.3,
        masking_risk=0.1,
        equal_loudness_hints=(),
    )
    corrections = production_corrections(report)
    assert corrections.dynamics > 0.0


def test_production_corrections_narrow_palette_diversifies() -> None:
    """Low spatial distribution should recommend palette diversification."""
    report = CriticalListeningReport(
        spectral_balance=0.5,
        dynamic_contour=0.4,
        spatial_distribution=0.1,
        timbral_quality=0.5,
        rhythmic_activity=0.5,
        harmonic_tension=0.3,
        masking_risk=0.2,
        equal_loudness_hints=(),
    )
    corrections = production_corrections(report)
    assert corrections.palette > 0.0
