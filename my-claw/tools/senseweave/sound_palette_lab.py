"""Structured sound-palette studies for the EMSD track."""
from __future__ import annotations

from dataclasses import dataclass

from .instrument_patches import select_instrument_patch


@dataclass(frozen=True)
class VoiceStudy:
    voice_name: str
    synthesis_method: str
    role: str
    brightness: float
    harshness: float
    harmonicity: float
    timbral_tags: tuple[str, ...]


@dataclass(frozen=True)
class PatchStudy:
    patch_name: str
    primary_voices: tuple[str, ...]
    secondary_voices: tuple[str, ...]
    study_focus: str


VOICE_STUDIES: tuple[VoiceStudy, ...] = (
    VoiceStudy("pluck", "subtractive", "melody", 0.72, 0.34, 0.82, ("articulate", "woody", "clear")),
    VoiceStudy("bowed", "physical_model", "bass", 0.34, 0.18, 0.88, ("warm", "sustained", "resonant")),
    VoiceStudy("choir", "additive", "color", 0.44, 0.16, 0.91, ("air", "choral", "soft")),
    VoiceStudy("breath", "subtractive", "color", 0.28, 0.08, 0.46, ("airy", "diffuse", "intimate")),
    VoiceStudy("pad", "wavetable", "color", 0.41, 0.13, 0.73, ("lush", "stable", "wide")),
    VoiceStudy("kotekan", "fm", "counter", 0.81, 0.59, 0.48, ("spark", "percussive", "bright")),
    VoiceStudy("gong", "fm", "bass", 0.36, 0.42, 0.31, ("resonant", "metallic", "deep")),
    VoiceStudy("bell", "fm", "counter", 0.88, 0.53, 0.37, ("glass", "ringing", "bright")),
    VoiceStudy("metal", "wavetable", "counter", 0.76, 0.61, 0.29, ("hard", "shimmer", "sharp")),
    VoiceStudy("grain", "granular", "color", 0.57, 0.47, 0.22, ("cloud", "spray", "textural")),
    VoiceStudy("tabla_tin", "physical_model", "rhythm", 0.69, 0.28, 0.66, ("pulse", "skin", "tight")),
    VoiceStudy("tabla_ge", "physical_model", "rhythm", 0.55, 0.24, 0.63, ("body", "earth", "thump")),
)


def catalog_by_method() -> dict[str, tuple[VoiceStudy, ...]]:
    by_method: dict[str, list[VoiceStudy]] = {}
    for study in VOICE_STUDIES:
        by_method.setdefault(study.synthesis_method, []).append(study)
    return {method: tuple(entries) for method, entries in by_method.items()}


def voice_study(voice_name: str) -> VoiceStudy:
    for study in VOICE_STUDIES:
        if study.voice_name == voice_name:
            return study
    raise KeyError(voice_name)


def study_for_patch(
    *,
    patch_name: str,
    cadence_state: str = "occupied_day",
    family_name: str = "bloom",
    occupancy_state: str = "occupied_quiet",
) -> PatchStudy:
    patch = select_instrument_patch(
        patch_name=patch_name,
        cadence_state=cadence_state,
        family_name=family_name,
        occupancy_state=occupancy_state,
    )
    primary = tuple(dict.fromkeys(patch.fallback.values()))
    secondary: list[str] = []
    for allowed in patch.allowed_voices.values():
        for voice in allowed:
            if voice not in primary and voice not in secondary:
                secondary.append(voice)
    if patch.name == "house_monastery":
        focus = "subtractive warmth, sustained bow pressure, and quiet harmonic blend"
    elif patch.name == "house_workshop":
        focus = "FM articulation, rhythmic counterpoint, and bright-edge control"
    elif patch.name == "house_procession":
        focus = "pulse clarity, register separation, and forward momentum"
    elif patch.name == "house_garden":
        focus = "lyric articulation, open air, and spacious texture support"
    else:
        focus = "balanced articulation, harmony support, and restrained motion"
    return PatchStudy(
        patch_name=patch.name,
        primary_voices=primary,
        secondary_voices=tuple(secondary),
        study_focus=focus,
    )
