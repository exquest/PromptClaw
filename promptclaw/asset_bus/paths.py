"""Path sanitization for the Deniable Asset Bus.

Every path that originates in a request — `target_path`, `style_refs`, asset
filenames written by renderers — is run through these helpers so the producer
cannot be coerced into reading or writing outside the bus's
``deliverables/<request_id>/`` sandbox.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

__all__ = [
    "UnsafePathError",
    "deliverable_dir",
    "safe_deliverable_path",
    "sanitize_request_id",
    "sanitize_target_path",
]


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class UnsafePathError(ValueError):
    """Raised when a path-bearing field would escape the bus sandbox."""


def sanitize_request_id(request_id: str) -> str:
    """Return ``request_id`` if it is a safe directory name, else raise.

    A request id becomes a directory name under ``deliverables/``; anything
    that could be reinterpreted by the filesystem (separators, ``..``, leading
    dot, NUL) is rejected.
    """
    if not isinstance(request_id, str):
        raise UnsafePathError(f"request_id must be a string, got {type(request_id).__name__}")
    if not _REQUEST_ID_RE.match(request_id):
        raise UnsafePathError(f"unsafe request_id: {request_id!r}")
    if request_id in {".", ".."}:
        raise UnsafePathError(f"unsafe request_id: {request_id!r}")
    return request_id


def sanitize_target_path(target_path: str) -> str:
    """Return a normalized, sandbox-safe relative POSIX path.

    Rejects empty strings, absolute paths (POSIX or Windows-style drive),
    ``..`` segments, NUL bytes, and any segment that resolves outside the
    starting directory.
    """
    if not isinstance(target_path, str):
        raise UnsafePathError(
            f"target_path must be a string, got {type(target_path).__name__}"
        )
    if not target_path:
        raise UnsafePathError("target_path must not be empty")
    if "\x00" in target_path:
        raise UnsafePathError("target_path contains NUL byte")

    normalized = target_path.replace("\\", "/")
    if normalized.startswith("/"):
        raise UnsafePathError(f"absolute target_path rejected: {target_path!r}")
    if re.match(r"^[A-Za-z]:", normalized):
        raise UnsafePathError(f"absolute target_path rejected: {target_path!r}")

    pure = PurePosixPath(normalized)
    if pure.is_absolute():
        raise UnsafePathError(f"absolute target_path rejected: {target_path!r}")

    parts = [p for p in pure.parts if p not in ("", ".")]
    if not parts:
        raise UnsafePathError(f"target_path resolves to empty: {target_path!r}")
    for part in parts:
        if part == "..":
            raise UnsafePathError(f"path traversal in target_path: {target_path!r}")
        if "/" in part or "\\" in part:
            raise UnsafePathError(f"unsafe segment in target_path: {target_path!r}")

    return "/".join(parts)


def deliverable_dir(bus_root: Path | str, request_id: str) -> Path:
    """Return the resolved ``<bus_root>/deliverables/<request_id>/`` directory.

    ``bus_root`` is expanded and resolved; ``request_id`` is sanitized.
    """
    safe_id = sanitize_request_id(request_id)
    root = Path(bus_root).expanduser().resolve()
    return root / "deliverables" / safe_id


def safe_deliverable_path(
    bus_root: Path | str, request_id: str, name: str
) -> Path:
    """Resolve a produced-file path under ``deliverables/<request_id>/``.

    ``name`` is treated as a relative path inside the request's deliverable
    directory. Any attempt to escape (absolute path, traversal, symlink-style
    tricks via ``..``) raises :class:`UnsafePathError`.
    """
    target_dir = deliverable_dir(bus_root, request_id)
    relative = sanitize_target_path(name)
    candidate = (target_dir / relative).resolve()
    try:
        candidate.relative_to(target_dir)
    except ValueError as exc:
        raise UnsafePathError(
            f"resolved path escapes deliverable dir: {name!r}"
        ) from exc
    return candidate
