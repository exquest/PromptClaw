"""Phrase capture writer — persists qualifying phrases to ``samples/<source>/``.

Wraps :class:`PhraseTracker` with a buffer that accumulates input while a
play session is in progress and flushes to a timestamped file once
``phrase_ended`` fires. Sub-threshold bursts are dropped without I/O.

Two sources are supported:

* ``"keyboard"`` — buffer entries are ``(rel_seconds, midi_bytes)`` tuples
  and are persisted as a Standard MIDI File (Type 0).
* ``"theramini"`` — buffer entries are float sample arrays and are
  persisted as 16-bit PCM mono WAV.

Each captured sample is paired with a sidecar ``.json`` metadata file
containing instrument/song_id/key/tempo/timestamp/duration/source tags.
"""
from __future__ import annotations

import json
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Optional, Sequence

import numpy as np
import numpy.typing as npt

from senseweave.phrase_tracker import PhraseTracker

CaptureSource = Literal["keyboard", "theramini"]
_VALID_SOURCES: frozenset[str] = frozenset({"keyboard", "theramini"})

DEFAULT_AUDIO_SAMPLE_RATE = 48_000
_MIDI_PPQ = 480
_MIDI_TEMPO_USEC_PER_QUARTER = 500_000  # 120 BPM
_MIDI_TICKS_PER_SECOND = _MIDI_PPQ * 1_000_000 // _MIDI_TEMPO_USEC_PER_QUARTER  # 960

DEFAULT_SAMPLE_PROVENANCE = "human"

# Sidecar metadata schema: required key -> tuple of allowed types.
SAMPLE_METADATA_SCHEMA: dict[str, tuple[type, ...]] = {
    "instrument": (str,),
    "song_id": (str, type(None)),
    "key": (str, type(None)),
    "tempo": (int, float, type(None)),
    "timestamp": (str,),
    "duration": (int, float),
    "source": (str,),
}


def validate_sample_metadata(meta: Mapping[str, Any]) -> None:
    """Raise ``ValueError`` if ``meta`` does not match :data:`SAMPLE_METADATA_SCHEMA`."""
    missing = sorted(set(SAMPLE_METADATA_SCHEMA) - set(meta))
    if missing:
        raise ValueError(f"sample metadata missing required keys: {missing}")
    extra = sorted(set(meta) - set(SAMPLE_METADATA_SCHEMA))
    if extra:
        raise ValueError(f"sample metadata has unknown keys: {extra}")
    for key, allowed in SAMPLE_METADATA_SCHEMA.items():
        value = meta[key]
        if not isinstance(value, allowed) or isinstance(value, bool):
            allowed_names = ", ".join(t.__name__ for t in allowed)
            raise ValueError(
                f"sample metadata field {key!r} has type "
                f"{type(value).__name__}, expected one of: {allowed_names}"
            )


