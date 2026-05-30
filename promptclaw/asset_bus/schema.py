"""Request and manifest models for the Deniable Asset Bus, v0.1.

These dataclasses describe the on-disk JSON contract from
``docs/deniable-asset-bus-spec.md`` v0.1: the ``requests/<request_id>.json``
the Deniable game writes, and the ``deliverables/<request_id>.result.json``
the CypherClaw producer writes back.

The models exist for typed construction and JSON round-tripping. They do not
re-validate ``spec`` payloads by ``asset_type`` — that belongs to the
renderer dispatch layer, not the wire format. Unknown top-level fields raise
``SchemaError`` so producer-side drift surfaces loudly rather than silently
discarding data; the requester is told to ignore unknown fields, which is
the asymmetry the spec calls out.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

__all__ = [
    "MANIFEST_ASSET_FIELDS",
    "MANIFEST_FIELDS",
    "REQUEST_FIELDS",
    "SCHEMA",
    "AssetRequest",
    "ManifestAsset",
    "ManifestStatus",
    "ResultManifest",
    "SchemaError",
]


SCHEMA: Final[str] = "deniable-asset-bus/v0.1"

ManifestStatus = Literal["done", "error", "partial", "deferred"]

REQUEST_FIELDS: Final[tuple[str, ...]] = (
    "request_id",
    "schema",
    "created_at",
    "requester",
    "asset_type",
    "title",
    "format",
    "target_path",
    "priority",
    "acceptance",
    "spec",
)

MANIFEST_FIELDS: Final[tuple[str, ...]] = (
    "request_id",
    "schema",
    "status",
    "produced_at",
    "producer",
    "assets",
    "notes",
    "error",
)

MANIFEST_ASSET_FIELDS: Final[tuple[str, ...]] = (
    "path",
    "type",
    "bytes",
    "sha256",
    "meta",
)


class SchemaError(ValueError):
    """Raised when a request or manifest dict does not match the v0.1 shape."""


def _check_fields(
    data: Mapping[str, Any],
    *,
    allowed: tuple[str, ...],
    required: tuple[str, ...],
    label: str,
) -> None:
    missing = [name for name in required if name not in data]
    if missing:
        raise SchemaError(f"{label} is missing required fields: {missing}")
    unknown = [name for name in data if name not in allowed]
    if unknown:
        raise SchemaError(f"{label} has unknown fields: {unknown}")


@dataclass(frozen=True)
class AssetRequest:
    """Typed view of a ``requests/<request_id>.json`` payload."""

    request_id: str
    created_at: str
    requester: str
    asset_type: str
    title: str
    format: str
    target_path: str
    priority: str
    acceptance: str
    spec: Mapping[str, Any]
    schema: str = SCHEMA

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AssetRequest:
        _check_fields(
            data,
            allowed=REQUEST_FIELDS,
            required=REQUEST_FIELDS,
            label="request",
        )
        spec = data["spec"]
        if not isinstance(spec, Mapping):
            raise SchemaError("request 'spec' must be a JSON object")
        return cls(
            request_id=data["request_id"],
            schema=data["schema"],
            created_at=data["created_at"],
            requester=data["requester"],
            asset_type=data["asset_type"],
            title=data["title"],
            format=data["format"],
            target_path=data["target_path"],
            priority=data["priority"],
            acceptance=data["acceptance"],
            spec=dict(spec),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "schema": self.schema,
            "created_at": self.created_at,
            "requester": self.requester,
            "asset_type": self.asset_type,
            "title": self.title,
            "format": self.format,
            "target_path": self.target_path,
            "priority": self.priority,
            "acceptance": self.acceptance,
            "spec": dict(self.spec),
        }


@dataclass(frozen=True)
class ManifestAsset:
    """Typed view of an entry in a manifest's ``assets`` array."""

    path: str
    type: str
    bytes: int
    sha256: str
    meta: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ManifestAsset:
        _check_fields(
            data,
            allowed=MANIFEST_ASSET_FIELDS,
            required=MANIFEST_ASSET_FIELDS,
            label="manifest asset",
        )
        meta = data["meta"]
        if not isinstance(meta, Mapping):
            raise SchemaError("manifest asset 'meta' must be a JSON object")
        return cls(
            path=data["path"],
            type=data["type"],
            bytes=data["bytes"],
            sha256=data["sha256"],
            meta=dict(meta),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "type": self.type,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class ResultManifest:
    """Typed view of a ``deliverables/<request_id>.result.json`` payload."""

    request_id: str
    status: ManifestStatus
    produced_at: str
    producer: str
    assets: tuple[ManifestAsset, ...] = ()
    notes: str | None = None
    error: str | None = None
    schema: str = SCHEMA

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ResultManifest:
        _check_fields(
            data,
            allowed=MANIFEST_FIELDS,
            required=MANIFEST_FIELDS,
            label="manifest",
        )
        assets_raw = data["assets"]
        if not isinstance(assets_raw, list):
            raise SchemaError("manifest 'assets' must be a list")
        return cls(
            request_id=data["request_id"],
            schema=data["schema"],
            status=data["status"],
            produced_at=data["produced_at"],
            producer=data["producer"],
            assets=tuple(ManifestAsset.from_dict(entry) for entry in assets_raw),
            notes=data["notes"],
            error=data["error"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "schema": self.schema,
            "status": self.status,
            "produced_at": self.produced_at,
            "producer": self.producer,
            "assets": [asset.to_dict() for asset in self.assets],
            "notes": self.notes,
            "error": self.error,
        }
