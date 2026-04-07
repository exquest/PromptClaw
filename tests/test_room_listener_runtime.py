"""Tests for room_listener.py — speech classification and hallucination filtering."""
from __future__ import annotations

import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from room_listener import is_hallucination
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
