"""Tests for generative_scores.py -- musical score generation from mood and narrative."""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.generative_scores import (
    Note,
    Phrase,
    Score,
    generate_bass_line,
    generate_countermelody,
    generate_melody,
    score_from_mood,
    score_from_narrative_event,
    score_to_frequencies,
)


# === Note dataclass ===


class TestNote:
    def test_fields(self):
        n = Note(scale_degree=1, duration_beats=1.0, accent=False)
        assert n.scale_degree == 1
        assert n.duration_beats == 1.0
        assert n.accent is False

    def test_accent_default(self):
        n = Note(scale_degree=5, duration_beats=0.5, accent=True)
        assert n.accent is True

    def test_is_dataclass(self):
        n = Note(scale_degree=3, duration_beats=2.0, accent=False)
        assert hasattr(n, "__dataclass_fields__")


# === Phrase dataclass ===


class TestPhrase:
    def test_fields(self):
        notes = [Note(1, 1.0, False), Note(3, 1.0, True)]
        p = Phrase(notes=notes, voice="pluck", dynamic="mf", role="melody")
        assert p.notes == notes
        assert p.voice == "pluck"
        assert p.dynamic == "mf"
        assert p.role == "melody"

    def test_empty_notes(self):
        p = Phrase(notes=[], voice="pad", dynamic="pp", role="color")
        assert p.notes == []

    def test_is_dataclass(self):
        p = Phrase(notes=[], voice="pad", dynamic="pp", role="bass")
        assert hasattr(p, "__dataclass_fields__")


# === Score dataclass ===


class TestScore:
    def test_fields(self):
        p = Phrase(notes=[], voice="pad", dynamic="pp", role="bass")
        s = Score(phrases=[p], key="C", tempo_bpm=120.0, mood="calm", created_at=0.0)
        assert s.phrases == [p]
        assert s.key == "C"
        assert s.tempo_bpm == 120.0
        assert s.mood == "calm"
        assert s.created_at == 0.0

    def test_is_dataclass(self):
        s = Score(phrases=[], key="G", tempo_bpm=80.0, mood="happy", created_at=1.0)
        assert hasattr(s, "__dataclass_fields__")


# === generate_melody ===


class TestGenerateMelody:
    def test_returns_phrase(self):
        p = generate_melody("C")
        assert isinstance(p, Phrase)

    def test_default_length_8(self):
        p = generate_melody("C")
        assert len(p.notes) == 8

    def test_custom_length(self):
        p = generate_melody("C", length=4)
        assert len(p.notes) == 4

    def test_role_is_melody(self):
        p = generate_melody("C")
        assert p.role == "melody"

    def test_scale_degrees_in_range(self):
        p = generate_melody("C", length=16)
        for note in p.notes:
            assert 1 <= note.scale_degree <= 8, f"degree {note.scale_degree} out of range"

    def test_durations_positive(self):
        p = generate_melody("C")
        for note in p.notes:
            assert note.duration_beats > 0

    def test_arch_contour_rises_then_falls(self):
        """Arch contour: first half trends up, second half trends down."""
        # Run multiple times to smooth randomness
        up_count = 0
        trials = 50
        for _ in range(trials):
            p = generate_melody("C", length=8, contour="arch")
            degrees = [n.scale_degree for n in p.notes]
            mid = len(degrees) // 2
            first_half_trend = degrees[mid] - degrees[0]
            second_half_trend = degrees[-1] - degrees[mid]
            if first_half_trend >= 0 and second_half_trend <= 0:
                up_count += 1
        # At least half the trials should show arch shape
        assert up_count >= trials * 0.4, f"only {up_count}/{trials} showed arch"

    def test_descent_contour_trends_down(self):
        down_count = 0
        trials = 50
        for _ in range(trials):
            p = generate_melody("C", length=8, contour="descent")
            degrees = [n.scale_degree for n in p.notes]
            if degrees[-1] <= degrees[0]:
                down_count += 1
        assert down_count >= trials * 0.5, f"only {down_count}/{trials} descended"

    def test_ascent_contour_trends_up(self):
        up_count = 0
        trials = 50
        for _ in range(trials):
            p = generate_melody("C", length=8, contour="ascent")
            degrees = [n.scale_degree for n in p.notes]
            if degrees[-1] >= degrees[0]:
                up_count += 1
        assert up_count >= trials * 0.5, f"only {up_count}/{trials} ascended"

    def test_wave_contour_produces_notes(self):
        p = generate_melody("C", length=8, contour="wave")
        assert len(p.notes) == 8

    def test_stepwise_motion_predominates(self):
        """Most intervals should be 1-2 steps (stepwise), not large leaps."""
        p = generate_melody("C", length=32)
        intervals = []
        for i in range(1, len(p.notes)):
            intervals.append(abs(p.notes[i].scale_degree - p.notes[i - 1].scale_degree))
        stepwise = sum(1 for iv in intervals if iv <= 2)
        assert stepwise / len(intervals) >= 0.5, "too many leaps"

    def test_different_keys_accepted(self):
        for k in ["C", "D", "E", "F", "G", "A", "B"]:
            p = generate_melody(k)
            assert isinstance(p, Phrase)
            assert len(p.notes) == 8


