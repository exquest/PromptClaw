"""Pure helpers for the sustained harmonic support bed (live tracker path).

The composer schedules mostly monophonic melodic lines; without a sustained
chordal foundation under them the ensemble reads as "no harmony" (listener
critique, 2026-05-30). The composer's ``_scene_polyphony_bed`` fires
choir/breath/bowed with long releases on sparse/suspended scenes to supply that
bed. These helpers decide *when* the bed should sound and *how loud* each voice
sits, kept pure so the choice is testable — the composer module itself is not
importable under the test harness.

END-WORK #88 raised the base amplitudes from their previous buried levels
(choir 0.078 / breath 0.066 / bowed 0.052) so the warm sustained harmony
actually reads under the melodic lines. The values stay under each voice's mix
ceiling after the composer's gain staging (``VOICE_AMP_CEILINGS``:
choir 0.175 / breath 0.165 / bowed 0.170, with ``counter``/``color`` roles
uncapped at 0.18), so raising them lifts the real output instead of clipping at
the ceiling. The melody/lead voices are capped at 0.086, so the bed is allowed
to be the dominant *warm* layer by design.
"""
from __future__ import annotations

from dataclasses import dataclass

# Scenes / sections / grooves / curves that always want a sustained harmonic
# bed underneath, regardless of lane count or density.
_BED_SCENES = frozenset(
    {"Emergence", "Divination", "Bridge", "Resolution", "Afterglow"}
)
_BED_IDENTITIES = frozenset({"suspended", "drift", "lyric"})
_BED_GROOVES = frozenset({"pull", "lilt"})
_BED_CURVES = frozenset(
    {"emergence_breath", "bridge_suspension", "resolution_fade", "residue_fade"}
)

# Below this density (or at/under this lane count) a scene is sparse enough that
# it wants the bed even when its name/identity/groove/curve don't request one.
BED_DENSITY_THRESHOLD = 0.45
BED_LANE_THRESHOLD = 3

# Above this density the bed is pulled back so it doesn't muddy busy passages.
_DENSE_SCENE_DENSITY = 0.65
_DENSE_AMP_SCALE = 0.75


@dataclass(frozen=True)
class BedVoice:
    """One sustained support voice in the harmonic bed.

    ``degree`` indexes the composer's key dict (scale-degree -> frequency);
    ``amp`` is the BASE amplitude before the composer's gain staging;
    ``release_mult`` scales the bed's base release for this voice.
    """

    voice: str
    degree: int
    amp: float
    release_mult: float
    role: str


# Base amplitudes RAISED in END-WORK #88 (see module docstring).
_BED_VOICES: tuple[BedVoice, ...] = (
    BedVoice(voice="choir", degree=8, amp=0.105, release_mult=1.0, role="counter"),
    BedVoice(voice="breath", degree=10, amp=0.092, release_mult=0.9, role="color"),
    BedVoice(voice="bowed", degree=5, amp=0.085, release_mult=1.2, role="counter"),
)


def wants_polyphony_bed(
    *,
    scene_name: str = "",
    identity: str = "",
    groove_type: str = "",
    curve: str = "",
    lanes: int = 0,
    density: float = 0.4,
) -> bool:
    """Return True when this scene should sound the sustained harmonic bed."""

    return (
        scene_name in _BED_SCENES
        or identity in _BED_IDENTITIES
        or groove_type in _BED_GROOVES
        or curve in _BED_CURVES
        or lanes <= BED_LANE_THRESHOLD
        or density < BED_DENSITY_THRESHOLD
    )


def bed_amp_scale(density: float) -> float:
    """Pull the bed back in dense passages so it supports without muddying."""

    return _DENSE_AMP_SCALE if density >= _DENSE_SCENE_DENSITY else 1.0


def polyphony_bed_voices(density: float = 0.4) -> tuple[BedVoice, ...]:
    """Return the bed voices with density-scaled base amplitudes.

    Amplitudes are pre-gain-staging base values for the composer to feed into
    ``play_voice`` (which applies per-voice mix gain and ceilings).
    """

    scale = bed_amp_scale(density)
    if scale == 1.0:
        return _BED_VOICES
    return tuple(
        BedVoice(
            voice=bv.voice,
            degree=bv.degree,
            amp=round(bv.amp * scale, 4),
            release_mult=bv.release_mult,
            role=bv.role,
        )
        for bv in _BED_VOICES
    )
