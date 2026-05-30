"""CLI coverage for `promptclaw asset-bus once` (T-019)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from promptclaw import cli as promptclaw_cli

SCHEMA = "deniable-asset-bus/v0.1"


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        rc = promptclaw_cli.main(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


@pytest.fixture(autouse=True)
def _stub_bootstrap_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cypherclaw.first_boot.bootstrap_identity", lambda: None)


def _write_request(bus_root: Path, request_id: str, asset_type: str = "image") -> None:
    request = {
        "request_id": request_id,
        "schema": SCHEMA,
        "asset_type": asset_type,
        "title": f"title-{request_id}",
        "format": "png" if asset_type == "image" else "wav",
        "spec": {"prompt": f"prompt for {request_id}", "count": 1},
    }
    request_path = bus_root / "requests" / f"{request_id}.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request), encoding="utf-8")


def test_once_produces_a_manifest_for_each_pending_request(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    _write_request(bus_root, "req-alpha")
    _write_request(bus_root, "req-beta", asset_type="music")

    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps({"image": "image-renderer", "music": "music-renderer"}),
        encoding="utf-8",
    )

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "once",
            "--bus-root",
            str(bus_root),
            "--matrix",
            str(matrix_path),
        ]
    )

    assert rc == 0, stderr

    alpha_manifest_path = bus_root / "deliverables" / "req-alpha.result.json"
    beta_manifest_path = bus_root / "deliverables" / "req-beta.result.json"
    assert alpha_manifest_path.is_file()
    assert beta_manifest_path.is_file()

    alpha_manifest = json.loads(alpha_manifest_path.read_text(encoding="utf-8"))
    beta_manifest = json.loads(beta_manifest_path.read_text(encoding="utf-8"))
    assert alpha_manifest["request_id"] == "req-alpha"
    assert beta_manifest["request_id"] == "req-beta"
    assert alpha_manifest["schema"] == SCHEMA
    assert beta_manifest["schema"] == SCHEMA

    summary = json.loads(stdout)
    assert sorted(summary["failed"]) == ["req-alpha", "req-beta"]
    assert summary["processed"] == []
    assert summary["partial"] == []
    assert summary["skipped"] == []


def test_once_writes_no_manifest_when_no_pending_requests(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    (bus_root / "requests").mkdir(parents=True)

    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps({"image": "image-renderer"}), encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "once",
            "--bus-root",
            str(bus_root),
            "--matrix",
            str(matrix_path),
        ]
    )

    assert rc == 0, stderr
    assert not (bus_root / "deliverables").exists() or not any(
        (bus_root / "deliverables").iterdir()
    )

    summary = json.loads(stdout)
    assert summary["processed"] == []
    assert summary["failed"] == []
    assert summary["partial"] == []
    assert summary["skipped"] == []


def test_once_skips_requests_with_existing_manifest(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    _write_request(bus_root, "req-already-done")
    deliverables = bus_root / "deliverables"
    deliverables.mkdir(parents=True)
    existing_manifest = {
        "request_id": "req-already-done",
        "schema": SCHEMA,
        "status": "done",
        "producer": "cypherclaw",
        "assets": [],
        "notes": "previously fulfilled",
        "error": None,
    }
    (deliverables / "req-already-done.result.json").write_text(
        json.dumps(existing_manifest), encoding="utf-8"
    )

    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps({"image": "image-renderer"}), encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "once",
            "--bus-root",
            str(bus_root),
            "--matrix",
            str(matrix_path),
        ]
    )

    assert rc == 0, stderr
    summary = json.loads(stdout)
    assert summary["processed"] == []
    assert summary["failed"] == []
    manifest_after = json.loads(
        (deliverables / "req-already-done.result.json").read_text(encoding="utf-8")
    )
    assert manifest_after == existing_manifest


def test_once_reports_invalid_matrix(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    (bus_root / "requests").mkdir(parents=True)

    matrix_path = tmp_path / "bad-matrix.json"
    matrix_path.write_text("{ not json", encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "once",
            "--bus-root",
            str(bus_root),
            "--matrix",
            str(matrix_path),
        ]
    )

    assert rc == 2
    assert stdout == ""
    assert "matrix" in stderr.lower()
