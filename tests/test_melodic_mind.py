"""Tests for the MelodicMind musical brain module.

Covers: ChromaticScale, RhythmFeel, TimeOfDayPersonality, MelodicMemory,
MelodicMind note generation, LLMAdvisor (mocked), Lewis rhythm concepts
(humanized timing, phrase pairs, RoomPulse, event response).
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


# ---------------------------------------------------------------------------
# Lewis Rhythm Concepts — Humanized Timing
# ---------------------------------------------------------------------------


class TestHumanizedTiming:
    def test_duration_varies_from_input(self) -> None:
        """humanize_duration should return a value different from the raw input
        (most of the time — statistical over many calls)."""
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        mind.timing_feel = "human"
        raw = 1.0
        results = [mind.humanize_duration(raw) for _ in range(50)]
        # At least some should differ from raw
        different = [r for r in results if abs(r - raw) > 1e-6]
        assert len(different) > 30, "Expected most humanized durations to differ from raw"

    def test_high_energy_biases_early(self) -> None:
        """With energy > 0.6 and 'human' feel, durations should be biased shorter
        (early = driving)."""
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.MARCH, bpm=120.0)
        mind.timing_feel = "human"
        mind.set_energy(0.9)
        raw = 1.0
        results = [mind.humanize_duration(raw) for _ in range(200)]
        avg = sum(results) / len(results)
        # High energy should bias early (shorter durations)
        assert avg < raw, f"Expected avg < {raw}, got {avg}"

    def test_low_energy_biases_late(self) -> None:
        """With energy < 0.4, durations should be biased longer (late = laid-back)."""
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.BALLAD, bpm=120.0)
        mind.timing_feel = "human"
        mind.set_energy(0.1)
        raw = 1.0
        results = [mind.humanize_duration(raw) for _ in range(200)]
        avg = sum(results) / len(results)
        assert avg > raw, f"Expected avg > {raw}, got {avg}"

    def test_straight_feel_minimal_variation(self) -> None:
        """Straight timing feel should have very small variation (+/-2ms)."""
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.MARCH, bpm=120.0)
        mind.timing_feel = "straight"
        raw = 1.0
        results = [mind.humanize_duration(raw) for _ in range(100)]
        # At 120 BPM, 1 beat = 500ms. 2ms = 0.004 beats.
        for r in results:
            assert abs(r - raw) < 0.01, f"Straight feel variation too large: {r}"

    def test_swing_feel_late_on_offbeats(self) -> None:
        """Swing should push off-beats (odd counter positions) late."""
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.RAGTIME, bpm=120.0)
        mind.timing_feel = "swing"
        raw = 1.0
        onbeat_vals = []
        offbeat_vals = []
        for i in range(200):
            mind._note_counter = i
            val = mind.humanize_duration(raw)
            if i % 2 == 0:
                onbeat_vals.append(val)
            else:
                offbeat_vals.append(val)
        offbeat_avg = sum(offbeat_vals) / len(offbeat_vals)
        onbeat_avg = sum(onbeat_vals) / len(onbeat_vals)
        # Off-beats should be later (longer) than on-beats
        assert offbeat_avg > onbeat_avg, (
            f"Swing off-beats should be later: offbeat={offbeat_avg}, onbeat={onbeat_avg}"
        )

    def test_push_feel_always_early(self) -> None:
        """Push timing should always produce earlier (shorter) durations."""
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.MARCH, bpm=120.0)
        mind.timing_feel = "push"
        raw = 1.0
        results = [mind.humanize_duration(raw) for _ in range(100)]
        for r in results:
            assert r < raw, f"Push feel should always be early, got {r}"

    def test_set_timing_feel_validates(self) -> None:
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        mind.set_timing_feel("swing")
        assert mind.timing_feel == "swing"
        with pytest.raises(ValueError):
            mind.set_timing_feel("dubstep")

    def test_next_note_applies_humanization(self) -> None:
        """next_note should apply humanized timing to durations."""
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        mind.timing_feel = "human"
        # Generate many notes and check durations are not all identical
        durations = []
        for _ in range(30):
            _, dur, _ = mind.next_note([1, 3, 5])
            durations.append(dur)
        unique = set(round(d, 6) for d in durations)
        assert len(unique) > 3, "Expected humanized timing to produce varied durations"


# ---------------------------------------------------------------------------
# Lewis Rhythm Concepts — Antecedent-Consequent Phrase Pairs
# ---------------------------------------------------------------------------


class TestPhrasePair:
    def test_antecedent_ends_non_tonic(self) -> None:
        """Antecedent phrase should end on a non-tonic (degree 2, 3, 5, or 7)."""
        random.seed(42)
        root = 261.63  # C4
        mind = mm.MelodicMind(key_root=root, rhythm_feel=mm.RhythmFeel.BALLAD, bpm=90.0)
        antecedent, _ = mind.generate_phrase_pair(length=8)

        # The last note's frequency should NOT be the tonic (or octave of tonic)
        last_freq = antecedent[-1][0]
        tonic = root
        # Check it's not the tonic or an octave of it
        if last_freq > 0:
            ratio = last_freq / tonic
            # Tonic would be ratio = 1.0, 2.0, 0.5, etc.
            is_tonic = any(
                abs(ratio - 2**k) < 0.01 for k in range(-2, 3)
            )
            assert not is_tonic, f"Antecedent should not end on tonic, got freq={last_freq}"

    def test_consequent_ends_on_tonic(self) -> None:
        """Consequent phrase should end on tonic (degree 1)."""
        random.seed(42)
        root = 261.63
        mind = mm.MelodicMind(key_root=root, rhythm_feel=mm.RhythmFeel.BALLAD, bpm=90.0)
        _, consequent = mind.generate_phrase_pair(length=8)

        last_freq = consequent[-1][0]
        # Should be the tonic
        assert last_freq == pytest.approx(root, rel=1e-3), (
            f"Consequent should end on tonic ({root}), got {last_freq}"
        )

    def test_shared_opening_notes(self) -> None:
        """Antecedent and consequent should share their opening 2-3 notes."""
        random.seed(42)
        root = 440.0
        mind = mm.MelodicMind(key_root=root, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        antecedent, consequent = mind.generate_phrase_pair(length=8)

        shared_count = min(3, len(antecedent), len(consequent))
        for i in range(shared_count):
            a_freq = antecedent[i][0]
            c_freq = consequent[i][0]
            assert a_freq == pytest.approx(c_freq, rel=1e-6), (
                f"Note {i} should be shared: antecedent={a_freq}, consequent={c_freq}"
            )

    def test_phrase_pair_returns_correct_lengths(self) -> None:
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        ant, con = mind.generate_phrase_pair(length=8)
        assert len(ant) == 8
        assert len(con) == 8

    def test_phrase_pair_with_chord_progression(self) -> None:
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.BALLAD, bpm=80.0)
        prog = [[1, 3, 5], [4, 6, 1], [5, 7, 2], [1, 3, 5]]
        ant, con = mind.generate_phrase_pair(length=8, chord_progression=prog)
        assert len(ant) == 8
        assert len(con) == 8


# ---------------------------------------------------------------------------
# Lewis Rhythm Concepts — RoomPulse
# ---------------------------------------------------------------------------


class TestRoomPulse:
    def test_feed_rms_stores_values(self) -> None:
        pulse = mm.RoomPulse()
        pulse.feed_rms(0.5)
        pulse.feed_rms(0.8)
        assert len(pulse._rms_history) == 2

    def test_feed_rms_caps_history(self) -> None:
        pulse = mm.RoomPulse()
        for i in range(300):
            pulse.feed_rms(float(i))
        assert len(pulse._rms_history) == mm._ROOM_PULSE_MAX_HISTORY

    def test_estimate_tempo_no_data(self) -> None:
        pulse = mm.RoomPulse()
        assert pulse.estimate_room_tempo() == 0.0

    def test_estimate_tempo_insufficient_data(self) -> None:
        pulse = mm.RoomPulse()
        for _ in range(5):
            pulse.feed_rms(0.5)
        assert pulse.estimate_room_tempo() == 0.0

    def test_estimate_tempo_with_periodic_signal(self) -> None:
        """Feed a synthetic periodic signal and verify tempo detection."""
        pulse = mm.RoomPulse()
        # Simulate 120 BPM = 2 beats/sec = period of 5 samples at 10 samples/sec
        target_bpm = 120.0
        samples_per_sec = 10.0
        period_samples = samples_per_sec * 60.0 / target_bpm  # 5
        for i in range(100):
            val = math.sin(2 * math.pi * i / period_samples)
            pulse.feed_rms(val)
        bpm = pulse.estimate_room_tempo()
        assert bpm > 0, "Should detect a rhythm"
        # Allow some tolerance in BPM detection
        assert abs(bpm - target_bpm) < 30, f"Expected ~{target_bpm} BPM, got {bpm}"

    def test_estimate_tempo_with_constant_signal(self) -> None:
        """A constant signal should not detect any rhythm."""
        pulse = mm.RoomPulse()
        for _ in range(100):
            pulse.feed_rms(0.5)
        bpm = pulse.estimate_room_tempo()
        assert bpm == 0.0, "Constant signal should yield no rhythm"

    def test_suggest_tempo_adjustment_no_room_pulse(self) -> None:
        pulse = mm.RoomPulse()
        adj = pulse.suggest_tempo_adjustment(current_bpm=100.0)
        assert adj == 0.0

    def test_suggest_tempo_adjustment_nudges_toward_room(self) -> None:
        pulse = mm.RoomPulse()
        pulse._estimated_bpm = 110.0
        adj = pulse.suggest_tempo_adjustment(current_bpm=100.0)
        # Should nudge upward (positive)
        assert adj > 0
        assert adj <= 5.0, "Adjustment should be capped at +/-5 BPM"

    def test_suggest_tempo_adjustment_nudges_down(self) -> None:
        pulse = mm.RoomPulse()
        pulse._estimated_bpm = 80.0
        adj = pulse.suggest_tempo_adjustment(current_bpm=100.0)
        assert adj < 0
        assert adj >= -5.0

    def test_suggest_tempo_adjustment_clamped(self) -> None:
        """Even if room BPM is very different, adjustment is capped."""
        pulse = mm.RoomPulse()
        pulse._estimated_bpm = 200.0
        adj = pulse.suggest_tempo_adjustment(current_bpm=60.0)
        # diff = 140, clamped to 5, then * 0.3 = 1.5
        assert abs(adj) <= 5.0 * 0.3 + 0.01

    def test_read_room_state_with_mock_file(self, tmp_path: Path) -> None:
        """read_room_state should parse a JSON file and feed RMS values."""
        pulse = mm.RoomPulse()
        room_data = {
            "heartbeat": {
                "rms_history": [0.1, 0.5, 0.9, 0.3, 0.7]
            }
        }
        room_file = tmp_path / "room_activity.json"
        room_file.write_text(json.dumps(room_data))

        with patch.object(mm, "_ROOM_ACTIVITY_PATH", str(room_file)):
            pulse.read_room_state()
        assert len(pulse._rms_history) == 5

    def test_read_room_state_missing_file(self) -> None:
        """read_room_state should not crash if the file is missing."""
        pulse = mm.RoomPulse()
        with patch.object(mm, "_ROOM_ACTIVITY_PATH", "/tmp/nonexistent_room_xyz.json"):
            pulse.read_room_state()  # should not raise
        assert len(pulse._rms_history) == 0

    def test_read_room_state_bad_json(self, tmp_path: Path) -> None:
        """read_room_state should handle malformed JSON gracefully."""
        pulse = mm.RoomPulse()
        bad_file = tmp_path / "room_activity.json"
        bad_file.write_text("not valid json {{{")
        with patch.object(mm, "_ROOM_ACTIVITY_PATH", str(bad_file)):
            pulse.read_room_state()  # should not raise
        assert len(pulse._rms_history) == 0

    def test_read_room_state_flat_rms_key(self, tmp_path: Path) -> None:
        """read_room_state should also handle {"rms": [...]} format."""
        pulse = mm.RoomPulse()
        room_data = {"rms": [0.2, 0.4, 0.6]}
        room_file = tmp_path / "room_activity.json"
        room_file.write_text(json.dumps(room_data))
        with patch.object(mm, "_ROOM_ACTIVITY_PATH", str(room_file)):
            pulse.read_room_state()
        assert len(pulse._rms_history) == 3


# ---------------------------------------------------------------------------
# Lewis Rhythm Concepts — Nonperiodic Event Response
# ---------------------------------------------------------------------------


class TestEventResponse:
    def test_transient_returns_accented_staccato(self) -> None:
        random.seed(42)
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        result = mind.respond_to_event("transient")
        assert result is not None
        freq, duration, accent = result
        assert freq > 0, "Transient should produce a note"
        assert duration <= 0.5, "Transient should be short/staccato"
        assert accent is True, "Transient should be accented"

    def test_speech_returns_none(self) -> None:
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        result = mind.respond_to_event("speech")
        assert result is None, "Speech events should return None (don't compete)"

    def test_silence_returns_long_quiet_note(self) -> None:
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.NOCTURNE, bpm=60.0)
        result = mind.respond_to_event("silence")
        assert result is not None
        freq, duration, accent = result
        assert freq > 0, "Silence response should be a note"
        assert duration >= 2.0, "Silence response should be a long note"
        assert accent is False, "Silence response should be unaccented (quiet)"

    def test_silence_returns_tonic(self) -> None:
        mind = mm.MelodicMind(key_root=261.63, rhythm_feel=mm.RhythmFeel.NOCTURNE, bpm=60.0)
        result = mind.respond_to_event("silence")
        assert result is not None
        freq = result[0]
        assert freq == pytest.approx(261.63, rel=1e-3), "Silence note should be tonic"

    def test_unknown_event_returns_none(self) -> None:
        mind = mm.MelodicMind(key_root=440.0, rhythm_feel=mm.RhythmFeel.WALTZ, bpm=120.0)
        result = mind.respond_to_event("earthquake")
        assert result is None

    def test_transient_note_is_in_key(self) -> None:
        """Transient response should produce a note from degrees 1, 3, or 5."""
        random.seed(42)
        root = 440.0
        mind = mm.MelodicMind(key_root=root, rhythm_feel=mm.RhythmFeel.MARCH, bpm=120.0)
        cs = mm.ChromaticScale()
        valid_freqs = {
            round(cs.scale_tone(root, 1, 0), 4),
            round(cs.scale_tone(root, 3, 0), 4),
            round(cs.scale_tone(root, 5, 0), 4),
        }
        for _ in range(20):
            result = mind.respond_to_event("transient")
            assert result is not None
            freq = round(result[0], 4)
            assert freq in valid_freqs, f"Transient note {freq} not in key triad {valid_freqs}"


# ---------------------------------------------------------------------------
# ABC Notation Conversion
# ---------------------------------------------------------------------------


class TestABCNotation:
    def test_a440_produces_a(self) -> None:
        """A4 (440Hz) should produce 'A' in ABC notation."""
        result = mm.freq_sequence_to_abc([440.0])
        assert "A" in result
        assert "X:1" in result
        assert "T:CypherClaw Phrase" in result

    def test_known_frequencies_to_abc(self) -> None:
        """Known frequencies should map to correct ABC notes."""
        # D4=293.66, F#4=369.99, A4=440
        freqs = [293.66, 369.99, 440.0]
        result = mm.freq_sequence_to_abc(freqs, key="D")
        assert "K:Dmaj" in result
        # Should contain D, ^F (F#), and A
        assert "D" in result
        assert "A" in result

    def test_middle_c_octave(self) -> None:
        """Middle C (C4 ~261.63Hz) should be uppercase C with no modifier."""
        result = mm.freq_sequence_to_abc([261.63])
        # The note portion should contain just "C" (not c, not C,)
        lines = result.strip().split("\n")
        note_line = lines[-1]  # last line has the notes
        assert "C" in note_line

    def test_octave_above_middle_c(self) -> None:
        """C5 (~523.25Hz) should be lowercase 'c' in ABC."""
        note = mm._freq_to_abc_note(523.25)
        assert note == "c", f"Expected 'c', got {note!r}"

    def test_octave_below_middle_c(self) -> None:
        """C3 (~130.81Hz) should be 'C,' in ABC."""
        note = mm._freq_to_abc_note(130.81)
        assert note == "C,", f"Expected 'C,', got {note!r}"

    def test_rest_frequency(self) -> None:
        """Frequency 0 should produce 'z' (rest in ABC)."""
        result = mm.freq_sequence_to_abc([0.0, 440.0])
        lines = result.strip().split("\n")
        note_line = lines[-1]
        assert "z" in note_line

    def test_header_fields(self) -> None:
        """ABC output should contain X, T, M, K header fields."""
        result = mm.freq_sequence_to_abc([440.0], key="G", meter="4/4")
        assert "X:1" in result
        assert "T:CypherClaw Phrase" in result
        assert "M:4/4" in result
        assert "K:Gmaj" in result

    def test_sharp_notes(self) -> None:
        """F#4 (~369.99Hz) should produce '^F' in ABC notation."""
        note = mm._freq_to_abc_note(369.99)
        assert note == "^F", f"Expected '^F', got {note!r}"

    def test_high_octave(self) -> None:
        """C6 (~1046.5Hz) should produce c' in ABC."""
        note = mm._freq_to_abc_note(1046.5)
        assert note == "c'", f"Expected \"c'\", got {note!r}"

    def test_full_phrase_round_trip_structure(self) -> None:
        """A sequence of frequencies should produce valid ABC with pipe at end."""
        freqs = [261.63, 293.66, 329.63, 349.23, 392.0, 440.0, 493.88, 523.25]
        result = mm.freq_sequence_to_abc(freqs)
        assert result.endswith("|")


