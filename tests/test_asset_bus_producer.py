"""Tests for the asset-bus producer batch pass (T-013)."""

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
    process_pending_requests_once,
    result_manifest_path,
)
import promptclaw.asset_bus.producer as producer


SCHEMA = "deniable-asset-bus/v0.1"
REQUEST_OK_1 = "batch-a-ok"
REQUEST_FAIL = "batch-b-fail"
REQUEST_OK_2 = "batch-c-ok"


def _write_request(bus_root: Path, request_id: str, *, title: str) -> None:
    request = {
        "request_id": request_id,
        "schema": SCHEMA,
        "asset_type": "image",
        "title": title,
        "format": "png",
        "spec": {"prompt": f"{title} prompt", "count": 1},
    }
    request_path = bus_root / "requests" / f"{request_id}.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request), encoding="utf-8")


def _success_manifest(
    bus_root: Path,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    request_id = str(request["request_id"])
    asset_name = f"{request['title']}.png"
    asset_path = deliverable_dir(bus_root, request_id) / asset_name
    atomic_write_bytes(asset_path, f"fake image for {request_id}".encode("utf-8"))
    return {
        "request_id": request_id,
        "schema": SCHEMA,
        "status": "done",
        "producer": "cypherclaw",
        "assets": [
            asset_manifest_entry(
                asset_path,
                bus_root,
                asset_type="image",
                meta={"renderer": "image-renderer-stub"},
            )
        ],
        "notes": "image-renderer-stub",
        "error": None,
    }


def test_process_pending_requests_once_writes_manifests_for_batch_despite_one_failure(
    tmp_path: Path,
) -> None:
    _write_request(tmp_path, REQUEST_OK_1, title="first")
    _write_request(tmp_path, REQUEST_FAIL, title="broken")
    _write_request(tmp_path, REQUEST_OK_2, title="third")

    calls: list[str] = []
    matrix = RendererMatrix({"image": "image-renderer-stub"})
    registry = RendererRegistry()

    def renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(request["request_id"])
        calls.append(request_id)
        if request_id == REQUEST_FAIL:
            raise RuntimeError("renderer exploded for this request")
        return _success_manifest(tmp_path, request)

    registry.register("image-renderer-stub", renderer)

    result = process_pending_requests_once(tmp_path, matrix=matrix, registry=registry)

    assert calls == [REQUEST_OK_1, REQUEST_FAIL, REQUEST_OK_2]
    assert result.processed == (REQUEST_OK_1, REQUEST_OK_2)
    assert result.failed == (REQUEST_FAIL,)
    assert result.skipped == ()

    first_manifest = json.loads(
        result_manifest_path(tmp_path, REQUEST_OK_1).read_text(encoding="utf-8")
    )
    failed_manifest = json.loads(
        result_manifest_path(tmp_path, REQUEST_FAIL).read_text(encoding="utf-8")
    )
    third_manifest = json.loads(
        result_manifest_path(tmp_path, REQUEST_OK_2).read_text(encoding="utf-8")
    )

    assert first_manifest["status"] == "done"
    assert third_manifest["status"] == "done"
    assert first_manifest["assets"][0]["path"] == f"deliverables/{REQUEST_OK_1}/first.png"
    assert third_manifest["assets"][0]["path"] == f"deliverables/{REQUEST_OK_2}/third.png"
    assert (tmp_path / first_manifest["assets"][0]["path"]).is_file()
    assert (tmp_path / third_manifest["assets"][0]["path"]).is_file()

    assert failed_manifest["request_id"] == REQUEST_FAIL
    assert failed_manifest["schema"] == SCHEMA
    assert failed_manifest["status"] == "error"
    assert failed_manifest["producer"] == "cypherclaw"
    assert failed_manifest["assets"] == []
    assert "renderer exploded for this request" in failed_manifest["error"]
    assert "failed" in failed_manifest["notes"].lower()


def test_process_pending_requests_once_reports_between_pass_skip_without_rewriting(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_request(tmp_path, REQUEST_OK_1, title="first")
    manifest_path = result_manifest_path(tmp_path, REQUEST_OK_1)
    original = '{"status": "done", "marker": "other-producer"}'

    def fake_pending_requests(bus_root: Path | str | None = None) -> list[str]:
        assert Path(bus_root) == tmp_path
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(original, encoding="utf-8")
        return [REQUEST_OK_1]

    monkeypatch.setattr(producer, "list_pending_requests", fake_pending_requests)
    matrix = RendererMatrix({"image": "image-renderer-stub"})
    registry = RendererRegistry()
    registry.register(
        "image-renderer-stub",
        lambda request: (_ for _ in ()).throw(
            AssertionError(f"renderer should not run for {request!r}")
        ),
    )

    result = process_pending_requests_once(tmp_path, matrix=matrix, registry=registry)

    assert result.processed == ()
    assert result.failed == ()
    assert result.skipped == (REQUEST_OK_1,)
    assert manifest_path.read_text(encoding="utf-8") == original
