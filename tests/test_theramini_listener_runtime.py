"""Tests for theramini_listener.py — monkeypatched subprocess."""
from __future__ import annotations

import json
import math
import os
import struct
import sys
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from theramini_listener import analyze_once, read_wav_mono, write_state


def _write_sine_wav(path: Path, freq: float, sr: int = 48000, duration: float = 0.25, amp: int = 16000):
    """Write a synthetic sine wave WAV file."""
    n = int(sr * duration)
    samples = [int(amp * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)]
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        # Stereo: duplicate mono to both channels
        stereo = []
        for s in samples:
            stereo.extend([s, s])
        w.writeframes(struct.pack(f"{len(stereo)}h", *stereo))


def _write_silence_wav(path: Path, sr: int = 48000, duration: float = 0.25):
    n = int(sr * duration)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack(f"{n * 2}h", *([0] * n * 2)))


class TestReadWavMono:
    def test_reads_stereo(self, tmp_path):
        wav = tmp_path / "test.wav"
        _write_sine_wav(wav, 440.0)
        samples, sr = read_wav_mono(wav)
        assert sr == 48000
        assert len(samples) > 0
        assert max(abs(s) for s in samples) > 1000

    def test_mixes_to_mono(self, tmp_path):
        wav = tmp_path / "test.wav"
        _write_sine_wav(wav, 440.0, sr=44100, duration=0.1)
        samples, sr = read_wav_mono(wav)
        assert sr == 44100
        # Mono should have half the samples of stereo
        assert len(samples) == int(44100 * 0.1)


class TestWriteState:
    def test_atomic_write(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("theramini_listener.STATE_FILE", state_file)
        write_state({"test": True})
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["test"] is True

    def test_overwrites(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("theramini_listener.STATE_FILE", state_file)
        write_state({"v": 1})
        write_state({"v": 2})
        assert json.loads(state_file.read_text())["v"] == 2


class TestAnalyzeOnce:
    def test_detects_pitch_from_sine(self, tmp_path, monkeypatch):
        clip = tmp_path / "clip.wav"
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("theramini_listener.CLIP_FILE", clip)
        monkeypatch.setattr("theramini_listener.STATE_FILE", state_file)

        # Pre-write the WAV so capture_jack "succeeds"
        _write_sine_wav(clip, 440.0, sr=48000)

        def fake_capture(ports, duration, output):
            # Clip already exists
            return True

        monkeypatch.setattr("theramini_listener.capture_jack", fake_capture)

        state, rms, onset_time, silence_start = analyze_once(
            ["fake:port"], 0.0, None, None
        )
        assert state["is_playing"] is True
        assert state["pitch_note"] == "A4"
        assert abs(state["pitch_hz"] - 440.0) < 10
        assert state["pitch_confidence"] > 0.5
        assert state["suggested_key"] == "A"

    def test_silence_not_playing(self, tmp_path, monkeypatch):
        clip = tmp_path / "clip.wav"
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("theramini_listener.CLIP_FILE", clip)
        monkeypatch.setattr("theramini_listener.STATE_FILE", state_file)

        _write_silence_wav(clip)

        monkeypatch.setattr("theramini_listener.capture_jack", lambda *a: True)

        state, rms, onset_time, silence_start = analyze_once(
            ["fake:port"], 0.0, None, None
        )
        assert state["is_playing"] is False
        assert state["state"] == "silence"

    def test_capture_failure(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("theramini_listener.CLIP_FILE", tmp_path / "nope.wav")
        monkeypatch.setattr("theramini_listener.STATE_FILE", state_file)
        monkeypatch.setattr("theramini_listener.capture_jack", lambda *a: False)

        state, rms, onset_time, silence_start = analyze_once(
            ["fake:port"], 0.0, None, None
        )
        assert state["is_playing"] is False
        assert "error" in state

    def test_onset_detected(self, tmp_path, monkeypatch):
        clip = tmp_path / "clip.wav"
        state_file = tmp_path / "state.json"
        monkeypatch.setattr("theramini_listener.CLIP_FILE", clip)
        monkeypatch.setattr("theramini_listener.STATE_FILE", state_file)
        _write_sine_wav(clip, 440.0)
        monkeypatch.setattr("theramini_listener.capture_jack", lambda *a: True)

        # Previous RMS was 0 (silence), now loud = onset
        state, rms, onset_time, silence_start = analyze_once(
            ["fake:port"], 0.0, None, 100.0
        )
        assert state["state"] == "onset"
        assert onset_time is not None
