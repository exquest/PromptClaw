"""Smoke-test entry point: simulate >5s keyboard and Theramini phrases during a song."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

from midi_keyboard_listener import capture_phrase_from_state as capture_keyboard_phrase
from sample_capture_daemon import SAMPLE_CAPTURE_ROOT
from senseweave.phrase_capture import validate_sample_metadata
from senseweave.phrase_capture_runtime import ActiveSongPhraseCapture
from theramini_listener import capture_phrase_from_state as capture_theramini_phrase


VERIFY_SAMPLE_RATE = 8000
VERIFY_SONG_STATE = {
    "song": "verify-song-1",
    "key": "Dm",
    "tempo": 96,
    "updated": 100.0,
}


def _write_composer_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _read_sidecar(path: Path) -> dict[str, object]:
    payload = json.loads(path.with_suffix(".json").read_text())
    validate_sample_metadata(payload)
    return payload


def _simulate_keyboard_phrase(capture: ActiveSongPhraseCapture) -> Path:
    stream = [
        (bytes([0x90, 60, 100]), {"playing": True, "timestamp": 100.0}),
        (None, {"playing": True, "timestamp": 102.0}),
        (None, {"playing": True, "timestamp": 105.0}),
        (bytes([0x80, 60, 0]), {"playing": False, "timestamp": 106.0}),
    ]
    written: Path | None = None
    for chunk, state in stream:
        written = capture_keyboard_phrase(capture, chunk=chunk, state=state)
    if written is None:
        raise AssertionError("keyboard phrase did not produce a capture")
    if written.parent.name != "keyboard":
        raise AssertionError(f"expected keyboard capture path, got {written}")
    return written


def _simulate_theramini_phrase(capture: ActiveSongPhraseCapture) -> Path:
    t = np.arange(VERIFY_SAMPLE_RATE, dtype=np.float32) / float(VERIFY_SAMPLE_RATE)
    tone = (0.1 * np.sin(2.0 * math.pi * 440.0 * t)).astype(np.float32)
    written: Path | None = None
    for when in (100.0, 101.0, 102.0, 103.0, 104.0, 105.0):
        written = capture_theramini_phrase(
            capture,
            chunk=tone,
            state={"is_playing": True, "timestamp": when},
        )
    written = capture_theramini_phrase(
        capture,
        chunk=tone,
        state={"is_playing": False, "timestamp": 106.0},
    )
    if written is None:
        raise AssertionError("Theramini phrase did not produce a capture")
    if written.parent.name != "theramini":
        raise AssertionError(f"expected Theramini capture path, got {written}")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture-root",
        default=str(SAMPLE_CAPTURE_ROOT),
        help="sample store root (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    capture_root = Path(args.capture_root)
    composer_state = capture_root / "_verify" / "composer_state.json"
    _write_composer_state(composer_state, VERIFY_SONG_STATE)

    keyboard_capture = ActiveSongPhraseCapture(
        "keyboard",
        capture_root=capture_root,
        composer_state_path=composer_state,
        active_song_max_age_seconds=999.0,
    )
    theramini_capture = ActiveSongPhraseCapture(
        "theramini",
        capture_root=capture_root,
        composer_state_path=composer_state,
        active_song_max_age_seconds=999.0,
        sample_rate=VERIFY_SAMPLE_RATE,
    )

    keyboard_path = _simulate_keyboard_phrase(keyboard_capture)
    theramini_path = _simulate_theramini_phrase(theramini_capture)
    keyboard_metadata = _read_sidecar(keyboard_path)
    theramini_metadata = _read_sidecar(theramini_path)

    print(f"keyboard_path={keyboard_path}")
    print(f"keyboard_metadata={json.dumps(keyboard_metadata, sort_keys=True)}")
    print(f"theramini_path={theramini_path}")
    print(f"theramini_metadata={json.dumps(theramini_metadata, sort_keys=True)}")
    print("HUMAN_PHRASE_CAPTURE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
