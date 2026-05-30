"""Capability matrix for the Deniable Asset Bus producer.

Single source of truth for what the producer can fulfill, per
``asset_type``. Mirrors the v0.1 spec's "Capability matrix" table in
``docs/deniable-asset-bus-spec.md``. Other modules (routing, deferral,
``doctor``) must consult :data:`CAPABILITIES` rather than re-deriving
the matrix.

Two related structures live here:

* :data:`CAPABILITIES` maps ``asset_type`` to a
  :class:`CapabilityStatus` (``supported`` / ``experimental`` /
  ``deferred``). This is the policy view.
* :class:`RendererMatrix` maps ``asset_type`` to the *name* of the
  renderer that handles it. This is the dispatch view; routing uses it
  to pick a concrete renderer for each request. The matrix is loaded
  from a JSON config file via :func:`load_renderer_matrix`.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Literal, Mapping

__all__ = [
    "CAPABILITIES",
    "CapabilityStatus",
    "RendererMatrix",
    "RendererMatrixError",
    "build_deferred_manifest",
    "capability_for",
    "is_deferred",
    "load_renderer_matrix",
]


_SCHEMA: Final[str] = "deniable-asset-bus/v0.1"
_PRODUCER: Final[str] = "cypherclaw"

_DEFERRAL_NOTES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "voiceover": (
            "voiceover is deferred per the capability matrix: no TTS path is "
            "wired on the producer yet. The same request_id will be fulfilled "
            "once a TTS renderer is available."
        ),
    }
)

_GENERIC_DEFERRAL_NOTE: Final[str] = (
    "asset_type is deferred per the capability matrix; the same request_id "
    "will be fulfilled once a renderer is available."
)


CapabilityStatus = Literal["supported", "experimental", "deferred"]


CAPABILITIES: Final[Mapping[str, CapabilityStatus]] = MappingProxyType(
    {
        "image": "supported",
        "music": "supported",
        "sfx": "experimental",
        "voiceover": "deferred",
    }
)


def capability_for(asset_type: str) -> CapabilityStatus | None:
    """Return the capability status for ``asset_type`` or ``None`` if unknown."""
    return CAPABILITIES.get(asset_type)


def is_deferred(asset_type: str) -> bool:
    """Return ``True`` iff the capability matrix marks ``asset_type`` as deferred.

    Unknown asset types are not deferred — they are simply unsupported and a
    request for one is a validation error handled elsewhere.
    """
    return capability_for(asset_type) == "deferred"


def build_deferred_manifest(request: Mapping[str, Any]) -> dict[str, Any]:
    """Build a v0.1 ``deferred`` manifest for ``request``.

    The renderer is intentionally not consulted: the producer cannot fulfill
    this ``asset_type`` yet, but accepts the request and explains the deferral
    in ``notes`` so the requester can plan around it. The same ``request_id``
    remains usable for a later fulfilled manifest once a renderer is wired.
    """
    asset_type = request.get("asset_type")
    if isinstance(asset_type, str):
        notes = _DEFERRAL_NOTES.get(asset_type, _GENERIC_DEFERRAL_NOTE)
    else:
        notes = _GENERIC_DEFERRAL_NOTE
    return {
        "request_id": request.get("request_id"),
        "schema": _SCHEMA,
        "status": "deferred",
        "producer": _PRODUCER,
        "assets": [],
        "notes": notes,
        "error": None,
    }


class RendererMatrixError(ValueError):
    """Raised when a renderer-matrix config is missing or malformed."""


class RendererMatrix(Mapping[str, str]):
    """Immutable mapping of ``asset_type`` to renderer name.

    Routing consults this matrix to pick a concrete renderer for each
    request's ``asset_type``. Entries are validated at construction:
    every ``asset_type`` must be unique and every renderer name must be
    a non-empty string.
    """

    __slots__ = ("_entries",)

    def __init__(self, entries: Mapping[str, str]) -> None:
        self._entries: Mapping[str, str] = MappingProxyType(dict(entries))

    def __getitem__(self, asset_type: str) -> str:
        return self._entries[asset_type]

    def __iter__(self):
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"RendererMatrix({dict(self._entries)!r})"


def _parse_renderer_entries(raw: Any) -> dict[str, str]:
    """Validate ``raw`` parsed config and return a clean asset_type → renderer dict.

    Accepts either:

    * a JSON object: ``{"image": "sd-image-renderer", ...}`` — keys are
      asset types, values are renderer names; or
    * a list of entries: ``[{"asset_type": "image", "renderer": "..."}, ...]``
      — useful for hand-edited configs where order matters and
      duplicates can sneak in.

    Raises :class:`RendererMatrixError` on any malformed entry.
    """
    entries: dict[str, str] = {}

    if isinstance(raw, dict):
        items: list[tuple[Any, Any]] = list(raw.items())
    elif isinstance(raw, list):
        items = []
        for index, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise RendererMatrixError(
                    f"entry at index {index} is not an object: {entry!r}"
                )
            if "asset_type" not in entry or "renderer" not in entry:
                raise RendererMatrixError(
                    f"entry at index {index} missing 'asset_type' or 'renderer': {entry!r}"
                )
            items.append((entry["asset_type"], entry["renderer"]))
    else:
        raise RendererMatrixError(
            f"renderer matrix must be a JSON object or list of entries, got {type(raw).__name__}"
        )

    for asset_type, renderer in items:
        if not isinstance(asset_type, str) or not asset_type:
            raise RendererMatrixError(
                f"asset_type must be a non-empty string, got {asset_type!r}"
            )
        if not isinstance(renderer, str) or not renderer.strip():
            raise RendererMatrixError(
                f"renderer name for asset_type {asset_type!r} must be a non-empty string, got {renderer!r}"
            )
        if asset_type in entries:
            raise RendererMatrixError(
                f"duplicate asset_type {asset_type!r} in renderer matrix"
            )
        entries[asset_type] = renderer

    if not entries:
        raise RendererMatrixError("renderer matrix is empty")

    return entries


def load_renderer_matrix(path: str | Path) -> RendererMatrix:
    """Load a :class:`RendererMatrix` from a JSON config file at ``path``.

    Raises :class:`RendererMatrixError` if the file is missing, is not
    valid JSON, or contains malformed entries (non-unique asset_types,
    empty renderer names, wrong shape).
    """
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RendererMatrixError(
            f"renderer matrix config not found: {config_path}"
        ) from exc

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RendererMatrixError(
            f"renderer matrix config is not valid JSON ({config_path}): {exc.msg}"
        ) from exc

    return RendererMatrix(_parse_renderer_entries(raw))
