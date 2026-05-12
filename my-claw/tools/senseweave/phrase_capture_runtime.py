"""Runtime wrapper for listener-driven human phrase capture during active songs."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from sample_capture_daemon import SAMPLE_CAPTURE_ROOT

from senseweave.phrase_capture import (
    DEFAULT_AUDIO_SAMPLE_RATE,
    CaptureSource,
    PhraseCaptureWriter,
)


DEFAULT_COMPOSER_STATE_PATH = Path("/tmp/composer_state.json")
DEFAULT_ACTIVE_SONG_MAX_AGE_SECONDS = 300.0
_KEYBOARD_INSTRUMENT = "midi_keyboard"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()
    return text or None


def _coerce_number(value: object) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _instrument_name(source: CaptureSource) -> str:
    if source == "keyboard":
        return _KEYBOARD_INSTRUMENT
    return "theramini"


def _extract_tempo(state: Mapping[str, Any]) -> int | float | None:
    for key in ("tempo", "tempo_bpm", "bpm"):
        value = _coerce_number(state.get(key))
        if value is not None:
            return value
    return None


def read_active_song_metadata(
    source: CaptureSource,
    *,
    composer_state_path: Path | str = DEFAULT_COMPOSER_STATE_PATH,
    now: float | None = None,
    max_age_seconds: float = DEFAULT_ACTIVE_SONG_MAX_AGE_SECONDS,
) -> dict[str, Any] | None:
    """Return sidecar metadata for the current song, or ``None`` when inactive."""
    state = _read_json(Path(composer_state_path))
    song_id = _coerce_text(state.get("song"))
    if song_id is None:
        return None

    updated = _coerce_number(state.get("updated"))
    current_time = time.time() if now is None else now
    if updated is not None and current_time - float(updated) > max_age_seconds:
        return None

    return {
        "instrument": _instrument_name(source),
        "song_id": song_id,
        "key": _coerce_text(state.get("key")),
        "tempo": _extract_tempo(state),
        "source": "human",
    }


class ActiveSongPhraseCapture:
    """Gate ``PhraseCaptureWriter`` behind current active-song metadata."""

    def __init__(
        self,
        source: CaptureSource,
        *,
        capture_root: Path | str = SAMPLE_CAPTURE_ROOT,
        composer_state_path: Path | str = DEFAULT_COMPOSER_STATE_PATH,
        active_song_max_age_seconds: float = DEFAULT_ACTIVE_SONG_MAX_AGE_SECONDS,
        sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    ) -> None:
        self.source = source
        self.composer_state_path = Path(composer_state_path)
        self.active_song_max_age_seconds = active_song_max_age_seconds
        self.writer = PhraseCaptureWriter(
            source,
            capture_root,
            sample_rate=sample_rate,
        )
        self._active_song_id: str | None = None

    def reset(self) -> None:
        """Drop the current phrase and forget the active song id."""
        self.writer.reset()
        self._active_song_id = None

    def feed(
        self,
        chunk: Any,
        is_playing: bool,
        now: float,
    ) -> Path | None:
        """Capture ``chunk`` only when a current composer song is active."""
        metadata = read_active_song_metadata(
            self.source,
            composer_state_path=self.composer_state_path,
            now=now,
            max_age_seconds=self.active_song_max_age_seconds,
        )
        if metadata is None:
            self.reset()
            return None

        song_id = str(metadata["song_id"])
        if self._active_song_id is not None and song_id != self._active_song_id:
            self.reset()
        self._active_song_id = song_id
        self.writer.set_metadata(**metadata)
        return self.writer.feed(chunk, is_playing, now)
