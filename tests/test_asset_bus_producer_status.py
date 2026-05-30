"""Tests for renderer/runner failure and partial outcomes (T-014).

Covers DAB-041: on renderer/runner failure the producer writes an ``error``
manifest carrying the reason; on partial success the manifest's ``status`` is
``partial`` and the request is classified as partial in the batch result.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from promptclaw.asset_bus import (
    BoxRunResult,
    FakeBoxRunner,
    RendererMatrix,
    RendererRegistry,
    asset_manifest_entry,
    atomic_write_bytes,
    build_error_manifest,
    build_partial_manifest,
    deliverable_dir,
    process_pending_requests_once,
    result_manifest_path,
)


SCHEMA = "deniable-asset-bus/v0.1"


def _write_image_request(bus_root: Path, request_id: str, *, title: str) -> None:
    request = {
        "request_id": request_id,
        "schema": SCHEMA,
        "asset_type": "image",
        "title": title,
        "format": "png",
        "spec": {"prompt": f"{title} prompt", "count": 2},
    }
    request_path = bus_root / "requests" / f"{request_id}.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request), encoding="utf-8")


def test_build_error_manifest_includes_reason_and_v01_envelope() -> None:
    manifest = build_error_manifest("req-err", error="renderer exploded")

    assert manifest["request_id"] == "req-err"
    assert manifest["schema"] == SCHEMA
    assert manifest["status"] == "error"
    assert manifest["producer"] == "cypherclaw"
    assert manifest["assets"] == []
    assert manifest["error"] == "renderer exploded"
    assert "failed" in manifest["notes"].lower()


def test_build_partial_manifest_preserves_assets_and_notes() -> None:
    assets = [
        {"path": "deliverables/req-p/a.png", "type": "image", "bytes": 1, "sha256": "x", "meta": {}},
    ]

    manifest = build_partial_manifest(
        "req-p",
        assets=assets,
        notes="1 of 2 frames rendered",
        error="frame-2 renderer timed out",
    )

    assert manifest["request_id"] == "req-p"
    assert manifest["schema"] == SCHEMA
    assert manifest["status"] == "partial"
    assert manifest["producer"] == "cypherclaw"
    assert manifest["assets"] == assets
    assert manifest["assets"] is not assets, "assets list must be copied, not aliased"
    assert manifest["notes"] == "1 of 2 frames rendered"
    assert manifest["error"] == "frame-2 renderer timed out"


def test_renderer_runner_failure_writes_error_manifest_with_reason(tmp_path: Path) -> None:
    request_id = "req-runner-fail"
    _write_image_request(tmp_path, request_id, title="boom")

    matrix = RendererMatrix({"image": "image-renderer-stub"})
    registry = RendererRegistry()

    def renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        # Real renderers will wrap a BoxRunner; simulate a nonzero-exit runner
        # by raising the typed failure they would raise.
        runner = FakeBoxRunner(exit_status=2, stderr="cuda OOM")
        result: BoxRunResult = runner.run(
            ["asset_render_image", "--prompt", "boom"],
            output_dir=tmp_path / "scratch" / str(request["request_id"]),
        )
        if result.exit_status != 0:
            raise RuntimeError(
                f"asset_render_image exited {result.exit_status}: {result.stderr}"
            )
        return {"status": "done"}  # unreachable in this test

    registry.register("image-renderer-stub", renderer)

    result = process_pending_requests_once(tmp_path, matrix=matrix, registry=registry)

    assert result.processed == ()
    assert result.partial == ()
    assert result.skipped == ()
    assert result.failed == (request_id,)

    manifest = json.loads(
        result_manifest_path(tmp_path, request_id).read_text(encoding="utf-8")
    )
    assert manifest["request_id"] == request_id
    assert manifest["schema"] == SCHEMA
    assert manifest["status"] == "error"
    assert manifest["producer"] == "cypherclaw"
    assert manifest["assets"] == []
    assert "exited 2" in manifest["error"]
    assert "cuda OOM" in manifest["error"]


def test_partial_success_writes_partial_manifest_and_classifies_request(
    tmp_path: Path,
) -> None:
    request_id = "req-partial"
    _write_image_request(tmp_path, request_id, title="half")

    matrix = RendererMatrix({"image": "image-renderer-stub"})
    registry = RendererRegistry()

    def renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        rid = str(request["request_id"])
        produced_dir = deliverable_dir(tmp_path, rid)
        produced_path = produced_dir / "half-1.png"
        atomic_write_bytes(produced_path, b"only the first frame landed")
        entry = asset_manifest_entry(
            produced_path,
            tmp_path,
            asset_type="image",
            meta={"frame": 1, "expected_frames": 2},
        )
        return build_partial_manifest(
            rid,
            assets=[entry],
            notes="1 of 2 frames rendered",
            error="frame-2 runner exited 1: oom",
        )

    registry.register("image-renderer-stub", renderer)

    result = process_pending_requests_once(tmp_path, matrix=matrix, registry=registry)

    assert result.processed == ()
    assert result.failed == ()
    assert result.skipped == ()
    assert result.partial == (request_id,)

    manifest = json.loads(
        result_manifest_path(tmp_path, request_id).read_text(encoding="utf-8")
    )
    assert manifest["status"] == "partial"
    assert manifest["request_id"] == request_id
    assert manifest["assets"][0]["path"] == f"deliverables/{request_id}/half-1.png"
    assert manifest["assets"][0]["meta"]["expected_frames"] == 2
    assert manifest["error"] == "frame-2 runner exited 1: oom"
    assert "1 of 2" in manifest["notes"]


def test_mixed_batch_separates_done_partial_and_failed_buckets(tmp_path: Path) -> None:
    _write_image_request(tmp_path, "req-done", title="done")
    _write_image_request(tmp_path, "req-partial", title="partial")
    _write_image_request(tmp_path, "req-error", title="error")

    matrix = RendererMatrix({"image": "image-renderer-stub"})
    registry = RendererRegistry()

    def renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        rid = str(request["request_id"])
        if rid == "req-done":
            produced = deliverable_dir(tmp_path, rid) / "done-1.png"
            atomic_write_bytes(produced, b"full bytes")
            return {
                "request_id": rid,
                "schema": SCHEMA,
                "status": "done",
                "producer": "cypherclaw",
                "assets": [
                    asset_manifest_entry(produced, tmp_path, asset_type="image")
                ],
                "notes": "ok",
                "error": None,
            }
        if rid == "req-partial":
            produced = deliverable_dir(tmp_path, rid) / "partial-1.png"
            atomic_write_bytes(produced, b"partial bytes")
            return build_partial_manifest(
                rid,
                assets=[asset_manifest_entry(produced, tmp_path, asset_type="image")],
                error="frame-2 dropped",
            )
        raise RuntimeError("renderer blew up")

    registry.register("image-renderer-stub", renderer)

    result = process_pending_requests_once(tmp_path, matrix=matrix, registry=registry)

    assert result.processed == ("req-done",)
    assert result.partial == ("req-partial",)
    assert result.failed == ("req-error",)
    assert result.skipped == ()

    error_manifest = json.loads(
        result_manifest_path(tmp_path, "req-error").read_text(encoding="utf-8")
    )
    assert error_manifest["status"] == "error"
    assert "renderer blew up" in error_manifest["error"]

    partial_manifest = json.loads(
        result_manifest_path(tmp_path, "req-partial").read_text(encoding="utf-8")
    )
    assert partial_manifest["status"] == "partial"
    assert partial_manifest["error"] == "frame-2 dropped"


def test_renderer_returning_error_status_classifies_as_failed(tmp_path: Path) -> None:
    """A renderer that catches its own runner failure and returns ``error``
    must still be counted as ``failed`` in the batch result."""
    request_id = "req-renderer-error"
    _write_image_request(tmp_path, request_id, title="handled")

    matrix = RendererMatrix({"image": "image-renderer-stub"})
    registry = RendererRegistry()

    def renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        return build_error_manifest(
            str(request["request_id"]),
            error="runner exited 137: killed",
            notes="renderer caught the failure",
        )

    registry.register("image-renderer-stub", renderer)

    result = process_pending_requests_once(tmp_path, matrix=matrix, registry=registry)

    assert result.failed == (request_id,)
    assert result.processed == ()
    assert result.partial == ()

    manifest = json.loads(
        result_manifest_path(tmp_path, request_id).read_text(encoding="utf-8")
    )
    assert manifest["status"] == "error"
    assert manifest["error"] == "runner exited 137: killed"
    assert manifest["notes"] == "renderer caught the failure"


def test_exception_with_empty_message_uses_class_name_as_reason(tmp_path: Path) -> None:
    request_id = "req-empty-msg"
    _write_image_request(tmp_path, request_id, title="silent")

    matrix = RendererMatrix({"image": "image-renderer-stub"})
    registry = RendererRegistry()

    class SilentRunnerError(RuntimeError):
        pass

    def renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        raise SilentRunnerError()

    registry.register("image-renderer-stub", renderer)

    result = process_pending_requests_once(tmp_path, matrix=matrix, registry=registry)

    assert result.failed == (request_id,)
    manifest = json.loads(
        result_manifest_path(tmp_path, request_id).read_text(encoding="utf-8")
    )
    assert manifest["status"] == "error"
    assert manifest["error"] == "SilentRunnerError"
