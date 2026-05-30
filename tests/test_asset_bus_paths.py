"""Tests for asset-bus path sanitization (T-001)."""

from __future__ import annotations

from pathlib import Path

import pytest

from promptclaw.asset_bus import (
    UnsafePathError,
    deliverable_dir,
    safe_deliverable_path,
    sanitize_request_id,
    sanitize_target_path,
)


REQUEST_ID = "8f3c1d8a-1111-4222-9333-abcdef012345"


def test_sanitize_target_path_accepts_simple_relative() -> None:
    assert sanitize_target_path("main-menu-bg.png") == "main-menu-bg.png"
    assert sanitize_target_path("assets/ui/main-menu-bg.png") == "assets/ui/main-menu-bg.png"


def test_sanitize_target_path_strips_redundant_dot_segments() -> None:
    assert sanitize_target_path("./a/b.png") == "a/b.png"
    assert sanitize_target_path("a/./b.png") == "a/b.png"


def test_sanitize_target_path_rejects_traversal() -> None:
    with pytest.raises(UnsafePathError):
        sanitize_target_path("../escape.png")
    with pytest.raises(UnsafePathError):
        sanitize_target_path("assets/../../escape.png")
    with pytest.raises(UnsafePathError):
        sanitize_target_path("a/b/../../../etc/passwd")


def test_sanitize_target_path_rejects_absolute_posix() -> None:
    with pytest.raises(UnsafePathError):
        sanitize_target_path("/etc/passwd")
    with pytest.raises(UnsafePathError):
        sanitize_target_path("/tmp/x.png")


def test_sanitize_target_path_rejects_absolute_windows() -> None:
    with pytest.raises(UnsafePathError):
        sanitize_target_path("C:/Windows/system32")
    with pytest.raises(UnsafePathError):
        sanitize_target_path("\\\\server\\share\\file")


def test_sanitize_target_path_rejects_empty_and_nul() -> None:
    with pytest.raises(UnsafePathError):
        sanitize_target_path("")
    with pytest.raises(UnsafePathError):
        sanitize_target_path("./.")
    with pytest.raises(UnsafePathError):
        sanitize_target_path("a\x00b")


def test_sanitize_target_path_rejects_non_string() -> None:
    with pytest.raises(UnsafePathError):
        sanitize_target_path(None)  # type: ignore[arg-type]
    with pytest.raises(UnsafePathError):
        sanitize_target_path(42)  # type: ignore[arg-type]


def test_sanitize_request_id_accepts_uuid_and_simple_names() -> None:
    assert sanitize_request_id(REQUEST_ID) == REQUEST_ID
    assert sanitize_request_id("abc.123_xyz") == "abc.123_xyz"


def test_sanitize_request_id_rejects_separators_and_dots() -> None:
    for bad in ("..", ".", "../etc", "a/b", "a\\b", ".hidden", "", "x" * 200, "  spaces "):
        with pytest.raises(UnsafePathError):
            sanitize_request_id(bad)


def test_deliverable_dir_lands_under_bus_root(tmp_path: Path) -> None:
    target = deliverable_dir(tmp_path, REQUEST_ID)
    assert target == (tmp_path / "deliverables" / REQUEST_ID).resolve()


def test_safe_deliverable_path_keeps_outputs_in_sandbox(tmp_path: Path) -> None:
    resolved = safe_deliverable_path(tmp_path, REQUEST_ID, "main-menu-bg.png")
    sandbox = (tmp_path / "deliverables" / REQUEST_ID).resolve()
    assert resolved == sandbox / "main-menu-bg.png"
    assert sandbox in resolved.parents


def test_safe_deliverable_path_rejects_absolute_name(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        safe_deliverable_path(tmp_path, REQUEST_ID, "/etc/passwd")


def test_safe_deliverable_path_rejects_traversal_name(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        safe_deliverable_path(tmp_path, REQUEST_ID, "../../escape.png")
    with pytest.raises(UnsafePathError):
        safe_deliverable_path(tmp_path, REQUEST_ID, "subdir/../../escape.png")


def test_safe_deliverable_path_rejects_bad_request_id(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        safe_deliverable_path(tmp_path, "../escape", "x.png")
    with pytest.raises(UnsafePathError):
        safe_deliverable_path(tmp_path, "a/b", "x.png")
