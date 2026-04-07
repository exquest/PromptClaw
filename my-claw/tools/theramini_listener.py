"""Theramini Listener — detects pitch and onset from JACK inputs 3+4.

Runs as a daemon. Captures 0.25s clips via jack_rec, analyzes with
audio_analysis, writes /tmp/theramini_state.json atomically.
"""
from __future__ import annotations

import argparse
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
from audio_analysis import (
    detect_amplitude,
    detect_onset,
    detect_pitch_autocorrelation,
    pitch_to_nearest_key,
    pitch_to_note_name,
)

STATE_FILE = Path("/tmp/theramini_state.json")
CLIP_FILE = Path("/tmp/theramini_clip.wav")
CAPTURE_DURATION = 1  # seconds (jack_rec needs >= 1s)
CYCLE_PERIOD = 1.2  # seconds (capture + analysis + sleep)

DEFAULT_PORTS = ["system:capture_3", "system:capture_4"]


def capture_jack(ports: list[str], duration: float, output: Path) -> bool:
    """Capture audio from JACK ports via jack_rec."""
    cmd = [
        "jack_rec", "-f", str(output), "-d", str(duration), "-b", "16",
    ] + ports
    try:
        subprocess.run(cmd, capture_output=True, timeout=duration + 5)
        return output.exists() and output.stat().st_size > 100
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def read_wav_mono(path: Path) -> tuple[list[int], int]:
    """Read a WAV file and return (mono_samples, sample_rate)."""
    with wave.open(str(path), "r") as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        nframes = w.getnframes()
        raw = w.readframes(nframes)
        samples = list(struct.unpack(f"{nframes * nch}h", raw))
        # Mix to mono by averaging channels
        if nch > 1:
            mono = []
            for i in range(0, len(samples), nch):
                mono.append(sum(samples[i : i + nch]) // nch)
            return mono, sr
        return samples, sr


def write_state(state: dict) -> None:
    """Write state JSON atomically."""
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(str(tmp), str(STATE_FILE))


def analyze_once(
    ports: list[str],
    previous_rms: float,
    onset_time: float | None,
    silence_start: float | None,
) -> tuple[dict, float, float | None, float | None]:
    """Capture and analyze one clip. Returns (state_dict, current_rms, onset_time, silence_start)."""
    now = time.time()

    if not capture_jack(ports, CAPTURE_DURATION, CLIP_FILE):
        state = {
            "timestamp": now,
            "is_playing": False,
            "pitch_hz": None,
            "pitch_note": None,
            "pitch_confidence": 0.0,
            "rms": 0.0,
            "peak": 0.0,
            "state": "silence",
            "suggested_key": None,
            "suggested_scale": None,
            "consecutive_silence_ms": int((now - silence_start) * 1000) if silence_start else 0,
            "onset_time": onset_time,
            "error": "capture_failed",
        }
        return state, 0.0, onset_time, silence_start or now

    try:
        samples, sr = read_wav_mono(CLIP_FILE)
    except Exception:
        return analyze_once.__wrapped_fallback(now, previous_rms, onset_time, silence_start)

    rms, peak = detect_amplitude(samples)
    freq, confidence = detect_pitch_autocorrelation(samples, sr)
    onset_state = detect_onset(rms, previous_rms)

    is_playing = freq is not None and confidence > 0.3 and rms > 0.005
    note_name = pitch_to_note_name(freq) if freq else None
    key_root, key_scale = pitch_to_nearest_key(freq) if freq else (None, None)

    # Track onset and silence timing
    if onset_state == "onset":
        onset_time = now
        silence_start = None
    elif onset_state in ("release", "silence"):
        if silence_start is None:
            silence_start = now
    else:
        silence_start = None

    consecutive_silence_ms = int((now - silence_start) * 1000) if silence_start else 0

    state = {
        "timestamp": now,
        "is_playing": is_playing,
        "pitch_hz": round(freq, 1) if freq else None,
        "pitch_note": note_name,
        "pitch_confidence": round(confidence, 3),
        "rms": round(rms, 4),
        "peak": round(peak, 4),
        "state": onset_state,
        "suggested_key": key_root,
        "suggested_scale": key_scale,
        "consecutive_silence_ms": consecutive_silence_ms,
        "onset_time": onset_time,
    }
    return state, rms, onset_time, silence_start


def run_daemon(ports: list[str]) -> None:
    """Main daemon loop."""
    running = True
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    previous_rms = 0.0
    onset_time: float | None = None
    silence_start: float | None = time.time()

    # Track pitch history to detect idle tone vs human playing
    pitch_history: list[float] = []
    PITCH_HISTORY_SIZE = 8  # ~8 seconds of history
    PITCH_VARIANCE_THRESHOLD = 5.0  # Hz — idle tone varies less than this (human moves >5Hz)

    print(f"Theramini listener started, ports={ports}", flush=True)

    while running:
        t0 = time.time()
        state, previous_rms, onset_time, silence_start = analyze_once(
            ports, previous_rms, onset_time, silence_start
        )

        # Idle tone detection: if pitch is constant (no variation), it's not a human
        if state.get("pitch_hz"):
            pitch_history.append(state["pitch_hz"])
            if len(pitch_history) > PITCH_HISTORY_SIZE:
                pitch_history.pop(0)

            if len(pitch_history) >= 4:
                mean_pitch = sum(pitch_history) / len(pitch_history)
                variance = max(abs(p - mean_pitch) for p in pitch_history)
                if variance < PITCH_VARIANCE_THRESHOLD:
                    # Constant pitch = idle tone, not human playing
                    state["is_playing"] = False
                    state["idle_tone"] = True
                    state["idle_pitch_hz"] = round(mean_pitch, 1)
        else:
            pitch_history.clear()

        write_state(state)

        if state.get("is_playing"):
            print(
                f"  PLAYING: {state['pitch_note']} ({state['pitch_hz']}Hz) "
                f"conf={state['pitch_confidence']} key={state['suggested_key']}",
                flush=True,
            )

        elapsed = time.time() - t0
        sleep_time = max(0, CYCLE_PERIOD - elapsed)
        time.sleep(sleep_time)


def run_once(ports: list[str]) -> None:
    """Single capture and analysis for debugging."""
    state, _, _, _ = analyze_once(ports, 0.0, None, None)
    write_state(state)
    print(json.dumps(state, indent=2, default=str))


def analyze_file(path: str) -> None:
    """Analyze an existing WAV file."""
    samples, sr = read_wav_mono(Path(path))
    rms, peak = detect_amplitude(samples)
    freq, conf = detect_pitch_autocorrelation(samples, sr)
    note = pitch_to_note_name(freq) if freq else None
    key_root, key_scale = pitch_to_nearest_key(freq) if freq else (None, None)
    onset = detect_onset(rms, 0.0)
    print(f"File: {path}")
    print(f"  RMS={rms:.4f} Peak={peak:.4f}")
    print(f"  Pitch={freq:.1f}Hz ({note}) confidence={conf:.3f}" if freq else "  No pitch detected")
    print(f"  Key={key_root} Scale={key_scale}" if key_root else "")
    print(f"  Onset state={onset}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Theramini Listener")
    parser.add_argument("--once", action="store_true", help="Single capture then exit")
    parser.add_argument("--analyze", metavar="FILE", help="Analyze existing WAV")
    parser.add_argument("--ports", nargs="+", default=DEFAULT_PORTS, help="JACK port names")
    args = parser.parse_args()

    if args.analyze:
        analyze_file(args.analyze)
    elif args.once:
        run_once(args.ports)
    else:
        run_daemon(args.ports)


if __name__ == "__main__":
    main()
