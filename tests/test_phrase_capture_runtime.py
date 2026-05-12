"""Tests for active-song phrase capture runtime wiring."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.phrase_capture import validate_sample_metadata
from senseweave.phrase_capture_runtime import (  # type: ignore[import-not-found]
    ActiveSongPhraseCapture,
    read_active_song_metadata,
)


def _write_composer_state(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload))


def _read_sidecar(path: Path) -> dict[str, object]:
    return json.loads(path.with_suffix(".json").read_text())


def test_read_active_song_metadata_maps_song_key_and_tempo(tmp_path: Path) -> None:
    composer_state = tmp_path / "composer_state.json"
    _write_composer_state(
        composer_state,
        {
            "song": 42,
            "key": "F#m",
            "tempo_bpm": 123.0,
            "updated": 100.0,
        },
    )

    meta = read_active_song_metadata(
        "keyboard",
        composer_state_path=composer_state,
        now=105.0,
        max_age_seconds=10.0,
    )

    assert meta == {
        "instrument": "midi_keyboard",
        "song_id": "42",
        "key": "F#m",
        "tempo": 123.0,
        "source": "human",
    }


def test_inactive_song_resets_partial_phrase_and_writes_nothing(tmp_path: Path) -> None:
    composer_state = tmp_path / "composer_state.json"
    _write_composer_state(
        composer_state,
        {
            "song": 1,
            "key": "C",
            "tempo": 90,
            "updated": 0.0,
        },
    )
    capture = ActiveSongPhraseCapture(
        "keyboard",
        capture_root=tmp_path,
        composer_state_path=composer_state,
        active_song_max_age_seconds=999.0,
    )

    # Start a partial phrase under song 1, then lose the active-song context.
    assert capture.feed(bytes([0x90, 70, 30]), True, 0.0) is None
    assert capture.feed(None, True, 2.0) is None
    _write_composer_state(
        composer_state,
        {
            "key": "C",
            "tempo": 90,
            "updated": 2.5,
        },
    )
    assert capture.feed(None, False, 2.5) is None

    # Reactivate with a different song and ensure only the new phrase lands.
    _write_composer_state(
        composer_state,
        {
            "song": 2,
            "key": "Gm",
            "tempo": 88,
            "updated": 10.0,
        },
    )
    assert capture.feed(bytes([0x90, 60, 100]), True, 10.0) is None
    assert capture.feed(None, True, 15.0) is None
    path = capture.feed(bytes([0x80, 60, 0]), False, 16.0)

    assert path is not None
    assert path.parent == tmp_path / "keyboard"
    sidecar = _read_sidecar(path)
    assert sidecar["song_id"] == "2"
    validate_sample_metadata(sidecar)

    data = path.read_bytes()
    assert bytes([0x90, 60, 100]) in data
    assert bytes([0x90, 70, 30]) not in data


def test_runtime_overrides_instrument_tag_per_source(tmp_path: Path) -> None:
    composer_state = tmp_path / "composer_state.json"
    _write_composer_state(
        composer_state,
        {
            "song": "piece-9",
            "key": "Bb",
            "bpm": 72,
            "updated": 50.0,
        },
    )

    keyboard_meta = read_active_song_metadata(
        "keyboard",
        composer_state_path=composer_state,
        now=55.0,
        max_age_seconds=10.0,
    )
    theramini_meta = read_active_song_metadata(
        "theramini",
        composer_state_path=composer_state,
        now=55.0,
        max_age_seconds=10.0,
    )

    assert keyboard_meta is not None
    assert theramini_meta is not None
    assert keyboard_meta["instrument"] == "midi_keyboard"
    assert theramini_meta["instrument"] == "theramini"
    assert set(keyboard_meta) == {"instrument", "song_id", "key", "tempo", "source"}
    assert set(theramini_meta) == {"instrument", "song_id", "key", "tempo", "source"}
