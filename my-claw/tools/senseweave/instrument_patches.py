"""Instrument patch selection for coherent tracker orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class InstrumentPatch:
    """One coherent set of voices for tracker role routing."""

    name: str
    allowed_voices: Mapping[str, frozenset[str]]
    remap: Mapping[tuple[str, str], str]
    fallback: Mapping[str, str]


_SOFT_ALLOWED = {
    "melody": frozenset({"bowed", "choir"}),
    "bass": frozenset({"bowed"}),
    "color": frozenset({"breath", "choir"}),
    "counter": frozenset({"bowed", "choir"}),
}

_CHAMBER_ALLOWED = {
    "melody": frozenset({"pluck", "bowed", "choir"}),
    "bass": frozenset({"pluck", "bowed"}),
    "color": frozenset({"breath", "choir"}),
    "counter": frozenset({"pluck", "bowed", "choir"}),
}

_WORKSHOP_ALLOWED = {
    "melody": frozenset({"pluck", "bowed", "kotekan", "choir"}),
    "bass": frozenset({"pluck", "bowed", "tabla_tin", "kotekan"}),
    "color": frozenset({"breath", "choir"}),
    "counter": frozenset({"pluck", "bowed", "choir", "kotekan"}),
}


INSTRUMENT_PATCHES: dict[str, InstrumentPatch] = {
    "house_monastery": InstrumentPatch(
        name="house_monastery",
        allowed_voices=_SOFT_ALLOWED,
        remap={
            ("melody", "pluck"): "bowed",
            ("melody", "bell"): "bowed",
            ("melody", "kotekan"): "bowed",
            ("bass", "pluck"): "bowed",
            ("bass", "gong"): "bowed",
            ("bass", "tabla_ge"): "bowed",
            ("bass", "tabla_tin"): "bowed",
            ("bass", "kotekan"): "bowed",
            ("color", "bell"): "breath",
            ("color", "metal"): "breath",
            ("color", "grain"): "breath",
            ("color", "pad"): "breath",
            ("counter", "bell"): "choir",
            ("counter", "metal"): "choir",
            ("counter", "grain"): "choir",
            ("counter", "kotekan"): "bowed",
            ("counter", "pad"): "choir",
        },
        fallback={
            "melody": "bowed",
            "bass": "bowed",
            "color": "breath",
            "counter": "choir",
        },
    ),
    "house_chamber": InstrumentPatch(
        name="house_chamber",
        allowed_voices=_CHAMBER_ALLOWED,
        remap={
            ("melody", "bell"): "bowed",
            ("melody", "kotekan"): "pluck",
            ("bass", "gong"): "bowed",
            ("bass", "tabla_ge"): "pluck",
            ("bass", "tabla_tin"): "pluck",
            ("bass", "kotekan"): "pluck",
            ("color", "bell"): "breath",
            ("color", "metal"): "breath",
            ("color", "grain"): "breath",
            ("color", "pad"): "breath",
            ("counter", "bell"): "choir",
            ("counter", "metal"): "choir",
            ("counter", "grain"): "choir",
            ("counter", "kotekan"): "bowed",
            ("counter", "pad"): "choir",
        },
        fallback={
            "melody": "bowed",
            "bass": "pluck",
            "color": "breath",
            "counter": "choir",
        },
    ),
    "house_garden": InstrumentPatch(
        name="house_garden",
        allowed_voices=_CHAMBER_ALLOWED,
        remap={
            ("melody", "bell"): "pluck",
            ("melody", "kotekan"): "pluck",
            ("bass", "gong"): "bowed",
            ("bass", "tabla_ge"): "bowed",
            ("bass", "tabla_tin"): "bowed",
            ("bass", "kotekan"): "pluck",
            ("color", "bell"): "choir",
            ("color", "metal"): "choir",
            ("color", "grain"): "breath",
            ("color", "pad"): "choir",
            ("counter", "bell"): "bowed",
            ("counter", "metal"): "choir",
            ("counter", "grain"): "choir",
            ("counter", "kotekan"): "pluck",
            ("counter", "pad"): "choir",
        },
        fallback={
            "melody": "pluck",
            "bass": "bowed",
            "color": "choir",
            "counter": "bowed",
        },
    ),
    "house_procession": InstrumentPatch(
        name="house_procession",
        allowed_voices=_CHAMBER_ALLOWED,
        remap={
            ("melody", "bell"): "pluck",
            ("melody", "kotekan"): "pluck",
            ("bass", "gong"): "bowed",
            ("bass", "tabla_ge"): "pluck",
            ("bass", "tabla_tin"): "pluck",
            ("bass", "kotekan"): "pluck",
            ("color", "bell"): "breath",
            ("color", "metal"): "breath",
            ("color", "grain"): "breath",
            ("color", "pad"): "breath",
            ("counter", "bell"): "pluck",
            ("counter", "metal"): "choir",
            ("counter", "grain"): "choir",
            ("counter", "kotekan"): "pluck",
            ("counter", "pad"): "choir",
        },
        fallback={
            "melody": "pluck",
            "bass": "pluck",
            "color": "breath",
            "counter": "pluck",
        },
    ),
    "house_workshop": InstrumentPatch(
        name="house_workshop",
        allowed_voices=_WORKSHOP_ALLOWED,
        remap={
            ("melody", "bell"): "bowed",
            ("bass", "gong"): "bowed",
            ("bass", "tabla_ge"): "tabla_tin",
            ("color", "bell"): "breath",
            ("color", "metal"): "choir",
            ("color", "grain"): "breath",
            ("color", "pad"): "breath",
            ("counter", "bell"): "choir",
            ("counter", "metal"): "choir",
            ("counter", "grain"): "choir",
            ("counter", "pad"): "choir",
        },
        fallback={
            "melody": "pluck",
            "bass": "bowed",
            "color": "breath",
            "counter": "choir",
        },
    ),
}


def select_instrument_patch(
    *,
    cadence_state: str | None = None,
    family_name: str | None = None,
    occupancy_state: str | None = None,
    patch_name: str | None = None,
) -> InstrumentPatch:
    """Select the tracker patch that should own this song's orchestration."""

    if patch_name and patch_name in INSTRUMENT_PATCHES:
        return INSTRUMENT_PATCHES[patch_name]

    if cadence_state in {"sleep", "wind_down"} or family_name in {"nocturne", "drift"}:
        return INSTRUMENT_PATCHES["house_monastery"]
    if cadence_state == "away_practice" or family_name == "forge":
        return INSTRUMENT_PATCHES["house_workshop"]
    if family_name == "pulse":
        return INSTRUMENT_PATCHES["house_procession"]
    if family_name == "bloom" or occupancy_state == "occupied_active":
        return INSTRUMENT_PATCHES["house_garden"]
    return INSTRUMENT_PATCHES["house_chamber"]


def normalize_patch_voice(
    role: str,
    voice: str,
    *,
    patch: InstrumentPatch,
) -> str:
    """Map a candidate voice into the chosen patch's coherent palette."""

    remapped = patch.remap.get((role, voice))
    if remapped is not None:
        return remapped

    allowed = patch.allowed_voices.get(role)
    if allowed is None or voice in allowed:
        return voice

    return patch.fallback.get(role, voice)
