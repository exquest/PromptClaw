"""Contact Mic Listener — detects room activity from JACK inputs 1+2.

Captures 0.5s clips, detects transients via rolling median comparison.
Writes /tmp/room_activity.json atomically.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import signal
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from audio_analysis import detect_amplitude
from capture_alias import persist_capture_alias

STATE_FILE = Path("/tmp/room_activity.json")
CLIP_FILE = Path("/tmp/contact_clip.wav")
SAMPLE_CAPTURE_FILE = Path("/tmp/contact_capture.wav")
CAPTURE_DURATION = 1  # jack_rec needs >= 1s
CYCLE_PERIOD = 1.5
ROLLING_WINDOW = 20  # 10 seconds of history at 0.5s per capture

DEFAULT_PORTS = ["system:capture_1", "system:capture_2"]


def capture_jack(ports: list[str], duration: float, output: Path) -> bool:
    cmd = ["jack_rec", "-f", str(output), "-d", str(duration), "-b", "16"] + ports
    try:
        subprocess.run(cmd, capture_output=True, timeout=duration + 5)
        return output.exists() and output.stat().st_size > 100
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def read_wav_stereo(path: Path) -> tuple[list[int], list[int], int]:
    """Read stereo WAV, return (ch1_samples, ch2_samples, sample_rate)."""
    with wave.open(str(path), "r") as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        nframes = w.getnframes()
        raw = w.readframes(nframes)
        samples = list(struct.unpack(f"{nframes * nch}h", raw))
        if nch >= 2:
            ch1 = samples[0::nch]
            ch2 = samples[1::nch]
            return ch1, ch2, sr
        return samples, samples, sr


def write_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(str(tmp), str(STATE_FILE))


def run_daemon(ports: list[str]) -> None:
    running = True
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    membrane_history: collections.deque[float] = collections.deque(maxlen=ROLLING_WINDOW)
    heartbeat_history: collections.deque[float] = collections.deque(maxlen=ROLLING_WINDOW)
    last_transient_time: float | None = None

    print(f"Contact listener started, ports={ports}", flush=True)

    while running:
        t0 = time.time()

        if not capture_jack(ports, CAPTURE_DURATION, CLIP_FILE):
            time.sleep(CYCLE_PERIOD)
            continue
        persist_capture_alias(CLIP_FILE, SAMPLE_CAPTURE_FILE)

        try:
            ch1, ch2, sr = read_wav_stereo(CLIP_FILE)
        except Exception:
            time.sleep(CYCLE_PERIOD)
            continue

        mem_rms, mem_peak = detect_amplitude(ch1)
        hb_rms, hb_peak = detect_amplitude(ch2)

        membrane_history.append(mem_rms)
        heartbeat_history.append(hb_rms)

        # Transient detection: compare to rolling median
        def median(vals: collections.deque[float]) -> float:
            if not vals:
                return 0.0
            s = sorted(vals)
            mid = len(s) // 2
            return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2

        mem_median = median(membrane_history)
        hb_median = median(heartbeat_history)

        mem_ratio = mem_rms / mem_median if mem_median > 0.0001 else 0.0
        hb_ratio = hb_rms / hb_median if hb_median > 0.0001 else 0.0

        transient = mem_ratio > 4.0 or hb_ratio > 4.0
        if transient:
            last_transient_time = time.time()

        # Recent transient: within last 2 seconds
        recent = last_transient_time is not None and (time.time() - last_transient_time) < 2.0

        max_ratio = max(mem_ratio, hb_ratio)
        if max_ratio > 4.0:
            activity = "active"
        elif max_ratio > 2.0:
            activity = "moderate"
        else:
            activity = "quiet"

        state = {
            "timestamp": time.time(),
            "membrane_rms": round(mem_rms, 5),
            "membrane_peak": round(mem_peak, 5),
            "heartbeat_rms": round(hb_rms, 5),
            "heartbeat_peak": round(hb_peak, 5),
            "recent_transient": recent,
            "transient_strength": round(max_ratio, 2),
            "activity_level": activity,
        }
        write_state(state)

        if transient:
            print(f"  TRANSIENT! membrane={mem_ratio:.1f}x heartbeat={hb_ratio:.1f}x", flush=True)

        elapsed = time.time() - t0
        time.sleep(max(0, CYCLE_PERIOD - elapsed))


def run_once(ports: list[str]) -> None:
    if not capture_jack(ports, CAPTURE_DURATION, CLIP_FILE):
        print("Capture failed")
        return
    ch1, ch2, sr = read_wav_stereo(CLIP_FILE)
    mem_rms, mem_peak = detect_amplitude(ch1)
    hb_rms, hb_peak = detect_amplitude(ch2)
    print(f"Membrane: rms={mem_rms:.5f} peak={mem_peak:.5f}")
    print(f"Heartbeat: rms={hb_rms:.5f} peak={hb_peak:.5f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Contact Mic Listener")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--ports", nargs="+", default=DEFAULT_PORTS)
    args = parser.parse_args()
    if args.once:
        run_once(args.ports)
    else:
        run_daemon(args.ports)


if __name__ == "__main__":
    main()
