"""Pure scheduler for a gentle tabla rhythm-section backbone (END-WORK #90).

Listener critique (2026-05-30): "no rhythm section" — the groove engine only
applies micro-timing, there is no percussion anchor. This adds one: a sparse,
WARM tabla pulse tuned to the scene root, firing on the beat grid. It is kept
deliberately restrained (mostly downbeat + mid-bar, low amplitude, organic
tabla timbre) so it anchors without pushing the music toward the "anxious /
driving" read the critique warned against.

Pure so the pattern is testable — the composer module is not importable under
the test harness. The composer feeds (row, rows_per_beat, beats_per_bar,
intensity, root_freq) and fires the returned hits via ``/s_new`` on the
existing ``sw_tabla_*`` synthdefs (already compiled on the box).
"""
from __future__ import annotations

from dataclasses import dataclass

# Scene rhythm-profiles / names where a pulse would intrude on stillness.
_NO_RHYTHM_ARC = frozenset({"rubato", "free", "ambient", "still", "radiant"})
_NO_RHYTHM_SCENES = frozenset({"Afterglow", "Resolution", "Divination"})

# Below this density a scene is too sparse/contemplative to want a beat.
RHYTHM_DENSITY_FLOOR = 0.30

# Intensity gates for how much of the pattern sounds (downbeat is always on
# when the scene wants rhythm; richer layers earn in as intensity rises).
_MID_BAR_INTENSITY = 0.25
_EVERY_BEAT_INTENSITY = 0.60
_OFFBEAT_TIN_INTENSITY = 0.72


@dataclass(frozen=True)
class RhythmHit:
    """One percussion stroke to fire on the beat grid.

    ``freq`` is the bass/centre pitch; ``freq_hi`` is only used by the two-tone
    ``tabla_dha`` stroke (its ``freqHi`` control). ``amp``/``decay`` map to the
    synthdef controls of the same name.
    """

    voice: str
    freq: float
    amp: float
    decay: float
    freq_hi: float = 0.0


def wants_rhythm(
    *,
    arc_rhythm: str = "",
    scene_name: str = "",
    density: float = 0.4,
) -> bool:
    """Return True when this scene should carry the tabla pulse."""

    if arc_rhythm in _NO_RHYTHM_ARC:
        return False
    if scene_name in _NO_RHYTHM_SCENES:
        return False
    return density >= RHYTHM_DENSITY_FLOOR


def _clamp_unit(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def rhythm_hits_for_row(
    row: int,
    rows_per_beat: int,
    beats_per_bar: int = 4,
    *,
    intensity: float = 0.5,
    root_freq: float = 130.8,
) -> tuple[RhythmHit, ...]:
    """Return the tabla strokes to fire at ``row`` (empty when off-grid).

    Pattern (one bar): a bass ``tabla_dha`` on the downbeat (always), a mid
    ``tabla_na`` on the mid-bar beat (intensity >= 0.25), ``na`` on the
    remaining beats only at higher intensity, and a light ``tabla_tin`` sparkle
    on the off-beat at the highest intensity. Amplitudes scale with intensity
    and stay under the tabla mix ceiling (~0.090).
    """

    if rows_per_beat <= 0 or beats_per_bar <= 0 or row < 0:
        return ()
    inten = _clamp_unit(intensity)
    root = max(1.0, float(root_freq))
    half = rows_per_beat // 2

    on_beat = row % rows_per_beat == 0
    on_offbeat = half >= 1 and row % rows_per_beat == half

    if on_beat:
        beat_in_bar = (row // rows_per_beat) % beats_per_bar
        if beat_in_bar == 0:
            # Downbeat: warm two-tone bass stroke, tuned an octave below root.
            amp = round(0.045 + 0.030 * inten, 4)
            return (
                RhythmHit(
                    voice="tabla_dha",
                    freq=round(root * 0.5, 3),
                    freq_hi=round(root, 3),
                    amp=amp,
                    decay=0.45,
                ),
            )
        if beat_in_bar == beats_per_bar // 2 and inten >= _MID_BAR_INTENSITY:
            amp = round(0.030 + 0.025 * inten, 4)
            return (
                RhythmHit(voice="tabla_na", freq=round(root, 3), amp=amp, decay=0.30),
            )
        if inten >= _EVERY_BEAT_INTENSITY:
            amp = round(0.022 + 0.018 * inten, 4)
            return (
                RhythmHit(voice="tabla_na", freq=round(root, 3), amp=amp, decay=0.26),
            )
        return ()

    if on_offbeat and inten >= _OFFBEAT_TIN_INTENSITY:
        amp = round(0.018 + 0.015 * inten, 4)
        return (
            RhythmHit(voice="tabla_tin", freq=round(root * 2.0, 3), amp=amp, decay=0.18),
        )
    return ()