class PhraseCaptureWriter:
    """Buffer input across a phrase and write to ``<root>/<source>/`` on phrase_ended.

    Parameters
    ----------
    source:
        ``"keyboard"`` or ``"theramini"`` — selects the on-disk format and
        the sub-directory under ``root``.
    root:
        Base directory (the ``samples/`` directory). Created on first write.
    sample_rate:
        Audio sample rate for ``"theramini"`` captures. Ignored for MIDI.
    tracker:
        Inject a custom :class:`PhraseTracker` (e.g., a non-default threshold
        or a tracker shared with a listener). Defaults to a fresh tracker.
    metadata:
        Initial sidecar tags. Recognised keys: ``instrument``, ``song_id``,
        ``key``, ``tempo``, ``source``. Unset keys are filled with defaults
        (instrument=``source`` arg, source=``"human"``, others ``None``).
        ``timestamp`` and ``duration`` are always derived per-phrase and
        cannot be set here.
    """

    def __init__(
        self,
        source: CaptureSource,
        root: Path | str,
        *,
        sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
        tracker: PhraseTracker | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if source not in _VALID_SOURCES:
            raise ValueError(f"unknown capture source: {source!r}")
        self.source: CaptureSource = source
        self.root = Path(root)
        self.sample_rate = sample_rate
        self.tracker = tracker or PhraseTracker()
        self._buffer: list[Any] = []
        self._first_play_time: Optional[float] = None
        self._metadata: dict[str, Any] = {}
        if metadata is not None:
            self.set_metadata(**dict(metadata))

    _USER_METADATA_KEYS: frozenset[str] = frozenset(
        {"instrument", "song_id", "key", "tempo", "source"}
    )

    def set_metadata(self, **fields: Any) -> None:
        """Update sidecar metadata fields. Derived keys are rejected."""
        bad = sorted(set(fields) - self._USER_METADATA_KEYS)
        if bad:
            raise ValueError(
                f"cannot set derived or unknown metadata fields: {bad}"
            )
        self._metadata.update(fields)

    @property
    def buffered_chunks(self) -> int:
        return len(self._buffer)

    def feed(
        self,
        chunk: Any,
        is_playing: bool,
        now: float,
    ) -> Optional[Path]:
        """Advance one tick. Returns the written path on phrase_ended, else None.

        ``chunk`` should be raw MIDI bytes (``"keyboard"``) or a float sample
        array (``"theramini"``). Pass ``None`` on ticks where no input is
        available — the tracker still advances.
        """
        if is_playing and self.tracker.play_start is None:
            # Fresh play session — discard any leftover buffer (defensive).
            self._buffer = []
            self._first_play_time = now

        # Append before tracker.update so the boundary tick (release/note-off
        # arriving alongside is_playing=False) still lands in the phrase.
        in_session = self.tracker.play_start is not None or is_playing
        if in_session and chunk is not None:
            self._append(chunk, now)

        event = self.tracker.update(is_playing, now)

        if event == "phrase_ended":
            path = self._write(now)
            self._buffer = []
            self._first_play_time = None
            return path

        if self.tracker.play_start is None and not self.tracker.phrase_active:
            # Sub-threshold burst just ended (or we're idle) — drop buffer.
            self._buffer = []
            self._first_play_time = None

        return None

    def _append(self, chunk: Any, now: float) -> None:
        first = self._first_play_time if self._first_play_time is not None else now
        rel_t = max(0.0, now - first)
        if self.source == "keyboard":
            self._buffer.append((rel_t, bytes(chunk)))
        else:
            self._buffer.append(np.asarray(chunk, dtype=np.float32).reshape(-1))

    def reset(self) -> None:
        """Drop buffered phrase state and reset the tracker."""
        self._buffer = []
        self._first_play_time = None
        self.tracker.reset()

    def _build_path(self, now: float) -> Path:
        captured = datetime.fromtimestamp(now, tz=timezone.utc)
        ts = captured.strftime("%Y%m%dT%H%M%SZ")
        unique = uuid.uuid4().hex[:8]
        ext = ".mid" if self.source == "keyboard" else ".wav"
        return self.root / self.source / f"{self.source}_{ts}_{unique}{ext}"

    def _write(self, now: float) -> Path:
        path = self._build_path(now)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.source == "keyboard":
            _write_smf0_midi(path, self._buffer)
        else:
            _write_pcm16_wav(path, self._buffer, self.sample_rate)
        self._write_sidecar(path, now)
        return path

    def _compose_metadata(self, now: float) -> dict[str, Any]:
        start = self._first_play_time if self._first_play_time is not None else now
        duration = max(0.0, now - start)
        timestamp = (
            datetime.fromtimestamp(now, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        meta: dict[str, Any] = {
            "instrument": self._metadata.get("instrument", self.source),
            "song_id": self._metadata.get("song_id"),
            "key": self._metadata.get("key"),
            "tempo": self._metadata.get("tempo"),
            "timestamp": timestamp,
            "duration": round(duration, 6),
            "source": self._metadata.get("source", DEFAULT_SAMPLE_PROVENANCE),
        }
        validate_sample_metadata(meta)
        return meta

    def _write_sidecar(self, path: Path, now: float) -> None:
        meta = self._compose_metadata(now)
        sidecar = path.with_suffix(".json")
        sidecar.write_text(json.dumps(meta, indent=2, sort_keys=True))


def _encode_varlen(value: int) -> bytes:
    if value < 0:
        raise ValueError("varlen value must be non-negative")
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def _write_smf0_midi(
    path: Path,
    events: Sequence[tuple[float, bytes]],
) -> None:
    """Write a Type-0 SMF with a leading tempo meta-event and the buffered events."""
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + _MIDI_PPQ.to_bytes(2, "big")

    track = bytearray()
    # Tempo meta event at tick 0 — anchors the tick→seconds mapping.
    track.extend(b"\x00\xFF\x51\x03")
    track.extend(_MIDI_TEMPO_USEC_PER_QUARTER.to_bytes(3, "big"))

    prev_ticks = 0
    for rel_t, midi_bytes in events:
        absolute_ticks = int(round(rel_t * _MIDI_TICKS_PER_SECOND))
        delta_ticks = max(0, absolute_ticks - prev_ticks)
        prev_ticks = absolute_ticks
        track.extend(_encode_varlen(delta_ticks))
        track.extend(midi_bytes)

    # End-of-track meta event.
    track.extend(b"\x00\xFF\x2F\x00")

    path.write_bytes(header + b"MTrk" + len(track).to_bytes(4, "big") + bytes(track))


def _write_pcm16_wav(
    path: Path,
    chunks: Iterable[npt.NDArray[np.float32]],
    sample_rate: int,
) -> None:
    arrays = [np.asarray(c, dtype=np.float32).reshape(-1) for c in chunks]
    if arrays:
        joined = np.concatenate(arrays)
    else:
        joined = np.zeros(0, dtype=np.float32)
    clipped = np.clip(joined, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
