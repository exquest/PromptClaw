"""Tests for atomic manifest/produced-file writes (T-005)."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from promptclaw.asset_bus import (
    TMP_SUFFIX,
    atomic_write_bytes,
    atomic_write_text,
)


def test_atomic_write_bytes_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    atomic_write_bytes(target, b'{"status":"ok"}')
    assert target.read_bytes() == b'{"status":"ok"}'


def test_atomic_write_text_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    atomic_write_text(target, '{"status":"ok"}')
    assert target.read_text(encoding="utf-8") == '{"status":"ok"}'


def test_atomic_write_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "deliverables" / "req-abc" / "manifest.json"
    atomic_write_bytes(target, b"data")
    assert target.read_bytes() == b"data"


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    target.write_bytes(b"OLD")
    atomic_write_bytes(target, b"NEW")
    assert target.read_bytes() == b"NEW"


def test_atomic_write_leaves_no_tmp_on_success(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    atomic_write_bytes(target, b"data")
    assert not (tmp_path / f"manifest.json{TMP_SUFFIX}").exists()


def test_atomic_write_goes_through_tmp_then_replace(tmp_path: Path) -> None:
    """Final path must be created by ``os.replace``, not by the writer."""
    target = tmp_path / "manifest.json"
    expected_tmp = tmp_path / f"manifest.json{TMP_SUFFIX}"

    real_replace = os.replace
    observed: dict[str, object] = {}

    def spy(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        observed["src"] = os.fspath(src)
        observed["dst"] = os.fspath(dst)
        observed["tmp_existed_before_replace"] = Path(src).exists()
        observed["final_existed_before_replace"] = Path(dst).exists()
        real_replace(src, dst)

    with patch("promptclaw.asset_bus.atomic.os.replace", side_effect=spy) as mock:
        atomic_write_bytes(target, b"payload")

    assert mock.called
    assert observed["src"] == str(expected_tmp)
    assert observed["dst"] == str(target)
    assert observed["tmp_existed_before_replace"] is True
    assert observed["final_existed_before_replace"] is False
    assert target.read_bytes() == b"payload"


def test_atomic_write_partial_file_not_observable_on_failure(tmp_path: Path) -> None:
    """If the write fails mid-flight the final path must not be created."""
    target = tmp_path / "manifest.json"

    def boom(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise RuntimeError("disk fell over")

    with patch("promptclaw.asset_bus.atomic.os.replace", side_effect=boom):
        with pytest.raises(RuntimeError, match="disk fell over"):
            atomic_write_bytes(target, b"never lands")

    assert not target.exists()
    assert not (tmp_path / f"manifest.json{TMP_SUFFIX}").exists()


def test_atomic_write_keeps_previous_contents_on_failure(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    target.write_bytes(b"PREVIOUS")

    def boom(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("nope")

    with patch("promptclaw.asset_bus.atomic.os.replace", side_effect=boom):
        with pytest.raises(OSError):
            atomic_write_bytes(target, b"NEW")

    assert target.read_bytes() == b"PREVIOUS"
    assert not (tmp_path / f"manifest.json{TMP_SUFFIX}").exists()


def test_atomic_write_no_partial_observed_by_concurrent_reader(tmp_path: Path) -> None:
    """A reader polling the final path sees either the old contents or the
    fully new contents — never a half-written byte stream."""
    target = tmp_path / "manifest.json"
    target.write_bytes(b"OLD")

    payload = b"X" * (1024 * 64)
    stop = threading.Event()
    observations: list[bytes] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                observations.append(target.read_bytes())
            except FileNotFoundError:
                observations.append(b"<missing>")

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        for _ in range(20):
            atomic_write_bytes(target, payload)
    finally:
        stop.set()
        thread.join()

    valid = {b"OLD", payload}
    bad = [obs for obs in observations if obs not in valid]
    assert not bad, f"observed partial write(s): {[len(b) for b in bad[:3]]}"


def test_atomic_write_accepts_str_path(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    atomic_write_bytes(str(target), b"data")
    assert target.read_bytes() == b"data"


def test_atomic_write_text_respects_encoding(tmp_path: Path) -> None:
    target = tmp_path / "manifest.txt"
    atomic_write_text(target, "café", encoding="latin-1")
    assert target.read_bytes() == "café".encode("latin-1")