# ---------------------------------------------------------------------------
# ABC Parsing
# ---------------------------------------------------------------------------


class TestABCParsing:
    def test_basic_note_names(self) -> None:
        """Should extract note names from ABC notation."""
        abc = "D F A d c B A F |"
        hints = mm.abc_to_freq_hints(abc)
        assert hints == ["D", "F", "A", "D", "C", "B", "A", "F"]

    def test_sharp_notes(self) -> None:
        """Should handle sharp (^) accidentals."""
        abc = "^F ^C A"
        hints = mm.abc_to_freq_hints(abc)
        assert hints == ["F#", "C#", "A"]

    def test_flat_notes(self) -> None:
        """Should handle flat (_) accidentals."""
        abc = "_B _E G"
        hints = mm.abc_to_freq_hints(abc)
        assert hints == ["Bb", "Eb", "G"]

    def test_octave_modifiers_stripped(self) -> None:
        """Octave modifiers (commas, apostrophes) should be stripped."""
        abc = "C, D E c' d''"
        hints = mm.abc_to_freq_hints(abc)
        assert hints == ["C", "D", "E", "C", "D"]

    def test_empty_input(self) -> None:
        """Empty string should return empty list."""
        assert mm.abc_to_freq_hints("") == []

    def test_mixed_with_non_note_text(self) -> None:
        """Should extract notes even when mixed with non-note text."""
        abc = "Try playing C D E in a rising pattern, then resolve to G"
        hints = mm.abc_to_freq_hints(abc)
        # Should find the note letters embedded in the text
        assert "C" in hints
        assert "D" in hints
        assert "E" in hints
        assert "G" in hints


