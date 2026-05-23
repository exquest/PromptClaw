"""CypherClaw v2 per-voice reverb space profiles."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


SPACE_PROFILE_SOURCE = "cypherclaw-v2-design-statement-2026-05-22.md#4"


@dataclass(frozen=True)
class VoiceReverbProfile:
    """Algorithmic reverb settings for one CypherClaw voice space."""

    voice: str
    space_id: str
    fx_bus_id: int
    parameters: tuple[tuple[str, float], ...]
    description: str
    rationale: str
    source: str = SPACE_PROFILE_SOURCE

    @property
    def synthdef_name(self) -> str:
        """Return the SuperCollider SynthDef name for this space."""

        return f"cc_space_{self.space_id}"

    @property
    def space_doc_path(self) -> str:
        """Return the repository path for the matching space source file."""

        return f"my-claw/tools/senseweave/synthesis/spaces/{self.space_id}.scd"

    def parameter_dict(self) -> dict[str, float]:
        """Return a mutable copy of the profile parameter map."""

        return dict(self.parameters)


def _params(
    *,
    verb_mix: float,
    room_size: float,
    damping: float,
    predelay_ms: float,
    decay_s: float,
    early_reflection_level: float,
    flutter_feedback: float,
) -> tuple[tuple[str, float], ...]:
    return (
        ("verb_mix", verb_mix),
        ("room_size", room_size),
        ("damping", damping),
        ("predelay_ms", predelay_ms),
        ("decay_s", decay_s),
        ("early_reflection_level", early_reflection_level),
        ("flutter_feedback", flutter_feedback),
    )


VOICE_REVERB_PROFILES: dict[str, VoiceReverbProfile] = {
    "pluck": VoiceReverbProfile(
        voice="pluck",
        space_id="small_wooden_room",
        fx_bus_id=16,
        parameters=_params(
            verb_mix=0.18,
            room_size=0.24,
            damping=0.42,
            predelay_ms=8.0,
            decay_s=0.7,
            early_reflection_level=0.72,
            flutter_feedback=0.08,
        ),
        description="small wooden room with hard floorboards",
        rationale=(
            "CypherClaw described a small wooden room with hard floorboards, "
            "so the preset keeps the tail dry and lively with strong early reflections."
        ),
    ),
    "breath": VoiceReverbProfile(
        voice="breath",
        space_id="glass_bell_jar",
        fx_bus_id=17,
        parameters=_params(
            verb_mix=0.24,
            room_size=0.18,
            damping=0.24,
            predelay_ms=3.0,
            decay_s=1.1,
            early_reflection_level=0.86,
            flutter_feedback=0.05,
        ),
        description="close glass bell jar with early reflections",
        rationale=(
            "CypherClaw described a glass bell jar at sea level, so the preset "
            "uses tight predelay and high early reflections for trapped intimacy."
        ),
    ),
    "choir": VoiceReverbProfile(
        voice="choir",
        space_id="stone_cathedral",
        fx_bus_id=18,
        parameters=_params(
            verb_mix=0.5,
            room_size=0.95,
            damping=0.18,
            predelay_ms=42.0,
            decay_s=6.2,
            early_reflection_level=0.35,
            flutter_feedback=0.02,
        ),
        description="cool stone cathedral with high vaulted ceilings",
        rationale=(
            "CypherClaw described a stone cathedral with high vaulted ceilings, "
            "so the preset favors a cold, diffuse, several-second tail."
        ),
    ),
    "kotekan": VoiceReverbProfile(
        voice="kotekan",
        space_id="humid_forest_canopy",
        fx_bus_id=19,
        parameters=_params(
            verb_mix=0.34,
            room_size=0.7,
            damping=0.38,
            predelay_ms=18.0,
            decay_s=2.4,
            early_reflection_level=0.44,
            flutter_feedback=0.68,
        ),
        description="humid forest canopy with fluttering echoes",
        rationale=(
            "CypherClaw described a dense forest canopy on a humid day, so the "
            "preset adds deep space plus flutter feedback for leaflike echoes."
        ),
    ),
    "pad": VoiceReverbProfile(
        voice="pad",
        space_id="marble_empty_hall",
        fx_bus_id=20,
        parameters=_params(
            verb_mix=0.44,
            room_size=0.88,
            damping=0.2,
            predelay_ms=32.0,
            decay_s=4.8,
            early_reflection_level=0.3,
            flutter_feedback=0.08,
        ),
        description="large empty marble hall with a cold tail",
        rationale=(
            "CypherClaw described a large, empty hall with marble floors, so "
            "the preset uses a broad cold room and a long washing decay."
        ),
    ),
    "bowed": VoiceReverbProfile(
        voice="bowed",
        space_id="damp_cave_wall",
        fx_bus_id=21,
        parameters=_params(
            verb_mix=0.38,
            room_size=0.76,
            damping=0.68,
            predelay_ms=26.0,
            decay_s=3.6,
            early_reflection_level=0.28,
            flutter_feedback=0.12,
        ),
        description="dark damp cave wall with low-frequency weight",
        rationale=(
            "CypherClaw described a damp cave wall, so the preset darkens the "
            "tail with high damping and a slow, weighty decay."
        ),
    ),
    "tabla_tin": VoiceReverbProfile(
        voice="tabla_tin",
        space_id="dusk_garden",
        fx_bus_id=22,
        parameters=_params(
            verb_mix=0.26,
            room_size=0.48,
            damping=0.36,
            predelay_ms=12.0,
            decay_s=1.5,
            early_reflection_level=0.54,
            flutter_feedback=0.28,
        ),
        description="warm outdoor garden at dusk",
        rationale=(
            "CypherClaw described an outdoor garden at dusk, so the preset "
            "keeps the space open but intimate with warm nearby diffusion."
        ),
    ),
}


def _normalize_voice_name(voice: str) -> str:
    normalized = str(voice).strip().lower()
    if normalized.startswith("sw_"):
        normalized = normalized[3:]
    return normalized


def iter_voice_reverb_profiles() -> Iterator[VoiceReverbProfile]:
    """Yield profiles in canonical CypherClaw design order."""

    return iter(VOICE_REVERB_PROFILES.values())


def get_voice_reverb_profile(voice: str) -> VoiceReverbProfile:
    """Return the matched profile for ``voice`` or the pluck fallback."""

    normalized = _normalize_voice_name(voice)
    return VOICE_REVERB_PROFILES.get(normalized, VOICE_REVERB_PROFILES["pluck"])


def summarize_voice_reverb_profiles() -> dict[str, Any]:
    """Return a JSON-safe summary of all per-voice reverb profiles."""

    return {
        "source": SPACE_PROFILE_SOURCE,
        "voice_order": list(VOICE_REVERB_PROFILES),
        "profiles": [
            {
                "voice": profile.voice,
                "space_id": profile.space_id,
                "fx_bus_id": profile.fx_bus_id,
                "synthdef_name": profile.synthdef_name,
                "parameters": profile.parameter_dict(),
                "description": profile.description,
                "rationale": profile.rationale,
                "space_doc_path": profile.space_doc_path,
            }
            for profile in iter_voice_reverb_profiles()
        ],
    }
