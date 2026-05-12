"""Smoke-test entry point: run the self-listener against composer self-quote output.

Operators run this on cypherclaw (or any host with the daemon module) after
``composer_quote_verify`` to confirm that the self-listener's WAV peak
analysis observes a non-trivial peak in each quoted sample WAV the
composer wrote into ``samples/self/``. Used to confirm that the
self-listener can hear the composer's self-quote.

The verifier is hardware-free: it re-uses ``trigger_composer_pieces`` to
drive the fake JACK self bus, then transcodes each 24-bit quote WAV to
the 16-bit PCM that ``self_listener.analyze_wav`` decodes and asserts at
least one observed peak clears ``EXPECTED_PEAK_FLOOR``.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import wave
from array import array
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from composer_quote_verify import PIECES_TO_RUN, trigger_composer_pieces
from sample_capture_daemon import SAMPLE_CAPTURE_ROOT
from self_listener import analyze_wav


# Known room sound is a 0.4-amplitude sine; save_capture peak-normalizes to
# -1 dBFS, so the WAV's expected peak is ~0.89. The floor leaves headroom
# for normalization drift while still rejecting silence.
EXPECTED_PEAK_FLOOR = 0.5


def _decode_24bit_mono_to_16bit_wav(src: Path, dst: Path) -> None:
    """Re-write a 24-bit mono WAV as 16-bit mono so ``analyze_wav`` can read it."""
    with wave.open(str(src), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frame_count = handle.getnframes()
        raw = handle.readframes(frame_count)
    if sample_width != 3:
        raise ValueError(f"expected 24-bit WAV at {src}, got {sample_width * 8}-bit")

    samples_24: list[int] = []
    for index in range(0, len(raw), 3):
        word = int.from_bytes(raw[index : index + 3], byteorder="little", signed=True)
        samples_24.append(word)
    if channels > 1:
        downmix: list[int] = []
        for index in range(0, len(samples_24), channels):
            frame = samples_24[index : index + channels]
            downmix.append(int(sum(frame) / len(frame)))
        samples_24 = downmix

    samples_16 = array(
        "h",
        [max(-32767, min(32767, value >> 8)) for value in samples_24],
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(samples_16.tobytes())


def list_self_quote_paths(index_path: Path) -> list[tuple[str, Path]]:
    """Return ``(sample_id, wav_path)`` rows for ``samples/self/`` in capture order."""
    with sqlite3.connect(str(index_path)) as con:
        rows = con.execute(
            "SELECT sample_id, path FROM samples WHERE source = 'self' "
            "ORDER BY captured_at_unix"
        ).fetchall()
    return [(str(sample_id), Path(str(path))) for sample_id, path in rows]


def observe_peak(quote_path: Path, *, scratch_root: Path) -> float:
    """Run the self-listener's ``analyze_wav`` against ``quote_path``."""
    transcoded = scratch_root / f"{quote_path.stem}_16bit.wav"
    _decode_24bit_mono_to_16bit_wav(quote_path, transcoded)
    return float(analyze_wav(str(transcoded))["peak"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture-root",
        default=str(SAMPLE_CAPTURE_ROOT),
        help="sample store root (default: %(default)s)",
    )
    parser.add_argument(
        "--pieces",
        type=int,
        default=PIECES_TO_RUN,
        help="number of composer pieces to simulate (default: %(default)s)",
    )
    parser.add_argument(
        "--peak-floor",
        type=float,
        default=EXPECTED_PEAK_FLOOR,
        help="minimum observed peak to accept (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    capture_root = Path(args.capture_root)
    captured, _ = trigger_composer_pieces(
        capture_root=capture_root,
        pieces=args.pieces,
    )
    if captured == 0:
        print(f"NO_SELF_QUOTES (pieces={args.pieces})", file=sys.stderr)
        return 1

    paths = list_self_quote_paths(capture_root / "index.sqlite")
    if not paths:
        print(f"NO_SELF_QUOTE_PATHS (captured={captured})", file=sys.stderr)
        return 2

    scratch_root = capture_root / "_self_listener_scratch"
    observations: list[tuple[str, Path, float]] = []
    for sample_id, path in paths:
        peak = observe_peak(path, scratch_root=scratch_root)
        observations.append((sample_id, path, peak))

    above_floor = [obs for obs in observations if obs[2] >= args.peak_floor]
    if not above_floor:
        peaks = [round(peak, 4) for _, _, peak in observations]
        print(
            f"NO_PEAK_OBSERVED (peaks={peaks}, floor={args.peak_floor})",
            file=sys.stderr,
        )
        return 3

    print(f"pieces_run={args.pieces}")
    print(f"self_quotes_captured={captured}")
    for sample_id, path, peak in observations:
        print(f"sample_id={sample_id} peak={peak:.4f} path={path}")
    print(f"peak_floor={args.peak_floor}")
    print(f"matches={len(above_floor)}/{len(observations)}")
    print("SELF_LISTENER_PEAK_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