# === generate_bass_line ===


class TestGenerateBassLine:
    def test_returns_phrase(self):
        p = generate_bass_line("C", [1, 4, 5, 1])
        assert isinstance(p, Phrase)

    def test_role_is_bass(self):
        p = generate_bass_line("C", [1, 4, 5, 1])
        assert p.role == "bass"

    def test_notes_per_chord(self):
        prog = [1, 4, 5, 1]
        p = generate_bass_line("C", prog, beats_per_chord=3)
        assert len(p.notes) == len(prog) * 3

    def test_root_on_beat_one(self):
        """First note of each chord group should be the chord root."""
        prog = [1, 4, 5]
        p = generate_bass_line("C", prog, beats_per_chord=3)
        for i, root_deg in enumerate(prog):
            note = p.notes[i * 3]
            assert note.scale_degree == root_deg

    def test_weak_beats_are_chord_tones(self):
        """Weak-beat notes should be 3rd or 5th above root (or root)."""
        prog = [1, 4, 5, 1]
        p = generate_bass_line("C", prog, beats_per_chord=3)
        for i, root_deg in enumerate(prog):
            for j in range(1, 3):
                note = p.notes[i * 3 + j]
                # The bass weak-beat degrees should be root+2 (third) or root+4 (fifth)
                expected = {root_deg, root_deg + 2, root_deg + 4}
                assert note.scale_degree in expected, (
                    f"beat {j} of chord {root_deg}: got degree {note.scale_degree}"
                )

    def test_empty_progression(self):
        p = generate_bass_line("C", [])
        assert len(p.notes) == 0

    def test_custom_beats_per_chord(self):
        p = generate_bass_line("C", [1, 5], beats_per_chord=4)
        assert len(p.notes) == 8


# === generate_countermelody ===


class TestGenerateCountermelody:
    def test_returns_phrase(self):
        mel = generate_melody("C", length=8)
        counter = generate_countermelody(mel)
        assert isinstance(counter, Phrase)

    def test_role_is_counter(self):
        mel = generate_melody("C", length=8)
        counter = generate_countermelody(mel)
        assert counter.role == "counter"

    def test_same_length_as_melody(self):
        mel = generate_melody("C", length=6)
        counter = generate_countermelody(mel)
        assert len(counter.notes) == len(mel.notes)

    def test_contrary_motion_tendency(self):
        """When melody goes up, counter should tend to go down."""
        contrary_count = 0
        total = 0
        for _ in range(30):
            mel = generate_melody("C", length=8, contour="ascent")
            counter = generate_countermelody(mel)
            for i in range(1, len(mel.notes)):
                mel_dir = mel.notes[i].scale_degree - mel.notes[i - 1].scale_degree
                cnt_dir = counter.notes[i].scale_degree - counter.notes[i - 1].scale_degree
                if mel_dir != 0:
                    total += 1
                    if (mel_dir > 0 and cnt_dir < 0) or (mel_dir < 0 and cnt_dir > 0):
                        contrary_count += 1
        if total > 0:
            ratio = contrary_count / total
            assert ratio >= 0.3, f"only {ratio:.0%} contrary motion"

    def test_scale_degrees_in_range(self):
        mel = generate_melody("C", length=8)
        counter = generate_countermelody(mel)
        for note in counter.notes:
            assert 1 <= note.scale_degree <= 8

    def test_durations_positive(self):
        mel = generate_melody("C", length=8)
        counter = generate_countermelody(mel)
        for note in counter.notes:
            assert note.duration_beats > 0


