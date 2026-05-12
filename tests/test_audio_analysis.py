"""Tests for audio_analysis.py — pure functions, synthetic signals."""
from __future__ import annotations

import json
import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from audio_analysis import (
    detect_amplitude,
    detect_click_transients,
    detect_onset,
    detect_pitch_autocorrelation,
    classify_audio_content,
    extract_spectral_peaks,
    pitch_to_note_name,
    pitch_to_nearest_key,
)


def _sine_wave(freq: float, sr: int, duration: float, amplitude: int = 16000) -> list[int]:
    """Generate a synthetic sine wave as 16-bit integer samples."""
    n = int(sr * duration)
    return [int(amplitude * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)]


def _silence(sr: int, duration: float) -> list[int]:
    return [0] * int(sr * duration)


def _saw_wave(freq: float, sr: int, duration: float, amplitude: int = 16000) -> list[int]:
    """Generate a synthetic saw wave as 16-bit integer samples."""
    n = int(sr * duration)
    period = sr / freq
    out = []
    for i in range(n):
        phase = (i % period) / period
        out.append(int(amplitude * ((phase * 2.0) - 1.0)))
    return out


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


# === detect_click_transients ===


class TestClickDetection:
    def test_clean_sine_has_no_clicks(self):
        samples = _sine_wave(220.0, 48000, 1.0, amplitude=6000)
        result = detect_click_transients(samples, 48000)
        assert result["count"] == 0
        assert result["events"] == []
        assert result["suppressed_as_periodic"] is False

    def test_single_impulse_is_detected(self):
        samples = _sine_wave(220.0, 48000, 1.0, amplitude=6000)
        samples[24000] = 32000
        result = detect_click_transients(samples, 48000)
        assert result["count"] == 1
        assert len(result["events"]) == 1
        event = result["events"][0]
        assert abs(event["time_seconds"] - 0.5) < 0.005
        assert event["width_samples"] <= 4
        assert event["residual"] > 0.5

    def test_sparse_click_burst_is_retained(self):
        samples = _sine_wave(220.0, 48000, 1.0, amplitude=5000)
        for idx in (9600, 10176, 10752, 11328, 11904):
            samples[idx] = 32000
        result = detect_click_transients(samples, 48000)
        assert result["count"] == 5
        assert result["suppressed_as_periodic"] is False

    def test_dense_impulse_train_is_suppressed_as_periodic(self):
        samples = _silence(48000, 1.0)
        for idx in range(0, len(samples), 240):
            samples[idx] = 32000
        result = detect_click_transients(samples, 48000)
        assert result["count"] == 0
        assert result["suppressed_as_periodic"] is True


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

# === extract_spectral_peaks (T-021) ===

class TestExtractSpectralPeaks:
    def test_extract_spectral_peaks_sine_wave(self) -> None:
        from audio_analysis import extract_spectral_peaks
        samples = _sine_wave(440.0, 44100, 0.1)
        peaks = extract_spectral_peaks(samples, 44100, max_peaks=1)
        assert len(peaks) == 1
        assert abs(peaks[0] - 440.0) < 50.0

    def test_extract_spectral_peaks_multiple(self) -> None:
        from audio_analysis import extract_spectral_peaks
        samples1 = _sine_wave(440.0, 44100, 0.1)
        samples2 = _sine_wave(880.0, 44100, 0.1)
        samples = [s1 + s2 for s1, s2 in zip(samples1, samples2)]
        peaks = extract_spectral_peaks(samples, 44100, max_peaks=2)
        assert len(peaks) == 2
        assert any(abs(p - 440.0) < 50.0 for p in peaks)
        assert any(abs(p - 880.0) < 50.0 for p in peaks)


