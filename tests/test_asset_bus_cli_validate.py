"""CLI coverage for `promptclaw asset-bus validate --request FILE` (T-018)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from promptclaw import cli as promptclaw_cli

FIXTURES = Path(__file__).parent / "fixtures" / "asset_bus"


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        rc = promptclaw_cli.main(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


@pytest.fixture(autouse=True)
def _stub_bootstrap_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cypherclaw.first_boot.bootstrap_identity", lambda: None)


def test_validate_prints_normalized_request_and_exits_zero(tmp_path: Path) -> None:
    raw = json.loads((FIXTURES / "request_image.json").read_text(encoding="utf-8"))
    request_path = tmp_path / "req.json"
    request_path.write_text(json.dumps(raw), encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        ["asset-bus", "validate", "--request", str(request_path)]
    )

    assert rc == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload == raw


def test_validate_strips_unknown_fields_from_printed_output(tmp_path: Path) -> None:
    raw = json.loads((FIXTURES / "request_image.json").read_text(encoding="utf-8"))
    raw["unrecognized_top_level"] = "from a future minor"
    request_path = tmp_path / "req.json"
    request_path.write_text(json.dumps(raw), encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        ["asset-bus", "validate", "--request", str(request_path)]
    )

    assert rc == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert "unrecognized_top_level" not in payload
    assert payload["request_id"] == raw["request_id"]


def test_validate_rejects_missing_required_field_with_distinguishable_error(
    tmp_path: Path,
) -> None:
    raw = json.loads((FIXTURES / "request_image.json").read_text(encoding="utf-8"))
    del raw["acceptance"]
    request_path = tmp_path / "req.json"
    request_path.write_text(json.dumps(raw), encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        ["asset-bus", "validate", "--request", str(request_path)]
    )

    assert rc == 1
    assert stdout == ""
    assert "missing required fields" in stderr
    assert "acceptance" in stderr


def test_validate_rejects_wrong_type(tmp_path: Path) -> None:
    raw = json.loads((FIXTURES / "request_image.json").read_text(encoding="utf-8"))
    raw["request_id"] = 12345
    request_path = tmp_path / "req.json"
    request_path.write_text(json.dumps(raw), encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        ["asset-bus", "validate", "--request", str(request_path)]
    )

    assert rc == 1
    assert stdout == ""
    assert "wrong type" in stderr
    assert "'request_id'" in stderr


def test_validate_rejects_invalid_enum_value(tmp_path: Path) -> None:
    raw = json.loads((FIXTURES / "request_image.json").read_text(encoding="utf-8"))
    raw["priority"] = "urgent"
    request_path = tmp_path / "req.json"
    request_path.write_text(json.dumps(raw), encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        ["asset-bus", "validate", "--request", str(request_path)]
    )

    assert rc == 1
    assert stdout == ""
    assert "invalid value" in stderr
    assert "'priority'" in stderr


def test_validate_reports_invalid_json(tmp_path: Path) -> None:
    request_path = tmp_path / "req.json"
    request_path.write_text("{ not json", encoding="utf-8")

    rc, stdout, stderr = _run_cli(
        ["asset-bus", "validate", "--request", str(request_path)]
    )

    assert rc == 2
    assert stdout == ""
    assert "not valid JSON" in stderr


def test_validate_reports_missing_file(tmp_path: Path) -> None:
    request_path = tmp_path / "does-not-exist.json"

    rc, stdout, stderr = _run_cli(
        ["asset-bus", "validate", "--request", str(request_path)]
    )

    assert rc == 2
    assert stdout == ""
    assert "cannot read" in stderr