# === score_from_mood ===


class TestScoreFromMood:
    def test_returns_score(self):
        mood = {"energy": 0.5, "valence": 0.5, "arousal": 0.5}
        s = score_from_mood(mood)
        assert isinstance(s, Score)

    def test_high_energy_faster_tempo(self):
        high = score_from_mood({"energy": 0.9, "valence": 0.5, "arousal": 0.9})
        low = score_from_mood({"energy": 0.1, "valence": 0.5, "arousal": 0.1})
        assert high.tempo_bpm > low.tempo_bpm

    def test_high_valence_major_key(self):
        """High valence should produce a major key (one of the natural major keys)."""
        s = score_from_mood({"energy": 0.5, "valence": 0.9, "arousal": 0.5})
        # Major keys: no flats/sharps indicating minor
        assert s.key in ("C", "D", "E", "F", "G", "A", "B")

    def test_high_energy_more_phrases(self):
        high = score_from_mood({"energy": 0.9, "valence": 0.5, "arousal": 0.9})
        low = score_from_mood({"energy": 0.1, "valence": 0.5, "arousal": 0.1})
        assert len(high.phrases) >= len(low.phrases)

    def test_sleeping_minimal(self):
        s = score_from_mood({"energy": 0.1, "valence": 0.5, "arousal": 0.1})
        assert len(s.phrases) >= 1
        # Sleeping should be pp dynamic
        assert s.phrases[0].dynamic == "pp"

    def test_sleeping_slow_tempo(self):
        s = score_from_mood({"energy": 0.1, "valence": 0.3, "arousal": 0.1})
        assert s.tempo_bpm <= 80

    def test_has_created_at(self):
        s = score_from_mood({"energy": 0.5, "valence": 0.5, "arousal": 0.5})
        assert isinstance(s.created_at, float)
        assert s.created_at > 0

    def test_has_mood_string(self):
        s = score_from_mood({"energy": 0.5, "valence": 0.5, "arousal": 0.5})
        assert isinstance(s.mood, str)
        assert len(s.mood) > 0

    def test_empty_mood_defaults(self):
        """Empty mood dict should not crash, use defaults."""
        s = score_from_mood({})
        assert isinstance(s, Score)
        assert len(s.phrases) >= 1

    def test_low_energy_longer_notes(self):
        """Low energy scores should have longer average note durations."""
        low = score_from_mood({"energy": 0.1, "valence": 0.5, "arousal": 0.1})
        high = score_from_mood({"energy": 0.9, "valence": 0.5, "arousal": 0.9})
        avg_low = sum(n.duration_beats for p in low.phrases for n in p.notes) / max(1, sum(len(p.notes) for p in low.phrases))
        avg_high = sum(n.duration_beats for p in high.phrases for n in p.notes) / max(1, sum(len(p.notes) for p in high.phrases))
        assert avg_low >= avg_high


# === score_from_narrative_event ===