class TestAudioAnalysisEndToEnd:
    def test_tonal_signals_flow_from_samples_to_musical_labels(self) -> None:
        cases = [
            ("A3", "A", 220.0),
            ("C4", "C", 261.63),
            ("A4", "A", 440.0),
        ]

        for expected_note, expected_root, freq in cases:
            samples = _sine_wave(freq, 44100, 0.25, amplitude=12000)
            rms, peak = detect_amplitude(samples)
            detected_freq, confidence = detect_pitch_autocorrelation(samples, 44100)
            content = classify_audio_content(samples, 44100)
            root, scale = pitch_to_nearest_key(detected_freq or 0.0)
            peaks = extract_spectral_peaks(samples, 44100, max_peaks=2)

            assert rms > 0.20
            assert peak > rms
            assert detected_freq is not None
            assert abs(detected_freq - freq) < 5.0
            assert confidence > 0.8
            assert pitch_to_note_name(detected_freq) == expected_note
            assert root == expected_root
            assert scale[0] == expected_root
            assert len(scale) == 7
            assert content["type"] == "tonal"
            assert any(abs(peak_hz - freq) < 50.0 for peak_hz in peaks)

    def test_speech_like_signal_reports_dynamic_content(self) -> None:
        samples = []
        for i in range(44100):
            burst = 1.0 if (i // 2205) % 3 != 1 else 0.18
            carrier = math.sin(2 * math.pi * 1800 * i / 44100)
            carrier += 0.45 * math.sin(2 * math.pi * 3100 * i / 44100)
            samples.append(int(6500 * burst * carrier))

        rms, peak = detect_amplitude(samples)
        content = classify_audio_content(samples, 44100)

        assert rms > 0.05
        assert peak > rms
        assert content["type"] == "speech"
        assert content["zcr"] > 0.05
        assert content["amp_variance"] > 0.005
        assert content["confidence"] > 0.8

    def test_sparse_impulse_reports_click_and_transient_summary(self) -> None:
        samples = _silence(44100, 1.0)
        for offset, value in ((22050, 32000), (22051, -32000)):
            samples[offset] = value

        click_report = detect_click_transients(samples, 44100)
        content = classify_audio_content(samples, 44100)
        event = click_report["events"][0]

        assert click_report["count"] == 1
        assert click_report["suppressed_as_periodic"] is False
        assert abs(event["time_seconds"] - 0.5) < 0.005
        assert event["width_samples"] <= 4
        assert click_report["max_residual"] > 0.9
        assert content["type"] == "transient"
        assert content["confidence"] >= 0.7

    def test_windowed_rms_drives_onset_sequence(self) -> None:
        windows = [
            _silence(44100, 1024 / 44100),
            [8000] * 1024,
            [9000] * 1024,
            _silence(44100, 1024 / 44100),
        ]
        rms_values = [detect_amplitude(window)[0] for window in windows]
        transitions = []

        previous_rms = 0.0
        for current_rms in rms_values:
            transitions.append(detect_onset(current_rms, previous_rms))
            previous_rms = current_rms

        assert transitions == ["silence", "onset", "sustain", "release"]
        assert rms_values[0] == 0.0
        assert rms_values[1] > 0.2
        assert rms_values[2] > rms_values[1]
        assert rms_values[3] == 0.0

    def test_public_outputs_can_feed_json_safe_diagnostics(self) -> None:
        signals = {
            "tonal": _sine_wave(440.0, 44100, 0.25, amplitude=12000),
            "silence": _silence(44100, 0.25),
            "transient": _silence(44100, 0.25),
        }
        signals["transient"][5512] = 32000
        diagnostics = {}

        for name, samples in signals.items():
            rms, peak = detect_amplitude(samples)
            freq, confidence = detect_pitch_autocorrelation(samples, 44100)
            root, scale = pitch_to_nearest_key(freq or 0.0)
            diagnostics[name] = {
                "rms": rms,
                "peak": peak,
                "pitch_hz": freq,
                "pitch_confidence": confidence,
                "note": pitch_to_note_name(freq or 0.0),
                "root": root,
                "scale": scale,
                "content": classify_audio_content(samples, 44100),
                "click_count": detect_click_transients(samples, 44100)["count"],
                "spectral_peaks": extract_spectral_peaks(samples, 44100, max_peaks=2),
            }

        encoded = json.dumps(diagnostics, sort_keys=True)
        assert "\"tonal\"" in encoded
        assert diagnostics["tonal"]["content"]["type"] == "tonal"
        assert diagnostics["silence"]["content"]["type"] == "silence"
        assert diagnostics["transient"]["content"]["type"] == "transient"
        assert diagnostics["transient"]["click_count"] == 1
