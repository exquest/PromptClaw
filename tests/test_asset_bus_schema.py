"""Tests for the asset-bus request/manifest schema models (T-016)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptclaw.asset_bus import (
    ASSET_TYPES,
    FORMATS,
    MANIFEST_ASSET_FIELDS,
    MANIFEST_FIELDS,
    PRIORITIES,
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


def test_validate_request_rejects_non_object_payload() -> None:
    with pytest.raises(SchemaError, match="request must be a JSON object"):
        validate_request("not a dict")  # type: ignore[arg-type]


def test_validate_request_reports_missing_required_field() -> None:
    raw = _load("request_image.json")
    del raw["acceptance"]
    with pytest.raises(SchemaError, match="missing required fields") as excinfo:
        validate_request(raw)
    assert "acceptance" in str(excinfo.value)


def test_validate_request_reports_wrong_type_for_string_field() -> None:
    raw = _load("request_image.json")
    raw["request_id"] = 12345
    with pytest.raises(SchemaError, match="wrong type") as excinfo:
        validate_request(raw)
    msg = str(excinfo.value)
    assert "'request_id'" in msg
    assert "expected str" in msg
    assert "got int" in msg


def test_validate_request_reports_wrong_type_for_spec() -> None:
    raw = _load("request_image.json")
    raw["spec"] = "not an object"
    with pytest.raises(SchemaError, match="wrong type") as excinfo:
        validate_request(raw)
    assert "'spec'" in str(excinfo.value)


def test_validate_request_reports_invalid_asset_type() -> None:
    raw = _load("request_image.json")
    raw["asset_type"] = "hologram"
    with pytest.raises(SchemaError, match="invalid value") as excinfo:
        validate_request(raw)
    msg = str(excinfo.value)
    assert "'asset_type'" in msg
    assert "'hologram'" in msg
    for allowed in ASSET_TYPES:
        assert allowed in msg


def test_validate_request_reports_invalid_format() -> None:
    raw = _load("request_image.json")
    raw["format"] = "tiff"
    with pytest.raises(SchemaError, match="invalid value") as excinfo:
        validate_request(raw)
    assert "'format'" in str(excinfo.value)
    for allowed in FORMATS:
        assert allowed in str(excinfo.value)


def test_validate_request_reports_invalid_priority() -> None:
    raw = _load("request_image.json")
    raw["priority"] = "urgent"
    with pytest.raises(SchemaError, match="invalid value") as excinfo:
        validate_request(raw)
    assert "'priority'" in str(excinfo.value)
    for allowed in PRIORITIES:
        assert allowed in str(excinfo.value)


def test_validate_request_reports_invalid_schema_constant() -> None:
    raw = _load("request_image.json")
    raw["schema"] = "deniable-asset-bus/v9.9"
    with pytest.raises(SchemaError, match="invalid value") as excinfo:
        validate_request(raw)
    msg = str(excinfo.value)
    assert "'schema'" in msg
    assert SCHEMA in msg


@pytest.mark.parametrize("field", REQUEST_FIELDS)
def test_validate_request_reports_each_missing_required_field(field: str) -> None:
    raw = _load("request_image.json")
    del raw[field]
    with pytest.raises(SchemaError, match="missing required fields") as excinfo:
        validate_request(raw)
    assert field in str(excinfo.value)


@pytest.mark.parametrize(
    "field",
    (
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
    ),
)
def test_validate_request_reports_each_string_field_wrong_type(field: str) -> None:
    raw = _load("request_image.json")
    raw[field] = 0
    with pytest.raises(SchemaError, match="wrong type") as excinfo:
        validate_request(raw)
    msg = str(excinfo.value)
    assert f"'{field}'" in msg
    assert "expected str" in msg


@pytest.mark.parametrize("bad_spec", [None, "string", 1, 1.5, True, ["list"]])
def test_validate_request_reports_each_non_object_spec(bad_spec: object) -> None:
    raw = _load("request_image.json")
    raw["spec"] = bad_spec
    with pytest.raises(SchemaError, match="wrong type") as excinfo:
        validate_request(raw)
    assert "'spec'" in str(excinfo.value)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("schema", "deniable-asset-bus/v0.2"),
        ("asset_type", "hologram"),
        ("format", "tiff"),
        ("priority", "urgent"),
    ],
)
def test_validate_request_reports_each_enum_violation(
    field: str, bad_value: str
) -> None:
    raw = _load("request_image.json")
    raw[field] = bad_value
    with pytest.raises(SchemaError, match="invalid value") as excinfo:
        validate_request(raw)
    msg = str(excinfo.value)
    assert f"'{field}'" in msg
    assert repr(bad_value) in msg


def test_validate_request_accepts_each_valid_enum_combination() -> None:
    raw = _load("request_image.json")
    for asset_type in ASSET_TYPES:
        for fmt in FORMATS:
            for priority in PRIORITIES:
                candidate = dict(
                    raw,
                    asset_type=asset_type,
                    format=fmt,
                    priority=priority,
                )
                request = validate_request(candidate)
                assert request.asset_type == asset_type
                assert request.format == fmt
                assert request.priority == priority


def test_validate_request_accepts_unknown_extras_with_each_json_type() -> None:
    raw = _load("request_image.json")
    raw["extra_string"] = "hi"
    raw["extra_int"] = 7
    raw["extra_null"] = None
    raw["extra_list"] = [1, 2, 3]
    raw["extra_object"] = {"nested": {"deep": True}}
    request = validate_request(raw)
    round_tripped = request.to_dict()
    for key in (
        "extra_string",
        "extra_int",
        "extra_null",
        "extra_list",
        "extra_object",
    ):
        assert key not in round_tripped


def test_validate_request_error_categories_are_distinguishable() -> None:
    base = _load("request_image.json")

    missing = dict(base)
    del missing["title"]
    wrong_type = dict(base, request_id=42)
    bad_enum = dict(base, priority="urgent")

    with pytest.raises(SchemaError) as miss_err:
        validate_request(missing)
    with pytest.raises(SchemaError) as type_err:
        validate_request(wrong_type)
    with pytest.raises(SchemaError) as enum_err:
        validate_request(bad_enum)

    messages = {str(miss_err.value), str(type_err.value), str(enum_err.value)}
    assert len(messages) == 3
    assert "missing required fields" in str(miss_err.value)
    assert "wrong type" in str(type_err.value)
    assert "invalid value" in str(enum_err.value)
