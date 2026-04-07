"""Tests for ContinuousLearner — learn by performing."""
from __future__ import annotations

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.synthesis.continuous_learner import (
    ContinuousLearner,
    GrowthState,
    PlayedNote,
    SongRecord,
)


class TestRecording:
    def test_start_song(self):
        cl = ContinuousLearner()
        cl.start_song(1, "D", "waltz", 90)
        assert cl.current_song is not None
        assert cl.current_song.key == "D"
        assert cl.growth.total_songs == 1
        assert "D" in cl.growth.keys_explored

    def test_record_note(self):
        cl = ContinuousLearner()
        cl.start_song(1, "D", "waltz", 90)
        cl.record_note(220.0, 1.0, False, "pluck")
        assert len(cl.current_song.notes) == 1
        assert cl.growth.total_notes == 1

    def test_multiple_notes(self):
        cl = ContinuousLearner()
        cl.start_song(1, "D", "waltz", 90)
        for f in [220, 277, 330, 440, 330, 277, 220]:
            cl.record_note(f, 0.5, False)
        assert len(cl.current_song.notes) == 7


class TestReflection:
    def test_no_reflect_too_soon(self):
        cl = ContinuousLearner()
        cl.start_song(1, "D", "waltz", 90)
        for f in [220, 277, 330, 440, 330, 277, 220, 330]:
            cl.record_note(f, 0.5, False)
        cl._last_reflect_time = time.time()
        result = cl.maybe_reflect()
        assert result is None  # too soon

    def test_reflect_detects_repetition(self):
        cl = ContinuousLearner()
        cl.start_song(1, "D", "waltz", 90)
        cl._last_reflect_time = time.time() - 60
        # Play the same note 16 times — extremely repetitive
        for _ in range(16):
            cl.record_note(220.0, 0.5, False)
        result = cl.maybe_reflect()
        assert result is not None
        assert "repetitive" in result.get("critique", "") or "chromatic_bump" in result

    def test_reflect_detects_stepwise(self):
        cl = ContinuousLearner()
        cl.start_song(1, "D", "waltz", 90)
        cl._last_reflect_time = time.time() - 60
        # Pure stepwise: each note is ~one step from the last
        freqs = [220, 230, 240, 250, 260, 270, 280, 290,
                 220, 230, 240, 250, 260, 270, 280, 290]
        for f in freqs:
            cl.record_note(float(f), 0.5, False)
        result = cl.maybe_reflect()
        assert result is not None

    def test_reflect_with_llm_mock(self):
        mock_llm = MagicMock()
        mock_llm.critique_phrase.return_value = "Too predictable, try more chromatic color"
        cl = ContinuousLearner(llm_advisor=mock_llm)
        cl.start_song(1, "D", "waltz", 90)
        cl._last_reflect_time = time.time() - 60
        for f in [220, 277, 330, 440, 330, 277, 220, 330]:
            cl.record_note(float(f), 0.5, False)
        result = cl.maybe_reflect()
        assert "llm_critique" in result
        assert cl.growth.chromatic_adjustment > 0  # adjusted up


class TestEvaluation:
    def test_end_song_basic(self):
        cl = ContinuousLearner()
        cl.start_song(1, "D", "waltz", 90)
        for f in [220, 277, 330, 440, 330, 277, 220, 330]:
            cl.record_note(float(f), 0.5, False)
        result = cl.end_song()
        assert result["song_num"] == 1
        assert result["notes_played"] == 8
        assert cl.current_song is None

    def test_end_song_finds_fragment(self):
        cl = ContinuousLearner()
        cl.start_song(1, "D", "waltz", 90)
        # Interesting fragment: leap + chromatic + rhythm variety
        for f, d, a in [(220, 0.5, False), (440, 1.0, True),
                         (415, 0.25, False), (330, 0.75, False),
                         (220, 0.5, False), (277, 1.0, False)]:
            cl.record_note(float(f), d, a)
        result = cl.end_song()
        assert "best_fragment" in result
        assert result["fragment_score"] > 0

    def test_end_song_stores_in_memory(self):
        mock_memory = MagicMock()
        cl = ContinuousLearner()
        cl.start_song(1, "D", "waltz", 90)
        for f, d, a in [(220, 0.5, False), (440, 1.0, True),
                         (415, 0.25, False), (330, 0.75, False)]:
            cl.record_note(float(f), d, a)
        result = cl.end_song(memory=mock_memory)
        if result.get("fragment_score", 0) > 0.5:
            assert mock_memory.store_fragment.called

    def test_recent_songs_tracked(self):
        cl = ContinuousLearner()
        for i in range(3):
            cl.start_song(i, "D", "waltz", 90)
            cl.record_note(220.0, 0.5, False)
            cl.end_song()
        assert len(cl.recent_songs) == 3


class TestEvolution:
    def test_get_adjustments(self):
        cl = ContinuousLearner()
        cl.growth.chromatic_adjustment = 0.1
        adj = cl.get_adjustments_for_mind()
        assert adj["chromatic_adjustment"] == 0.1

    def test_suggest_exploration_keys(self):
        cl = ContinuousLearner()
        cl.growth.keys_explored = {"C", "D", "G"}
        suggestion = cl.suggest_exploration()
        assert suggestion is not None
        assert "try_key" in suggestion
        assert suggestion["try_key"] not in {"C", "D", "G"}

    def test_suggest_exploration_feels(self):
        cl = ContinuousLearner()
        cl.growth.feels_explored = {"waltz"}
        suggestion = cl.suggest_exploration()
        assert "try_feel" in suggestion
        assert suggestion["try_feel"] != "waltz"

    def test_no_suggestion_when_fully_explored(self):
        cl = ContinuousLearner()
        cl.growth.keys_explored = {"C", "D", "E", "F", "G", "A", "Bb", "B"}
        cl.growth.feels_explored = {"waltz", "ragtime", "nocturne", "ballad", "beguine", "march"}
        suggestion = cl.suggest_exploration()
        assert suggestion is None


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "growth.json"
        with patch("senseweave.synthesis.continuous_learner.GROWTH_PATH", path):
            cl = ContinuousLearner()
            cl.growth.total_songs = 42
            cl.growth.keys_explored = {"C", "D"}
            cl.growth.chromatic_adjustment = 0.15
            cl._save_growth()

            cl2 = ContinuousLearner()
            # Need to reload
            cl2.growth = cl2._load_growth()
            assert cl2.growth.total_songs == 42
            assert "C" in cl2.growth.keys_explored
            assert cl2.growth.chromatic_adjustment == 0.15


class TestGrowthState:
    def test_adjustments_clamp(self):
        cl = ContinuousLearner()
        for _ in range(100):
            cl._apply_adjustments({"chromatic_bump": 0.1})
        assert cl.growth.chromatic_adjustment <= 0.2

    def test_critiques_limited(self):
        cl = ContinuousLearner()
        for i in range(30):
            cl._apply_adjustments({"critique": f"critique {i}"})
        assert len(cl.growth.recent_critiques) <= 20
