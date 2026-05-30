"""Capability matrix for the Deniable Asset Bus producer.

Single source of truth for what the producer can fulfill, per
``asset_type``. Mirrors the v0.1 spec's "Capability matrix" table in
``docs/deniable-asset-bus-spec.md``. Other modules (routing, deferral,
``doctor``) must consult :data:`CAPABILITIES` rather than re-deriving
the matrix.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Final, Literal, Mapping

__all__ = [
    "CAPABILITIES",
    "CapabilityStatus",
    "build_deferred_manifest",
    "capability_for",
    "is_deferred",
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
