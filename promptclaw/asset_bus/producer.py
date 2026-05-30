"""One-pass producer loop for the Deniable Asset Bus.

This module sits above the single-request store helper. It takes one snapshot
of pending request ids, processes each independently, and converts per-request
failures into v0.1 error manifests so a bad request does not abort the batch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic import atomic_write_text
from .capabilities import RendererMatrix
from .renderers import RendererRegistry
from .store import (
    list_pending_requests,
    process_request_if_pending,
    resolve_bus_root,
    result_manifest_path,
)

__all__ = [
    "BatchProcessResult",
    "process_pending_requests_once",
]


_SCHEMA = "deniable-asset-bus/v0.1"
_PRODUCER = "cypherclaw"


@dataclass(frozen=True)
class BatchProcessResult:
    """Summary of one producer pass over a pending-request snapshot."""

    processed: tuple[str, ...]
    failed: tuple[str, ...]
    skipped: tuple[str, ...]


def _error_manifest(request_id: str, exc: Exception) -> dict[str, Any]:
    reason = str(exc) or exc.__class__.__name__
    return {
        "request_id": request_id,
        "schema": _SCHEMA,
        "status": "error",
        "producer": _PRODUCER,
        "assets": [],
        "notes": "request failed during producer batch processing",
        "error": reason,
    }


def _write_error_manifest(
    bus_root: Path,
    request_id: str,
    exc: Exception,
) -> None:
    manifest_path = result_manifest_path(bus_root, request_id)
    atomic_write_text(
        manifest_path,
        json.dumps(_error_manifest(request_id, exc), indent=2, sort_keys=True),
    )


def process_pending_requests_once(
    bus_root: Path | str | None = None,
    *,
    matrix: RendererMatrix,
    registry: RendererRegistry,
) -> BatchProcessResult:
    """Process the current pending-request snapshot without batch aborts.

    Each request id returned by :func:`list_pending_requests` is processed
    through :func:`process_request_if_pending`, preserving the existing
    idempotent single-request path. Exceptions raised while handling one
    request are converted to an ``error`` manifest for that request, then the
    loop continues to the next pending id.
    """
    root = resolve_bus_root() if bus_root is None else Path(bus_root).expanduser().absolute()
    processed: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []

    for request_id in list_pending_requests(root):
        try:
            did_process = process_request_if_pending(
                root,
                request_id,
                matrix=matrix,
                registry=registry,
            )
        except Exception as exc:
            _write_error_manifest(root, request_id, exc)
            failed.append(request_id)
            continue

        if did_process:
            processed.append(request_id)
        else:
            skipped.append(request_id)

    return BatchProcessResult(
        processed=tuple(processed),
        failed=tuple(failed),
        skipped=tuple(skipped),
    )