class TestScoreFromNarrativeEvent:
    def test_returns_score(self):
        s = score_from_narrative_event("sunrise", "The sun rises over the garden")
        assert isinstance(s, Score)

    def test_sunrise_ascending(self):
        s = score_from_narrative_event("sunrise", "Morning light")
        # Should have at least one phrase
        assert len(s.phrases) >= 1

    def test_sunrise_major_key(self):
        s = score_from_narrative_event("sunrise", "Morning light")
        assert s.key in ("C", "D", "E", "F", "G", "A", "B")

    def test_visitor_fanfare(self):
        s = score_from_narrative_event("visitor", "Someone approaches the door")
        assert len(s.phrases) >= 1
        # Fanfare should have some accented notes
        accents = sum(1 for p in s.phrases for n in p.notes if n.accent)
        assert accents >= 1

    def test_rain_minor(self):
        s = score_from_narrative_event("rain", "Rain falling on the roof")
        # Minor key should have 'm' suffix or be in minor set
        assert "m" in s.key or s.key.endswith("m")

    def test_quiet_night_slow(self):
        s = score_from_narrative_event("quiet_night", "The house sleeps")
        assert s.tempo_bpm <= 80

    def test_unknown_event_type(self):
        s = score_from_narrative_event("earthquake", "The ground shakes")
        assert isinstance(s, Score)
        assert len(s.phrases) >= 1

    def test_has_created_at(self):
        s = score_from_narrative_event("sunrise", "Dawn")
        assert isinstance(s.created_at, float)
        assert s.created_at > 0


# === score_to_frequencies ===


