"""One-pass producer loop for the Deniable Asset Bus.

This module sits above the single-request store helper. It takes one snapshot
of pending request ids, processes each independently, and classifies the
written manifest by status: ``done`` requests land in ``processed``, ``partial``
in ``partial``, anything else (including renderer/runner exceptions) in
``failed``. Per-request failures never abort the batch — a bad request is
converted into a v0.1 ``error`` manifest so the requester still gets a verdict.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

from .atomic import atomic_write_text
from .capabilities import RendererMatrix
from .dispatch import dispatch_request
from .paths import sanitize_request_id
from .renderers import RendererRegistry
from .store import (
    list_pending_requests,
    process_request_if_pending,
    resolve_bus_root,
    result_manifest_path,
)

__all__ = [
    "BatchProcessResult",
    "ProducerClock",
    "ProducerRunResult",
    "SystemProducerClock",
    "build_error_manifest",
    "build_partial_manifest",
    "process_pending_requests_once",
    "run_asset_bus_producer",
]


_SCHEMA = "deniable-asset-bus/v0.1"
_PRODUCER = "cypherclaw"
_DEFAULT_ERROR_NOTES = "request failed during producer batch processing"
_DEFAULT_PARTIAL_NOTES = "renderer produced some but not all expected assets"


@dataclass(frozen=True)
class BatchProcessResult:
    """Summary of one producer pass over a pending-request snapshot."""

    processed: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    partial: tuple[str, ...] = field(default=())


class ProducerClock(Protocol):
    """Clock boundary used by the continuous producer loop."""

    def sleep(self, seconds: float) -> None: ...


@dataclass(frozen=True)
class SystemProducerClock:
    """Real clock implementation for production producer runs."""

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True)
class ProducerRunResult:
    """Summary of a bounded producer run."""

    polls: int = 0
    batches: tuple[BatchProcessResult, ...] = ()

    @property
    def processed(self) -> tuple[str, ...]:
        return tuple(request_id for batch in self.batches for request_id in batch.processed)

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(request_id for batch in self.batches for request_id in batch.failed)

    @property
    def skipped(self) -> tuple[str, ...]:
        return tuple(request_id for batch in self.batches for request_id in batch.skipped)

    @property
    def partial(self) -> tuple[str, ...]:
        return tuple(request_id for batch in self.batches for request_id in batch.partial)


def build_error_manifest(
    request_id: str,
    *,
    error: str,
    notes: str = _DEFAULT_ERROR_NOTES,
) -> dict[str, Any]:
    """Build a v0.1 ``error`` manifest naming ``error`` as the failure reason.

    Used by the producer when a renderer raises and by renderers/runners that
    want to surface a typed failure rather than crash the batch pass.
    """
    return {
        "request_id": request_id,
        "schema": _SCHEMA,
        "status": "error",
        "producer": _PRODUCER,
        "assets": [],
        "notes": notes,
        "error": error,
    }


def build_partial_manifest(
    request_id: str,
    *,
    assets: Iterable[Mapping[str, Any]],
    notes: str = _DEFAULT_PARTIAL_NOTES,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a v0.1 ``partial`` manifest carrying the assets that were produced.

    ``partial`` means some assets landed on disk but the renderer/runner could
    not deliver the full set. ``error`` is optional — when set it carries the
    reason for the shortfall so the requester can decide whether to retry.
    """
    return {
        "request_id": request_id,
        "schema": _SCHEMA,
        "status": "partial",
        "producer": _PRODUCER,
        "assets": [dict(asset) for asset in assets],
        "notes": notes,
        "error": error,
    }


def _error_manifest_from_exception(request_id: str, exc: BaseException) -> dict[str, Any]:
    reason = str(exc) or exc.__class__.__name__
    return build_error_manifest(request_id, error=reason)


def _write_error_manifest(
    bus_root: Path,
    request_id: str,
    exc: BaseException,
) -> None:
    manifest_path = result_manifest_path(bus_root, request_id)
    atomic_write_text(
        manifest_path,
        json.dumps(_error_manifest_from_exception(request_id, exc), indent=2, sort_keys=True),
    )


