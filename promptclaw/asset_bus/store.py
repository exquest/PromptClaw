"""Bus root resolution and pending-request enumeration.

The Deniable Asset Bus is a directory on disk shared between the requester
(Deniable) and the producer (CypherClaw). Its location is controlled by the
``DENIABLE_ASSET_BUS`` environment variable, defaulting to
``~/deniable-asset-bus``. Within it:

- ``requests/<request_id>.json`` is written by the requester.
- ``deliverables/<request_id>.result.json`` is written by the producer when
  the request has been fulfilled (or errored / deferred).

A request is "pending" when its request file exists but no matching result
manifest does. This module exposes the two primitives the producer's polling
loop needs: :func:`resolve_bus_root` and :func:`list_pending_requests`.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .atomic import atomic_write_text
from .capabilities import RendererMatrix
from .dispatch import dispatch_request
from .paths import UnsafePathError, sanitize_request_id
from .renderers import RendererRegistry

__all__ = [
    "DEFAULT_BUS_ROOT",
    "ENV_VAR",
    "asset_manifest_entry",
    "list_pending_requests",
    "process_request_if_pending",
    "resolve_bus_root",
    "result_manifest_path",
]


_HASH_CHUNK_BYTES: int = 1024 * 1024


ENV_VAR: str = "DENIABLE_ASSET_BUS"
DEFAULT_BUS_ROOT: str = "~/deniable-asset-bus"

_REQUEST_SUFFIX: str = ".json"
_RESULT_SUFFIX: str = ".result.json"


def resolve_bus_root(env: Mapping[str, str] | None = None) -> Path:
    """Return the bus root directory as an expanded, absolute :class:`Path`.

    If ``env`` is ``None`` the process environment is consulted. The value of
    ``$DENIABLE_ASSET_BUS`` is used when set and non-empty; otherwise
    ``~/deniable-asset-bus``. The returned path is expanded (``~``) and made
    absolute, but is not required to exist.
    """
    source = os.environ if env is None else env
    raw = source.get(ENV_VAR) or DEFAULT_BUS_ROOT
    return Path(raw).expanduser().absolute()


def list_pending_requests(bus_root: Path | str | None = None) -> list[str]:
    """Return request ids in ``requests/`` that have no result manifest.

    A request file is ``requests/<request_id>.json``; its fulfillment marker
    is ``deliverables/<request_id>.result.json``. Files whose stem does not
    pass :func:`sanitize_request_id` are skipped — they cannot have been
    written by a conforming requester and would be unsafe to route. Results
    are sorted for deterministic ordering.

    A missing ``requests/`` directory yields an empty list rather than an
    error so the polling loop can start before the requester has written
    anything.
    """
    root = Path(bus_root).expanduser().absolute() if bus_root is not None else resolve_bus_root()
    requests_dir = root / "requests"
    deliverables_dir = root / "deliverables"

    if not requests_dir.is_dir():
        return []

    pending: list[str] = []
    for entry in requests_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix != _REQUEST_SUFFIX:
            continue
        request_id = entry.stem
        try:
            sanitize_request_id(request_id)
        except UnsafePathError:
            continue
        manifest = deliverables_dir / f"{request_id}{_RESULT_SUFFIX}"
        if manifest.exists():
            continue
        pending.append(request_id)

    pending.sort()
    return pending


def asset_manifest_entry(
    asset_path: Path | str,
    bus_root: Path | str,
    *,
    asset_type: str,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a manifest entry describing a produced asset.

    The entry's ``path`` is the asset's location expressed as a POSIX-style
    string relative to ``bus_root`` — manifests are portable across machines,
    so absolute paths must not leak in. ``bytes`` is the file size and
    ``sha256`` is a hex digest of its contents, both read from disk so the
    manifest cannot disagree with what was actually written. ``meta`` is
    passed through unchanged; callers own its shape.

    Raises :class:`UnsafePathError` if ``asset_path`` is not located under
    ``bus_root``.
    """
    root = Path(bus_root).expanduser().resolve()
    asset = Path(asset_path).expanduser().resolve()
    try:
        relative = asset.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(
            f"asset path {asset_path!r} is not under bus root {bus_root!r}"
        ) from exc

    size = asset.stat().st_size
    digest = hashlib.sha256()
    with open(asset, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)

    entry: dict[str, Any] = {
        "path": relative.as_posix(),
        "type": asset_type,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "meta": dict(meta) if meta is not None else {},
    }
    return entry


def result_manifest_path(bus_root: Path | str, request_id: str) -> Path:
    """Return the result-manifest path for ``request_id`` under ``bus_root``.

    The path is ``<bus_root>/deliverables/<request_id>.result.json``;
    ``request_id`` is sanitized so callers cannot escape the deliverables
    directory. The file is not required to exist.
    """
    safe_id = sanitize_request_id(request_id)
    root = Path(bus_root).expanduser().absolute()
    return root / "deliverables" / f"{safe_id}{_RESULT_SUFFIX}"


def _request_file_path(bus_root: Path | str, request_id: str) -> Path:
    safe_id = sanitize_request_id(request_id)
    root = Path(bus_root).expanduser().absolute()
    return root / "requests" / f"{safe_id}{_REQUEST_SUFFIX}"


def _read_request_file(bus_root: Path | str, request_id: str) -> Mapping[str, Any]:
    request_path = _request_file_path(bus_root, request_id)
    raw = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"request file must contain a JSON object: {request_path}")
    return raw


def _dispatch_request_manifest(
    bus_root: Path | str,
    request_id: str,
    matrix: RendererMatrix,
    registry: RendererRegistry,
) -> Mapping[str, Any]:
    request = _read_request_file(bus_root, request_id)
    manifest = dispatch_request(request, matrix, registry)
    if not isinstance(manifest, Mapping):
        raise TypeError(
            "asset-bus renderer must return a mapping-shaped result manifest"
        )
    return manifest


def process_request_if_pending(
    bus_root: Path | str,
    request_id: str,
    render: Callable[[], Mapping[str, Any]] | None = None,
    *,
    matrix: RendererMatrix | None = None,
    registry: RendererRegistry | None = None,
) -> bool:
    """Render and write the result manifest unless one already exists.

    ``request_id`` keys the deliverable; if its result manifest is already on
    disk this is a no-op — no request file is read, no renderer is invoked, and
    the existing manifest is not rewritten.

    Existing callback callers can pass ``render`` directly. Producer callers
    can instead pass ``matrix`` and ``registry``; the request JSON is read from
    ``requests/<request_id>.json`` and routed through
    :func:`promptclaw.asset_bus.dispatch.dispatch_request`.

    Returns ``True`` if rendering occurred, ``False`` if the request was
    already fulfilled. The idempotency check is a single ``exists()`` and is
    not synchronized — two concurrent producers may both render, but the
    atomic write keeps the manifest readable at all times.
    """
    manifest_path = result_manifest_path(bus_root, request_id)
    if manifest_path.exists():
        return False
    if render is None:
        if matrix is None or registry is None:
            raise ValueError(
                "process_request_if_pending requires either render or both "
                "matrix and registry"
            )
        manifest = _dispatch_request_manifest(
            bus_root,
            request_id,
            matrix,
            registry,
        )
    else:
        manifest = render()
    atomic_write_text(
        manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True),
    )
    return True