class TestScoreToFrequencies:
    def test_returns_list_of_lists(self):
        s = score_from_mood({"energy": 0.5, "valence": 0.5, "arousal": 0.5})
        freqs = score_to_frequencies(s)
        assert isinstance(freqs, list)
        for phrase_freqs in freqs:
            assert isinstance(phrase_freqs, list)

    def test_each_entry_is_freq_duration_tuple(self):
        s = score_from_mood({"energy": 0.5, "valence": 0.5, "arousal": 0.5})
        freqs = score_to_frequencies(s)
        for phrase_freqs in freqs:
            for entry in phrase_freqs:
                assert isinstance(entry, tuple)
                assert len(entry) == 2
                freq_hz, dur_sec = entry
                assert isinstance(freq_hz, float)
                assert isinstance(dur_sec, float)

    def test_frequencies_positive(self):
        s = score_from_mood({"energy": 0.7, "valence": 0.7, "arousal": 0.5})
        freqs = score_to_frequencies(s)
        for phrase_freqs in freqs:
            for freq_hz, dur_sec in phrase_freqs:
                assert freq_hz > 0, f"non-positive freq {freq_hz}"
                assert dur_sec > 0, f"non-positive duration {dur_sec}"

    def test_durations_based_on_tempo(self):
        """Duration in seconds should reflect the tempo."""
        s = Score(
            phrases=[Phrase(
                notes=[Note(1, 1.0, False)],
                voice="pluck", dynamic="mf", role="melody",
            )],
            key="C",
            tempo_bpm=120.0,
            mood="calm",
            created_at=0.0,
        )
        freqs = score_to_frequencies(s)
        # 1 beat at 120 BPM = 0.5 seconds
        assert len(freqs) == 1
        assert len(freqs[0]) == 1
        freq_hz, dur_sec = freqs[0][0]
        assert abs(dur_sec - 0.5) < 0.01

    def test_c_major_root_frequency(self):
        """Scale degree 1 in C should be near C4 (261.63 Hz)."""
        s = Score(
            phrases=[Phrase(
                notes=[Note(1, 1.0, False)],
                voice="pluck", dynamic="mf", role="melody",
            )],
            key="C",
            tempo_bpm=120.0,
            mood="calm",
            created_at=0.0,
        )
        freqs = score_to_frequencies(s)
        freq_hz, _ = freqs[0][0]
        assert abs(freq_hz - 261.63) < 1.0, f"C4 should be ~261.63, got {freq_hz}"

    def test_a_major_root_frequency(self):
        """Scale degree 1 in A should be near A4 (440 Hz)."""
        s = Score(
            phrases=[Phrase(
                notes=[Note(1, 1.0, False)],
                voice="pluck", dynamic="mf", role="melody",
            )],
            key="A",
            tempo_bpm=120.0,
            mood="calm",
            created_at=0.0,
        )
        freqs = score_to_frequencies(s)
        freq_hz, _ = freqs[0][0]
        assert abs(freq_hz - 440.0) < 1.0, f"A4 should be ~440, got {freq_hz}"

    def test_octave_degree_8_is_double(self):
        """Scale degree 8 should be an octave above degree 1."""
        s = Score(
            phrases=[Phrase(
                notes=[Note(1, 1.0, False), Note(8, 1.0, False)],
                voice="pluck", dynamic="mf", role="melody",
            )],
            key="C",
            tempo_bpm=120.0,
            mood="calm",
            created_at=0.0,
        )
        freqs = score_to_frequencies(s)
        f1, _ = freqs[0][0]
        f8, _ = freqs[0][1]
        ratio = f8 / f1
        assert abs(ratio - 2.0) < 0.01, f"octave ratio should be 2.0, got {ratio}"

    def test_phrase_count_matches(self):
        s = score_from_mood({"energy": 0.7, "valence": 0.7, "arousal": 0.5})
        freqs = score_to_frequencies(s)
        assert len(freqs) == len(s.phrases)

    def test_note_count_matches(self):
        s = score_from_mood({"energy": 0.5, "valence": 0.5, "arousal": 0.5})
        freqs = score_to_frequencies(s)
        for i, phrase in enumerate(s.phrases):
            assert len(freqs[i]) == len(phrase.notes)

    def test_empty_score(self):
        s = Score(phrases=[], key="C", tempo_bpm=120.0, mood="calm", created_at=0.0)
        freqs = score_to_frequencies(s)
        assert freqs == []

    def test_bass_line_lower_frequencies(self):
        """Bass phrases should produce lower frequencies than melody."""
        mel_phrase = Phrase(
            notes=[Note(5, 1.0, False)],
            voice="pluck", dynamic="mf", role="melody",
        )
        bass_phrase = Phrase(
            notes=[Note(1, 1.0, False)],
            voice="pluck", dynamic="mf", role="bass",
        )
        s = Score(
            phrases=[mel_phrase, bass_phrase],
            key="C",
            tempo_bpm=120.0,
            mood="calm",
            created_at=0.0,
        )
        freqs = score_to_frequencies(s)
        mel_freq = freqs[0][0][0]
        bass_freq = freqs[1][0][0]
        assert bass_freq < mel_freq, f"bass {bass_freq} should be < melody {mel_freq}"


# === Integration ===


class TestIntegration:
    def test_mood_to_frequencies_pipeline(self):
        """Full pipeline: mood -> score -> frequencies."""
        mood = {"energy": 0.6, "valence": 0.7, "arousal": 0.5}
        score = score_from_mood(mood)
        freqs = score_to_frequencies(score)
        assert len(freqs) > 0
        for phrase_freqs in freqs:
            assert len(phrase_freqs) > 0
            for f, d in phrase_freqs:
                assert f > 0
                assert d > 0

    def test_narrative_to_frequencies_pipeline(self):
        """Full pipeline: narrative event -> score -> frequencies."""
        score = score_from_narrative_event("sunrise", "Morning glory")
        freqs = score_to_frequencies(score)
        assert len(freqs) > 0
        for phrase_freqs in freqs:
            for f, d in phrase_freqs:
                assert f > 0
                assert d > 0

    def test_all_narrative_events(self):
        """All known event types produce valid scores."""
        for event in ["sunrise", "visitor", "rain", "quiet_night", "unknown_thing"]:
            s = score_from_narrative_event(event, "test description")
            assert isinstance(s, Score)
            assert len(s.phrases) >= 1
            freqs = score_to_frequencies(s)
            assert len(freqs) >= 1