def _read_request(bus_root: Path, request_id: str) -> Mapping[str, Any]:
    safe_id = sanitize_request_id(request_id)
    request_path = bus_root / "requests" / f"{safe_id}.json"
    raw = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"request file must contain a JSON object: {request_path}")
    return raw


def _build_manifest(
    bus_root: Path,
    request_id: str,
    matrix: RendererMatrix,
    registry: RendererRegistry,
) -> Mapping[str, Any]:
    request = _read_request(bus_root, request_id)
    manifest = dispatch_request(request, matrix, registry)
    if not isinstance(manifest, Mapping):
        raise TypeError(
            "asset-bus renderer must return a mapping-shaped result manifest"
        )
    return manifest


def process_pending_requests_once(
    bus_root: Path | str | None = None,
    *,
    matrix: RendererMatrix,
    registry: RendererRegistry,
) -> BatchProcessResult:
    """Process the current pending-request snapshot without batch aborts.

    Each request id returned by :func:`list_pending_requests` is processed
    through :func:`process_request_if_pending`, preserving the existing
    idempotent single-request path. The renderer's returned manifest is
    inspected: ``done`` → ``processed``, ``partial`` → ``partial``, ``error``
    or any other status → ``failed``. Exceptions raised while handling one
    request are converted to a v0.1 ``error`` manifest for that request and
    counted as ``failed``, then the loop continues to the next pending id.
    """
    root = resolve_bus_root() if bus_root is None else Path(bus_root).expanduser().absolute()
    processed: list[str] = []
    partial: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []

    for request_id in list_pending_requests(root):
        captured: list[Mapping[str, Any]] = []

        def _render(rid: str = request_id) -> Mapping[str, Any]:
            manifest = _build_manifest(root, rid, matrix, registry)
            captured.append(manifest)
            return manifest

        try:
            did_process = process_request_if_pending(root, request_id, _render)
        except Exception as exc:
            _write_error_manifest(root, request_id, exc)
            failed.append(request_id)
            continue

        if not did_process:
            skipped.append(request_id)
            continue

        status = captured[0].get("status") if captured else None
        if status == "partial":
            partial.append(request_id)
        elif status == "error":
            failed.append(request_id)
        else:
            processed.append(request_id)

    return BatchProcessResult(
        processed=tuple(processed),
        failed=tuple(failed),
        skipped=tuple(skipped),
        partial=tuple(partial),
    )


def run_asset_bus_producer(
    bus_root: Path | str | None = None,
    *,
    matrix: RendererMatrix,
    registry: RendererRegistry,
    poll_interval_s: float = 5.0,
    clock: ProducerClock | None = None,
    max_polls: int | None = None,
    stop: Callable[[], bool] | None = None,
) -> ProducerRunResult:
    """Poll the bus continuously and process newly arrived requests.

    The loop performs one immediate poll, sleeps ``poll_interval_s`` between
    polls through ``clock``, and delegates all request work to
    :func:`process_pending_requests_once`. ``max_polls`` bounds the loop for
    tests and smoke invocations; ``None`` runs until interrupted or until
    ``stop`` returns ``True``.
    """
    if poll_interval_s <= 0:
        raise ValueError("poll_interval_s must be positive")
    if max_polls is not None and max_polls <= 0:
        raise ValueError("max_polls must be positive when supplied")

    root = resolve_bus_root() if bus_root is None else Path(bus_root).expanduser().absolute()
    active_clock: ProducerClock = clock if clock is not None else SystemProducerClock()
    batches: list[BatchProcessResult] = []

    while max_polls is None or len(batches) < max_polls:
        if stop is not None and stop():
            break

        batches.append(
            process_pending_requests_once(root, matrix=matrix, registry=registry)
        )

        if max_polls is not None and len(batches) >= max_polls:
            break
        if stop is not None and stop():
            break

        active_clock.sleep(poll_interval_s)

    return ProducerRunResult(polls=len(batches), batches=tuple(batches))
