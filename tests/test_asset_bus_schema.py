"""Tests for the asset-bus request/manifest schema models (T-016)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptclaw.asset_bus import (
    MANIFEST_ASSET_FIELDS,
    MANIFEST_FIELDS,
    REQUEST_FIELDS,
    SCHEMA,
    AssetRequest,
    ManifestAsset,
    ResultManifest,
    SchemaError,
    validate_request,
)

FIXTURES = Path(__file__).parent / "fixtures" / "asset_bus"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_schema_constant_matches_spec_v01() -> None:
    assert SCHEMA == "deniable-asset-bus/v0.1"


def test_request_field_set_matches_spec() -> None:
    assert set(REQUEST_FIELDS) == {
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
    }


def test_manifest_field_set_matches_spec() -> None:
    assert set(MANIFEST_FIELDS) == {
        "request_id",
        "schema",
        "status",
        "produced_at",
        "producer",
        "assets",
        "notes",
        "error",
    }
    assert set(MANIFEST_ASSET_FIELDS) == {
        "path",
        "type",
        "bytes",
        "sha256",
        "meta",
    }


def test_request_round_trips_fixture() -> None:
    raw = _load("request_image.json")
    request = AssetRequest.from_dict(raw)
    assert request.to_dict() == raw


def test_manifest_round_trips_fixture() -> None:
    raw = _load("manifest_done.json")
    manifest = ResultManifest.from_dict(raw)
    assert manifest.to_dict() == raw


def test_manifest_asset_round_trips_fixture_entry() -> None:
    raw = _load("manifest_done.json")["assets"][0]
    asset = ManifestAsset.from_dict(raw)
    assert asset.to_dict() == raw


def test_request_rejects_missing_field() -> None:
    raw = _load("request_image.json")
    del raw["acceptance"]
    with pytest.raises(SchemaError, match="missing required fields"):
        AssetRequest.from_dict(raw)


def test_request_rejects_unknown_field() -> None:
    raw = _load("request_image.json")
    raw["extra"] = "nope"
    with pytest.raises(SchemaError, match="unknown fields"):
        AssetRequest.from_dict(raw)


def test_manifest_rejects_missing_field() -> None:
    raw = _load("manifest_done.json")
    del raw["produced_at"]
    with pytest.raises(SchemaError, match="missing required fields"):
        ResultManifest.from_dict(raw)


def test_manifest_rejects_unknown_field() -> None:
    raw = _load("manifest_done.json")
    raw["extra"] = "nope"
    with pytest.raises(SchemaError, match="unknown fields"):
        ResultManifest.from_dict(raw)


def test_manifest_rejects_non_list_assets() -> None:
    raw = _load("manifest_done.json")
    raw["assets"] = {"not": "a list"}
    with pytest.raises(SchemaError, match="'assets' must be a list"):
        ResultManifest.from_dict(raw)


def test_request_rejects_non_object_spec() -> None:
    raw = _load("request_image.json")
    raw["spec"] = "not an object"
    with pytest.raises(SchemaError, match="'spec' must be a JSON object"):
        AssetRequest.from_dict(raw)


def test_validate_request_accepts_conforming_fixture() -> None:
    raw = _load("request_image.json")
    request = validate_request(raw)
    assert isinstance(request, AssetRequest)
    assert request.to_dict() == raw


def test_validate_request_silently_ignores_unknown_fields() -> None:
    raw = _load("request_image.json")
    raw["unrecognized_top_level"] = "from a future minor"
    raw["another_extra"] = {"nested": True}
    request = validate_request(raw)
    assert isinstance(request, AssetRequest)
    assert "unrecognized_top_level" not in request.to_dict()
    assert "another_extra" not in request.to_dict()
    assert request.request_id == raw["request_id"]
    assert request.schema == raw["schema"]
