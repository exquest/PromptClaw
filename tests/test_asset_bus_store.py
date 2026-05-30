"""Tests for asset-bus root resolution and pending-request enumeration (T-004)."""

from __future__ import annotations

from pathlib import Path

import pytest

from promptclaw.asset_bus import (
    DEFAULT_BUS_ROOT,
    ENV_VAR,
    list_pending_requests,
    resolve_bus_root,
)


REQUEST_A = "8f3c1d8a-1111-4222-9333-aaaaaaaaaaaa"
REQUEST_B = "8f3c1d8a-1111-4222-9333-bbbbbbbbbbbb"
REQUEST_C = "8f3c1d8a-1111-4222-9333-cccccccccccc"


def _write_request(bus_root: Path, request_id: str) -> None:
    requests_dir = bus_root / "requests"
    requests_dir.mkdir(parents=True, exist_ok=True)
    (requests_dir / f"{request_id}.json").write_text("{}", encoding="utf-8")


def _write_result(bus_root: Path, request_id: str) -> None:
    deliverables_dir = bus_root / "deliverables"
    deliverables_dir.mkdir(parents=True, exist_ok=True)
    (deliverables_dir / f"{request_id}.result.json").write_text("{}", encoding="utf-8")


def test_resolve_bus_root_uses_env_var(tmp_path: Path) -> None:
    target = tmp_path / "custom-bus"
    resolved = resolve_bus_root({ENV_VAR: str(target)})
    assert resolved == target.absolute()


def test_resolve_bus_root_defaults_when_unset() -> None:
    resolved = resolve_bus_root({})
    assert resolved == Path(DEFAULT_BUS_ROOT).expanduser().absolute()


def test_resolve_bus_root_defaults_when_blank() -> None:
    resolved = resolve_bus_root({ENV_VAR: ""})
    assert resolved == Path(DEFAULT_BUS_ROOT).expanduser().absolute()


def test_resolve_bus_root_expands_tilde() -> None:
    resolved = resolve_bus_root({ENV_VAR: "~/some-bus"})
    assert resolved == (Path.home() / "some-bus").absolute()
    assert "~" not in str(resolved)


def test_resolve_bus_root_reads_process_env_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "process-bus"
    monkeypatch.setenv(ENV_VAR, str(target))
    assert resolve_bus_root() == target.absolute()


def test_list_pending_requests_returns_unfulfilled_ids(tmp_path: Path) -> None:
    _write_request(tmp_path, REQUEST_A)
    _write_request(tmp_path, REQUEST_B)
    _write_request(tmp_path, REQUEST_C)
    _write_result(tmp_path, REQUEST_B)

    pending = list_pending_requests(tmp_path)

    assert pending == sorted([REQUEST_A, REQUEST_C])


def test_list_pending_requests_empty_when_all_fulfilled(tmp_path: Path) -> None:
    _write_request(tmp_path, REQUEST_A)
    _write_result(tmp_path, REQUEST_A)

    assert list_pending_requests(tmp_path) == []


def test_list_pending_requests_empty_when_no_requests_dir(tmp_path: Path) -> None:
    assert list_pending_requests(tmp_path) == []


def test_list_pending_requests_empty_when_requests_dir_empty(tmp_path: Path) -> None:
    (tmp_path / "requests").mkdir()
    assert list_pending_requests(tmp_path) == []


def test_list_pending_requests_skips_non_json(tmp_path: Path) -> None:
    requests_dir = tmp_path / "requests"
    requests_dir.mkdir()
    (requests_dir / f"{REQUEST_A}.json").write_text("{}", encoding="utf-8")
    (requests_dir / f"{REQUEST_B}.txt").write_text("nope", encoding="utf-8")
    (requests_dir / f"{REQUEST_C}.json.tmp").write_text("{}", encoding="utf-8")

    assert list_pending_requests(tmp_path) == [REQUEST_A]


def test_list_pending_requests_skips_unsafe_ids(tmp_path: Path) -> None:
    requests_dir = tmp_path / "requests"
    requests_dir.mkdir()
    (requests_dir / f"{REQUEST_A}.json").write_text("{}", encoding="utf-8")
    (requests_dir / ".hidden.json").write_text("{}", encoding="utf-8")

    assert list_pending_requests(tmp_path) == [REQUEST_A]


def test_list_pending_requests_uses_env_when_root_not_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    _write_request(tmp_path, REQUEST_A)
    _write_request(tmp_path, REQUEST_B)
    _write_result(tmp_path, REQUEST_A)

    assert list_pending_requests() == [REQUEST_B]


def test_list_pending_requests_ignores_subdirectories(tmp_path: Path) -> None:
    requests_dir = tmp_path / "requests"
    requests_dir.mkdir()
    (requests_dir / f"{REQUEST_A}.json").write_text("{}", encoding="utf-8")
    (requests_dir / "weird.json").mkdir()

    assert list_pending_requests(tmp_path) == [REQUEST_A]
