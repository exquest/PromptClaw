"""Tests for renderer dispatch (T-012c).

Dispatch composes the renderer matrix (``asset_type`` → renderer name)
and the registry (name → callable). A missing matrix entry or a missing
renderer must surface as a typed error so a misconfigured deployment
fails loudly rather than silently routing nowhere.
"""

from __future__ import annotations

import pytest

from promptclaw.asset_bus import (
    RendererMatrix,
    RendererRegistry,
    UnknownAssetTypeError,
    UnknownRendererError,
    dispatch_request,
)


def test_dispatch_happy_path_routes_to_named_renderer() -> None:
    matrix = RendererMatrix({"image": "sd-image-renderer"})
    registry = RendererRegistry()
    calls: list[dict[str, object]] = []

    def image_handler(request: dict[str, object]) -> str:
        calls.append(request)
        return "image-bytes"

    registry.register("sd-image-renderer", image_handler)

    request = {"asset_type": "image", "request_id": "req-1"}
    result = dispatch_request(request, matrix, registry)

    assert result == "image-bytes"
    assert calls == [request]


def test_dispatch_routes_each_asset_type_to_its_own_renderer() -> None:
    matrix = RendererMatrix(
        {"image": "sd-image-renderer", "music": "music-renderer"}
    )
    registry = RendererRegistry()
    registry.register("sd-image-renderer", lambda req: ("img", req["request_id"]))
    registry.register("music-renderer", lambda req: ("mus", req["request_id"]))

    assert dispatch_request(
        {"asset_type": "image", "request_id": "a"}, matrix, registry
    ) == ("img", "a")
    assert dispatch_request(
        {"asset_type": "music", "request_id": "b"}, matrix, registry
    ) == ("mus", "b")


def test_dispatch_unknown_asset_type_raises_typed_error() -> None:
    matrix = RendererMatrix({"image": "sd-image-renderer"})
    registry = RendererRegistry()
    registry.register("sd-image-renderer", lambda req: "image-bytes")

    with pytest.raises(UnknownAssetTypeError) as excinfo:
        dispatch_request(
            {"asset_type": "voiceover", "request_id": "x"}, matrix, registry
        )
    assert excinfo.value.asset_type == "voiceover"
    assert "voiceover" in str(excinfo.value)


def test_unknown_asset_type_error_is_a_key_error() -> None:
    matrix = RendererMatrix({"image": "sd-image-renderer"})
    registry = RendererRegistry()
    with pytest.raises(KeyError):
        dispatch_request({"asset_type": "nope"}, matrix, registry)


def test_dispatch_missing_asset_type_field_raises_typed_error() -> None:
    matrix = RendererMatrix({"image": "sd-image-renderer"})
    registry = RendererRegistry()
    registry.register("sd-image-renderer", lambda req: "image-bytes")

    with pytest.raises(UnknownAssetTypeError):
        dispatch_request({"request_id": "x"}, matrix, registry)


def test_dispatch_unknown_renderer_raises_typed_error() -> None:
    # Matrix maps the asset_type to a renderer that nobody registered.
    matrix = RendererMatrix({"image": "ghost-renderer"})
    registry = RendererRegistry()

    with pytest.raises(UnknownRendererError) as excinfo:
        dispatch_request(
            {"asset_type": "image", "request_id": "x"}, matrix, registry
        )
    assert excinfo.value.name == "ghost-renderer"
    assert "ghost-renderer" in str(excinfo.value)


def test_dispatch_does_not_invoke_handler_on_unknown_asset_type() -> None:
    matrix = RendererMatrix({"image": "sd-image-renderer"})
    registry = RendererRegistry()
    calls: list[object] = []
    registry.register("sd-image-renderer", lambda req: calls.append(req))

    with pytest.raises(UnknownAssetTypeError):
        dispatch_request({"asset_type": "unknown"}, matrix, registry)
    assert calls == []
