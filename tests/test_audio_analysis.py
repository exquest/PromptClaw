"""Tests for audio_analysis.py — pure functions, synthetic signals."""
from __future__ import annotations

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from audio_analysis import (
    detect_amplitude,
    detect_onset,
    detect_pitch_autocorrelation,
    classify_audio_content,
    pitch_to_note_name,
    pitch_to_nearest_key,
)


def _sine_wave(freq: float, sr: int, duration: float, amplitude: int = 16000) -> list[int]:
    """Generate a synthetic sine wave as 16-bit integer samples."""
    n = int(sr * duration)
    return [int(amplitude * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)]


def _silence(sr: int, duration: float) -> list[int]:
    return [0] * int(sr * duration)


# === detect_amplitude ===


class TestDetectAmplitude:
    def test_silence(self):
        rms, peak = detect_amplitude(_silence(44100, 0.1))
        assert rms == 0.0
        assert peak == 0.0

    def test_empty(self):
        rms, peak = detect_amplitude([])
        assert rms == 0.0
        assert peak == 0.0

    def test_full_scale_sine(self):
        samples = _sine_wave(440, 44100, 0.1, amplitude=32767)
        rms, peak = detect_amplitude(samples)
        assert 0.6 < rms < 0.8  # sine RMS ≈ 0.707 * peak
        assert 0.99 < peak <= 1.0

    def test_quiet_sine(self):
        samples = _sine_wave(440, 44100, 0.1, amplitude=3276)
        rms, peak = detect_amplitude(samples)
        assert 0.05 < rms < 0.15
        assert 0.09 < peak < 0.11


# === detect_pitch_autocorrelation ===


class TestPitchDetection:
    def test_a4_440(self):
        samples = _sine_wave(440.0, 44100, 0.25)
        freq, conf = detect_pitch_autocorrelation(samples, 44100)
        assert freq is not None
        assert abs(freq - 440.0) < 5.0
        assert conf > 0.8

    def test_a3_220(self):
        samples = _sine_wave(220.0, 44100, 0.25)
        freq, conf = detect_pitch_autocorrelation(samples, 44100)
        assert freq is not None
        assert abs(freq - 220.0) < 3.0
        assert conf > 0.8

    def test_b3_247(self):
        samples = _sine_wave(246.94, 44100, 0.25)
        freq, conf = detect_pitch_autocorrelation(samples, 44100)
        assert freq is not None
        assert abs(freq - 246.94) < 4.0
        assert conf > 0.7

    def test_gsharp3_208(self):
        samples = _sine_wave(207.65, 44100, 0.25)
        freq, conf = detect_pitch_autocorrelation(samples, 44100)
        assert freq is not None
        assert abs(freq - 207.65) < 4.0
        assert conf > 0.7

    def test_high_frequency(self):
        samples = _sine_wave(1000.0, 44100, 0.25)
        freq, conf = detect_pitch_autocorrelation(samples, 44100)
        assert freq is not None
        assert abs(freq - 1000.0) < 10.0

    def test_low_frequency(self):
        samples = _sine_wave(100.0, 44100, 0.25)
        freq, conf = detect_pitch_autocorrelation(samples, 44100)
        assert freq is not None
        assert abs(freq - 100.0) < 3.0

    def test_silence_returns_none(self):
        samples = _silence(44100, 0.25)
        freq, conf = detect_pitch_autocorrelation(samples, 44100)
        assert freq is None
        assert conf == 0.0

    def test_below_min_freq_filtered(self):
        # Room hum at 61.8 Hz should be rejected (min_freq=80)
        samples = _sine_wave(61.8, 44100, 0.25)
        freq, conf = detect_pitch_autocorrelation(samples, 44100, min_freq=80.0)
        assert freq is None or freq >= 80.0

    def test_48khz_sample_rate(self):
        samples = _sine_wave(440.0, 48000, 0.25)
        freq, conf = detect_pitch_autocorrelation(samples, 48000)
        assert freq is not None
        assert abs(freq - 440.0) < 5.0


# === detect_onset ===


class TestOnsetDetection:
    def test_silence_to_silence(self):
        assert detect_onset(0.001, 0.001) == "silence"

    def test_onset_from_silence(self):
        assert detect_onset(0.1, 0.001) == "onset"

    def test_sustain(self):
        assert detect_onset(0.1, 0.09) == "sustain"

    def test_release(self):
        assert detect_onset(0.001, 0.1) == "release"

    def test_sudden_jump_is_onset(self):
        # Even during sustain, a 3x jump counts as onset
        assert detect_onset(0.3, 0.08) == "onset"

    def test_custom_thresholds(self):
        assert detect_onset(0.02, 0.001, release_threshold=0.01) == "onset"
        assert detect_onset(0.005, 0.001, release_threshold=0.01) == "silence"


# === classify_audio_content ===


class TestClassifyAudio:
    def test_silence(self):
        result = classify_audio_content(_silence(44100, 1.0), 44100)
        assert result["type"] == "silence"

    def test_tonal_sine(self):
        # A steady sine wave = tonal
        samples = _sine_wave(440, 44100, 1.0)
        result = classify_audio_content(samples, 44100)
        assert result["type"] == "tonal"

    def test_noise_like_speech(self):
        # Simulate speech-like: random-ish signal with high ZCR and variable amplitude
        import random
        random.seed(42)
        samples = []
        for i in range(44100):
            # Alternate between loud and quiet bursts (like syllables)
            burst = 1.0 if (i // 2000) % 2 == 0 else 0.1
            samples.append(int(random.gauss(0, 8000 * burst)))
        result = classify_audio_content(samples, 44100)
        assert result["type"] == "speech"

    def test_transient(self):
        # Single sharp impulse in silence
        samples = [0] * 44100
        samples[22050] = 32000
        samples[22051] = -32000
        result = classify_audio_content(samples, 44100)
        assert result["type"] == "transient"


# === pitch_to_note_name ===


class TestPitchToNoteName:
    def test_a4(self):
        assert pitch_to_note_name(440.0) == "A4"

    def test_c4(self):
        assert pitch_to_note_name(261.63) == "C4"

    def test_b3(self):
        assert pitch_to_note_name(246.94) == "B3"

    def test_gsharp3(self):
        assert pitch_to_note_name(207.65) == "G#3"

    def test_zero(self):
        assert pitch_to_note_name(0) == "?"


# === pitch_to_nearest_key ===


class TestPitchToNearestKey:
    def test_a4_gives_a_major(self):
        root, scale = pitch_to_nearest_key(440.0)
        assert root == "A"
        assert scale == ["A", "B", "C#", "D", "E", "F#", "G#"]

    def test_c4_gives_c_major(self):
        root, scale = pitch_to_nearest_key(261.63)
        assert root == "C"
        assert scale == ["C", "D", "E", "F", "G", "A", "B"]

    def test_d3_gives_d_major(self):
        root, scale = pitch_to_nearest_key(146.83)
        assert root == "D"
        assert scale == ["D", "E", "F#", "G", "A", "B", "C#"]