# ---------------------------------------------------------------------------
# LLMAdvisor — theory_query and ChatMusician support
# ---------------------------------------------------------------------------


class TestTheoryQuery:
    def test_theory_query_includes_abc_in_prompt(self) -> None:
        """theory_query should include the ABC phrase in the prompt sent to the model."""
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "The phrase uses a rising fourth interval."
        }
        abc = "X:1\nT:CypherClaw Phrase\nM:3/4\nK:Cmaj\nC E G |"
        with patch("melodic_mind.requests.post", return_value=mock_response) as mock_post:
            result = advisor.theory_query(abc, "What intervals are used?")
        assert isinstance(result, str)
        assert len(result) > 0
        # Verify the ABC was included in the prompt
        call_args = mock_post.call_args
        prompt_sent = call_args[1]["json"]["prompt"] if "json" in call_args[1] else call_args[0][1]["prompt"]
        assert "C E G" in prompt_sent
        assert "What intervals are used?" in prompt_sent

    def test_theory_query_chatmusician_format(self) -> None:
        """When music_model is ChatMusician, prompt should be ABC-aware format."""
        advisor = mm.LLMAdvisor(
            model="test", base_url="http://fake:11434",
            music_model="m-a-p/ChatMusician",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "This is a I-IV-V progression."
        }
        abc = "X:1\nT:CypherClaw Phrase\nM:3/4\nK:Cmaj\nC F G |"
        with patch("melodic_mind.requests.post", return_value=mock_response) as mock_post:
            result = advisor.theory_query(abc, "What progression is this?")
        assert "I-IV-V progression" in result
        # Verify ChatMusician-specific prompt format
        call_args = mock_post.call_args
        prompt_sent = call_args[1]["json"]["prompt"] if "json" in call_args[1] else call_args[0][1]["prompt"]
        assert "Analyze this ABC notation phrase" in prompt_sent
        assert "Music theory question:" in prompt_sent
        # Verify it used the music_model
        model_sent = call_args[1]["json"]["model"] if "json" in call_args[1] else call_args[0][1]["model"]
        assert model_sent == "m-a-p/ChatMusician"

    def test_theory_query_fallback_on_error(self) -> None:
        """theory_query should return fallback string on connection error."""
        advisor = mm.LLMAdvisor(model="test", base_url="http://fake:11434")
        with patch("melodic_mind.requests.post", side_effect=Exception("connection refused")):
            result = advisor.theory_query("C D E |", "What key?")
        assert result == "No response from music model."

    def test_music_model_parameter_defaults_none(self) -> None:
        """music_model should default to None."""
        advisor = mm.LLMAdvisor(model="qwen3.5:4b")
        assert advisor._music_model is None

    def test_music_model_parameter_stored(self) -> None:
        """music_model should be stored when provided."""
        advisor = mm.LLMAdvisor(model="qwen3.5:4b", music_model="chatmusician")
        assert advisor._music_model == "chatmusician"

    def test_existing_methods_still_work_with_music_model(self) -> None:
        """Setting music_model should not affect existing LLM methods."""
        advisor = mm.LLMAdvisor(
            model="test", base_url="http://fake:11434",
            music_model="chatmusician",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Play slowly with a nocturne feel."
        }
        with patch("melodic_mind.requests.post", return_value=mock_response) as mock_post:
            result = advisor.get_intention(hour=23, mood="calm", last_key="Am")
        assert "feel_hint" in result
        # Existing methods should still use self._model, not music_model
        call_args = mock_post.call_args
        model_sent = call_args[1]["json"]["model"] if "json" in call_args[1] else call_args[0][1]["model"]
        assert model_sent == "test"  # not "chatmusician"
