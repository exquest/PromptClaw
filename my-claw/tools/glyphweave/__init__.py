"""GlyphWeave — ASCII+emoji hybrid art for CypherClaw.

Reuses the Canvas DSL from PromptLab with a CypherClaw-specific scene layer.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_DSL_EXPORTS = {
    "Canvas",
    "Animation",
    "Motif",
    "PALETTE_WATER",
    "PALETTE_SPACE",
    "PALETTE_CUTE",
    "PALETTE_DRAGON",
    "PALETTE_NIGHT",
    "PALETTE_UI",
}

_PET_EXPORTS = {"get_frames", "get_portrait", "SPRITES"}

__all__ = [
    "Canvas",
    "Animation",
    "Motif",
    "PALETTE_WATER",
    "PALETTE_SPACE",
    "PALETTE_CUTE",
    "PALETTE_DRAGON",
    "PALETTE_NIGHT",
    "PALETTE_UI",
    "get_frames",
    "get_portrait",
    "SPRITES",
]


def __getattr__(name: str) -> Any:
    if name in _DSL_EXPORTS:
        module = import_module(".dsl", __name__)
    elif name in _PET_EXPORTS:
        module = import_module(".pet_sprites", __name__)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    value = getattr(module, name)
    globals()[name] = value
    return value
