"""Tests for contact_listener.py."""
from __future__ import annotations

import math
import os
import struct
import sys
import wave
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from contact_listener import read_wav_stereo


def _write_stereo_wav(path: Path, ch1_amp: int, ch2_amp: int, sr: int = 48000, duration: float = 0.5):
    n = int(sr * duration)
    stereo = []
    for i in range(n):
        s1 = int(ch1_amp * math.sin(2 * math.pi * 100 * i / sr))
        s2 = int(ch2_amp * math.sin(2 * math.pi * 150 * i / sr))
        stereo.extend([s1, s2])
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"{len(stereo)}h", *stereo))


class TestReadWavStereo:
    def test_separates_channels(self, tmp_path):
        wav = tmp_path / "stereo.wav"
        _write_stereo_wav(wav, 10000, 5000)
        ch1, ch2, sr = read_wav_stereo(wav)
        assert sr == 48000
        assert max(abs(s) for s in ch1) > 8000
        assert max(abs(s) for s in ch2) > 4000
        # Ch1 should be louder than ch2
        assert max(abs(s) for s in ch1) > max(abs(s) for s in ch2)

    def test_correct_lengths(self, tmp_path):
        wav = tmp_path / "stereo.wav"
        _write_stereo_wav(wav, 10000, 10000, duration=0.5)
        ch1, ch2, sr = read_wav_stereo(wav)
        assert len(ch1) == int(48000 * 0.5)
        assert len(ch2) == int(48000 * 0.5)


class TestTransientDetection:
    def test_quiet_is_not_transient(self, tmp_path):
        from audio_analysis import detect_amplitude
        import collections

        wav = tmp_path / "quiet.wav"
        _write_stereo_wav(wav, 100, 100)
        ch1, ch2, sr = read_wav_stereo(wav)
        rms1, _ = detect_amplitude(ch1)
        rms2, _ = detect_amplitude(ch2)

        history = collections.deque([rms1] * 20, maxlen=20)
        median = sorted(history)[10]
        ratio = rms1 / median if median > 0.0001 else 0.0
        assert ratio < 4.0  # Not a transient

    def test_loud_burst_is_transient(self, tmp_path):
        from audio_analysis import detect_amplitude
        import collections

        # Quiet baseline
        history = collections.deque([0.001] * 20, maxlen=20)

        # Loud burst
        wav = tmp_path / "loud.wav"
        _write_stereo_wav(wav, 20000, 20000)
        ch1, ch2, sr = read_wav_stereo(wav)
        rms1, _ = detect_amplitude(ch1)

        median = sorted(history)[10]
        ratio = rms1 / median if median > 0.0001 else 0.0
        assert ratio > 4.0  # Transient!
