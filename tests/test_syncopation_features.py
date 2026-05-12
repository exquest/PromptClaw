"""Tests for syncopation + polyrhythmic-cross lane phasing.

depth: 2

Adds coverage for:
  - GROOVE_TYPES vocabulary additions
  - GrooveProfile.syncopation_intensity + lane_phase_offsets fields
  - _GROOVE_PROFILES["syncopated"], _GROOVE_PROFILES["polyrhythmic_cross"]
  - syncopate_phrase: deterministic rest insertion, role scaling, no-op below threshold
  - _parse_lane_phase_offsets: parses CSV strings, tuples, rejects malformed
  - _quantize_phrase_to_lane phase_offset_rows: shifts melody, exempts bass
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.generative_scores import Note, Phrase
from senseweave.groove_engine import GROOVE_TYPES, _GROOVE_PROFILES, GrooveProfile
from senseweave.music_tracker import (
    DEFAULT_LANE_PHASE_OFFSETS,
    _parse_lane_phase_offsets,
    _quantize_phrase_to_lane,
    syncopate_phrase,
)


# ---------------------------------------------------------------------------
# Groove vocabulary additions
# ---------------------------------------------------------------------------

class TestGrooveVocabulary:
    def test_syncopated_in_groove_types(self):
        assert "syncopated" in GROOVE_TYPES

    def test_polyrhythmic_cross_in_groove_types(self):
        assert "polyrhythmic_cross" in GROOVE_TYPES

    def test_syncopated_profile_registered(self):
        prof = _GROOVE_PROFILES["syncopated"]
        assert isinstance(prof, GrooveProfile)
        assert prof.syncopation_intensity > 0.5
        assert prof.lane_phase_offsets

    def test_polyrhythmic_cross_profile_registered(self):
        prof = _GROOVE_PROFILES["polyrhythmic_cross"]
        assert isinstance(prof, GrooveProfile)
        assert prof.syncopation_intensity > 0.0
        assert prof.polyrhythm == (3, 4)
        assert prof.lane_phase_offsets

    def test_existing_profiles_keep_zero_default(self):
        # Calm profiles must stay at intensity=0.0 so they don't gain
        # unwanted syncopation.
        assert _GROOVE_PROFILES["drift"].syncopation_intensity == 0.0
        assert _GROOVE_PROFILES["drone"].syncopation_intensity == 0.0
        assert _GROOVE_PROFILES["sustain"].syncopation_intensity == 0.0
        assert _GROOVE_PROFILES["pad"].syncopation_intensity == 0.0


# ---------------------------------------------------------------------------
# syncopate_phrase
# ---------------------------------------------------------------------------

def _phrase(*, role: str, durations: list[float]) -> Phrase:
    return Phrase(
        notes=[Note(scale_degree=1 + i, duration_beats=d, accent=False) for i, d in enumerate(durations)],
        voice="pluck",
        dynamic="mf",
        role=role,
    )


class TestSyncopatePhrase:
    def test_zero_intensity_is_noop(self):
        phrase = _phrase(role="melody", durations=[1.0, 1.0, 2.0])
        result = syncopate_phrase(phrase, intensity=0.0)
        assert result is phrase

    def test_full_intensity_inserts_rests(self):
        phrase = _phrase(role="melody", durations=[2.0, 2.0, 2.0])
        result = syncopate_phrase(phrase, intensity=1.0, rng_seed=42)
        # at least one note should have been split into rest + remaining
        rest_count = sum(1 for n in result.notes if n.scale_degree == 0)
        assert rest_count > 0
        # total duration preserved
        assert abs(sum(n.duration_beats for n in result.notes) - 6.0) < 0.01

    def test_short_notes_unchanged(self):
        # Notes shorter than 1.0 beat should not be split
        phrase = _phrase(role="melody", durations=[0.5, 0.25, 0.5])
        result = syncopate_phrase(phrase, intensity=1.0, rng_seed=1)
        assert result is phrase or [n.scale_degree for n in result.notes] == [1, 2, 3]

    def test_deterministic_same_seed(self):
        phrase = _phrase(role="melody", durations=[1.5, 1.5, 1.5, 1.5])
        a = syncopate_phrase(phrase, intensity=0.7, rng_seed=99)
        b = syncopate_phrase(phrase, intensity=0.7, rng_seed=99)
        assert [(n.scale_degree, n.duration_beats) for n in a.notes] == [
            (n.scale_degree, n.duration_beats) for n in b.notes
        ]

    def test_bass_role_halved_intensity(self):
        # At intensity=0.6 with role=bass (scaled to 0.3), fewer rests than melody.
        bass = _phrase(role="bass", durations=[2.0] * 8)
        mel = _phrase(role="melody", durations=[2.0] * 8)
        b = syncopate_phrase(bass, intensity=0.6, rng_seed=7)
        m = syncopate_phrase(mel, intensity=0.6, rng_seed=7)
        bass_rests = sum(1 for n in b.notes if n.scale_degree == 0)
        mel_rests = sum(1 for n in m.notes if n.scale_degree == 0)
        assert mel_rests >= bass_rests

    def test_metadata_marks_syncopated(self):
        phrase = _phrase(role="melody", durations=[2.0, 2.0])
        result = syncopate_phrase(phrase, intensity=1.0, rng_seed=42)
        if result is not phrase:  # only if we actually changed it
            assert result.metadata.get("syncopated") == "true"


# ---------------------------------------------------------------------------
# _parse_lane_phase_offsets
# ---------------------------------------------------------------------------

class TestParseLanePhaseOffsets:
    def test_csv_string(self):
        assert _parse_lane_phase_offsets("0,1,2,3,1") == (0, 1, 2, 3, 1)

    def test_csv_with_spaces(self):
        assert _parse_lane_phase_offsets(" 0, 2 ,1 ") == (0, 2, 1)

    def test_empty_string(self):
        assert _parse_lane_phase_offsets("") == ()

    def test_none(self):
        assert _parse_lane_phase_offsets(None) == ()

    def test_tuple_input(self):
        assert _parse_lane_phase_offsets((0, 1, 2)) == (0, 1, 2)

    def test_list_input(self):
        assert _parse_lane_phase_offsets([0, 1, 2]) == (0, 1, 2)

    def test_negative_values_clamped_to_zero(self):
        # negative offsets would corrupt timing; clamp to 0
        assert _parse_lane_phase_offsets("0,-3,2") == (0, 0, 2)

    def test_malformed_returns_empty(self):
        assert _parse_lane_phase_offsets("not,a,number") == ()


# ---------------------------------------------------------------------------
# _quantize_phrase_to_lane phase offset
# ---------------------------------------------------------------------------

class TestPhaseOffsetInQuantize:
    def test_default_offset_is_zero(self):
        phrase = _phrase(role="melody", durations=[1.0, 1.0])
        lane = _quantize_phrase_to_lane(phrase, lane_name="L", rows_per_beat=4, repeat_count=1)
        # First step row should be 0 (no offset)
        assert lane.steps[0].row == 0

    def test_offset_shifts_melody_lane(self):
        phrase = _phrase(role="melody", durations=[1.0, 1.0])
        lane = _quantize_phrase_to_lane(
            phrase,
            lane_name="L",
            rows_per_beat=4,
            repeat_count=1,
            phase_offset_rows=2,
        )
        assert lane.steps[0].row == 2

    def test_offset_skipped_for_bass(self):
        phrase = _phrase(role="bass", durations=[1.0, 1.0])
        lane = _quantize_phrase_to_lane(
            phrase,
            lane_name="L",
            rows_per_beat=4,
            repeat_count=1,
            phase_offset_rows=3,
        )
        # Bass anchors on row 0 even when offset is requested
        assert lane.steps[0].row == 0


# ---------------------------------------------------------------------------
# DEFAULT_LANE_PHASE_OFFSETS sanity
# ---------------------------------------------------------------------------

class TestDefaultLanePhaseOffsets:
    def test_default_starts_with_bass_zero(self):
        # Index 0 is bass; must be 0 to keep harmonic anchor solid.
        assert DEFAULT_LANE_PHASE_OFFSETS[0] == 0

    def test_default_has_five_lanes(self):
        # bass, melody, counter, color, texture
        assert len(DEFAULT_LANE_PHASE_OFFSETS) == 5

    def test_default_offsets_are_nonzero_for_non_bass(self):
        # at least one non-bass lane is offset, otherwise feature does nothing
        assert any(v > 0 for v in DEFAULT_LANE_PHASE_OFFSETS[1:])


# ---------------------------------------------------------------------------
# End-to-end depth-2 coverage
# ---------------------------------------------------------------------------


class SyncopationFeaturesEndToEndTests:
    """End-to-end diagnostic coverage for syncopation + polyrhythmic-cross."""

    __test__ = True

    def test_syncopation_features_groove_lifecycle_round_trips_json_diagnostic(
        self,
    ) -> None:
        sync_profile = _GROOVE_PROFILES["syncopated"]
        cross_profile = _GROOVE_PROFILES["polyrhythmic_cross"]

        assert "syncopated" in GROOVE_TYPES
        assert "polyrhythmic_cross" in GROOVE_TYPES
        assert sync_profile.syncopation_intensity > 0.5
        assert cross_profile.syncopation_intensity > 0.0
        assert cross_profile.polyrhythm == (3, 4)
        assert sync_profile.lane_phase_offsets
        assert cross_profile.lane_phase_offsets

        csv_offsets = _parse_lane_phase_offsets("0,1,2,3,1")
        tuple_offsets = _parse_lane_phase_offsets((0, 1, 2, 3, 1))
        assert csv_offsets == (0, 1, 2, 3, 1)
        assert csv_offsets == tuple_offsets

        melody_phrase = _phrase(role="melody", durations=[2.0, 2.0, 2.0, 2.0])
        bass_phrase = _phrase(role="bass", durations=[2.0, 2.0, 2.0, 2.0])

        full_intensity_melody = syncopate_phrase(
            melody_phrase, intensity=1.0, rng_seed=42
        )
        assert full_intensity_melody is not melody_phrase
        full_rest_count = sum(
            1 for note in full_intensity_melody.notes if note.scale_degree == 0
        )
        assert full_rest_count > 0
        assert (
            abs(
                sum(note.duration_beats for note in full_intensity_melody.notes)
                - 8.0
            )
            < 0.01
        )
        assert full_intensity_melody.metadata.get("syncopated") == "true"

        scaled_melody = syncopate_phrase(
            melody_phrase, intensity=0.6, rng_seed=7
        )
        scaled_bass = syncopate_phrase(
            bass_phrase, intensity=0.6, rng_seed=7
        )
        melody_rest_count = sum(
            1 for note in scaled_melody.notes if note.scale_degree == 0
        )
        bass_rest_count = sum(
            1 for note in scaled_bass.notes if note.scale_degree == 0
        )
        assert melody_rest_count >= bass_rest_count

        offset_rows = 2
        melody_lane = _quantize_phrase_to_lane(
            melody_phrase,
            lane_name="melody",
            rows_per_beat=4,
            repeat_count=1,
            phase_offset_rows=offset_rows,
        )
        bass_lane = _quantize_phrase_to_lane(
            bass_phrase,
            lane_name="bass",
            rows_per_beat=4,
            repeat_count=1,
            phase_offset_rows=offset_rows,
        )
        assert melody_lane.steps[0].row == offset_rows
        assert bass_lane.steps[0].row == 0

        diagnostic = {
            "groove_types": list(GROOVE_TYPES),
            "profiles": {
                "syncopated": {
                    "groove_type": sync_profile.groove_type,
                    "syncopation_intensity": sync_profile.syncopation_intensity,
                    "lane_phase_offsets": list(sync_profile.lane_phase_offsets),
                },
                "polyrhythmic_cross": {
                    "groove_type": cross_profile.groove_type,
                    "syncopation_intensity": cross_profile.syncopation_intensity,
                    "polyrhythm": list(cross_profile.polyrhythm or ()),
                    "lane_phase_offsets": list(cross_profile.lane_phase_offsets),
                },
            },
            "parsed_offsets": {
                "csv": list(csv_offsets),
                "tuple": list(tuple_offsets),
            },
            "syncopate_phrase": {
                "full_intensity_melody": {
                    "rest_count": full_rest_count,
                    "total_duration": round(
                        sum(
                            note.duration_beats
                            for note in full_intensity_melody.notes
                        ),
                        3,
                    ),
                    "metadata_syncopated": full_intensity_melody.metadata.get(
                        "syncopated"
                    ),
                },
                "role_scaling": {
                    "melody_rest_count": melody_rest_count,
                    "bass_rest_count": bass_rest_count,
                },
            },
            "phase_offset_quantize": {
                "offset_rows": offset_rows,
                "melody_first_row": melody_lane.steps[0].row,
                "bass_first_row": bass_lane.steps[0].row,
            },
            "default_lane_phase_offsets": list(DEFAULT_LANE_PHASE_OFFSETS),
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert round_tripped["profiles"]["syncopated"]["groove_type"] == "syncopated"
        assert (
            round_tripped["profiles"]["polyrhythmic_cross"]["polyrhythm"]
            == [3, 4]
        )
        assert round_tripped["parsed_offsets"]["csv"] == [0, 1, 2, 3, 1]
        assert (
            round_tripped["syncopate_phrase"]["full_intensity_melody"][
                "metadata_syncopated"
            ]
            == "true"
        )
        assert (
            round_tripped["phase_offset_quantize"]["melody_first_row"]
            == offset_rows
        )
        assert round_tripped["phase_offset_quantize"]["bass_first_row"] == 0
        assert round_tripped["default_lane_phase_offsets"][0] == 0
