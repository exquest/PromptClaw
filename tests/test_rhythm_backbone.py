"""Tests for the tabla rhythm-section backbone (END-WORK #90).

Listener critique (2026-05-30): "no rhythm section." This pins the gentle tabla
pulse: when it sounds, the bar pattern it produces, intensity gating, root
tuning, and the restraint (amps under the tabla mix ceiling) that keeps it
contemplative rather than driving.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave")
)

from senseweave.rhythm_backbone import (
    RHYTHM_DENSITY_FLOOR,
    RhythmHit,
    rhythm_hits_for_row,
    wants_rhythm,
)

TABLA_CEILING = 0.090  # composer VOICE_AMP_CEILINGS for tabla voices


def _voices(hits) -> list[str]:
    return [h.voice for h in hits]


# --- wants_rhythm -----------------------------------------------------------


def test_pulse_scene_wants_rhythm() -> None:
    assert wants_rhythm(arc_rhythm="pulse", scene_name="Theme", density=0.42) is True


@pytest.mark.parametrize("arc", ["rubato", "free", "ambient", "still", "radiant"])
def test_free_arc_rhythms_suppress_the_pulse(arc: str) -> None:
    assert wants_rhythm(arc_rhythm=arc, scene_name="Theme", density=0.8) is False


@pytest.mark.parametrize("scene", ["Afterglow", "Resolution", "Divination"])
def test_breathing_scenes_suppress_the_pulse(scene: str) -> None:
    assert wants_rhythm(arc_rhythm="pulse", scene_name=scene, density=0.8) is False


def test_very_sparse_scene_does_not_want_rhythm() -> None:
    assert wants_rhythm(arc_rhythm="pulse", density=RHYTHM_DENSITY_FLOOR - 0.01) is False
    assert wants_rhythm(arc_rhythm="pulse", density=RHYTHM_DENSITY_FLOOR) is True


# --- pattern ----------------------------------------------------------------


def test_downbeat_fires_bass_dha_with_two_tones() -> None:
    hits = rhythm_hits_for_row(0, rows_per_beat=4, beats_per_bar=4, intensity=0.5, root_freq=130.8)
    assert _voices(hits) == ["tabla_dha"]
    dha = hits[0]
    assert dha.freq == pytest.approx(65.4, abs=0.1)   # octave below root
    assert dha.freq_hi == pytest.approx(130.8, abs=0.1)
    assert dha.decay > 0.0


def test_mid_bar_beat_fires_na_when_intensity_moderate() -> None:
    # Beat 2 of a 4-beat bar at rows_per_beat=4 -> row 8.
    hits = rhythm_hits_for_row(8, rows_per_beat=4, beats_per_bar=4, intensity=0.3)
    assert _voices(hits) == ["tabla_na"]


def test_low_intensity_only_keeps_the_downbeat() -> None:
    # Mid-bar beat at very low intensity -> silent (only downbeat survives).
    assert rhythm_hits_for_row(8, 4, 4, intensity=0.1) == ()
    # ...but the downbeat still fires.
    assert _voices(rhythm_hits_for_row(0, 4, 4, intensity=0.1)) == ["tabla_dha"]


def test_high_intensity_fills_every_beat() -> None:
    # Beat 1 (row 4) and beat 3 (row 12) are non-down/non-mid beats.
    assert _voices(rhythm_hits_for_row(4, 4, 4, intensity=0.9)) == ["tabla_na"]
    assert _voices(rhythm_hits_for_row(12, 4, 4, intensity=0.9)) == ["tabla_na"]
    # ...and they are silent at moderate intensity.
    assert rhythm_hits_for_row(4, 4, 4, intensity=0.4) == ()


def test_offbeat_tin_sparkle_only_at_high_intensity() -> None:
    # Off-beat = half-way through a beat -> row 2 with rows_per_beat=4.
    assert _voices(rhythm_hits_for_row(2, 4, 4, intensity=0.9)) == ["tabla_tin"]
    assert rhythm_hits_for_row(2, 4, 4, intensity=0.5) == ()


def test_off_grid_rows_are_silent() -> None:
    # row 1 and 3 are neither beat nor mid-beat for rows_per_beat=4.
    assert rhythm_hits_for_row(1, 4, 4, intensity=1.0) == ()
    assert rhythm_hits_for_row(3, 4, 4, intensity=1.0) == ()


def test_degenerate_inputs_are_safe() -> None:
    assert rhythm_hits_for_row(0, 0, 4, intensity=1.0) == ()
    assert rhythm_hits_for_row(-1, 4, 4, intensity=1.0) == ()
    assert rhythm_hits_for_row(0, 4, 0, intensity=1.0) == ()


def test_root_tuning_tracks_the_scene_key() -> None:
    hits = rhythm_hits_for_row(0, 4, 4, intensity=0.5, root_freq=196.0)
    assert hits[0].freq == pytest.approx(98.0, abs=0.1)  # octave below 196
    assert hits[0].freq_hi == pytest.approx(196.0, abs=0.1)


def test_all_hit_amps_stay_under_tabla_ceiling() -> None:
    seen = []
    for inten in (0.0, 0.25, 0.5, 0.6, 0.75, 0.9, 1.0):
        for row in range(16):
            seen.extend(rhythm_hits_for_row(row, 4, 4, intensity=inten))
    assert seen, "expected at least some hits across the grid"
    for hit in seen:
        assert isinstance(hit, RhythmHit)
        assert 0.0 < hit.amp <= TABLA_CEILING


def test_amps_grow_with_intensity() -> None:
    quiet = rhythm_hits_for_row(0, 4, 4, intensity=0.1)[0].amp
    loud = rhythm_hits_for_row(0, 4, 4, intensity=1.0)[0].amp
    assert loud > quiet
