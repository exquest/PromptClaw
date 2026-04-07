"""Tests for Korsakov Ch.4 accompaniment patterns."""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.synthesis.accompaniment import (
    DensityTracker,
    arpeggiated,
    breathing_swell,
    broken_figure,
    get_pattern,
    ostinato_cell,
    pedal_note,
    repeated_chords,
    select_accompaniment_type,
    should_pedal,
    should_transition_gradually,
    sustained,
    tremolo,
)


class TestDensityTracker:
    def test_empty_density(self):
        dt = DensityTracker()
        assert dt.density() == 0.0

    def test_records_notes(self):
        dt = DensityTracker(window_seconds=4.0)
        for _ in range(8):
            dt.note_played()
        assert dt.density() == 2.0  # 8 notes / 4 seconds

    def test_is_resting_when_no_notes(self):
        dt = DensityTracker()
        assert dt.is_resting() is True

    def test_not_resting_after_note(self):
        dt = DensityTracker()
        dt.note_played()
        assert dt.is_resting(silence_threshold=1.0) is False

    def test_resting_after_silence(self):
        dt = DensityTracker()
        dt._timestamps = [time.time() - 5.0]  # 5 seconds ago
        assert dt.is_resting(silence_threshold=2.0) is True


class TestSelectAccompanimentType:
    def test_resting_gives_fill(self):
        result = select_accompaniment_type(0.0, is_resting=True)
        assert result in [4, 5]  # arpeggiated or broken

    def test_high_density_gives_sustained(self):
        result = select_accompaniment_type(4.0, is_resting=False)
        assert result == 1  # sustained — get out of the way

    def test_medium_density_gives_repeated(self):
        result = select_accompaniment_type(2.5, is_resting=False)
        assert result == 2

    def test_low_density_gives_moderate(self):
        result = select_accompaniment_type(0.5, is_resting=False)
        assert result in [2, 4]


class TestPatterns:
    def test_sustained_returns_one_note(self):
        notes = sustained(146.8, 220.0, 0.43, 0.5)
        assert len(notes) == 1
        freq, amp, release, wait = notes[0]
        assert freq < 146.8  # bass register
        assert release > 1.0  # long

    def test_repeated_chords_returns_three(self):
        notes = repeated_chords(146.8, 220.0, 0.43, 0.7)
        assert len(notes) == 3
        # First is loudest (downbeat)
        assert notes[0][1] > notes[1][1]
        assert notes[0][1] > notes[2][1]

    def test_tremolo_returns_many_short(self):
        notes = tremolo(146.8, 220.0, 0.43, 0.5)
        assert len(notes) >= 6
        for _, _, release, wait in notes:
            assert release < 0.3  # short
            assert wait < 0.3  # rapid

    def test_arpeggiated_returns_ascending(self):
        notes = arpeggiated(146.8, 220.0, 0.43, 0.6)
        assert len(notes) == 3
        # Frequencies should ascend
        assert notes[0][0] <= notes[1][0] <= notes[2][0]

    def test_broken_figure_returns_irregular(self):
        notes = broken_figure(146.8, 220.0, 0.43, 0.5)
        assert len(notes) == 4
        # Not strictly ascending or descending
        freqs = [n[0] for n in notes]
        assert freqs != sorted(freqs)

    def test_ostinato_returns_three_descending(self):
        notes = ostinato_cell(146.8, 220.0, 0.43, 0.4)
        assert len(notes) == 3
        # Should descend
        assert notes[0][0] >= notes[1][0] >= notes[2][0]

    def test_get_pattern_valid_type(self):
        notes = get_pattern(2, 146.8, 220.0, 0.43)
        assert len(notes) == 3  # repeated chords

    def test_get_pattern_invalid_falls_back(self):
        notes = get_pattern(99, 146.8, 220.0, 0.43)
        assert len(notes) == 3  # falls back to repeated chords


class TestPedalPoint:
    def test_pedal_note_low_freq(self):
        freq, amp, release = pedal_note(146.8, 0.43)
        assert freq < 50  # very low
        assert release > 4  # long ring

    def test_should_pedal_at_boundaries(self):
        assert should_pedal(0) is True
        assert should_pedal(4) is True
        assert should_pedal(8) is True

    def test_should_not_pedal_mid_phrase(self):
        assert should_pedal(1) is False
        assert should_pedal(2) is False
        assert should_pedal(3) is False


class TestBreathing:
    def test_swell_when_resting(self):
        result = breathing_swell(0.0, True, 2)
        assert result == 3  # swell up

    def test_thin_when_active(self):
        result = breathing_swell(3.0, False, 4)
        assert result == 3  # thin down

    def test_no_change_at_edges(self):
        assert breathing_swell(0.0, True, 5) == 5  # already at 5, cap
        assert breathing_swell(3.0, False, 1) == 1  # already at 1

    def test_moderate_stays(self):
        result = breathing_swell(1.5, False, 3)
        assert result == 3


class TestTransition:
    def test_small_change_gradual(self):
        assert should_transition_gradually(2, 4) is True
        assert should_transition_gradually(3, 1) is True

    def test_large_change_abrupt(self):
        assert should_transition_gradually(1, 6) is False
        assert should_transition_gradually(6, 1) is False

    def test_same_type_gradual(self):
        assert should_transition_gradually(3, 3) is True
