"""Tests for request-level idempotency (T-007).

Re-processing a ``request_id`` whose result manifest already exists must be a
no-op: the renderer is not called and the existing manifest is not rewritten.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from promptclaw.asset_bus import (
    UnsafePathError,
    process_request_if_pending,
    result_manifest_path,
)


REQUEST_ID = "8f3c1d8a-1111-4222-9333-aaaaaaaaaaaa"


def _manifest_payload(request_id: str) -> dict[str, object]:
    return {
        "request_id": request_id,
        "schema": "deniable-asset-bus/v0.1",
        "status": "done",
        "producer": "cypherclaw",
        "assets": [],
    }


def test_result_manifest_path_is_under_deliverables(tmp_path: Path) -> None:
    path = result_manifest_path(tmp_path, REQUEST_ID)
    assert path == tmp_path.absolute() / "deliverables" / f"{REQUEST_ID}.result.json"


def test_result_manifest_path_rejects_unsafe_request_id(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        result_manifest_path(tmp_path, "../escape")


def test_process_request_if_pending_renders_when_no_manifest(tmp_path: Path) -> None:
    calls: list[int] = []

    def render() -> dict[str, object]:
        calls.append(1)
        return _manifest_payload(REQUEST_ID)

    rendered = process_request_if_pending(tmp_path, REQUEST_ID, render)

    assert rendered is True
    assert calls == [1]
    manifest_path = result_manifest_path(tmp_path, REQUEST_ID)
    assert manifest_path.is_file()
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == _manifest_payload(
        REQUEST_ID
    )


def test_process_request_if_pending_is_noop_when_manifest_exists(
    tmp_path: Path,
) -> None:
    manifest_path = result_manifest_path(tmp_path, REQUEST_ID)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    original = '{"status": "done", "marker": "original"}'
    manifest_path.write_text(original, encoding="utf-8")
    original_mtime_ns = manifest_path.stat().st_mtime_ns

    def render() -> dict[str, object]:
        raise AssertionError("render must not be called when manifest exists")

    rendered = process_request_if_pending(tmp_path, REQUEST_ID, render)

    assert rendered is False
    assert manifest_path.read_text(encoding="utf-8") == original
    assert manifest_path.stat().st_mtime_ns == original_mtime_ns


def test_second_pass_does_no_work_and_does_not_rewrite(tmp_path: Path) -> None:
    calls: list[int] = []

    def render() -> dict[str, object]:
        calls.append(1)
        return _manifest_payload(REQUEST_ID)

    assert process_request_if_pending(tmp_path, REQUEST_ID, render) is True
    manifest_path = result_manifest_path(tmp_path, REQUEST_ID)
    first_bytes = manifest_path.read_bytes()
    first_mtime_ns = manifest_path.stat().st_mtime_ns

    assert process_request_if_pending(tmp_path, REQUEST_ID, render) is False

    assert calls == [1]
    assert manifest_path.read_bytes() == first_bytes
    assert manifest_path.stat().st_mtime_ns == first_mtime_ns


def test_process_request_if_pending_propagates_render_error(tmp_path: Path) -> None:
    class Boom(RuntimeError):
        pass

    def render() -> dict[str, object]:
        raise Boom("renderer failed")

    with pytest.raises(Boom):
        process_request_if_pending(tmp_path, REQUEST_ID, render)

    assert not result_manifest_path(tmp_path, REQUEST_ID).exists()


def test_process_request_if_pending_rejects_unsafe_request_id(tmp_path: Path) -> None:
    def render() -> dict[str, object]:
        raise AssertionError("render must not be called for unsafe id")

    with pytest.raises(UnsafePathError):
        process_request_if_pending(tmp_path, "../escape", render)
