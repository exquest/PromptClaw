"""Tests for music_theory.py -- pitch, interval, scale, and microtonal helpers."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

import pytest

from senseweave.music_theory import (
    A4_HZ,
    AEOLIAN,
    BHAIRAV,
    BLUES,
    CHROMATIC,
    DORIAN,
    HARMONIC_MINOR,
    HIRAJOSHI,
    HUNGARIAN_MINOR,
    IN_SEN,
    INTERVAL_BY_SEMITONES,
    INTERVAL_BY_SHORT_NAME,
    INTERVALS,
    IONIAN,
    JUST_RATIOS,
    LOCRIAN,
    LYDIAN,
    MAJOR,
    MAJOR_PENTATONIC,
    MELODIC_MINOR,
    MINOR,
    MINOR_PENTATONIC,
    MIXOLYDIAN,
    OCTATONIC_HW,
    OCTATONIC_WH,
    PELOG,
    PHRYGIAN,
    PROMETHEUS,
    SCALES,
    WHOLE_TONE,
    VoicingConfig,
    chord_by_name,
    chord_from_symbol,
    chord_pitch_classes,
    choose_voicing,
    cents_to_ratio,
    freq_to_midi,
    generate_voicings,
    interval_between,
    just_interval_freq,
    midi_to_freq,
    midi_to_note_name,
    note_name_to_midi,
    note_name_to_pitch_class,
    pitch_class_set,
    ratio_to_cents,
    scale_by_name,
)


# === MIDI / frequency conversion ===


class TestMidiFreqConversion:
    def test_a4_is_440(self) -> None:
        assert midi_to_freq(69) == A4_HZ

    def test_c4_frequency(self) -> None:
        freq = midi_to_freq(60)
        assert abs(freq - 261.63) < 0.01

    def test_octave_doubles_frequency(self) -> None:
        f_low = midi_to_freq(60)
        f_high = midi_to_freq(72)
        assert abs(f_high / f_low - 2.0) < 1e-10

    def test_freq_to_midi_roundtrip(self) -> None:
        for midi in range(21, 109):
            freq = midi_to_freq(midi)
            assert abs(freq_to_midi(freq) - midi) < 1e-10

    def test_custom_a4_reference(self) -> None:
        freq = midi_to_freq(69, a4=432.0)
        assert abs(freq - 432.0) < 1e-10

    def test_freq_to_midi_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            freq_to_midi(0.0)
        with pytest.raises(ValueError, match="positive"):
            freq_to_midi(-100.0)


# === Note name helpers ===


class TestNoteNameHelpers:
    def test_note_name_to_pitch_class(self) -> None:
        assert note_name_to_pitch_class("C") == 0
        assert note_name_to_pitch_class("A") == 9
        assert note_name_to_pitch_class("B") == 11

    def test_enharmonic_equivalents(self) -> None:
        assert note_name_to_pitch_class("Db") == note_name_to_pitch_class("C#")
        assert note_name_to_pitch_class("Eb") == note_name_to_pitch_class("D#")
        assert note_name_to_pitch_class("Gb") == note_name_to_pitch_class("F#")
        assert note_name_to_pitch_class("Ab") == note_name_to_pitch_class("G#")
        assert note_name_to_pitch_class("Bb") == note_name_to_pitch_class("A#")

    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            note_name_to_pitch_class("H")

    def test_note_name_to_midi_c4_is_60(self) -> None:
        assert note_name_to_midi("C", 4) == 60

    def test_note_name_to_midi_a4_is_69(self) -> None:
        assert note_name_to_midi("A", 4) == 69

    def test_midi_to_note_name_roundtrip(self) -> None:
        for midi in range(0, 128):
            name, octave = midi_to_note_name(midi)
            assert note_name_to_midi(name, octave) == midi


# === Intervals ===


class TestIntervals:
    def test_all_chromatic_intervals_present(self) -> None:
        for semi in range(13):
            assert semi in INTERVAL_BY_SEMITONES

    def test_interval_consonance_categories(self) -> None:
        perfect = {iv.semitones for iv in INTERVALS if iv.consonance == "perfect"}
        assert perfect == {0, 5, 7, 12}

        imperfect = {iv.semitones for iv in INTERVALS if iv.consonance == "imperfect"}
        assert imperfect == {3, 4, 8, 9}

        mild = {iv.semitones for iv in INTERVALS if iv.consonance == "mild_dissonance"}
        assert mild == {2, 10}

        sharp = {iv.semitones for iv in INTERVALS if iv.consonance == "sharp_dissonance"}
        assert sharp == {1, 6, 11}

    def test_interval_short_name_lookup(self) -> None:
        assert INTERVAL_BY_SHORT_NAME["P1"].semitones == 0
        assert INTERVAL_BY_SHORT_NAME["P5"].semitones == 7
        assert INTERVAL_BY_SHORT_NAME["TT"].semitones == 6
        assert INTERVAL_BY_SHORT_NAME["P8"].semitones == 12

    def test_interval_between_computes_mod12(self) -> None:
        iv = interval_between(60, 67)
        assert iv.semitones == 7
        assert iv.short_name == "P5"

    def test_interval_between_direction_independent(self) -> None:
        assert interval_between(60, 64) == interval_between(64, 60)

    def test_every_interval_has_arc_phase(self) -> None:
        valid_phases = {
            "Emergence", "Theme", "Development", "Bridge",
            "Recap", "Release", "Resolution", "Afterglow",
        }
        for iv in INTERVALS:
            assert iv.arc_phase in valid_phases, f"{iv.name} has invalid phase {iv.arc_phase}"

    def test_every_interval_has_character(self) -> None:
        for iv in INTERVALS:
            assert len(iv.character) > 0


# === Scale pitch-class sets ===


class TestScalePitchClasses:
    def test_chromatic_has_12_pcs(self) -> None:
        assert CHROMATIC.pitch_classes == frozenset(range(12))

    def test_major_scale_pcs(self) -> None:
        assert IONIAN.pitch_classes == frozenset({0, 2, 4, 5, 7, 9, 11})

    def test_minor_scale_pcs(self) -> None:
        assert AEOLIAN.pitch_classes == frozenset({0, 2, 3, 5, 7, 8, 10})

    def test_major_is_ionian(self) -> None:
        assert MAJOR is IONIAN

    def test_minor_is_aeolian(self) -> None:
        assert MINOR is AEOLIAN

    def test_seven_diatonic_modes_are_seven_notes(self) -> None:
        for mode in (IONIAN, DORIAN, PHRYGIAN, LYDIAN, MIXOLYDIAN, AEOLIAN, LOCRIAN):
            assert mode.degree_count == 7, f"{mode.name} has {mode.degree_count} notes"

    def test_dorian_pcs(self) -> None:
        assert DORIAN.pitch_classes == frozenset({0, 2, 3, 5, 7, 9, 10})

    def test_phrygian_pcs(self) -> None:
        assert PHRYGIAN.pitch_classes == frozenset({0, 1, 3, 5, 7, 8, 10})

    def test_lydian_pcs(self) -> None:
        assert LYDIAN.pitch_classes == frozenset({0, 2, 4, 6, 7, 9, 11})

    def test_mixolydian_pcs(self) -> None:
        assert MIXOLYDIAN.pitch_classes == frozenset({0, 2, 4, 5, 7, 9, 10})

    def test_locrian_pcs(self) -> None:
        assert LOCRIAN.pitch_classes == frozenset({0, 1, 3, 5, 6, 8, 10})

    def test_harmonic_minor_pcs(self) -> None:
        assert HARMONIC_MINOR.pitch_classes == frozenset({0, 2, 3, 5, 7, 8, 11})

    def test_melodic_minor_pcs(self) -> None:
        assert MELODIC_MINOR.pitch_classes == frozenset({0, 2, 3, 5, 7, 9, 11})

    def test_pentatonic_scales_have_5_notes(self) -> None:
        assert MAJOR_PENTATONIC.degree_count == 5
        assert MINOR_PENTATONIC.degree_count == 5

    def test_major_pentatonic_pcs(self) -> None:
        assert MAJOR_PENTATONIC.pitch_classes == frozenset({0, 2, 4, 7, 9})

    def test_minor_pentatonic_pcs(self) -> None:
        assert MINOR_PENTATONIC.pitch_classes == frozenset({0, 3, 5, 7, 10})

    def test_whole_tone_pcs(self) -> None:
        assert WHOLE_TONE.pitch_classes == frozenset({0, 2, 4, 6, 8, 10})
        assert WHOLE_TONE.degree_count == 6

    def test_octatonic_hw_pcs(self) -> None:
        assert OCTATONIC_HW.pitch_classes == frozenset({0, 1, 3, 4, 6, 7, 9, 10})
        assert OCTATONIC_HW.degree_count == 8

    def test_octatonic_wh_pcs(self) -> None:
        assert OCTATONIC_WH.pitch_classes == frozenset({0, 2, 3, 5, 6, 8, 9, 11})
        assert OCTATONIC_WH.degree_count == 8

    def test_blues_pcs(self) -> None:
        assert BLUES.pitch_classes == frozenset({0, 3, 5, 6, 7, 10})
        assert BLUES.degree_count == 6

    def test_hirajoshi_pcs(self) -> None:
        assert HIRAJOSHI.pitch_classes == frozenset({0, 2, 3, 7, 8})
        assert HIRAJOSHI.degree_count == 5

    def test_in_sen_pcs(self) -> None:
        assert IN_SEN.pitch_classes == frozenset({0, 1, 5, 7, 10})
        assert IN_SEN.degree_count == 5

    def test_pelog_pcs(self) -> None:
        assert PELOG.pitch_classes == frozenset({0, 1, 3, 7, 8})
        assert PELOG.degree_count == 5

    def test_bhairav_pcs(self) -> None:
        assert BHAIRAV.pitch_classes == frozenset({0, 1, 4, 5, 7, 8, 11})
        assert BHAIRAV.degree_count == 7

    def test_hungarian_minor_pcs(self) -> None:
        assert HUNGARIAN_MINOR.pitch_classes == frozenset({0, 2, 3, 6, 7, 8, 11})
        assert HUNGARIAN_MINOR.degree_count == 7

    def test_prometheus_pcs(self) -> None:
        assert PROMETHEUS.pitch_classes == frozenset({0, 2, 4, 6, 9, 10})
        assert PROMETHEUS.degree_count == 6


# === Scale operations ===


class TestScaleOperations:
    def test_transpose_c_major_to_g(self) -> None:
        g_major_pcs = IONIAN.transpose(7)
        assert g_major_pcs == frozenset({7, 9, 11, 0, 2, 4, 6})

    def test_transpose_wraps_mod12(self) -> None:
        pcs = AEOLIAN.transpose(9)
        assert all(0 <= pc < 12 for pc in pcs)

    def test_to_midi_notes_single_octave(self) -> None:
        notes = IONIAN.to_midi_notes(60)
        assert notes == [60, 62, 64, 65, 67, 69, 71]

    def test_to_midi_notes_two_octaves(self) -> None:
        notes = MAJOR_PENTATONIC.to_midi_notes(60, octaves=2)
        assert len(notes) == 10
        assert notes[5] == notes[0] + 12

    def test_to_frequencies_a_major_root(self) -> None:
        freqs = IONIAN.to_frequencies(69)
        assert abs(freqs[0] - 440.0) < 0.01

    def test_scale_intervals_returns_interval_objects(self) -> None:
        ivs = IONIAN.intervals()
        assert len(ivs) == 7
        assert ivs[0].semitones == 0
        assert ivs[4].semitones == 7

    def test_scale_by_name_lookup(self) -> None:
        assert scale_by_name("ionian") is IONIAN
        assert scale_by_name("blues") is BLUES
        assert scale_by_name("hungarian_minor") is HUNGARIAN_MINOR

    def test_scale_by_name_normalizes(self) -> None:
        assert scale_by_name("Hungarian Minor") is HUNGARIAN_MINOR
        assert scale_by_name("In-Sen") is IN_SEN

    def test_scale_by_name_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            scale_by_name("superlocrian")

    def test_all_scales_registered(self) -> None:
        assert len(SCALES) >= 24


# === MIDI / frequency via scales ===


class TestScaleMidiFreq:
    def test_c_major_scale_frequencies(self) -> None:
        freqs = IONIAN.to_frequencies(60)
        expected_approx = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88]
        for actual, expected in zip(freqs, expected_approx):
            assert abs(actual - expected) < 0.5, f"expected ~{expected}, got {actual}"

    def test_chromatic_scale_12_semitones(self) -> None:
        notes = CHROMATIC.to_midi_notes(60)
        assert notes == list(range(60, 72))

    def test_pentatonic_midi_gaps(self) -> None:
        notes = MAJOR_PENTATONIC.to_midi_notes(60)
        gaps = [notes[i + 1] - notes[i] for i in range(len(notes) - 1)]
        assert gaps == [2, 2, 3, 2]

    def test_blues_scale_midi(self) -> None:
        notes = BLUES.to_midi_notes(60)
        assert notes == [60, 63, 65, 66, 67, 70]


# === Microtonal / ratio helpers ===


class TestMicrotonalHelpers:
    def test_octave_is_1200_cents(self) -> None:
        assert abs(ratio_to_cents(2.0) - 1200.0) < 1e-10

    def test_perfect_fifth_just_cents(self) -> None:
        cents = ratio_to_cents(3 / 2)
        assert abs(cents - 701.955) < 0.01

    def test_cents_to_ratio_roundtrip(self) -> None:
        for cents in [0, 100, 386.31, 700, 1200]:
            ratio = cents_to_ratio(cents)
            assert abs(ratio_to_cents(ratio) - cents) < 1e-10

    def test_ratio_to_cents_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ratio_to_cents(0.0)
        with pytest.raises(ValueError, match="positive"):
            ratio_to_cents(-1.0)

    def test_just_interval_freq_perfect_fifth(self) -> None:
        freq = just_interval_freq(440.0, 3, 2)
        assert abs(freq - 660.0) < 1e-10

    def test_just_interval_freq_major_third(self) -> None:
        freq = just_interval_freq(440.0, 5, 4)
        assert abs(freq - 550.0) < 1e-10

    def test_just_interval_freq_zero_denom_raises(self) -> None:
        with pytest.raises(ValueError, match="non-zero"):
            just_interval_freq(440.0, 3, 0)

    def test_just_ratios_table_complete(self) -> None:
        assert len(JUST_RATIOS) == 13
        assert JUST_RATIOS["unison"] == (1, 1)
        assert JUST_RATIOS["octave"] == (2, 1)
        assert JUST_RATIOS["perfect_fifth"] == (3, 2)

    def test_equal_temperament_vs_just_fifth_comma(self) -> None:
        et_fifth_cents = 700.0
        just_fifth_cents = ratio_to_cents(3 / 2)
        assert abs(just_fifth_cents - et_fifth_cents) < 2.0

    def test_unison_is_zero_cents(self) -> None:
        assert abs(ratio_to_cents(1.0)) < 1e-10

    def test_cents_to_ratio_unison(self) -> None:
        assert abs(cents_to_ratio(0.0) - 1.0) < 1e-10


# === pitch_class_set utility ===


class TestPitchClassSet:
    def test_c_major_triad_midi(self) -> None:
        assert pitch_class_set([60, 64, 67]) == frozenset({0, 4, 7})

    def test_octave_equivalence(self) -> None:
        assert pitch_class_set([60, 72, 84]) == frozenset({0})

    def test_across_octaves(self) -> None:
        assert pitch_class_set([48, 64, 79]) == frozenset({0, 4, 7})


# === Chords and voicings ===


class TestChordConstruction:
    def test_triads_and_sevenths(self) -> None:
        assert chord_pitch_classes("C", "major") == frozenset({0, 4, 7})
        assert chord_pitch_classes("A", "minor") == frozenset({9, 0, 4})
        assert chord_by_name("B", "diminished").pitch_classes == frozenset({11, 2, 5})
        assert chord_from_symbol("Cmaj7").pitch_classes == frozenset({0, 4, 7, 11})

    def test_extended_altered_suspended_and_add_chords(self) -> None:
        assert chord_from_symbol("G13").pitch_classes == frozenset({7, 11, 2, 5, 9, 0, 4})
        assert chord_from_symbol("C7b9").pitch_classes == frozenset({0, 4, 7, 10, 1})
        assert chord_from_symbol("C7alt").pitch_classes == frozenset({0, 1, 3, 4, 6, 8, 10})
        assert chord_from_symbol("Dsus4").pitch_classes == frozenset({2, 7, 9})
        assert chord_from_symbol("Cadd9").pitch_classes == frozenset({0, 2, 4, 7})


class TestChordVoicings:
    def test_drop_voicings_are_unique_and_in_range(self) -> None:
        config = VoicingConfig(low=48, high=72, max_spacing=19)
        voicings = generate_voicings(chord_from_symbol("Cmaj7"), style="drop2", config=config)
        drop3_voicings = generate_voicings(chord_from_symbol("Cmaj7"), style="drop3", config=config)

        assert (55, 60, 64, 71) in voicings
        assert (52, 60, 67, 71) in drop3_voicings
        assert len(voicings) == len(set(voicings))
        assert all(config.low <= note <= config.high for voicing in voicings for note in voicing)

    def test_open_voicings_respect_spacing(self) -> None:
        config = VoicingConfig(low=48, high=76, min_spacing=3, max_spacing=12)
        voicings = generate_voicings(chord_from_symbol("C"), style="open", config=config)

        assert voicings
        for voicing in voicings:
            gaps = [higher - lower for lower, higher in zip(voicing, voicing[1:])]
            assert all(config.min_spacing <= gap <= config.max_spacing for gap in gaps)

    def test_rootless_and_guide_tone_voicings(self) -> None:
        config = VoicingConfig(low=48, high=84)

        rootless = choose_voicing(chord_from_symbol("C13"), style="rootless", config=config)
        assert pitch_class_set(rootless) == frozenset({2, 4, 9, 10})

        guide_tones = choose_voicing(chord_from_symbol("C7"), style="guide_tone", config=config)
        assert pitch_class_set(guide_tones) == frozenset({4, 10})

    def test_close_voicings_respect_register_and_configured_spacing(self) -> None:
        config = VoicingConfig(low=60, high=72, min_spacing=3, max_spacing=4)
        voicings = generate_voicings(chord_from_symbol("Cmaj7"), style="close", config=config)

        assert voicings == [(60, 64, 67, 71)]

    def test_smooth_voice_leading_prefers_small_motion(self) -> None:
        previous = (60, 64, 67, 71)
        config = VoicingConfig(low=48, high=84)

        voicing = choose_voicing(chord_from_symbol("G7"), previous=previous, config=config)

        assert voicing == (62, 65, 67, 71)

# === Post-tonal and Spectral (T-021) ===

class TestPostTonalAndSpectral:
    def test_pitch_class_set_from_prime_form(self) -> None:
        from senseweave.music_theory import PitchClassSet
        pcs = PitchClassSet.from_prime_form([0, 1, 4])
        assert pcs.pitch_classes == frozenset({0, 1, 4})

    def test_spectral_partials(self) -> None:
        from senseweave.music_theory import spectral_partials
        partials = spectral_partials(100.0, 4)
        assert len(partials) == 4
        assert abs(partials[0] - 100.0) < 0.1
        assert abs(partials[1] - 200.0) < 0.1
        assert abs(partials[2] - 300.0) < 0.1
        assert abs(partials[3] - 400.0) < 0.1

    def test_spectral_partials_with_stretch(self) -> None:
        from senseweave.music_theory import spectral_partials
        partials = spectral_partials(100.0, 3, stretch=1.05)
        assert partials[0] == 100.0
        assert partials[1] > 200.0
        assert partials[2] > 300.0

    def test_quarter_tone_to_freq(self) -> None:
        from senseweave.music_theory import quarter_tone_to_freq
        freq_a4 = quarter_tone_to_freq(69.0)
        assert abs(freq_a4 - 440.0) < 0.1
        freq_a4_quarter_sharp = quarter_tone_to_freq(69.5)
        assert freq_a4 < freq_a4_quarter_sharp < quarter_tone_to_freq(70.0)

    def test_just_intonation_chord(self) -> None:
        from senseweave.music_theory import just_intonation_chord
        freqs = just_intonation_chord(440.0, [(1, 1), (5, 4), (3, 2)])
        assert len(freqs) == 3
        assert abs(freqs[0] - 440.0) < 0.1
        assert abs(freqs[1] - 550.0) < 0.1
        assert abs(freqs[2] - 660.0) < 0.1


# === End-to-end public music-theory path ===


class MusicTheoryEndToEndTests:
    __test__ = True

    def test_builds_json_safe_ii_v_i_theory_snapshot(self) -> None:
        from senseweave.music_theory import (
            just_intonation_chord,
            quarter_tone_to_freq,
            spectral_partials,
        )

        key = scale_by_name("ionian")
        root_midi = note_name_to_midi("C", 4)
        root_pc = note_name_to_pitch_class("C")
        key_pitch_classes = key.transpose(root_pc)
        voicing_config = VoicingConfig(
            low=48,
            high=76,
            min_spacing=3,
            max_spacing=12,
            max_voicings=128,
        )

        progression: list[dict[str, object]] = []
        previous_voicing: tuple[int, ...] | None = None
        for symbol in ("Dm7", "G7", "Cmaj7"):
            chord = chord_from_symbol(symbol)
            voicing = choose_voicing(
                chord,
                previous=previous_voicing,
                style="close",
                config=voicing_config,
            )
            pitch_classes = pitch_class_set(voicing)

            assert chord.pitch_classes <= key_pitch_classes
            assert pitch_classes == chord.pitch_classes
            assert voicing_config.low <= voicing[0] <= voicing[-1] <= voicing_config.high

            note_labels: list[str] = []
            frequencies: list[float] = []
            for midi_note in voicing:
                name, octave = midi_to_note_name(midi_note)
                note_labels.append(f"{name}{octave}")
                frequencies.append(round(midi_to_freq(midi_note), 3))

            progression.append(
                {
                    "symbol": symbol,
                    "quality": chord.quality,
                    "pitch_classes": sorted(pitch_classes),
                    "voicing": list(voicing),
                    "note_labels": note_labels,
                    "frequencies": frequencies,
                }
            )
            previous_voicing = voicing

        melody_targets = ("F", "G", "E")
        melody_intervals = []
        for note_name in melody_targets:
            target_midi = note_name_to_midi(note_name, 4)
            interval = interval_between(root_midi, target_midi)
            assert interval.character
            assert interval.arc_phase
            melody_intervals.append(
                {
                    "target": f"{note_name}4",
                    "short_name": interval.short_name,
                    "consonance": interval.consonance,
                    "character": interval.character,
                    "arc_phase": interval.arc_phase,
                }
            )

        c4_hz = midi_to_freq(root_midi)
        equal_tempered_fifth_hz = midi_to_freq(note_name_to_midi("G", 4))
        just_fifth_hz = just_interval_freq(c4_hz, 3, 2)
        equal_tempered_fifth_cents = ratio_to_cents(equal_tempered_fifth_hz / c4_hz)
        just_fifth_cents = ratio_to_cents(just_fifth_hz / c4_hz)
        fifth_difference = abs(just_fifth_cents - equal_tempered_fifth_cents)

        assert 1.0 < fifth_difference < 2.0
        assert abs(cents_to_ratio(1200.0) - 2.0) < 1e-10

        just_chord = just_intonation_chord(c4_hz, [(1, 1), (5, 4), (3, 2)])
        partials = spectral_partials(c4_hz, 4, stretch=1.01)
        quarter_tone_hz = quarter_tone_to_freq(root_midi + 0.5)

        assert just_chord[0] < just_chord[1] < just_chord[2]
        assert partials == sorted(partials)
        assert c4_hz < quarter_tone_hz < midi_to_freq(root_midi + 1)

        snapshot = {
            "key": key.name,
            "root": {
                "note": "C4",
                "midi": root_midi,
                "frequency": round(c4_hz, 3),
            },
            "scale_notes": [
                f"{name}{octave}"
                for name, octave in (midi_to_note_name(note) for note in key.to_midi_notes(root_midi))
            ],
            "progression": progression,
            "melody_intervals": melody_intervals,
            "tuning": {
                "equal_tempered_fifth_cents": round(equal_tempered_fifth_cents, 3),
                "just_fifth_cents": round(just_fifth_cents, 3),
                "difference_cents": round(fifth_difference, 3),
            },
            "just_chord_hz": [round(freq, 3) for freq in just_chord],
            "spectral_partials_hz": [round(freq, 3) for freq in partials],
            "quarter_tone_hz": round(quarter_tone_hz, 3),
        }

        round_tripped = json.loads(json.dumps(snapshot, sort_keys=True))
        assert round_tripped == snapshot
        assert round_tripped["progression"][0]["symbol"] == "Dm7"
        assert round_tripped["progression"][-1]["quality"] == "maj7"
        assert round_tripped["melody_intervals"][1]["short_name"] == "P5"
