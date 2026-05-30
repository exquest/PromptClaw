"""Integration tests for request entry-point dispatch wiring (T-012d)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from promptclaw.asset_bus import (
    RendererMatrix,
    RendererRegistry,
    asset_manifest_entry,
    atomic_write_bytes,
    deliverable_dir,
    process_request_if_pending,
    result_manifest_path,
)


SCHEMA = "deniable-asset-bus/v0.1"
IMAGE_REQUEST_ID = "8f3c1d8a-1111-4222-9333-image0000000"
MUSIC_REQUEST_ID = "8f3c1d8a-1111-4222-9333-music0000000"


def _write_request(
    bus_root: Path,
    request_id: str,
    *,
    asset_type: str,
    title: str,
    fmt: str,
    spec: Mapping[str, Any],
) -> None:
    request = {
        "request_id": request_id,
        "schema": SCHEMA,
        "asset_type": asset_type,
        "title": title,
        "format": fmt,
        "spec": dict(spec),
    }
    request_path = bus_root / "requests" / f"{request_id}.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request), encoding="utf-8")


def _manifest(
    bus_root: Path,
    request: Mapping[str, Any],
    *,
    asset_name: str,
    asset_type: str,
    payload: bytes,
    renderer_name: str,
) -> dict[str, Any]:
    request_id = str(request["request_id"])
    asset_path = deliverable_dir(bus_root, request_id) / asset_name
    atomic_write_bytes(asset_path, payload)
    return {
        "request_id": request_id,
        "schema": SCHEMA,
        "status": "done",
        "producer": "cypherclaw",
        "assets": [
            asset_manifest_entry(
                asset_path,
                bus_root,
                asset_type=asset_type,
                meta={"renderer": renderer_name},
            )
        ],
        "notes": f"{renderer_name} stub",
        "error": None,
    }


def test_process_request_if_pending_routes_two_asset_types_to_renderer_stubs(
    tmp_path: Path,
) -> None:
    _write_request(
        tmp_path,
        IMAGE_REQUEST_ID,
        asset_type="image",
        title="main-menu-bg",
        fmt="png",
        spec={"prompt": "steel desk dossier", "count": 1},
    )
    _write_request(
        tmp_path,
        MUSIC_REQUEST_ID,
        asset_type="music",
        title="stakeout-loop",
        fmt="wav",
        spec={"scene": "patient surveillance", "duration_seconds": 12},
    )
    calls: list[tuple[str, str]] = []
    matrix = RendererMatrix(
        {"image": "image-renderer-stub", "music": "music-renderer-stub"}
    )
    registry = RendererRegistry()

    def image_renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(("image", str(request["request_id"])))
        return _manifest(
            tmp_path,
            request,
            asset_name="main-menu-bg.png",
            asset_type="image",
            payload=b"\x89PNG\r\n\x1a\nstub-image",
            renderer_name="image-renderer-stub",
        )

    def music_renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(("music", str(request["request_id"])))
        return _manifest(
            tmp_path,
            request,
            asset_name="stakeout-loop.wav",
            asset_type="music",
            payload=b"RIFFstub-music-WAVE",
            renderer_name="music-renderer-stub",
        )

    registry.register("image-renderer-stub", image_renderer)
    registry.register("music-renderer-stub", music_renderer)

    image_processed = process_request_if_pending(
        tmp_path,
        IMAGE_REQUEST_ID,
        matrix=matrix,
        registry=registry,
    )
    music_processed = process_request_if_pending(
        tmp_path,
        MUSIC_REQUEST_ID,
        matrix=matrix,
        registry=registry,
    )

    assert image_processed is True
    assert music_processed is True
    assert calls == [
        ("image", IMAGE_REQUEST_ID),
        ("music", MUSIC_REQUEST_ID),
    ]

    image_manifest = json.loads(
        result_manifest_path(tmp_path, IMAGE_REQUEST_ID).read_text(encoding="utf-8")
    )
    music_manifest = json.loads(
        result_manifest_path(tmp_path, MUSIC_REQUEST_ID).read_text(encoding="utf-8")
    )
    assert image_manifest["status"] == "done"
    assert music_manifest["status"] == "done"
    assert image_manifest["assets"][0]["type"] == "image"
    assert music_manifest["assets"][0]["type"] == "music"
    assert image_manifest["assets"][0]["path"] == (
        f"deliverables/{IMAGE_REQUEST_ID}/main-menu-bg.png"
    )
    assert music_manifest["assets"][0]["path"] == (
        f"deliverables/{MUSIC_REQUEST_ID}/stakeout-loop.wav"
    )
    assert image_manifest["assets"][0]["meta"]["renderer"] == "image-renderer-stub"
    assert music_manifest["assets"][0]["meta"]["renderer"] == "music-renderer-stub"
    assert (tmp_path / image_manifest["assets"][0]["path"]).read_bytes().startswith(
        b"\x89PNG"
    )
    assert (tmp_path / music_manifest["assets"][0]["path"]).read_bytes().startswith(
        b"RIFF"
    )


def test_process_request_if_pending_dispatch_mode_still_noops_when_fulfilled(
    tmp_path: Path,
) -> None:
    manifest_path = result_manifest_path(tmp_path, IMAGE_REQUEST_ID)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    original = '{"status": "done", "marker": "already-rendered"}'
    manifest_path.write_text(original, encoding="utf-8")
    matrix = RendererMatrix({"image": "image-renderer-stub"})
    registry = RendererRegistry()

    def image_renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        raise AssertionError(f"renderer should not be called for {request!r}")

    registry.register("image-renderer-stub", image_renderer)

    processed = process_request_if_pending(
        tmp_path,
        IMAGE_REQUEST_ID,
        matrix=matrix,
        registry=registry,
    )

    assert processed is False
    assert manifest_path.read_text(encoding="utf-8") == original
