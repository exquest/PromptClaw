"""Tests for asset-bus per-request resource ceilings (T-003)."""

from __future__ import annotations

import pytest

from promptclaw.asset_bus import (
    MAX_IMAGES_PER_REQUEST,
    MAX_MUSIC_DURATION_SECONDS,
    MAX_TOTAL_OUTPUT_BYTES,
    CeilingExceededError,
    check_request_within_ceilings,
    error_manifest_for_ceiling,
)


REQUEST_ID = "8f3c1d8a-1111-4222-9333-abcdef012345"


def _image_request(**spec_overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "prompt": "noir dossier",
        "width": 512,
        "height": 512,
        "count": 1,
    }
    spec.update(spec_overrides)
    return {
        "request_id": REQUEST_ID,
        "schema": "deniable-asset-bus/v0.1",
        "asset_type": "image",
        "spec": spec,
    }


def _music_request(**spec_overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "scene": "tense stakeout",
        "duration_seconds": 60,
    }
    spec.update(spec_overrides)
    return {
        "request_id": REQUEST_ID,
        "schema": "deniable-asset-bus/v0.1",
        "asset_type": "music",
        "spec": spec,
    }


def test_image_within_ceilings_is_accepted() -> None:
    check_request_within_ceilings(_image_request(count=MAX_IMAGES_PER_REQUEST))


def test_image_count_over_ceiling_is_rejected() -> None:
    with pytest.raises(CeilingExceededError) as excinfo:
        check_request_within_ceilings(_image_request(count=MAX_IMAGES_PER_REQUEST + 1))
    assert excinfo.value.ceiling == "image_count"
    assert excinfo.value.limit == MAX_IMAGES_PER_REQUEST
    assert excinfo.value.requested == MAX_IMAGES_PER_REQUEST + 1


def test_music_within_duration_ceiling_is_accepted() -> None:
    check_request_within_ceilings(
        _music_request(duration_seconds=MAX_MUSIC_DURATION_SECONDS)
    )


def test_music_duration_over_ceiling_is_rejected() -> None:
    with pytest.raises(CeilingExceededError) as excinfo:
        check_request_within_ceilings(
            _music_request(duration_seconds=MAX_MUSIC_DURATION_SECONDS + 1)
        )
    assert excinfo.value.ceiling == "music_duration_seconds"
    assert excinfo.value.limit == MAX_MUSIC_DURATION_SECONDS


def test_image_total_output_bytes_over_ceiling_is_rejected() -> None:
    # 4 images × 4096 × 4096 × 4 bytes = 256 MiB exactly; one more byte trips it.
    with pytest.raises(CeilingExceededError) as excinfo:
        check_request_within_ceilings(
            _image_request(count=8, width=4096, height=4096)
        )
    assert excinfo.value.ceiling == "total_output_bytes"
    assert excinfo.value.limit == MAX_TOTAL_OUTPUT_BYTES


def test_non_image_non_music_asset_types_are_not_checked() -> None:
    check_request_within_ceilings(
        {
            "request_id": REQUEST_ID,
            "schema": "deniable-asset-bus/v0.1",
            "asset_type": "voiceover",
            "spec": {"script": "x" * 100_000, "character": "handler"},
        }
    )


def test_missing_spec_uses_safe_defaults() -> None:
    check_request_within_ceilings(
        {
            "request_id": REQUEST_ID,
            "schema": "deniable-asset-bus/v0.1",
            "asset_type": "image",
        }
    )


def test_non_numeric_count_field_falls_back_to_default() -> None:
    check_request_within_ceilings(_image_request(count="lots"))  # type: ignore[arg-type]


def test_error_manifest_states_exceeded_ceiling() -> None:
    request = _image_request(count=MAX_IMAGES_PER_REQUEST + 50)
    try:
        check_request_within_ceilings(request)
    except CeilingExceededError as err:
        manifest = error_manifest_for_ceiling(request, err)
    else:
        pytest.fail("expected CeilingExceededError")

    assert manifest["request_id"] == REQUEST_ID
    assert manifest["schema"] == "deniable-asset-bus/v0.1"
    assert manifest["status"] == "error"
    assert manifest["assets"] == []
    assert "image_count" in manifest["notes"]
    assert "image_count" in manifest["error"]
    assert str(MAX_IMAGES_PER_REQUEST) in manifest["error"]


def test_error_manifest_for_music_duration() -> None:
    request = _music_request(duration_seconds=MAX_MUSIC_DURATION_SECONDS * 10)
    try:
        check_request_within_ceilings(request)
    except CeilingExceededError as err:
        manifest = error_manifest_for_ceiling(request, err)
    else:
        pytest.fail("expected CeilingExceededError")

    assert manifest["status"] == "error"
    assert "music_duration_seconds" in manifest["error"]
