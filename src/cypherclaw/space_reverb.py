"""CypherClaw v2 per-voice reverb space profiles."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
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

EXPRESSIVE_SPACE_VOICE_BY_VOICE: dict[str, str] = {
    "pluck": "kotekan",
    "breath": "pad",
    "choir": "bowed",
    "kotekan": "tabla_tin",
    "pad": "pluck",
    "bowed": "breath",
    "tabla_tin": "choir",
}

HOUSE_BOUND_SPACE_VOICE_BY_HOUSE: dict[str, str] = {
    "house_monastery": "choir",
    "house_chamber": "breath",
    "house_garden": "tabla_tin",
    "house_procession": "kotekan",
    "house_workshop": "pluck",
}

DEFAULT_HOUSE_BOUND_HOUSE = "house_chamber"


def _normalize_voice_name(voice: str) -> str:
    normalized = str(voice).strip().lower()
    if normalized.startswith("sw_"):
        normalized = normalized[3:]
    return normalized


def _normalize_mood_mode(value: object) -> str:
    raw = getattr(value, "value", value)
    key = str(raw or "").strip().lower().replace("_", "-").replace(" ", "-")
    if key in {"matched", "expressive", "house-bound"}:
        return key
    return "matched"


def normalize_active_house(active_house: object) -> str:
    """Return a canonical house patch key for space selection."""

    raw = getattr(active_house, "value", active_house)
    key = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in HOUSE_BOUND_SPACE_VOICE_BY_HOUSE:
        return key
    prefixed = f"house_{key}"
    if prefixed in HOUSE_BOUND_SPACE_VOICE_BY_HOUSE:
        return prefixed
    return DEFAULT_HOUSE_BOUND_HOUSE


def mood_mode_from_scene_metadata(scene_metadata: Mapping[str, object] | None) -> str:
    """Return the normalized mood-space mode encoded in scene metadata."""

    metadata = scene_metadata or {}
    return _normalize_mood_mode(
        metadata.get("mood_mode") or metadata.get("space_mode")
    )


def active_house_from_scene_metadata(scene_metadata: Mapping[str, object] | None) -> str:
    """Return the canonical active house encoded in scene metadata."""

    metadata = scene_metadata or {}
    return normalize_active_house(
        metadata.get("active_house") or metadata.get("patch_name")
    )


def iter_voice_reverb_profiles() -> Iterator[VoiceReverbProfile]:
    """Yield profiles in canonical CypherClaw design order."""

    return iter(VOICE_REVERB_PROFILES.values())


def build_voice_s_new_args(
    voice: str,
    *,
    node_id: int,
    freq: float,
    amp: float = 0.06,
    attack: float = 0.01,
    release: float = 1.0,
    add_action: int = 0,
    target_id: int = 0,
    mood_mode: object = "matched",
    active_house: object = None,
) -> list[float | int | str]:
    """Build a `/s_new` OSC arg list routing *voice* into its FX return bus.

    Each voice synthdef exposes an ``fx_bus_id`` control selecting which
    per-voice FX return bus its signal feeds. The bus id comes from the
    voice's :class:`VoiceReverbProfile` so the dry voice signal and the
    matching space reverb share the same return path. Unknown voices fall
    back to the pluck profile (see :func:`get_voice_reverb_profile`).
    """

    voice_profile = get_voice_reverb_profile(voice)
    space_profile = resolve_voice_space_profile(
        voice_profile.voice,
        mood_mode=mood_mode,
        active_house=active_house,
    )
    return [
        f"sw_{voice_profile.voice}",
        int(node_id),
        int(add_action),
        int(target_id),
        "freq", float(freq),
        "amp", float(amp),
        "attack", float(attack),
        "release", float(release),
        "fx_bus_id", int(space_profile.fx_bus_id),
    ]


def get_voice_reverb_profile(voice: str) -> VoiceReverbProfile:
    """Return the matched profile for ``voice`` or the pluck fallback."""

    normalized = _normalize_voice_name(voice)
    return VOICE_REVERB_PROFILES.get(normalized, VOICE_REVERB_PROFILES["pluck"])


def resolve_voice_space_profile(
    voice: str,
    *,
    mood_mode: object = "matched",
    active_house: object = None,
) -> VoiceReverbProfile:
    """Return the reverb profile selected by scene mood-space rules."""

    voice_profile = get_voice_reverb_profile(voice)
    mode = _normalize_mood_mode(mood_mode)
    if mode == "expressive":
        space_voice = EXPRESSIVE_SPACE_VOICE_BY_VOICE[voice_profile.voice]
    elif mode == "house-bound":
        house = normalize_active_house(active_house)
        space_voice = HOUSE_BOUND_SPACE_VOICE_BY_HOUSE[house]
    else:
        space_voice = voice_profile.voice
    return VOICE_REVERB_PROFILES[space_voice]


def resolve_scene_voice_space_profile(
    voice: str,
    scene_metadata: Mapping[str, object] | None,
) -> VoiceReverbProfile:
    """Return the reverb profile selected by a scene's mood-space metadata."""

    return resolve_voice_space_profile(
        voice,
        mood_mode=mood_mode_from_scene_metadata(scene_metadata),
        active_house=active_house_from_scene_metadata(scene_metadata),
    )


def summarize_voice_reverb_profiles() -> dict[str, Any]:
    """Return a JSON-safe summary of all per-voice reverb profiles."""

    default_house_space_voice = HOUSE_BOUND_SPACE_VOICE_BY_HOUSE[
        DEFAULT_HOUSE_BOUND_HOUSE
    ]
    default_house_profile = VOICE_REVERB_PROFILES[default_house_space_voice]
    return {
        "source": SPACE_PROFILE_SOURCE,
        "voice_order": list(VOICE_REVERB_PROFILES),
        "expressive_space_voice_by_voice": dict(EXPRESSIVE_SPACE_VOICE_BY_VOICE),
        "house_bound_space_voice_by_house": dict(HOUSE_BOUND_SPACE_VOICE_BY_HOUSE),
        "default_house_bound_house": DEFAULT_HOUSE_BOUND_HOUSE,
        "default_house_bound_space_voice": default_house_space_voice,
        "default_house_bound_fx_bus_id": default_house_profile.fx_bus_id,
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
