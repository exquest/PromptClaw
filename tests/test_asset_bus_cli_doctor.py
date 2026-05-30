"""CLI coverage for `promptclaw asset-bus doctor` (T-020)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from promptclaw import cli as promptclaw_cli
from promptclaw.asset_bus import CAPABILITIES, ENV_VAR


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        rc = promptclaw_cli.main(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


@pytest.fixture(autouse=True)
def _stub_bootstrap_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cypherclaw.first_boot.bootstrap_identity", lambda: None)


def _snapshot_tree(root: Path) -> set[Path]:
    return {p for p in root.rglob("*")}


def test_doctor_reports_bus_paths_runner_and_capabilities(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"

    before = _snapshot_tree(tmp_path)

    rc, stdout, stderr = _run_cli(
        ["asset-bus", "doctor", "--bus-root", str(bus_root)]
    )

    assert rc == 0, stderr
    assert stderr == ""

    after = _snapshot_tree(tmp_path)
    assert after == before

    report = json.loads(stdout)
    assert report["bus_paths"]["bus_root"] == str(bus_root)
    assert report["bus_paths"]["requests_dir"] == str(bus_root / "requests")
    assert report["bus_paths"]["deliverables_dir"] == str(bus_root / "deliverables")
    assert report["bus_paths"]["bus_root_exists"] is False
    assert report["bus_paths"]["requests_dir_exists"] is False
    assert report["bus_paths"]["deliverables_dir_exists"] is False
    assert report["bus_paths"]["env_var"] == ENV_VAR
    assert report["runner"] == "fake"
    assert report["capabilities"] == dict(CAPABILITIES)
    assert report["renderer_matrix"] == {
        "path": None,
        "entries": None,
        "error": None,
    }


def test_doctor_reflects_existing_bus_directories(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    (bus_root / "requests").mkdir(parents=True)
    (bus_root / "deliverables").mkdir(parents=True)

    before = _snapshot_tree(tmp_path)

    rc, stdout, stderr = _run_cli(
        ["asset-bus", "doctor", "--bus-root", str(bus_root)]
    )

    assert rc == 0, stderr
    assert _snapshot_tree(tmp_path) == before

    report = json.loads(stdout)
    assert report["bus_paths"]["bus_root_exists"] is True
    assert report["bus_paths"]["requests_dir_exists"] is True
    assert report["bus_paths"]["deliverables_dir_exists"] is True


def test_doctor_reports_loaded_renderer_matrix(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps({"image": "image-renderer", "music": "music-renderer"}),
        encoding="utf-8",
    )

    before = _snapshot_tree(tmp_path)

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "doctor",
            "--bus-root",
            str(bus_root),
            "--matrix",
            str(matrix_path),
        ]
    )

    assert rc == 0, stderr
    assert _snapshot_tree(tmp_path) == before

    report = json.loads(stdout)
    assert report["renderer_matrix"]["path"] == str(matrix_path)
    assert report["renderer_matrix"]["entries"] == {
        "image": "image-renderer",
        "music": "music-renderer",
    }
    assert report["renderer_matrix"]["error"] is None


def test_doctor_reports_invalid_matrix_without_writing(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    matrix_path = tmp_path / "bad-matrix.json"
    matrix_path.write_text("{ not json", encoding="utf-8")

    before = _snapshot_tree(tmp_path)

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "doctor",
            "--bus-root",
            str(bus_root),
            "--matrix",
            str(matrix_path),
        ]
    )

    assert rc == 0, stderr
    assert _snapshot_tree(tmp_path) == before

    report = json.loads(stdout)
    assert report["renderer_matrix"]["entries"] is None
    assert report["renderer_matrix"]["error"] is not None
    assert "json" in report["renderer_matrix"]["error"].lower()


def test_doctor_accepts_runner_override(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"

    rc, stdout, stderr = _run_cli(
        [
            "asset-bus",
            "doctor",
            "--bus-root",
            str(bus_root),
            "--runner",
            "ssh",
        ]
    )

    assert rc == 0, stderr
    report = json.loads(stdout)
    assert report["runner"] == "ssh"


def test_doctor_does_not_process_pending_requests(tmp_path: Path) -> None:
    bus_root = tmp_path / "bus"
    requests_dir = bus_root / "requests"
    requests_dir.mkdir(parents=True)
    request_path = requests_dir / "req-untouched.json"
    request_path.write_text(
        json.dumps(
            {
                "request_id": "req-untouched",
                "schema": "deniable-asset-bus/v0.1",
                "asset_type": "image",
                "title": "untouched",
                "format": "png",
                "spec": {"prompt": "do not run", "count": 1},
            }
        ),
        encoding="utf-8",
    )
    before = _snapshot_tree(tmp_path)

    rc, _, stderr = _run_cli(
        ["asset-bus", "doctor", "--bus-root", str(bus_root)]
    )

    assert rc == 0, stderr
    assert _snapshot_tree(tmp_path) == before
    assert not (bus_root / "deliverables").exists()
