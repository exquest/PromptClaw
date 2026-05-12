"""Smoke-test entry point: capture a known room sound and confirm the descriptor.

Operators run this on cypherclaw (or any host with the daemon module) to
verify end-to-end that ``save_capture`` writes a WAV plus a descriptor row
(tags + acoustic features) into the sample store.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

from sample_capture_daemon import SAMPLE_CAPTURE_ROOT, SavedCapture, save_capture


KNOWN_ROOM_SOUND_FREQ_HZ = 220.0
KNOWN_ROOM_SOUND_DURATION_SEC = 4.0
KNOWN_ROOM_SOUND_AMPLITUDE = 0.4
KNOWN_ROOM_SOUND_SAMPLE_RATE = 48_000
KNOWN_ROOM_SOUND_CONTEXT = {
    "organism": {
        "arc_phase": "rest",
        "mood": {"label": "content", "valence": 0.3, "arousal": 0.2},
    },
    "room_presence": {"presence": "solo", "confidence": 0.8, "someone_here": True},
}
EXPECTED_ACOUSTIC_TAGS = ("warm", "sustained")


def synthesize_known_room_sound(
    *,
    sample_rate: int = KNOWN_ROOM_SOUND_SAMPLE_RATE,
    frequency_hz: float = KNOWN_ROOM_SOUND_FREQ_HZ,
    duration_sec: float = KNOWN_ROOM_SOUND_DURATION_SEC,
    amplitude: float = KNOWN_ROOM_SOUND_AMPLITUDE,
) -> np.ndarray:
    """Return a deterministic low-centroid, low-transient room-like tone."""
    frame_count = int(round(sample_rate * duration_sec))
    t = np.arange(frame_count, dtype=np.float32) / float(sample_rate)
    return (amplitude * np.sin(2.0 * np.pi * frequency_hz * t)).astype(np.float32)


def capture_known_room_sound(
    *,
    capture_root: Path | str = SAMPLE_CAPTURE_ROOT,
    captured_at: float | None = None,
) -> SavedCapture:
    """Synthesize a known room sound and persist it via ``save_capture``."""
    samples = synthesize_known_room_sound()
    return save_capture(
        samples,
        source="room",
        sample_rate=KNOWN_ROOM_SOUND_SAMPLE_RATE,
        capture_root=capture_root,
        context=KNOWN_ROOM_SOUND_CONTEXT,
        captured_at=captured_at,
        mode="solo",
        extra_tags={"smoke_test": "known_220hz_sine"},
    )


def read_descriptor_row(capture: SavedCapture) -> dict[str, object]:
    """Read the descriptor row written for ``capture`` from the sample index."""
    with sqlite3.connect(str(capture.index_path)) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM samples WHERE sample_id = ?", (capture.sample_id,)
        ).fetchone()
    if row is None:
        raise AssertionError(f"no descriptor row for sample_id {capture.sample_id}")
    return dict(row)


def assert_descriptor_complete(descriptor: dict[str, object]) -> None:
    """Verify the descriptor carries both context tags and acoustic features."""
    if descriptor["source"] != "room":
        raise AssertionError(f"expected source=room, got {descriptor['source']!r}")
    if descriptor["arc_phase"] != "rest":
        raise AssertionError(f"expected arc_phase=rest, got {descriptor['arc_phase']!r}")
    acoustic_tags = tuple(json.loads(str(descriptor["acoustic_tags_json"])))
    if acoustic_tags != EXPECTED_ACOUSTIC_TAGS:
        raise AssertionError(
            f"expected acoustic_tags={EXPECTED_ACOUSTIC_TAGS}, got {acoustic_tags}"
        )
    payload = json.loads(str(descriptor["tags_json"]))
    for key in ("mood_label", "presence", "time_of_day", "captured_at_iso", "acoustic_tags"):
        if key not in payload:
            raise AssertionError(f"tags_json missing {key}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture-root",
        default=str(SAMPLE_CAPTURE_ROOT),
        help="sample store root (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    capture = capture_known_room_sound(capture_root=args.capture_root)
    descriptor = read_descriptor_row(capture)
    assert_descriptor_complete(descriptor)
    print(f"sample_id={capture.sample_id}")
    print(f"path={capture.path}")
    print(f"index={capture.index_path}")
    print(f"acoustic_tags={descriptor['acoustic_tags_json']}")
    print("DESCRIPTOR_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
