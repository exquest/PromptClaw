"""Atomic file writes for the Deniable Asset Bus.

Producers race the requester's polling loop: the moment a manifest or
produced file appears at its final path, the requester may read it. A
half-written file would be observed as a successful delivery with truncated
content. Every write therefore lands in ``<path>.tmp`` first and is moved
into place with :func:`os.replace`, which is atomic on POSIX and on Windows
(Python 3.3+).
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "TMP_SUFFIX",
    "atomic_write_bytes",
    "atomic_write_text",
]


TMP_SUFFIX: str = ".tmp"


def _tmp_path(path: Path) -> Path:
    return path.with_name(path.name + TMP_SUFFIX)


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically via ``<path>.tmp`` + ``os.replace``.

    Creates the parent directory if missing. On any failure during the write,
    the temp file is removed so it does not linger. Readers either see the
    previous contents (if any) or the complete new contents — never a partial
    file at the final path.
    """
    final = Path(path)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(final)
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, final)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(
    path: Path | str, text: str, encoding: str = "utf-8"
) -> None:
    """Atomic text write — encodes ``text`` and delegates to :func:`atomic_write_bytes`."""
    atomic_write_bytes(path, text.encode(encoding))
