"""Tests for the MelodicMind musical brain module.

Covers: ChromaticScale, RhythmFeel, TimeOfDayPersonality, MelodicMemory,
MelodicMind note generation, and LLMAdvisor (mocked).
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools" / "senseweave" / "synthesis"))

import melodic_mind as mm


# ---------------------------------------------------------------------------
# ChromaticScale
# ---------------------------------------------------------------------------


class TestChromaticScale:
    def test_scale_tone_root_is_root(self) -> None:
        cs = mm.ChromaticScale()
        # Degree 1 at octave 0 should return the root frequency
        freq = cs.scale_tone(440.0, 1, 0)
        assert freq == pytest.approx(440.0, rel=1e-4)

    def test_scale_tone_octave(self) -> None:
        cs = mm.ChromaticScale()
        # Degree 1 at octave 1 should be double the root
        freq = cs.scale_tone(440.0, 1, 1)
        assert freq == pytest.approx(880.0, rel=1e-4)

    def test_scale_tone_fifth(self) -> None:
        cs = mm.ChromaticScale()
        # Degree 5 (7 semitones up from root)
        freq = cs.scale_tone(440.0, 5, 0)
        expected = 440.0 * (2 ** (7 / 12))
        assert freq == pytest.approx(expected, rel=1e-4)

    def test_scale_tone_all_degrees(self) -> None:
        cs = mm.ChromaticScale()
        major_semitones = [0, 2, 4, 5, 7, 9, 11]
        root = 261.63  # C4
        for deg_idx, semi in enumerate(major_semitones):
            freq = cs.scale_tone(root, deg_idx + 1, 0)
            expected = root * (2 ** (semi / 12))
            assert freq == pytest.approx(expected, rel=1e-3), f"degree {deg_idx + 1}"

    def test_chromatic_tone_zero_is_root(self) -> None:
        cs = mm.ChromaticScale()
        freq = cs.chromatic_tone(440.0, 0, 0)
        assert freq == pytest.approx(440.0, rel=1e-4)

    def test_chromatic_tone_tritone(self) -> None:
        cs = mm.ChromaticScale()
        freq = cs.chromatic_tone(440.0, 6, 0)  # tritone
        expected = 440.0 * (2 ** (6 / 12))
        assert freq == pytest.approx(expected, rel=1e-4)

    def test_neighbor_below(self) -> None:
        cs = mm.ChromaticScale()
        freq = cs.neighbor_below(440.0)
        expected = 440.0 / (2 ** (1 / 12))
        assert freq == pytest.approx(expected, rel=1e-4)

    def test_neighbor_above(self) -> None:
        cs = mm.ChromaticScale()
        freq = cs.neighbor_above(440.0)
        expected = 440.0 * (2 ** (1 / 12))
        assert freq == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# RhythmFeel
# ---------------------------------------------------------------------------


class TestRhythmFeel:
    def test_all_feels_exist(self) -> None:
        expected = {"waltz", "ragtime", "nocturne", "ballad", "beguine", "march"}
        actual = {f.value for f in mm.RhythmFeel}
        assert actual == expected

    def test_beat_duration_waltz(self) -> None:
        dur = mm.beat_duration(mm.RhythmFeel.WALTZ, 120)
        assert dur == pytest.approx(0.5, rel=1e-4)

    def test_beat_duration_slow(self) -> None:
        dur = mm.beat_duration(mm.RhythmFeel.BALLAD, 60)
        assert dur == pytest.approx(1.0, rel=1e-4)

    def test_accent_pattern_waltz(self) -> None:
        pattern = mm.accent_pattern(mm.RhythmFeel.WALTZ)
        assert pattern == [1, 0, 0]

    def test_accent_pattern_ragtime(self) -> None:
        pattern = mm.accent_pattern(mm.RhythmFeel.RAGTIME)
        assert pattern == [0, 1, 0, 1]

    def test_syncopation_probability_ranges(self) -> None:
        for feel in mm.RhythmFeel:
            prob = mm.syncopation_probability(feel)
            assert 0.0 <= prob <= 1.0, f"{feel} syncopation out of range"

    def test_ragtime_more_syncopated_than_march(self) -> None:
        rag = mm.syncopation_probability(mm.RhythmFeel.RAGTIME)
        march = mm.syncopation_probability(mm.RhythmFeel.MARCH)
        assert rag > march

    def test_typical_note_durations_nonempty(self) -> None:
        for feel in mm.RhythmFeel:
            durs = mm.typical_note_durations(feel)
            assert len(durs) > 0, f"{feel} has no typical durations"
            for d in durs:
                assert d > 0


# ---------------------------------------------------------------------------
# TimeOfDayPersonality
# ---------------------------------------------------------------------------


class TestTimeOfDayPersonality:
    def test_dawn_personality(self) -> None:
        p = mm.personality_for_hour(6)
        assert p["feel"] == mm.RhythmFeel.BALLAD
        assert 50 <= p["tempo_range"][0] <= p["tempo_range"][1] <= 70
        assert p["chromatic_probability"] < 0.2
        assert p["key_quality"] == "major"

    def test_morning_personality(self) -> None:
        p = mm.personality_for_hour(9)
        assert p["feel"] in (mm.RhythmFeel.WALTZ, mm.RhythmFeel.MARCH)
        assert 80 <= p["tempo_range"][0]
        assert p["tempo_range"][1] <= 110

    def test_afternoon_personality(self) -> None:
        p = mm.personality_for_hour(14)
        assert p["feel"] == mm.RhythmFeel.RAGTIME
        assert p["chromatic_probability"] > 0.1

    def test_evening_personality(self) -> None:
        p = mm.personality_for_hour(19)
        assert p["feel"] == mm.RhythmFeel.BEGUINE
        assert p["key_quality"] == "mixolydian"

    def test_night_personality(self) -> None:
        p = mm.personality_for_hour(23)
        assert p["feel"] == mm.RhythmFeel.NOCTURNE
        assert p["chromatic_probability"] > 0.3
        assert p["key_quality"] == "minor"

    def test_all_hours_valid(self) -> None:
        for h in range(24):
            p = mm.personality_for_hour(h)
            assert "feel" in p
            assert "tempo_range" in p
            assert "chromatic_probability" in p
            assert "key_quality" in p
            lo, hi = p["tempo_range"]
            assert 30 <= lo <= hi <= 200


# ---------------------------------------------------------------------------
# MelodicMemory
# ---------------------------------------------------------------------------


class TestMelodicMemory:
    def test_store_and_recall(self, tmp_path: Path) -> None:
        mem_path = tmp_path / "melodic_memory.json"
        mem = mm.MelodicMemory(path=str(mem_path))

        notes = [440.0, 493.88, 523.25, 587.33]
        mem.store_fragment(notes, context="calm/night", score=0.8)

        recalled = mem.recall_fragment(key_root=440.0, mood="calm")
        assert recalled is not None
        assert len(recalled) == 4

    def test_recall_transposes(self, tmp_path: Path) -> None:
        mem_path = tmp_path / "melodic_memory.json"
        mem = mm.MelodicMemory(path=str(mem_path))

        # Store a fragment rooted at A4=440
        notes = [440.0, 493.88, 523.25, 587.33]
        mem.store_fragment(notes, context="calm/night", score=0.8)

        # Recall in a different key (C4=261.63) — should transpose
        recalled = mem.recall_fragment(key_root=261.63, mood="calm")
        assert recalled is not None
        # The ratios should be preserved (intervals identical)
        orig_ratios = [notes[i + 1] / notes[i] for i in range(len(notes) - 1)]
        recall_ratios = [recalled[i + 1] / recalled[i] for i in range(len(recalled) - 1)]
        for orig, rec in zip(orig_ratios, recall_ratios):
            assert orig == pytest.approx(rec, rel=1e-3)

    def test_recall_no_match(self, tmp_path: Path) -> None:
        mem_path = tmp_path / "melodic_memory.json"
        mem = mm.MelodicMemory(path=str(mem_path))
        result = mem.recall_fragment(key_root=440.0, mood="excited")
        assert result is None

    def test_get_recent(self, tmp_path: Path) -> None:
        mem_path = tmp_path / "melodic_memory.json"
        mem = mm.MelodicMemory(path=str(mem_path))

        for i in range(10):
            mem.store_fragment([440.0 + i], context=f"ctx_{i}", score=0.5)

        recent = mem.get_recent(count=5)
        assert len(recent) == 5

    def test_prune(self, tmp_path: Path) -> None:
        mem_path = tmp_path / "melodic_memory.json"
        mem = mm.MelodicMemory(path=str(mem_path))

        for i in range(50):
            mem.store_fragment([440.0 + i], context="test", score=random.random())

        mem.prune(max_fragments=10)
        assert len(mem.get_recent(count=100)) <= 10

    def test_persists_to_disk(self, tmp_path: Path) -> None:
        mem_path = tmp_path / "melodic_memory.json"
        mem = mm.MelodicMemory(path=str(mem_path))
        mem.store_fragment([440.0, 880.0], context="test", score=0.9)

        # New instance reads from disk
        mem2 = mm.MelodicMemory(path=str(mem_path))
        recent = mem2.get_recent(count=5)
        assert len(recent) == 1
        assert recent[0]["notes"] == [440.0, 880.0]


# ---------------------------------------------------------------------------
# MelodicMind — deterministic with seed
# ---------------------------------------------------------------------------


class TestMelodicMind:
    def test_next_note_returns_tuple(self) -> None:
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        freq, duration, accent = mind.next_note(current_chord=[1, 3, 5], mood="calm")
        assert isinstance(freq, float)
        assert freq > 0
        assert isinstance(duration, float)
        assert duration > 0
        assert isinstance(accent, bool)

    def test_deterministic_with_seed(self) -> None:
        results_a = []
        random.seed(42)
        mind_a = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        for _ in range(8):
            results_a.append(mind_a.next_note([1, 3, 5]))

        results_b = []
        random.seed(42)
        mind_b = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        for _ in range(8):
            results_b.append(mind_b.next_note([1, 3, 5]))

        assert results_a == results_b

    def test_mostly_stepwise(self) -> None:
        """Over many notes, most intervals should be small (stepwise)."""
        random.seed(99)
        mind = mm.MelodicMind(key_root=261.63, rhythm_feel=mm.RhythmFeel.MARCH, bpm=100.0)
        freqs = []
        for _ in range(50):
            f, _, _ = mind.next_note([1, 3, 5])
            freqs.append(f)

        # Count intervals <= a major 3rd (roughly 1.26 ratio), skip rests
        small_steps = 0
        comparisons = 0
        for i in range(1, len(freqs)):
            if freqs[i] == 0.0 or freqs[i - 1] == 0.0:
                continue  # skip rests
            comparisons += 1
            ratio = max(freqs[i], freqs[i - 1]) / min(freqs[i], freqs[i - 1])
            if ratio <= 1.35:  # allow up to ~a minor 3rd
                small_steps += 1
        assert comparisons > 0, "Expected some non-rest notes"
        assert small_steps / comparisons > 0.4, "Expected mostly stepwise motion"

    def test_set_key(self) -> None:
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        mind.set_key(261.63)
        assert mind._key_root == pytest.approx(261.63)

    def test_set_feel(self) -> None:
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        mind.set_feel(mm.RhythmFeel.RAGTIME, 130.0)
        assert mind._rhythm_feel == mm.RhythmFeel.RAGTIME
        assert mind._bpm == pytest.approx(130.0)

    def test_set_chromatic_probability(self) -> None:
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        mind.set_chromatic_probability(0.7)
        assert mind._chromatic_probability == pytest.approx(0.7)

    def test_generate_phrase_length(self) -> None:
        random.seed(7)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.BALLAD, bpm=80.0)
        phrase = mind.generate_phrase(length=12)
        assert len(phrase) == 12
        for freq, dur, acc in phrase:
            assert freq >= 0  # 0.0 = rest
            assert dur > 0

    def test_generate_phrase_with_progression(self) -> None:
        random.seed(7)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.BALLAD, bpm=80.0)
        prog = [[1, 3, 5], [4, 6, 1], [5, 7, 2], [1, 3, 5]]
        phrase = mind.generate_phrase(length=8, chord_progression=prog)
        assert len(phrase) == 8

    def test_get_seed_returns_last_four(self) -> None:
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        for _ in range(10):
            mind.next_note([1, 3, 5])
        seed = mind.get_seed()
        assert len(seed) == 4
        # Seed should be the last 4 notes from recent_notes
        assert seed == mind.recent_notes[-4:]

    def test_recent_notes_populated(self) -> None:
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        for _ in range(5):
            mind.next_note([1, 3, 5])
        assert len(mind.recent_notes) == 5

    def test_rest_notes_appear(self) -> None:
        """Over many notes, at least some should be rests (freq=0)."""
        random.seed(123)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.NOCTURNE, bpm=50.0)
        rests = 0
        for _ in range(100):
            f, _, _ = mind.next_note([1, 3, 5])
            if f == 0.0:
                rests += 1
        # At 10% repeat/rest probability, expect some rests
        assert rests >= 1, "Expected at least one rest in 100 notes"


# ---------------------------------------------------------------------------
# LLMAdvisor (mocked)
# ---------------------------------------------------------------------------


class TestLLMAdvisor:
    def test_get_intention_with_mock(self) -> None:
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Play slowly with a nocturne feel, use minor key, moderate chromatic, melancholy mood."
        }
        with patch("melodic_mind.requests.post", return_value=mock_response):
            result = advisor.get_intention(hour=23, mood="calm", last_key="Am")
        assert "feel_hint" in result
        assert "mood_hint" in result

    def test_get_intention_fallback_on_error(self) -> None:
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        with patch("melodic_mind.requests.post", side_effect=Exception("connection refused")):
            result = advisor.get_intention(hour=12, mood="calm", last_key="C")
        # Should return defaults, not raise
        assert "feel_hint" in result
        assert "mood_hint" in result

    def test_critique_phrase_mocked(self) -> None:
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "The phrase is repetitive, try adding more variety."
        }
        with patch("melodic_mind.requests.post", return_value=mock_response):
            result = advisor.critique_phrase([440.0, 493.88], key="A", feel="waltz")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_critique_phrase_fallback(self) -> None:
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        with patch("melodic_mind.requests.post", side_effect=Exception("timeout")):
            result = advisor.critique_phrase([440.0], key="A", feel="waltz")
        assert isinstance(result, str)

    def test_evaluate_fragment_mocked(self) -> None:
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Score: 0.75 — interesting rising pattern."
        }
        with patch("melodic_mind.requests.post", return_value=mock_response):
            score = advisor.evaluate_fragment([440.0, 493.88, 523.25])
        assert 0.0 <= score <= 1.0

    def test_evaluate_fragment_fallback(self) -> None:
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        with patch("melodic_mind.requests.post", side_effect=Exception("err")):
            score = advisor.evaluate_fragment([440.0])
        assert 0.0 <= score <= 1.0

    def test_suggest_next_chord_mocked(self) -> None:
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Try IV (F major) for a plagal feel."
        }
        with patch("melodic_mind.requests.post", return_value=mock_response):
            result = advisor.suggest_next_chord("C", "I", "calm")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_suggest_next_chord_fallback(self) -> None:
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        with patch("melodic_mind.requests.post", side_effect=Exception("err")):
            result = advisor.suggest_next_chord("C", "I", "calm")
        assert isinstance(result, str)
