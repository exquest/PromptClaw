"""Tests for the sustained harmonic support bed (END-WORK #88).

The live tracker path fires choir/breath/bowed as a sustained harmonic bed under
the melodic lines. Listener critique (2026-05-30) was "no harmony" — the bed was
buried. These tests pin the predicate that decides when the bed sounds, the
density-aware amp scaling, and the RAISED base amplitudes (kept under the
composer's per-voice mix ceilings so the lift reaches the output, not the cap).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave")
)

from senseweave.polyphony_bed import (
    BED_DENSITY_THRESHOLD,
    BED_LANE_THRESHOLD,
    BedVoice,
    bed_amp_scale,
    polyphony_bed_voices,
    wants_polyphony_bed,
)

# Per-voice mix ceilings from the composer's VOICE_AMP_CEILINGS. The bed voices
# use counter/color roles (uncapped at 0.18), so the effective cap is the voice
# ceiling. The raised base amps must stay under these AFTER mix-gain staging.
_VOICE_MIX_GAIN = {"choir": 1.55, "breath": 1.35, "bowed": 1.45}
_VOICE_CEILING = {"choir": 0.175, "breath": 0.165, "bowed": 0.170}
_ROLE_GAIN = {"counter": 1.0, "color": 0.95}


def test_sparse_scene_wants_bed_by_lane_count() -> None:
    assert wants_polyphony_bed(lanes=BED_LANE_THRESHOLD, density=0.9) is True


def test_dense_many_lane_scene_does_not_want_bed() -> None:
    assert (
        wants_polyphony_bed(
            scene_name="Theme",
            identity="study",
            groove_type="straight",
            curve="statement_swell",
            lanes=5,
            density=0.8,
        )
        is False
    )


def test_low_density_scene_wants_bed_even_with_many_lanes() -> None:
    assert wants_polyphony_bed(lanes=6, density=BED_DENSITY_THRESHOLD - 0.01) is True


@pytest.mark.parametrize("scene", ["Emergence", "Divination", "Bridge", "Resolution", "Afterglow"])
def test_named_bed_scenes_always_want_bed(scene: str) -> None:
    assert wants_polyphony_bed(scene_name=scene, lanes=8, density=0.99) is True


@pytest.mark.parametrize("identity", ["suspended", "drift", "lyric"])
def test_suspended_identities_want_bed(identity: str) -> None:
    assert wants_polyphony_bed(identity=identity, lanes=8, density=0.99) is True


@pytest.mark.parametrize("groove", ["pull", "lilt"])
def test_pull_and_lilt_grooves_want_bed(groove: str) -> None:
    assert wants_polyphony_bed(groove_type=groove, lanes=8, density=0.99) is True


def test_bed_amp_scale_full_when_sparse_and_reduced_when_dense() -> None:
    assert bed_amp_scale(0.4) == 1.0
    assert bed_amp_scale(0.64) == 1.0
    assert bed_amp_scale(0.65) == 0.75
    assert bed_amp_scale(0.9) == 0.75


def test_bed_has_three_warm_voices_in_expected_roles() -> None:
    voices = polyphony_bed_voices(0.4)
    assert [bv.voice for bv in voices] == ["choir", "breath", "bowed"]
    by_name = {bv.voice: bv for bv in voices}
    assert by_name["choir"].role == "counter"
    assert by_name["breath"].role == "color"
    assert by_name["bowed"].role == "counter"
    assert all(isinstance(bv, BedVoice) for bv in voices)


def test_raised_amps_are_above_old_buried_levels() -> None:
    by_name = {bv.voice: bv for bv in polyphony_bed_voices(0.4)}
    # Old buried base amps the critique flagged as inaudible.
    assert by_name["choir"].amp > 0.078
    assert by_name["breath"].amp > 0.066
    assert by_name["bowed"].amp > 0.052


def test_raised_amps_stay_under_mix_ceilings_after_gain_staging() -> None:
    for bv in polyphony_bed_voices(0.4):
        final = bv.amp * _VOICE_MIX_GAIN[bv.voice] * _ROLE_GAIN[bv.role]
        assert final <= _VOICE_CEILING[bv.voice], (
            f"{bv.voice} final {final:.4f} exceeds ceiling {_VOICE_CEILING[bv.voice]}"
        )
        # ...but high enough to genuinely use the headroom (>70% of ceiling).
        assert final >= 0.7 * _VOICE_CEILING[bv.voice]


def test_dense_scenes_scale_amps_down_proportionally() -> None:
    sparse = {bv.voice: bv.amp for bv in polyphony_bed_voices(0.4)}
    dense = {bv.voice: bv.amp for bv in polyphony_bed_voices(0.8)}
    for voice in sparse:
        assert dense[voice] == pytest.approx(round(sparse[voice] * 0.75, 4))


def test_release_multipliers_match_voice_intent() -> None:
    by_name = {bv.voice: bv for bv in polyphony_bed_voices(0.4)}
    assert by_name["choir"].release_mult == 1.0
    assert by_name["breath"].release_mult == 0.9
    assert by_name["bowed"].release_mult == 1.2  # longest tail
