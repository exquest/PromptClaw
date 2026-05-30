"""CLI coverage for `promptclaw asset-bus run` (T-020)."""

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


def _write_request(bus_root: Path, request_id: str) -> None:
    request = {
        "request_id": request_id,
        "schema": SCHEMA,
        "asset_type": "image",
        "title": f"title-{request_id}",
        "format": "png",
        "spec": {"prompt": f"prompt for {request_id}", "count": 1},
    }
    request_path = bus_root / "requests" / f"{request_id}.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request), encoding="utf-8")


def test_run_bounded_by_max_polls_processes_pending_requests(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    _write_request(bus_root, "req-alpha")

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "run",
            "--bus-root",
            str(bus_root),
            "--max-polls",
            "1",
            "--poll-interval-s",
            "0.01",
        ]
    )

    assert rc == 0, stderr
    summary = json.loads(stdout)
    assert summary["polls"] == 1
    assert summary["failed"] == ["req-alpha"]
    assert summary["processed"] == []
    assert summary["partial"] == []
    assert summary["skipped"] == []


def test_run_rejects_invalid_matrix(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    (bus_root / "requests").mkdir(parents=True)
    matrix_path = tmp_path / "bad-matrix.json"
    matrix_path.write_text("{ not json", encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "run",
            "--bus-root",
            str(bus_root),
            "--matrix",
            str(matrix_path),
            "--max-polls",
            "1",
        ]
    )

    assert rc == 2
    assert stdout == ""
    assert "matrix" in stderr.lower()


def test_run_rejects_non_positive_poll_interval(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    (bus_root / "requests").mkdir(parents=True)

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "run",
            "--bus-root",
            str(bus_root),
            "--poll-interval-s",
            "0",
            "--max-polls",
            "1",
        ]
    )

    assert rc == 2
    assert stdout == ""
    assert "poll_interval_s" in stderr


def test_run_with_max_polls_one_does_not_sleep(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    (bus_root / "requests").mkdir(parents=True)

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "run",
            "--bus-root",
            str(bus_root),
            "--max-polls",
            "1",
            "--poll-interval-s",
            "120",
        ]
    )

    assert rc == 0, stderr
    summary = json.loads(stdout)
    assert summary["polls"] == 1
    assert summary["processed"] == []
