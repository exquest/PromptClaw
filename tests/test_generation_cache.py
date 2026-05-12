"""Tests for content-addressed generated-audio cache."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.cache import GenerationCache  # noqa: E402


class TickClock:
    def __init__(self, start: float = 100.0) -> None:
        self.value = start

    def __call__(self) -> float:
        current = self.value
        self.value += 1.0
        return current


def _req(request_hash: str) -> SimpleNamespace:
    return SimpleNamespace(hash=lambda: request_hash)


def _write_audio(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def _index(root: Path) -> dict:
    return json.loads((root / "cache_index.json").read_text())


def test_lookup_miss_and_hit_updates_lru_timestamp(tmp_path: Path) -> None:
    clock = TickClock()
    cache = GenerationCache(tmp_path / "cache", clock=clock)
    source = _write_audio(tmp_path / "source.wav", b"audio")

    assert cache.lookup(_req("missing")) is None

    cached_path = cache.put(_req("a" * 64), source)
    first_timestamp = _index(tmp_path / "cache")["entries"]["a" * 64]["accessed_at"]

    hit_path = cache.lookup(_req("a" * 64))

    assert hit_path == cached_path
    assert hit_path is not None
    assert hit_path.read_bytes() == b"audio"
    assert hit_path != source
    assert _index(tmp_path / "cache")["entries"]["a" * 64]["accessed_at"] > first_timestamp


def test_lookup_touch_controls_count_lru_eviction(tmp_path: Path) -> None:
    cache = GenerationCache(tmp_path / "cache", max_entries=2, clock=TickClock())

    cache.put(_req("a" * 64), _write_audio(tmp_path / "a.wav", b"a"))
    cache.put(_req("b" * 64), _write_audio(tmp_path / "b.wav", b"b"))
    assert cache.lookup(_req("a" * 64)) is not None

    cache.put(_req("c" * 64), _write_audio(tmp_path / "c.wav", b"c"))

    assert cache.lookup(_req("a" * 64)) is not None
    assert cache.lookup(_req("b" * 64)) is None
    assert cache.lookup(_req("c" * 64)) is not None


def test_size_cap_evicts_lru_even_when_count_cap_has_room(tmp_path: Path) -> None:
    max_size_gb = 10 / (1024**3)
    cache = GenerationCache(
        tmp_path / "cache",
        max_entries=10,
        max_size_gb=max_size_gb,
        clock=TickClock(),
    )

    cache.put(_req("a" * 64), _write_audio(tmp_path / "a.wav", b"abcdef"))
    cache.put(_req("b" * 64), _write_audio(tmp_path / "b.wav", b"ghijkl"))

    assert cache.lookup(_req("a" * 64)) is None
    assert cache.lookup(_req("b" * 64)) is not None


def test_cache_state_survives_restart(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    GenerationCache(root, clock=TickClock()).put(
        _req("a" * 64),
        _write_audio(tmp_path / "source.wav", b"audio"),
    )

    cache = GenerationCache(root, clock=TickClock(start=500.0))
    hit_path = cache.lookup(_req("a" * 64))

    assert hit_path is not None
    assert hit_path.exists()
    assert hit_path.read_bytes() == b"audio"
    assert _index(root)["entries"]["a" * 64]["accessed_at"] == 500.0


class GenerationCacheEndToEndTests:
    """End-to-end coverage for the generated-audio cache public API (depth-2)."""

    __test__ = True

    def test_full_miss_put_hit_replace_cycle(self, tmp_path: Path) -> None:
        clock = TickClock(start=1000.0)
        cache = GenerationCache(tmp_path / "cache", clock=clock)
        request_hash = "a" * 64

        # Initial miss before any payload is stored.
        assert cache.lookup(_req(request_hash)) is None

        first_source = _write_audio(tmp_path / "first.wav", b"first-audio")
        first_path = cache.put(_req(request_hash), first_source)

        # Content-addressed filename, suffix preserved.
        assert first_path.name == f"{request_hash}.wav"
        assert first_path.parent == tmp_path / "cache"
        assert first_path.read_bytes() == b"first-audio"

        # Hit returns the cached path (not the source) and updates accessed_at.
        first_index = _index(tmp_path / "cache")
        first_accessed_at = first_index["entries"][request_hash]["accessed_at"]
        hit_path = cache.lookup(_req(request_hash))
        assert hit_path == first_path
        assert hit_path is not None
        assert hit_path != first_source
        second_index = _index(tmp_path / "cache")
        assert (
            second_index["entries"][request_hash]["accessed_at"] > first_accessed_at
        )

        # Replacement put for the same hash overwrites in place.
        replacement_source = _write_audio(
            tmp_path / "second.wav", b"replacement-audio"
        )
        replacement_path = cache.put(_req(request_hash), replacement_source)
        assert replacement_path == first_path
        assert replacement_path.read_bytes() == b"replacement-audio"

        post_replace_index = _index(tmp_path / "cache")
        assert set(post_replace_index["entries"]) == {request_hash}
        assert (
            post_replace_index["entries"][request_hash]["size_bytes"]
            == len(b"replacement-audio")
        )

    def test_queue_storage_aliases_share_entry_with_put_lookup(
        self, tmp_path: Path
    ) -> None:
        cache = GenerationCache(tmp_path / "cache", clock=TickClock(start=2000.0))
        alias_hash = "b" * 64

        result = {
            "audio_path": _write_audio(tmp_path / "alias.wav", b"alias-bytes"),
        }

        # The set/get aliases should drive the same on-disk entry path as put/lookup.
        stored_path = cache.set(_req(alias_hash), result)
        assert stored_path.name == f"{alias_hash}.wav"
        assert stored_path.read_bytes() == b"alias-bytes"

        get_hit = cache.get(_req(alias_hash))
        lookup_hit = cache.lookup(_req(alias_hash))
        assert get_hit == stored_path
        assert lookup_hit == stored_path

        index = _index(tmp_path / "cache")
        assert set(index["entries"]) == {alias_hash}
        assert index["entries"][alias_hash]["filename"] == stored_path.name

    def test_index_is_json_safe_with_sorted_keys(self, tmp_path: Path) -> None:
        cache = GenerationCache(tmp_path / "cache", clock=TickClock(start=3000.0))
        first_hash = "c" * 64
        second_hash = "d" * 64

        cache.put(_req(first_hash), _write_audio(tmp_path / "c.wav", b"cc"))
        cache.put(_req(second_hash), _write_audio(tmp_path / "d.wav", b"dd"))

        index = _index(tmp_path / "cache")
        assert index["version"] == 1
        assert set(index["entries"]) == {first_hash, second_hash}

        # JSON-safe round-trip with sorted keys.
        rendered = json.dumps(index, sort_keys=True)
        roundtripped = json.loads(rendered)
        assert roundtripped == index

        # Each entry exposes the fields downstream tooling reads.
        for entry in index["entries"].values():
            assert set(entry) >= {"filename", "accessed_at", "size_bytes"}
            assert isinstance(entry["filename"], str)
            assert entry["filename"]

    def test_restart_recovers_entries_and_prunes_missing_payload(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "cache"
        first_hash = "e" * 64
        second_hash = "f" * 64
        third_hash = "0" * 64

        warm = GenerationCache(root, clock=TickClock(start=4000.0))
        first_path = warm.put(_req(first_hash), _write_audio(tmp_path / "e.wav", b"ee"))
        warm.put(_req(second_hash), _write_audio(tmp_path / "f.wav", b"ffff"))
        warm.put(_req(third_hash), _write_audio(tmp_path / "0.wav", b"000000"))

        # Simulate an out-of-band deletion of one payload before restart.
        first_path.unlink()

        restarted = GenerationCache(root, clock=TickClock(start=5000.0))

        # The deleted entry is pruned; the surviving entries still resolve.
        assert restarted.lookup(_req(first_hash)) is None
        second_hit = restarted.lookup(_req(second_hash))
        third_hit = restarted.lookup(_req(third_hash))
        assert second_hit is not None and second_hit.read_bytes() == b"ffff"
        assert third_hit is not None and third_hit.read_bytes() == b"000000"

        post_restart_index = _index(root)
        assert set(post_restart_index["entries"]) == {second_hash, third_hash}
        # Index remains JSON-safe across the restart.
        assert json.loads(json.dumps(post_restart_index, sort_keys=True)) == (
            post_restart_index
        )

    def test_combined_count_and_size_lru_keeps_warmed_entry(
        self, tmp_path: Path
    ) -> None:
        max_size_gb = 12 / (1024**3)
        cache = GenerationCache(
            tmp_path / "cache",
            max_entries=5,
            max_size_gb=max_size_gb,
            clock=TickClock(start=6000.0),
        )

        oldest_hash = "1" * 64
        middle_hash = "2" * 64
        newest_hash = "3" * 64

        cache.put(_req(oldest_hash), _write_audio(tmp_path / "1.wav", b"oldest"))
        cache.put(_req(middle_hash), _write_audio(tmp_path / "2.wav", b"middle"))

        # Keep the oldest entry warm so eviction targets the middle entry.
        warmed = cache.lookup(_req(oldest_hash))
        assert warmed is not None and warmed.read_bytes() == b"oldest"

        cache.put(_req(newest_hash), _write_audio(tmp_path / "3.wav", b"newest"))

        # The warmed entry survives; the LRU entry is evicted under the size cap.
        assert cache.lookup(_req(oldest_hash)) is not None
        assert cache.lookup(_req(middle_hash)) is None
        assert cache.lookup(_req(newest_hash)) is not None

        final_index = _index(tmp_path / "cache")
        assert set(final_index["entries"]) == {oldest_hash, newest_hash}
