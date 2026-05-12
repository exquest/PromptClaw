"""Character → voice metadata registry.

Each entry maps a character id (e.g. ``voice_sampler``) to a ``voice`` dict
containing the synth name, musical role, register (MIDI note range),
default per-voice params, and any per-mode gain overrides. Downstream
consumers (cast planner, duet composer, dispatch) read these entries to
play notes/grains as the chosen character.
"""
from __future__ import annotations

from typing import Mapping


SAMPLER_SYNTH = "sw_sampler"
SAMPLER_ROLE = "sampler"

#: Default grain/playback params for the sampler voice. Tweakable per-piece
#: by `sampler_dispatch.dispatch_sample(...)`.
SAMPLER_DEFAULT_PARAMS: dict[str, float] = {
    "grain_size_ms": 80.0,
    "density": 12.0,
    "pitch_transpose": 0.0,
}

#: Per-mode amplitude overrides for the sampler voice. Names match the
#: ``ArtistMode.name`` values declared in ``artist_identity``. Modes with
#: high sampler density get more presence; working_ambience pulls back.
SAMPLER_MODE_GAIN_OVERRIDES: dict[str, float] = {
    "solitary": 0.85,
    "companion": 0.55,
    "working_ambience": 0.30,
    "evening_reflection": 0.80,
    "storm": 0.65,
}

VOICE_SAMPLER_ID = "voice_sampler"

VOICE_SAMPLER: dict[str, object] = {
    "voice": {
        "synth": SAMPLER_SYNTH,
        "role": SAMPLER_ROLE,
        "register": [36, 84],
        "params": dict(SAMPLER_DEFAULT_PARAMS),
        "mode_gain_overrides": dict(SAMPLER_MODE_GAIN_OVERRIDES),
    },
}


class CharacterRegistry:
    """In-memory store of organism characters and their voice metadata.

    Acts as the local source of truth for character → voice mapping that
    the cast planner consumes. The deployed registry on cypherclaw also
    holds the visual/expressive characters; this module focuses on the
    voice metadata that downstream Python modules and tests need.
    """

    def __init__(self) -> None:
        self._chars: dict[str, dict[str, object]] = {}
        self.register(VOICE_SAMPLER_ID, VOICE_SAMPLER)

    def register(self, character_id: str, char: Mapping[str, object]) -> None:
        self._chars[character_id] = _deepcopy_char(char)

    def get(self, character_id: str) -> Mapping[str, object]:
        return self._chars[character_id]

    def get_all(self) -> dict[str, dict[str, object]]:
        return {cid: _deepcopy_char(char) for cid, char in self._chars.items()}


def voice_of(char: Mapping[str, object]) -> Mapping[str, object]:
    """Return the embedded ``voice`` mapping for a character entry.

    Raises ``ValueError`` when the input is not a mapping or carries no
    nested ``voice`` dict so misuse fails loudly instead of silently
    returning ``None``.
    """
    if not isinstance(char, Mapping):
        raise ValueError(
            f"character must be a mapping, got {type(char).__name__}"
        )
    voice = char.get("voice")
    if not isinstance(voice, Mapping):
        raise ValueError("character is missing a 'voice' mapping")
    return voice


def mode_gain_for(
    voice: Mapping[str, object],
    mode: str,
    *,
    default: float = 1.0,
) -> float:
    """Return the per-mode gain override for ``voice``.

    Falls back to ``default`` when the voice has no override table, the
    requested mode is missing, or the stored value cannot be coerced
    through ``float()``.
    """
    if not isinstance(voice, Mapping):
        return float(default)
    overrides = voice.get("mode_gain_overrides")
    if not isinstance(overrides, Mapping):
        return float(default)
    if mode not in overrides:
        return float(default)
    raw = overrides[mode]
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float(default)


def params_for(
    voice: Mapping[str, object],
    overrides: Mapping[str, float | None] | None = None,
) -> dict[str, float]:
    """Merge a voice's default ``params`` with caller overrides.

    ``None``-valued overrides are skipped so optional kwargs from
    ``sampler_dispatch`` callers can pass through unchanged. Values that
    cannot be coerced through ``float()`` are dropped rather than raising.
    """
    merged: dict[str, float] = {}
    base = voice.get("params") if isinstance(voice, Mapping) else None
    if isinstance(base, Mapping):
        for key, value in base.items():
            try:
                merged[str(key)] = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
    if overrides:
        for key, value in overrides.items():
            if value is None:
                continue
            try:
                merged[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    return merged


def summarize_registry(registry: CharacterRegistry) -> dict[str, object]:
    """Return aggregate stats across all registered characters."""
    chars = registry.get_all()
    synth_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for char in chars.values():
        voice = char.get("voice") if isinstance(char, Mapping) else None
        if not isinstance(voice, Mapping):
            continue
        synth = voice.get("synth")
        if isinstance(synth, str) and synth:
            synth_counts[synth] = synth_counts.get(synth, 0) + 1
        role = voice.get("role")
        if isinstance(role, str) and role:
            role_counts[role] = role_counts.get(role, 0) + 1
    return {
        "character_count": len(chars),
        "character_ids": sorted(chars.keys()),
        "synth_counts": synth_counts,
        "role_counts": role_counts,
    }


def voices_by_role(registry: CharacterRegistry) -> dict[str, list[str]]:
    """Group registered character IDs by voice role with sorted buckets."""
    grouped: dict[str, list[str]] = {}
    for cid, char in registry.get_all().items():
        voice = char.get("voice") if isinstance(char, Mapping) else None
        if not isinstance(voice, Mapping):
            continue
        role = voice.get("role")
        if not isinstance(role, str) or not role:
            continue
        grouped.setdefault(role, []).append(cid)
    for cid_list in grouped.values():
        cid_list.sort()
    return grouped


def find_voices_by_synth(registry: CharacterRegistry, synth: str) -> list[str]:
    """Return the sorted list of character IDs whose voice synth matches."""
    matches: list[str] = []
    for cid, char in registry.get_all().items():
        voice = char.get("voice") if isinstance(char, Mapping) else None
        if not isinstance(voice, Mapping):
            continue
        if voice.get("synth") == synth:
            matches.append(cid)
    matches.sort()
    return matches


def _deepcopy_char(char: Mapping[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in char.items():
        if isinstance(value, Mapping):
            out[key] = {k: _copy_value(v) for k, v in value.items()}
        else:
            out[key] = _copy_value(value)
    return out


def _copy_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {k: _copy_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy_value(v) for v in value]
    return value
