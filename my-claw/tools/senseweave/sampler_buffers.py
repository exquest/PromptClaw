"""Sampler buffer loading for the cypherclaw scsynth backend.

`BufferLoader.on_sampler_load(record)` allocates an scsynth buffer via
`/b_alloc` (sized from the WAV header), reads the WAV file into it via
`/b_allocRead`, and stores the assigned buffer id back on the record.
`BufferLoader.on_sampler_free(record)` releases the buffer via `/b_free`
and clears the id; calling it on a record without a live buffer is a
no-op so callers can free idempotently.

Live records are tracked in an LRU ordering: loads and `touch(record)`
mark a record most-recently-used, and once the live set exceeds
`capacity` the least-recently-used record is auto-freed on the next
load.
"""
from __future__ import annotations

import wave
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class OSCSender(Protocol):
    """Minimal scsynth OSC client surface used by the buffer loader."""

    def send_message(self, address: str, args: list) -> None: ...


@dataclass
class BufferRecord:
    """Record carrying a sample's WAV path and assigned scsynth buffer id.

    A placeholder until the full `SampleRecord` (T-024) lands; any record
    with `path` and a settable `buffer_id` attribute satisfies the loader.
    """

    path: Path | str
    buffer_id: int | None = None


class BufferLoader:
    """Allocates scsynth buffers and loads WAV files into them via OSC.

    Maintains LRU ordering of live records: each load or `touch` marks a
    record most-recently-used, and the least-recently-used record is
    auto-evicted (freed) when a load would push the live set past
    `capacity`.
    """

    def __init__(
        self,
        osc: OSCSender,
        start_bufnum: int = 100,
        capacity: int = 64,
    ) -> None:
        if capacity < 1:
            raise ValueError("BufferLoader capacity must be positive")
        self.osc = osc
        self._next_bufnum = start_bufnum
        self.capacity = capacity
        self._lru: OrderedDict[int, BufferRecord] = OrderedDict()

    def on_sampler_load(self, record: BufferRecord) -> int:
        """Allocate a buffer, read `record.path` into it, return the bufnum.

        Mutates `record` by setting `buffer_id` to the assigned bufnum and
        marking it most-recently-used. If the live set is already at
        `capacity`, the least-recently-used record is freed first.
        Raises `FileNotFoundError` if the WAV path does not exist; no OSC
        traffic is sent in that case and `record.buffer_id` is left alone.
        """
        path = Path(record.path)
        with wave.open(str(path), "rb") as handle:
            num_frames = handle.getnframes()
            num_channels = handle.getnchannels()

        if len(self._lru) >= self.capacity:
            self.evict_lru()

        bufnum = self._next_bufnum
        self._next_bufnum += 1

        self.osc.send_message("/b_alloc", [bufnum, num_frames, num_channels])
        self.osc.send_message("/b_allocRead", [bufnum, str(path), 0, -1])

        record.buffer_id = bufnum
        self._lru[id(record)] = record
        return bufnum

    def on_sampler_free(self, record: BufferRecord) -> None:
        """Release `record.buffer_id` via `/b_free` and clear it on the record.

        No-op when `record.buffer_id is None` (already freed or never loaded);
        no OSC traffic is sent in that case.
        """
        bufnum = record.buffer_id
        if bufnum is None:
            return

        self.osc.send_message("/b_free", [bufnum])
        record.buffer_id = None
        self._lru.pop(id(record), None)

    def touch(self, record: BufferRecord) -> None:
        """Mark `record` as most-recently-used.

        No-op for records not currently tracked (already freed or never
        loaded); no OSC traffic is sent.
        """
        key = id(record)
        if key in self._lru:
            self._lru.move_to_end(key)

    def evict_lru(self) -> BufferRecord | None:
        """Evict and return the least-recently-used tracked record."""
        if not self._lru:
            return None

        _, oldest = next(iter(self._lru.items()))
        self.on_sampler_free(oldest)
        return oldest
