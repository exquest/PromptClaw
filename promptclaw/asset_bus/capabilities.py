"""Capability matrix for the Deniable Asset Bus producer.

Single source of truth for what the producer can fulfill, per
``asset_type``. Mirrors the v0.1 spec's "Capability matrix" table in
``docs/deniable-asset-bus-spec.md``. Other modules (routing, deferral,
``doctor``) must consult :data:`CAPABILITIES` rather than re-deriving
the matrix.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final, Literal, Mapping

__all__ = [
    "CAPABILITIES",
    "CapabilityStatus",
    "capability_for",
]


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
