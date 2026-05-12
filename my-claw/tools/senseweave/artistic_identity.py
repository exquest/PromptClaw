"""Identity summaries derived from CypherClaw repertoire."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ArtisticIdentity:
    signature_families: tuple[str, ...]
    signature_patches: tuple[str, ...]
    signature_images: tuple[str, ...]
    statement: str


def _image_hint(song: Mapping[str, object]) -> str:
    title = str(song.get("title", "")).lower()
    hook = str(song.get("hook_text", "")).lower()
    if any(word in f"{title} {hook}" for word in ("room", "threshold", "corner")):
        return "room"
    if any(word in f"{title} {hook}" for word in ("line", "wire", "thread", "circuit")):
        return "line"
    if any(word in f"{title} {hook}" for word in ("light", "glass", "lamp")):
        return "light"
    return "signal"


def derive_artistic_identity(songs: Sequence[Mapping[str, object]]) -> ArtisticIdentity:
    family_counts = Counter(str(song.get("family", "")) for song in songs if song.get("family"))
    patch_counts = Counter(str(song.get("patch_name", "")) for song in songs if song.get("patch_name"))
    image_counts = Counter(_image_hint(song) for song in songs if song)
    families = tuple(name for name, _count in family_counts.most_common(2)) or ("bloom",)
    patches = tuple(name for name, _count in patch_counts.most_common(2)) or ("house_chamber",)
    images = tuple(name for name, _count in image_counts.most_common(2)) or ("signal",)
    statement = (
        f"CypherClaw leans toward {families[0]} forms, speaks through {patches[0]}, "
        f"and returns to {images[0]} imagery."
    )
    return ArtisticIdentity(
        signature_families=families,
        signature_patches=patches,
        signature_images=images,
        statement=statement,
    )
