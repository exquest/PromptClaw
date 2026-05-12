"""Shared helpers for persisting temporary listener captures."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def persist_capture_alias(source: str | Path, alias: str | Path) -> bool:
    """Copy a fresh capture clip to a stable alias path.

    The listeners often capture into short-lived clip files that are deleted or
    overwritten each cycle. EMSD sample planning needs a stable path, so this
    helper mirrors the latest clip to the configured alias when possible.
    """

    src = Path(source)
    dst = Path(alias)
    try:
        if not src.exists() or src.stat().st_size <= 0:
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        shutil.copy2(src, tmp)
        os.replace(str(tmp), str(dst))
        return True
    except OSError:
        return False
