"""Content-addressed generated-audio cache with LRU eviction."""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


INDEX_NAME = "cache_index.json"
BYTES_PER_GB = 1024**3


@dataclass
class _CacheEntry:
    filename: str
    accessed_at: float
    size_bytes: int


class GenerationCache:
    """Filesystem-backed generated-audio cache keyed by request content hash."""

    def __init__(
        self,
        root: Path | str,
        max_entries: int = 256,
        max_size_gb: float = 5.0,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        if max_size_gb < 0:
            raise ValueError("max_size_gb must be non-negative")
        self.root = Path(root)
        self.max_entries = max_entries
        self.max_size_bytes = int(max_size_gb * BYTES_PER_GB)
        self._clock = clock or time.time
        self._index_path = self.root / INDEX_NAME
        self.root.mkdir(parents=True, exist_ok=True)
        self._entries = self._load_index()
        self._prune_missing()
        self._evict_if_needed()
        self._write_index()

    def lookup(self, req: Any) -> Path | None:
        """Return the cached audio path for ``req`` and update its LRU timestamp."""
        request_hash = _request_hash(req)
        entry = self._entries.get(request_hash)
        if entry is None:
            return None

        path = self.root / entry.filename
        if not path.exists():
            del self._entries[request_hash]
            self._write_index()
            return None

        entry.accessed_at = self._clock()
        entry.size_bytes = path.stat().st_size
        self._write_index()
        return path

    def put(self, req: Any, audio_path: Path | str) -> Path:
        """Copy ``audio_path`` into the cache under ``req``'s content hash."""
        request_hash = _request_hash(req)
        source_path = Path(audio_path)
        if not source_path.exists():
            raise FileNotFoundError(f"generated audio file missing: {source_path}")

        filename = _cache_filename(request_hash, source_path)
        target_path = self.root / filename
        existing = self._entries.get(request_hash)
        if existing is not None and existing.filename != filename:
            _unlink_quietly(self.root / existing.filename)

        if source_path.resolve() != target_path.resolve():
            shutil.copy2(source_path, target_path)

        self._entries[request_hash] = _CacheEntry(
            filename=filename,
            accessed_at=self._clock(),
            size_bytes=target_path.stat().st_size,
        )
        self._evict_if_needed()
        self._write_index()
        return target_path

    def get(self, req: Any) -> Path | None:
        """Compatibility alias for older queue cache hooks."""
        return self.lookup(req)

    def set(self, req: Any, result: Any) -> Path:
        """Compatibility alias accepting a generation result object or mapping."""
        return self.put(req, _audio_path(result))

    def _load_index(self) -> dict[str, _CacheEntry]:
        if not self._index_path.exists():
            return {}

        data = json.loads(self._index_path.read_text())
        raw_entries = data.get("entries", {})
        if not isinstance(raw_entries, Mapping):
            return {}

        entries: dict[str, _CacheEntry] = {}
        for request_hash, raw_entry in raw_entries.items():
            if not isinstance(raw_entry, Mapping):
                continue
            filename = str(raw_entry.get("filename", ""))
            if not filename or Path(filename).name != filename:
                continue
            accessed_at = float(raw_entry.get("accessed_at", 0.0))
            size_bytes = int(raw_entry.get("size_bytes", 0))
            entries[str(request_hash)] = _CacheEntry(
                filename=filename,
                accessed_at=accessed_at,
                size_bytes=size_bytes,
            )
        return entries

    def _write_index(self) -> None:
        payload = {
            "version": 1,
            "entries": {
                request_hash: {
                    "filename": entry.filename,
                    "accessed_at": entry.accessed_at,
                    "size_bytes": entry.size_bytes,
                }
                for request_hash, entry in sorted(self._entries.items())
            },
        }
        tmp_path = self._index_path.with_name(f"{INDEX_NAME}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(tmp_path, self._index_path)

    def _prune_missing(self) -> None:
        missing = [
            request_hash
            for request_hash, entry in self._entries.items()
            if not (self.root / entry.filename).exists()
        ]
        for request_hash in missing:
            del self._entries[request_hash]

    def _evict_if_needed(self) -> None:
        while self._over_limits() and self._entries:
            request_hash = min(
                self._entries,
                key=lambda key: (self._entries[key].accessed_at, key),
            )
            entry = self._entries.pop(request_hash)
            _unlink_quietly(self.root / entry.filename)

    def _over_limits(self) -> bool:
        return (
            len(self._entries) > self.max_entries
            or sum(entry.size_bytes for entry in self._entries.values())
            > self.max_size_bytes
        )


def _cache_filename(request_hash: str, audio_path: Path) -> str:
    suffix = audio_path.suffix.lower() or ".audio"
    return f"{request_hash}{suffix}"


def _request_hash(req: Any) -> str:
    value = _field(req, "hash", "request_hash")
    if callable(value):
        value = value()
    if value is None:
        raise ValueError("generation request must expose hash() or request_hash")
    text = str(value).strip()
    if not text:
        raise ValueError("generation request hash must be non-empty")
    if Path(text).name != text:
        raise ValueError("generation request hash must not contain path separators")
    return text


def _audio_path(result: Any) -> Path:
    if isinstance(result, Path):
        return result
    if isinstance(result, str):
        return Path(result)
    value = _field(result, "audio_path", "wav_path", "path")
    if value is None:
        raise ValueError("generation result must expose audio_path, wav_path, or path")
    return Path(value)


def _field(obj: Any, *names: str) -> Any:
    if isinstance(obj, Mapping):
        for name in names:
            if name in obj:
                return obj[name]
        return None
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


__all__ = ("GenerationCache",)
