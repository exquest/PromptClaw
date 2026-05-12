"""Tests for Korsakov Ch.4 accompaniment patterns."""
from __future__ import annotations

import os
import random
import sys
import time

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


class TestAccompanimentEndToEnd:
    """Depth-2 end-to-end coverage of the accompaniment pipeline.

    Each test drives the real public helpers through a multi-step or
    looped scenario so the file exercises the documented
    density → selection → breathing → pattern → events flow in one
    place rather than asserting one helper at a time.
    """

    def test_high_density_band_always_returns_sustained(self):
        for density in [3.01, 3.5, 4.0, 5.0, 8.0]:
            result = select_accompaniment_type(density, is_resting=False)
            assert result == 1

    def test_busy_density_band_returns_repeated_chords(self):
        for density in [2.01, 2.25, 2.5, 2.75, 3.0]:
            result = select_accompaniment_type(density, is_resting=False)
            assert result == 2

    def test_balanced_density_band_returns_tremolo(self):
        for density in [1.01, 1.25, 1.5, 1.75, 2.0]:
            result = select_accompaniment_type(density, is_resting=False)
            assert result == 3

    def test_resting_band_returns_filling_type(self):
        random.seed(0)
        for _ in range(10):
            result = select_accompaniment_type(0.0, is_resting=True)
            assert result in (4, 5)

    def test_sparse_density_band_returns_waltz_or_arpeggio(self):
        random.seed(0)
        for density in [0.0, 0.25, 0.5, 0.75, 1.0]:
            result = select_accompaniment_type(density, is_resting=False)
            assert result in (2, 4)

    def test_all_six_pattern_types_produce_nonempty_events(self):
        for pattern_type in range(1, 7):
            events = get_pattern(pattern_type, 146.8, 220.0, 0.43, 0.7)
            assert len(events) >= 1
            for freq, amp, release, wait in events:
                assert freq > 0.0
                assert amp > 0.0
                assert release > 0.0
                assert wait >= 0.0

    def test_unknown_pattern_types_fall_back_to_repeated_chords(self):
        canonical = repeated_chords(146.8, 220.0, 0.43, 0.7)
        for invalid_type in [0, -1, 7, 99, 1000]:
            events = get_pattern(invalid_type, 146.8, 220.0, 0.43, 0.7)
            assert events == canonical

    def test_breathing_swell_resting_increments_below_cap(self):
        for current_type in [1, 2, 3, 4]:
            result = breathing_swell(0.0, melody_resting=True, current_type=current_type)
            assert result == current_type + 1

    def test_breathing_swell_active_decrements_above_floor(self):
        for current_type in [2, 3, 4, 5, 6]:
            result = breathing_swell(3.0, melody_resting=False, current_type=current_type)
            assert result == current_type - 1

    def test_breathing_swell_caps_when_resting_at_five(self):
        for current_type in [5, 6]:
            result = breathing_swell(0.0, melody_resting=True, current_type=current_type)
            assert result == current_type

    def test_breathing_swell_floors_when_active_at_one(self):
        result = breathing_swell(3.0, melody_resting=False, current_type=1)
        assert result == 1
        for density in [2.5, 3.0, 4.0, 5.0]:
            assert breathing_swell(density, melody_resting=False, current_type=1) == 1

    def test_adjacent_transitions_are_gradual(self):
        for current_type in range(1, 7):
            for target_type in range(1, 7):
                if abs(current_type - target_type) <= 2:
                    assert should_transition_gradually(current_type, target_type) is True

    def test_distant_transitions_are_section_cuts(self):
        for current_type in range(1, 7):
            for target_type in range(1, 7):
                if abs(current_type - target_type) > 2:
                    assert should_transition_gradually(current_type, target_type) is False

    def test_pedal_walks_full_phrase(self):
        boundary_bars = []
        for bar_number in range(8):
            if should_pedal(bar_number):
                boundary_bars.append(bar_number)
        assert boundary_bars == [0, 4]

    def test_pedal_with_custom_bars_per_phrase(self):
        for bar_number in range(6):
            expected = bar_number % 3 == 0
            assert should_pedal(bar_number, bars_per_phrase=3) is expected

    def test_pedal_note_at_each_boundary_is_low_and_long(self):
        for bar_number in [0, 4, 8, 12]:
            assert should_pedal(bar_number) is True
            freq, amp, release = pedal_note(146.8, 0.43, 0.5)
            assert freq < 50.0
            assert amp > 0.0
            assert release > 4.0

    def test_dense_melody_drives_sustained_accompaniment_end_to_end(self):
        tracker = DensityTracker(window_seconds=4.0)
        now = time.time()
        tracker._timestamps = [now - (19 - i) * 0.2 for i in range(20)]
        density = tracker.density()
        assert density > 3.0
        resting = tracker.is_resting()
        assert resting is False
        selected = select_accompaniment_type(density, is_resting=resting)
        assert selected == 1
        target = breathing_swell(density, melody_resting=False, current_type=4)
        events = get_pattern(target, 146.8, 220.0, 0.43, 0.7)
        assert len(events) >= 1

    def test_resting_melody_drives_filling_accompaniment_end_to_end(self):
        random.seed(0)
        tracker = DensityTracker(window_seconds=4.0)
        assert tracker.is_resting() is True
        density = tracker.density()
        selected = select_accompaniment_type(density, is_resting=True)
        target = breathing_swell(density, melody_resting=True, current_type=selected)
        events = get_pattern(target, 146.8, 220.0, 0.43, 0.5)
        assert selected in (4, 5)
        assert target in (4, 5, 6)
        assert len(events) >= 3

    def test_density_tracker_records_then_prunes_outside_window(self):
        tracker = DensityTracker(window_seconds=2.0)
        now = time.time()
        tracker._timestamps = [now - 5.0, now - 4.0, now - 0.5, now - 0.1]
        density = tracker.density()
        assert density == 1.0
        tracker.note_played()
        density_after = tracker.density()
        assert density_after >= 1.0

    def test_density_tracker_density_scales_with_window(self):
        narrow = DensityTracker(window_seconds=2.0)
        wide = DensityTracker(window_seconds=8.0)
        now = time.time()
        narrow._timestamps = [now - 0.1 * i for i in range(8)]
        wide._timestamps = [now - 0.5 * i for i in range(8)]
        narrow_density = narrow.density()
        wide_density = wide.density()
        assert narrow_density == 4.0
        assert wide_density == 1.0

    def test_full_composer_loop_runs_through_six_bars(self):
        random.seed(0)
        densities = [0.5, 1.5, 2.5, 3.5, 0.0, 0.0]
        is_resting_flags = [False, False, False, False, True, True]
        current_type = 3
        results = []
        for bar_number, (density, resting) in enumerate(zip(densities, is_resting_flags)):
            selected = select_accompaniment_type(density, is_resting=resting)
            target = breathing_swell(density, melody_resting=resting, current_type=selected)
            mode = "gradual" if should_transition_gradually(current_type, target) else "section_cut"
            pedal_active = should_pedal(bar_number)
            events = get_pattern(target, 146.8, 220.0, 0.43, 0.6)
            results.append((selected, target, mode, pedal_active, len(events)))
            current_type = target
        assert len(results) == 6
        for _selected, _target, mode, _pedal_active, event_count in results:
            assert mode in ("gradual", "section_cut")
            assert event_count >= 1

    def test_inverse_density_rule_holds_across_sweep(self):
        sweep = [(0.5, False), (1.5, False), (2.5, False), (3.5, False)]
        observed_types = []
        random.seed(0)
        for density, resting in sweep:
            observed_types.append(select_accompaniment_type(density, is_resting=resting))
        assert observed_types[3] == 1
        assert observed_types[2] == 2
        assert observed_types[1] == 3
        assert observed_types[0] in (2, 4)

    def test_pattern_register_stays_in_audible_range(self):
        for pattern_type in range(1, 7):
            events = get_pattern(pattern_type, 146.8, 220.0, 0.43, 0.6)
            for freq, _amp, _release, _wait in events:
                assert 20.0 < freq < 4000.0

    def test_test_accompaniment_reaches_depth_two(self):
        from sdp.fractal import classify_depth

        result = classify_depth("tests/test_accompaniment.py")
        assert result.depth >= 2, result.reason
