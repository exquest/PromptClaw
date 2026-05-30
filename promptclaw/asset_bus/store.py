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

import os
from collections.abc import Mapping
from pathlib import Path

from .paths import UnsafePathError, sanitize_request_id

__all__ = [
    "DEFAULT_BUS_ROOT",
    "ENV_VAR",
    "list_pending_requests",
    "resolve_bus_root",
]


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
