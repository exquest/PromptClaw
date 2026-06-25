"""Felt-sub / growl bass timbre selection (anthony-taste SIG-8).

SIG-8 names the #1 gap: ``bass = felt_sub + growl``. The live bass role
(``generate_bass_line``, ``role="bass"``) had no dedicated low timbre — it
borrowed ``bowed``/``pluck``, which reads as sharp/thin. This module picks the
bass timbre once per song: a warm clean ``felt_sub`` by default (the foundation
that was missing), with an occasional ``growl`` (FM/saturated, slow resonant
filter) for grit and variety across the meditative->ecstatic arc.

Pure + deterministic per ``song_num`` so it is fully unit-testable; the composer
applies it by overriding the ``bass`` role hint's ``voice`` (the same seam as
the melody palette rotation). It never fabricates a bass role — bass onsets only
exist when the cast casts one — and it deep-copies, never mutating its input.
"""
from __future__ import annotations

from collections.abc import Mapping

#: The two bass timbres. Names match the composer voice keys (sw_bass / sw_growl).
FELT_SUB = "bass"
GROWL = "growl"

#: Felt-sub first (the warm foundation), growl second (the grit).
BASS_PALETTE: tuple[str, ...] = (FELT_SUB, GROWL)


def select_bass_voice(song_num: int, *, palette: tuple[str, ...] = BASS_PALETTE) -> str:
    """Return the bass timbre for a song.

    Felt-sub-dominant: growl every third song (``song_num % 3 == 2``), felt sub
    otherwise — ~2/3 warm foundation, ~1/3 grit. Deterministic per ``song_num``.
    Empty palette -> ``""`` (caller leaves the bass role untouched).
    """
    if not palette:
        return ""
    if int(song_num) % 3 == 2 and GROWL in palette:
        return GROWL
    return palette[0]


def apply_bass_routing(
    role_hints: Mapping[str, Mapping[str, str]],
    song_num: int,
    *,
    palette: tuple[str, ...] = BASS_PALETTE,
) -> dict[str, dict[str, str]]:
    """Override the ``bass`` role hint's voice with the selected bass timbre.

    Returns a deep copy. No-op (byte-identical copy) when there is no ``bass``
    role or the palette is empty. Only the ``bass`` role's ``voice`` changes;
    character identity and every other role hint are preserved.
    """
    new = {role: dict(hint) for role, hint in role_hints.items()}
    if "bass" not in new:
        return new
    voice = select_bass_voice(song_num, palette=palette)
    if not voice:
        return new
    bass = dict(new["bass"])
    bass["voice"] = voice
    new["bass"] = bass
    return new
