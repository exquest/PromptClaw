"""Korsakov Ch.6 — Orchestral form, tutti, dynamic architecture.

Tutti roles, diverging crescendo, sfp pairs, timbral tinting,
effect budget, post-tutti silence. Builds on voice_manager_v2 and
accompaniment modules.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


# === TUTTI ROLES ===

class TuttiRole(Enum):
    """Role assignment during full-orchestra passages."""
    FOUNDATION = "foundation"   # root/fifth on downbeats (gong, bowed)
    FIGURATION = "figuration"   # scalar motion, arpeggios (pluck, kotekan)
    MELODY = "melody"           # main line doubling (choir, bell)
    COLOR = "color"             # sustained wash, tremolo (breath)


# Default role assignments for each voice
VOICE_ROLES: dict[str, TuttiRole] = {
    "gong": TuttiRole.FOUNDATION,
    "bowed": TuttiRole.FOUNDATION,
    "pluck": TuttiRole.FIGURATION,
    "kotekan": TuttiRole.FIGURATION,
    "choir": TuttiRole.MELODY,
    "bell": TuttiRole.MELODY,
    "breath": TuttiRole.COLOR,
}


def assign_tutti_roles(voice_names: list[str]) -> dict[str, TuttiRole]:
    """Assign roles to active voices during tutti.

    Each voice gets its natural role. Prevents all voices from
    playing melody (which creates mud).
    """
    return {name: VOICE_ROLES.get(name, TuttiRole.COLOR) for name in voice_names}


def voices_for_role(roles: dict[str, TuttiRole], role: TuttiRole) -> list[str]:
    """Get voice names assigned to a specific role."""
    return [name for name, r in roles.items() if r == role]


# === DIVERGING CRESCENDO ===

# Center-outward voice entry order (Korsakov: expand like lungs filling)
DIVERGE_ORDER = [
    ["bowed", "choir"],         # Center: mid-range voices first
    ["pluck", "bell"],          # Next ring: lower + higher
    ["gong", "kotekan"],        # Outer ring: lowest + highest
    ["breath"],                 # Color: last, fills the space
]

CONVERGE_ORDER = list(reversed(DIVERGE_ORDER))


def plan_diverging_crescendo(total_bars: int) -> list[list[str]]:
    """Plan a crescendo that expands from center register outward.

    Returns list of voice-name lists, one per bar.
    Voices enter in pairs: mid-range first, then low+high together.
    """
    if total_bars < 1:
        return []

    bars_per_stage = max(1, total_bars // len(DIVERGE_ORDER))
    result: list[list[str]] = []
    active: list[str] = []

    for stage_idx, voices in enumerate(DIVERGE_ORDER):
        active = active + voices
        for _ in range(bars_per_stage):
            result.append(list(active))
            if len(result) >= total_bars:
                return result

    # Fill remaining bars with full voice list
    while len(result) < total_bars:
        result.append(list(active))
    return result[:total_bars]


def plan_converging_diminuendo(total_bars: int) -> list[list[str]]:
    """Plan a diminuendo that contracts from extremes inward.

    Strips voices from top and bottom first, mid-range last.
    """
    if total_bars < 1:
        return []

    all_voices = [v for group in DIVERGE_ORDER for v in group]
    bars_per_stage = max(1, total_bars // len(CONVERGE_ORDER))
    result: list[list[str]] = []
    active = list(all_voices)

    for stage_idx, voices_to_remove in enumerate(CONVERGE_ORDER):
        for _ in range(bars_per_stage):
            result.append(list(active))
            if len(result) >= total_bars:
                return result
        for v in voices_to_remove:
            if v in active:
                active.remove(v)

    while len(result) < total_bars:
        result.append(list(active) if active else [])
    return result[:total_bars]


# === SFORZANDO-PIANO PAIRS ===

@dataclass
class ArticulationPair:
    """Two voices coordinated: one attacks, one sustains."""
    attack_voice: str
    sustain_voice: str
    attack_amp: float = 0.20
    sustain_amp: float = 0.04
    attack_release: float = 0.3
    sustain_release: float = 3.0


# Pre-composed sfp pairs
SFP_PAIRS = [
    ArticulationPair("pluck", "choir"),        # pizz attack + vocal sustain
    ArticulationPair("pluck", "bowed"),         # pizz attack + cello sustain
    ArticulationPair("gong", "breath"),         # gong hit + wind sustain
    ArticulationPair("bell", "choir"),          # bell strike + vocal hold
    ArticulationPair("kotekan", "bowed"),       # sparkle attack + cello hold
]

# pSfz pairs (sustain first, then attack)
PSFZ_PAIRS = [
    ArticulationPair("gong", "breath", attack_amp=0.18, sustain_amp=0.03),
    ArticulationPair("pluck", "choir", attack_amp=0.15, sustain_amp=0.05),
]


def select_sfp_pair(mood: str = "calm") -> ArticulationPair:
    """Select an appropriate sfp pair for the current mood."""
    if mood in ("excited", "active"):
        return SFP_PAIRS[2]  # gong + breath (dramatic)
    if mood in ("anxious", "tense"):
        return SFP_PAIRS[4]  # kotekan + bowed
    if mood in ("happy", "joyful"):
        return SFP_PAIRS[3]  # bell + choir
    return SFP_PAIRS[0]      # pluck + choir (default, warm)


# === TIMBRAL TINTING ===

def tint_texture(
    active_voices: list[str],
    tint_voice: str,
    tint_amplitude_ratio: float = 0.15,
) -> tuple[str, float]:
    """Add one quiet voice to shift the color of a texture.

    Returns (tint_voice, amplitude) where amplitude is a fraction
    of the texture's average amplitude. Use at phrase boundaries
    to mark form without changing harmony.
    """
    if tint_voice in active_voices:
        return tint_voice, 0.0  # Already present, no tinting needed

    return tint_voice, tint_amplitude_ratio


# Voice pairs for tinting by movement
TINT_SUGGESTIONS: dict[str, str] = {
    "Emergence": "breath",    # Lightest color
    "Theme": "choir",         # Warmth
    "Development": "kotekan", # Sparkle
    "Recap": "bell",          # Nostalgia
    "Resolution": "breath",   # Return to lightest
}


def suggest_tint(movement: str) -> str:
    """Suggest a tint voice for a movement."""
    return TINT_SUGGESTIONS.get(movement, "breath")


# === EFFECT BUDGET ===

@dataclass
class EffectBudget:
    """Track which orchestral techniques have been spent in the current song.

    The art of holding back: don't use everything in Movement I.
    """
    tremolo_available_from: int = 2       # Movement index (0-based)
    fusion_available_from: int = 2
    tutti_available_from: int = 2          # Only at the peak of development
    tinting_available_from: int = 1
    new_timbre_reserved_for: int = 4       # Resolution only
    sfp_available_from: int = 2
    post_tutti_silence_beats: int = 2

    tremolo_used: bool = False
    fusion_used: bool = False
    tutti_used: bool = False
    sfp_used: bool = False
    new_timbre_used: bool = False

    def can_use(self, technique: str, movement_index: int) -> bool:
        """Check if a technique is available in this movement."""
        thresholds = {
            "tremolo": self.tremolo_available_from,
            "fusion": self.fusion_available_from,
            "tutti": self.tutti_available_from,
            "tinting": self.tinting_available_from,
            "new_timbre": self.new_timbre_reserved_for,
            "sfp": self.sfp_available_from,
        }
        threshold = thresholds.get(technique, 0)
        return movement_index >= threshold

    def spend(self, technique: str) -> None:
        """Mark a technique as used."""
        attr = f"{technique}_used"
        if hasattr(self, attr):
            setattr(self, attr, True)

    def reset(self) -> None:
        """Reset for a new song."""
        self.tremolo_used = False
        self.fusion_used = False
        self.tutti_used = False
        self.sfp_used = False
        self.new_timbre_used = False


# Movement name to index mapping
MOVEMENT_INDEX: dict[str, int] = {
    "Emergence": 0,
    "Theme": 1,
    "Development": 2,
    "Recap": 3,
    "Resolution": 4,
}


# === POST-TUTTI SILENCE ===

def should_insert_silence(
    previous_voice_count: int,
    current_voice_count: int,
    tutti_threshold: int = 5,
) -> bool:
    """True if we just came from a tutti and should insert silence.

    Silence after tutti is the loudest moment in music.
    """
    return previous_voice_count >= tutti_threshold and current_voice_count < tutti_threshold


def silence_duration_beats(previous_voice_count: int) -> int:
    """How many beats of silence to insert after tutti.

    More voices = longer silence needed for the contrast.
    """
    if previous_voice_count >= 7:
        return 3
    if previous_voice_count >= 5:
        return 2
    return 1


def suggest_reentry_voice() -> str:
    """After silence, the lightest voice re-enters.

    The most fragile timbre has outsized emotional weight
    after a grand pause.
    """
    return "breath"
