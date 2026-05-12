"""Tests for room_listener.py — speech classification and hallucination filtering."""
from __future__ import annotations

import math
import os
import random
import subprocess
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

import room_listener
from room_listener import (
    capture_audio,
    is_hallucination,
    resolve_jack_capture_ports,
    resolve_pipewire_target,
    select_alsa_capture_device,
)
from audio_analysis import classify_audio_content


def _sine_wave(freq: float, sr: int, duration: float, amp: int = 16000) -> list[int]:
    n = int(sr * duration)
    return [int(amp * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)]


class TestIsHallucination:
    def test_known_patterns(self):
        assert is_hallucination("Thank you.") is True
        assert is_hallucination("thanks for watching") is True
        assert is_hallucination("Subscribe") is True
        assert is_hallucination("you") is True
        assert is_hallucination("...") is True
        assert is_hallucination("oh") is True

    def test_short_text(self):
        assert is_hallucination("hi") is True
        assert is_hallucination("ok") is True

    def test_repeated_words(self):
        assert is_hallucination("thank you thank you thank you") is True

    def test_real_speech_passes(self):
        assert is_hallucination("Can you play something in A major?") is False
        assert is_hallucination("That sounds really nice") is False
        assert is_hallucination("I think the theremin needs tuning") is False


class TestSpeechClassification:
    def test_silence_classified(self):
        result = classify_audio_content([0] * 44100, 44100)
        assert result["type"] == "silence"

    def test_tonal_classified(self):
        # Steady sine wave = tonal (Theramini-like)
        samples = _sine_wave(440, 44100, 1.0)
        result = classify_audio_content(samples, 44100)
        assert result["type"] == "tonal"

    def test_speech_like_classified(self):
        random.seed(42)
        samples = []
        for i in range(44100):
            burst = 1.0 if (i // 2000) % 2 == 0 else 0.1
            samples.append(int(random.gauss(0, 8000 * burst)))
        result = classify_audio_content(samples, 44100)
        assert result["type"] == "speech"

    def test_tonal_not_sent_to_whisper(self):
        """The pre-classifier should prevent Whisper from running on tonal audio."""
        samples = _sine_wave(440, 16000, 8.0)
        result = classify_audio_content(samples, 16000)
        # If type is tonal, the room_listener skips Whisper
        assert result["type"] == "tonal"


class TestAlsaSelection:
    def test_resolve_pipewire_target_finds_perform_ve(self, monkeypatch):
        status = """
Audio
 ├─ Devices:
 │      68. HD Pro Webcam C920                  [alsa]
 │     112. Perform-VE                          [alsa]
"""
        assert resolve_pipewire_target(status, "Perform-VE") == "112"

    def test_select_alsa_capture_device_prefers_perform_ve(self):
        listing = """
**** List of CAPTURE Hardware Devices ****
card 0: USB [Scarlett 4i4 USB], device 0: USB Audio [USB Audio]
card 3: PerformVE [Perform-VE], device 0: USB Audio [USB Audio]
card 5: C920 [HD Pro Webcam C920], device 0: USB Audio [USB Audio]
card 7: C920_1 [HD Pro Webcam C920], device 0: USB Audio [USB Audio]
"""
        assert select_alsa_capture_device(listing) == "hw:3,0"

    def test_select_alsa_capture_device_prefers_perform_ve_over_generic_analog(self):
        listing = """
**** List of CAPTURE Hardware Devices ****
card 2: PCH [HDA Intel PCH], device 0: ALC3246 Analog [ALC3246 Analog]
card 3: PerformVE [Perform-VE], device 0: USB Audio [USB Audio]
"""
        assert select_alsa_capture_device(listing) == "hw:3,0"

    def test_capture_audio_uses_auto_detected_alsa_device(self, monkeypatch, tmp_path):
        clip = tmp_path / "room_clip.wav"
        monkeypatch.setattr(room_listener, "CLIP_FILE", clip)
        monkeypatch.setattr(room_listener, "resolve_pipewire_target", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(room_listener, "list_alsa_capture_devices", lambda _listing=None: ["hw:5,0"])

        calls: list[list[str]] = []

        def fake_run(cmd, capture_output=True, timeout=None, text=False, check=False):
            calls.append(cmd)
            if cmd == ["jack_lsp"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="Perform-VE Analog Surround 7.1:capture_FL\n")
            clip.write_bytes(b"0" * 2048)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(room_listener.subprocess, "run", fake_run)

        assert capture_audio(None, "auto") == (True, "alsa", "hw:5,0")
        assert calls
        assert calls[0][0] == "arecord"
        assert "hw:5,0" in calls[0]

    def test_capture_audio_prefers_jack_when_available(self, monkeypatch, tmp_path):
        clip = tmp_path / "room_clip.wav"
        monkeypatch.setattr(room_listener, "CLIP_FILE", clip)
        monkeypatch.setattr(room_listener, "resolve_pipewire_target", lambda *_args, **_kwargs: None)

        calls: list[list[str]] = []

        def fake_run(cmd, capture_output=True, timeout=None, text=False, check=False):
            calls.append(cmd)
            if cmd == ["jack_lsp"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="Perform-VE Analog Surround 7.1:capture_FL\n")
            clip.write_bytes(b"0" * 2048)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(room_listener.subprocess, "run", fake_run)

        assert capture_audio("Perform-VE Analog Surround 7.1:capture_FL", "auto") == (
            True,
            "jack",
            "Perform-VE Analog Surround 7.1:capture_FL",
        )
        assert calls
        assert calls[0][0] == "jack_lsp"
        assert calls[1][0] == "jack_rec"

    def test_capture_audio_falls_back_to_system_jack_capture_when_preferred_port_missing(self, monkeypatch, tmp_path):
        clip = tmp_path / "room_clip.wav"
        monkeypatch.setattr(room_listener, "CLIP_FILE", clip)
        monkeypatch.setattr(room_listener, "resolve_pipewire_target", lambda *_args, **_kwargs: None)

        calls: list[list[str]] = []

        def fake_run(cmd, capture_output=True, timeout=None, text=False, check=False):
            calls.append(cmd)
            if cmd == ["jack_lsp"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="system:capture_1\nSuperCollider:out_1\n")
            clip.write_bytes(b"0" * 2048)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(room_listener.subprocess, "run", fake_run)

        assert capture_audio("Perform-VE Analog Surround 7.1:capture_FL", None) == (
            True,
            "jack",
            "system:capture_1",
        )
        assert any(cmd[-1] == "system:capture_1" for cmd in calls if cmd and cmd[0] == "jack_rec")

    def test_resolve_jack_capture_ports_preserves_preference_before_fallbacks(self):
        ports = resolve_jack_capture_ports("Perform-VE Analog Surround 7.1:capture_FL")
        assert ports[0] == "Perform-VE Analog Surround 7.1:capture_FL"
        assert "system:capture_1" in ports

    def test_capture_audio_prefers_pipewire_target_when_available(self, monkeypatch, tmp_path):
        clip = tmp_path / "room_clip.wav"
        monkeypatch.setattr(room_listener, "CLIP_FILE", clip)
        monkeypatch.setattr(room_listener, "resolve_pipewire_target", lambda *_args, **_kwargs: "112")

        calls: list[list[str]] = []

        def fake_run(cmd, capture_output=True, timeout=None, **kwargs):
            calls.append(cmd)
            clip.write_bytes(b"0" * 2048)
            return subprocess.CompletedProcess(cmd, 124)

        monkeypatch.setattr(room_listener.subprocess, "run", fake_run)

        assert capture_audio("Perform-VE Analog Surround 7.1:capture_FL", "auto") == (
            True,
            "pipewire",
            "112",
        )
        assert calls
        assert calls[0][0] == "timeout"
        assert "pw-record" in calls[0]

    def test_capture_audio_auto_falls_back_to_second_alsa_device(self, monkeypatch, tmp_path):
        clip = tmp_path / "room_clip.wav"
        monkeypatch.setattr(room_listener, "CLIP_FILE", clip)
        monkeypatch.setattr(room_listener, "resolve_pipewire_target", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            room_listener,
            "list_alsa_capture_devices",
            lambda _listing=None: ["hw:3,0", "hw:5,0"],
        )

        calls: list[list[str]] = []

        def fake_run(cmd, capture_output=True, timeout=None):
            calls.append(cmd)
            if "hw:3,0" in cmd:
                if clip.exists():
                    clip.unlink()
                return subprocess.CompletedProcess(cmd, 1)
            clip.write_bytes(b"0" * 2048)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(room_listener.subprocess, "run", fake_run)

        assert capture_audio(None, "auto") == (True, "alsa", "hw:5,0")
        assert len(calls) == 3
        assert "hw:3,0" in calls[0]
        assert "S32_LE" in calls[1]
        assert "hw:5,0" in calls[2]

    def test_capture_audio_retries_alternate_alsa_format_on_same_device(self, monkeypatch, tmp_path):
        clip = tmp_path / "room_clip.wav"
        monkeypatch.setattr(room_listener, "CLIP_FILE", clip)
        monkeypatch.setattr(room_listener, "resolve_pipewire_target", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            room_listener,
            "list_alsa_capture_devices",
            lambda _listing=None: ["hw:3,0"],
        )

        calls: list[list[str]] = []

        def fake_run(cmd, capture_output=True, timeout=None, **kwargs):
            calls.append(cmd)
            if "S16_LE" in cmd:
                if clip.exists():
                    clip.unlink()
                return subprocess.CompletedProcess(cmd, 1)
            clip.write_bytes(b"0" * 2048)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(room_listener.subprocess, "run", fake_run)

        assert capture_audio(None, "auto") == (True, "alsa", "hw:3,0")
        assert len(calls) == 2
        assert "S16_LE" in calls[0]
        assert "S32_LE" in calls[1]
