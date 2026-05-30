"""Tests for asset manifest entry construction (T-006)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from promptclaw.asset_bus import (
    UnsafePathError,
    asset_manifest_entry,
)


REQUEST_ID = "8f3c1d8a-1111-4222-9333-aaaaaaaaaaaa"


def _write_asset(bus_root: Path, name: str, payload: bytes) -> Path:
    deliverable = bus_root / "deliverables" / REQUEST_ID
    deliverable.mkdir(parents=True, exist_ok=True)
    target = deliverable / name
    target.write_bytes(payload)
    return target


def test_records_sha256_and_byte_size_from_fixture_bytes(tmp_path: Path) -> None:
    payload = b"the quick brown fox jumps over the lazy dog\n" * 17
    asset = _write_asset(tmp_path, "main-menu-bg.png", payload)

    entry = asset_manifest_entry(asset, tmp_path, asset_type="image")

    assert entry["bytes"] == len(payload)
    assert entry["sha256"] == hashlib.sha256(payload).hexdigest()


def test_records_bus_root_relative_path(tmp_path: Path) -> None:
    asset = _write_asset(tmp_path, "main-menu-bg.png", b"x")

    entry = asset_manifest_entry(asset, tmp_path, asset_type="image")

    assert entry["path"] == f"deliverables/{REQUEST_ID}/main-menu-bg.png"
    assert not Path(entry["path"]).is_absolute()


def test_records_relative_path_for_nested_asset(tmp_path: Path) -> None:
    deliverable = tmp_path / "deliverables" / REQUEST_ID / "sprites"
    deliverable.mkdir(parents=True)
    asset = deliverable / "hero.png"
    asset.write_bytes(b"png-bytes")

    entry = asset_manifest_entry(asset, tmp_path, asset_type="image")

    assert entry["path"] == f"deliverables/{REQUEST_ID}/sprites/hero.png"


def test_accepts_string_paths(tmp_path: Path) -> None:
    asset = _write_asset(tmp_path, "drone.wav", b"RIFF....WAVEfmt ")

    entry = asset_manifest_entry(str(asset), str(tmp_path), asset_type="music")

    assert entry["type"] == "music"
    assert entry["bytes"] == len(b"RIFF....WAVEfmt ")


def test_passes_through_caller_supplied_meta(tmp_path: Path) -> None:
    asset = _write_asset(tmp_path, "main-menu-bg.png", b"img")
    meta = {"width": 768, "height": 512, "seed": 12345, "model": "dreamshaper-8"}

    entry = asset_manifest_entry(asset, tmp_path, asset_type="image", meta=meta)

    assert entry["meta"] == meta
    meta["width"] = 99
    assert entry["meta"]["width"] == 768


def test_meta_defaults_to_empty_mapping(tmp_path: Path) -> None:
    asset = _write_asset(tmp_path, "x.bin", b"")

    entry = asset_manifest_entry(asset, tmp_path, asset_type="image")

    assert entry["meta"] == {}


def test_empty_asset_records_zero_bytes_and_empty_sha(tmp_path: Path) -> None:
    asset = _write_asset(tmp_path, "empty.bin", b"")

    entry = asset_manifest_entry(asset, tmp_path, asset_type="image")

    assert entry["bytes"] == 0
    assert entry["sha256"] == hashlib.sha256(b"").hexdigest()


def test_rejects_asset_outside_bus_root(tmp_path: Path) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    outside = other / "leak.png"
    outside.write_bytes(b"nope")

    bus_root = tmp_path / "bus"
    bus_root.mkdir()

    with pytest.raises(UnsafePathError):
        asset_manifest_entry(outside, bus_root, asset_type="image")


def test_hashes_large_asset_in_chunks(tmp_path: Path) -> None:
    payload = b"a" * (3 * 1024 * 1024 + 7)
    asset = _write_asset(tmp_path, "big.bin", payload)

    entry = asset_manifest_entry(asset, tmp_path, asset_type="image")

    assert entry["bytes"] == len(payload)
    assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
