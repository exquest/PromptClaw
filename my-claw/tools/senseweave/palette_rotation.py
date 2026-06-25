"""Per-song melody-timbre rotation (END-WORK #91).

Listeners (2026-05-30) heard the plucked string on nearly every melodic
onset: repetitive, monotonous, "sharp/anxious" instead of warm. The melody
role *allows* {pluck, bowed, bell, kotekan} but both the cast-hint path and
the downstream fallback collapse to pluck, so it carries the whole arc.

This module spreads the melody across a warm-first palette, one timbre per
song, so no single voice dominates and the warm/sustained strings lead. It is
deliberately pure (no I/O, deterministic per ``song_num``) so the composer can
call it from ``tracker_solo_song`` and it can be unit-tested without scsynth.
"""
from __future__ import annotations

from collections.abc import Mapping

# Ordered warm-first: the sustained bowed string and the contemplative bell
# lead; the sharp pluck the listeners were tired of stays in rotation but no
# longer carries every movement; kotekan adds gamelan shimmer. Every entry is
# a member of music_tracker._TRACKER_ROLE_ALLOWED_VOICES["melody"], so the
# downstream voice normaliser is a no-op on these values.
MELODY_PALETTE: tuple[str, ...] = ("bowed", "bell", "pluck", "kotekan")


def rotate_melody_voice(song_num: int, *, palette: tuple[str, ...] = MELODY_PALETTE) -> str:
    """Return the melody timbre for ``song_num``, cycling the warm-first palette.

    Pure and deterministic: ``song_num`` modulo the palette length. pluck's
    share of melodic onsets drops from ~100% to ``1/len(palette)``.
    """
    if not palette:
        return ""
    return palette[int(song_num) % len(palette)]


def rotate_role_hints(
    role_hints: Mapping[str, Mapping[str, str]],
    song_num: int,
    *,
    palette: tuple[str, ...] = MELODY_PALETTE,
) -> dict[str, dict[str, str]]:
    """Copy ``role_hints`` with the melody role's voice rotated for ``song_num``.

    Only the melody ``voice`` changes; character identity metadata and every
    other role hint are preserved. A melody hint is synthesised when the cast
    supplied none, so the rotation also overrides the downstream pluck default.
    The input mapping is never mutated.
    """
    new: dict[str, dict[str, str]] = {role: dict(hint) for role, hint in role_hints.items()}
    voice = rotate_melody_voice(song_num, palette=palette)
    if not voice:
        return new
    melody = dict(new.get("melody", {}))
    melody["voice"] = voice
    new["melody"] = melody
    return new
