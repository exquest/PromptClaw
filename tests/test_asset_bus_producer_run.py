"""Tests for the continuous asset-bus producer run mode (T-015)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from promptclaw.asset_bus import (
    BatchProcessResult,
    RendererMatrix,
    RendererRegistry,
    asset_manifest_entry,
    atomic_write_bytes,
    deliverable_dir,
    result_manifest_path,
    run_asset_bus_producer,
)


SCHEMA = "deniable-asset-bus/v0.1"
REQUEST_ID = "run-late-request"


class FakeClock:
    def __init__(self, on_sleep: Callable[[float], None]) -> None:
        self.sleeps: list[float] = []
        self._on_sleep = on_sleep

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._on_sleep(seconds)


def _write_image_request(bus_root: Path, request_id: str, *, title: str) -> None:
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
    asset_path = deliverable_dir(bus_root, request_id) / "late.png"
    atomic_write_bytes(asset_path, b"late image bytes")
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


def test_run_asset_bus_producer_processes_request_added_after_interval(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    matrix = RendererMatrix({"image": "image-renderer-stub"})
    registry = RendererRegistry()

    def renderer(request: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(str(request["request_id"]))
        return _success_manifest(tmp_path, request)

    registry.register("image-renderer-stub", renderer)

    def add_request_after_first_empty_poll(seconds: float) -> None:
        assert seconds == 2.5
        _write_image_request(tmp_path, REQUEST_ID, title="late")

    clock = FakeClock(add_request_after_first_empty_poll)

    result = run_asset_bus_producer(
        tmp_path,
        matrix=matrix,
        registry=registry,
        poll_interval_s=2.5,
        clock=clock,
        max_polls=2,
    )

    assert clock.sleeps == [2.5]
    assert calls == [REQUEST_ID]
    assert result.polls == 2
    assert result.batches[0] == BatchProcessResult()
    assert result.batches[1].processed == (REQUEST_ID,)
    assert result.processed == (REQUEST_ID,)
    assert result.failed == ()
    assert result.partial == ()
    assert result.skipped == ()

    manifest = json.loads(
        result_manifest_path(tmp_path, REQUEST_ID).read_text(encoding="utf-8")
    )
    assert manifest["status"] == "done"
    assert manifest["assets"][0]["path"] == f"deliverables/{REQUEST_ID}/late.png"
    assert (tmp_path / manifest["assets"][0]["path"]).is_file()
