"""PARE-005 Art Engine — daemon loop replacing the GlyphWeave art generation cycle.

Reads organism state, composes a scene via scene_composer, renders it
through the Pareidolia renderer, and saves PNG + JSON sidecar to the gallery.

Can run standalone (``python pareidolia_art_engine.py``) or be imported
and called programmatically.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from senseweave.scene_composer import (
    compose_scene,
    render_composed_scene,
    save_to_gallery,
)

logger = logging.getLogger(__name__)

ORGANISM_STATE_PATH = "/tmp/organism_state.json"
DEFAULT_GALLERY_DIR = "/home/user/cypherclaw/gallery/renders/"

_DEFAULT_MOOD: dict = {"energy": 0.4, "valence": 0.5, "arousal": 0.3}


def _read_organism_state() -> dict:
    """Read organism state from disk, returning defaults on any error."""
    try:
        with open(ORGANISM_STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"organism_mood": dict(_DEFAULT_MOOD)}


def generate_art_piece(gallery_dir: str = DEFAULT_GALLERY_DIR) -> str:
    """Generate one Pareidolia art piece.

    1. Read organism state (or use defaults).
    2. Compose a scene via scene_composer.
    3. Render to a PIL Image.
    4. Save PNG + JSON sidecar to *gallery_dir*.

    Returns the file path of the saved PNG.
    """
    state = _read_organism_state()
    mood = state.get("organism_mood", dict(_DEFAULT_MOOD))

    spec = compose_scene(mood=mood)
    image = render_composed_scene(spec)
    png_path = save_to_gallery(image, spec, gallery_dir=gallery_dir)

    logger.info("Art piece saved: %s — %s", png_path, spec.title)
    return png_path


def run_art_cycle(
    interval: int = 1800,
    gallery_dir: str = DEFAULT_GALLERY_DIR,
) -> None:
    """Daemon loop: generate a piece every *interval* seconds (default 30 min).

    Runs indefinitely. Catches and logs errors per-cycle so one failure
    does not stop the loop.
    """
    logger.info(
        "PARE-005 art cycle started — interval %ds, gallery %s",
        interval,
        gallery_dir,
    )
    while True:
        try:
            path = generate_art_piece(gallery_dir=gallery_dir)
            logger.info("Cycle complete: %s", path)
        except Exception:
            logger.exception("Art cycle error — will retry next interval")
        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
    )
    run_art_cycle()
