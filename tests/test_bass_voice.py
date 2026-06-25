"""Tests for the felt-sub / growl bass timbre selection (SIG-8).

anthony-taste signature SIG-8: bass = felt_sub + growl. The live bass role
(``generate_bass_line``) borrows ``bowed``/``pluck`` — sharp/thin, no dedicated
low timbre. This pins the per-song selection that routes the bass role to a
warm felt-sub by default with occasional growl grit for variety across the arc.

Selection only touches the ``bass`` role's *voice*; it never fabricates a bass
role (bass onsets only exist when the cast casts one) and every other role hint
is preserved byte-for-byte.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave")
)

from senseweave.bass_voice import (  # noqa: E402
    BASS_PALETTE,
    FELT_SUB,
    GROWL,
    apply_bass_routing,
    select_bass_voice,
)


def test_palette_is_felt_sub_then_growl():
    assert BASS_PALETTE == (FELT_SUB, GROWL)
    assert FELT_SUB == "bass"
    assert GROWL == "growl"


def test_selection_is_deterministic():
    for n in range(50):
        assert select_bass_voice(n) == select_bass_voice(n)


def test_felt_sub_dominates_the_arc():
    picks = [select_bass_voice(n) for n in range(12)]
    assert picks.count(FELT_SUB) > picks.count(GROWL)


def test_growl_actually_appears():
    picks = {select_bass_voice(n) for n in range(12)}
    assert GROWL in picks
    assert FELT_SUB in picks


def test_growl_on_every_third_song():
    # song_num % 3 == 2 -> growl, felt sub otherwise.
    assert select_bass_voice(2) == GROWL
    assert select_bass_voice(5) == GROWL
    assert select_bass_voice(8) == GROWL
    for n in (0, 1, 3, 4, 6, 7):
        assert select_bass_voice(n) == FELT_SUB


def test_selection_handles_large_song_num():
    assert select_bass_voice(101) in BASS_PALETTE


def test_empty_palette_returns_empty():
    assert select_bass_voice(0, palette=()) == ""


def test_routing_overrides_only_bass_voice():
    hints = {
        "melody": {"voice": "bell", "character": "lyra"},
        "bass": {"voice": "bowed", "character": "drone"},
    }
    out = apply_bass_routing(hints, song_num=0)
    assert out["bass"]["voice"] == FELT_SUB
    assert out["melody"] == {"voice": "bell", "character": "lyra"}


def test_routing_preserves_bass_identity_metadata():
    hints = {"bass": {"voice": "pluck", "character": "drone", "octave": "-3"}}
    out = apply_bass_routing(hints, song_num=0)
    assert out["bass"]["character"] == "drone"
    assert out["bass"]["octave"] == "-3"


def test_routing_noop_when_no_bass_role():
    hints = {"melody": {"voice": "bell"}}
    out = apply_bass_routing(hints, song_num=0)
    assert out == {"melody": {"voice": "bell"}}
    assert "bass" not in out


def test_routing_does_not_mutate_input():
    hints = {"bass": {"voice": "bowed"}}
    snapshot = {"bass": {"voice": "bowed"}}
    apply_bass_routing(hints, song_num=2)
    assert hints == snapshot


def test_routing_uses_growl_on_growl_songs():
    hints = {"bass": {"voice": "bowed"}}
    out = apply_bass_routing(hints, song_num=2)
    assert out["bass"]["voice"] == GROWL


def test_routing_empty_palette_leaves_bass_unchanged():
    hints = {"bass": {"voice": "bowed"}}
    out = apply_bass_routing(hints, song_num=0, palette=())
    assert out["bass"]["voice"] == "bowed"
