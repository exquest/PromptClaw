"""Tests for melody-timbre palette rotation (END-WORK #91).

Listener critique (2026-05-30): the plucked string carries nearly every
melodic onset, so the set sounds repetitive/monotonous and "sharp/anxious"
rather than warm. This pins the per-song rotation that spreads the melody
across a warm-first palette so no single timbre dominates the arc.

The rotation only touches the melody role's *voice*; character identity
metadata and every other role hint are preserved byte-for-byte.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave")
)

from senseweave.palette_rotation import (
    MELODY_PALETTE,
    rotate_melody_voice,
    rotate_role_hints,
)

# The composer's allowed melody voices (music_tracker _TRACKER_ROLE_ALLOWED_VOICES).
ALLOWED_MELODY_VOICES = frozenset({"pluck", "bowed", "bell", "kotekan"})


# --- rotate_melody_voice ----------------------------------------------------


def test_palette_is_a_subset_of_the_allowed_melody_voices() -> None:
    assert set(MELODY_PALETTE) <= ALLOWED_MELODY_VOICES
    assert len(MELODY_PALETTE) == len(set(MELODY_PALETTE))  # no dupes


def test_rotation_is_warm_first() -> None:
    # Song 0 leads with the warm sustained string, not the sharp pluck.
    assert rotate_melody_voice(0) == "bowed"
    assert MELODY_PALETTE[0] == "bowed"
    # pluck appears, but not until later in the cycle.
    assert "pluck" in MELODY_PALETTE
    assert MELODY_PALETTE.index("pluck") > 0


def test_rotation_cycles_through_the_whole_palette() -> None:
    seen = {rotate_melody_voice(n) for n in range(len(MELODY_PALETTE))}
    assert seen == set(MELODY_PALETTE)


def test_rotation_is_deterministic_per_song() -> None:
    for n in (0, 1, 2, 3, 7, 41, 100):
        assert rotate_melody_voice(n) == rotate_melody_voice(n)


def test_rotation_wraps_modulo_palette_length() -> None:
    period = len(MELODY_PALETTE)
    assert rotate_melody_voice(period) == rotate_melody_voice(0)
    assert rotate_melody_voice(period + 2) == rotate_melody_voice(2)


def test_pluck_share_is_one_in_palette_over_a_long_run() -> None:
    voices = [rotate_melody_voice(n) for n in range(len(MELODY_PALETTE) * 25)]
    pluck_share = voices.count("pluck") / len(voices)
    assert abs(pluck_share - 1.0 / len(MELODY_PALETTE)) < 1e-9


def test_empty_palette_returns_empty_string() -> None:
    assert rotate_melody_voice(3, palette=()) == ""


# --- rotate_role_hints ------------------------------------------------------


def test_rotate_overrides_only_the_melody_voice() -> None:
    hints = {
        "melody": {"voice": "pluck", "character_id": "c1", "character_role": "melody"},
        "bass": {"voice": "bowed", "character_id": "c2"},
        "color": {"voice": "breath"},
    }
    out = rotate_role_hints(hints, song_num=0)
    assert out["melody"]["voice"] == "bowed"
    # Other roles untouched.
    assert out["bass"] == {"voice": "bowed", "character_id": "c2"}
    assert out["color"] == {"voice": "breath"}


def test_rotate_preserves_character_identity_metadata() -> None:
    hints = {"melody": {"voice": "pluck", "character_id": "atlas", "character_role": "melody"}}
    out = rotate_role_hints(hints, song_num=1)
    assert out["melody"]["voice"] == "bell"
    assert out["melody"]["character_id"] == "atlas"
    assert out["melody"]["character_role"] == "melody"


def test_rotate_creates_a_melody_hint_when_cast_supplied_none() -> None:
    # When the cast yields no melody hint the downstream fallback is pluck;
    # the rotation must still override it.
    out = rotate_role_hints({"bass": {"voice": "gong"}}, song_num=0)
    assert out["melody"]["voice"] == "bowed"
    assert out["bass"] == {"voice": "gong"}


def test_rotate_does_not_mutate_the_input() -> None:
    hints = {"melody": {"voice": "pluck", "character_id": "c1"}}
    snapshot = {"melody": dict(hints["melody"])}
    rotate_role_hints(hints, song_num=2)
    assert hints == snapshot


def test_rotate_chosen_voice_is_always_allowed() -> None:
    for n in range(40):
        out = rotate_role_hints({"melody": {"voice": "pluck"}}, song_num=n)
        assert out["melody"]["voice"] in ALLOWED_MELODY_VOICES
