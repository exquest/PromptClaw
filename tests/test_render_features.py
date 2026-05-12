from __future__ import annotations

import math
from pathlib import Path

from cypherclaw.render.features import (
    metric_weight_for_onset,
    phrase_features_from_score_path,
    tonal_pitch_space_distance,
)


FIXTURE = Path(__file__).parent / "fixtures" / "c_major_cadence.musicxml"


def test_partitura_cadence_fixture_features_are_stable() -> None:
    features = phrase_features_from_score_path(FIXTURE, phrase_beats=4.0, key="C")

    assert len(features) == 1
    phrase = features[0]
    assert math.isclose(phrase.harmonic_charge, 0.188, abs_tol=0.001)
    assert math.isclose(phrase.melodic_charge, 0.333, abs_tol=0.001)
    assert math.isclose(phrase.metric_weight, 0.688, abs_tol=0.001)
    assert phrase.is_cadential is True
    assert phrase.contour_apex_index == 3
    assert phrase.contour_apex == 1.0


def test_tonal_pitch_space_distance_is_normalized() -> None:
    distances = [
        tonal_pitch_space_distance(pitch, key="C")
        for pitch in (60, 67, 64, 62, 61)
    ]

    assert distances == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert all(0.0 <= distance <= 1.0 for distance in distances)


def test_metric_weight_marks_downbeat_strongest() -> None:
    assert metric_weight_for_onset(0.0) == 1.0
    assert metric_weight_for_onset(2.0) == 0.75
    assert metric_weight_for_onset(1.0) == 0.5
    assert metric_weight_for_onset(0.5) == 0.25
