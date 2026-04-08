"""Room Listener — speech detection via Perform-VE mic + Whisper.

Pre-classifies audio to avoid Whisper hallucinations on non-speech.
Captures from Perform-VE Analog Surround 7.1:capture_FL via JACK (or webcam mic fallback).
Writes /tmp/room_speech.json atomically.
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
from audio_analysis import classify_audio_content

STATE_FILE = Path("/tmp/room_speech.json")
CLIP_FILE = Path("/tmp/room_clip.wav")
CAPTURE_DURATION = 8  # seconds
CYCLE_PERIOD = 10  # seconds

# Prefer Perform-VE mic via JACK, fall back to webcam mic via ALSA
DEFAULT_JACK_PORT = "Perform-VE Analog Surround 7.1:capture_FL"
FALLBACK_ALSA_DEVICE = "hw:4,0"

# Known Whisper hallucination patterns
HALLUCINATION_PATTERNS = [
    "thank you", "thanks for watching", "subscribe",
    "like and subscribe", "see you next time", "bye",
    "the end", "music", "applause", "♪",
    "subtitles by", "amara.org", "captions by",
    "you", "...", ".", "oh", "hmm",
    "thanks", "okay", "so",
]


def capture_audio(jack_port: str | None, alsa_device: str | None) -> bool:
    """Capture audio from JACK or ALSA fallback."""
    if jack_port:
        cmd = ["pw-jack", "jack_rec", "-f", str(CLIP_FILE), "-d", str(CAPTURE_DURATION),
               "-b", "16", jack_port]
        try:
            subprocess.run(cmd, capture_output=True, timeout=CAPTURE_DURATION + 5)
            if CLIP_FILE.exists() and CLIP_FILE.stat().st_size > 1000:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # Fallback to ALSA webcam mic
    if alsa_device:
        cmd = ["arecord", "-D", alsa_device, "-f", "S16_LE", "-r", "16000",
               "-c", "2", "-d", str(CAPTURE_DURATION), str(CLIP_FILE)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=CAPTURE_DURATION + 5)
            return CLIP_FILE.exists() and CLIP_FILE.stat().st_size > 1000
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
    return False


def read_wav_mono(path: Path) -> tuple[list[int], int]:
    with wave.open(str(path), "r") as w:
        sr = w.getframerate()
        nch = w.getnchannels()
        nframes = w.getnframes()
        raw = w.readframes(nframes)
        samples = list(struct.unpack(f"{nframes * nch}h", raw))
        if nch > 1:
            mono = [sum(samples[i : i + nch]) // nch for i in range(0, len(samples), nch)]
            return mono, sr
        return samples, sr


def write_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(str(tmp), str(STATE_FILE))


def is_hallucination(text: str) -> bool:
    """Check if Whisper output is a known hallucination."""
    clean = text.lower().strip().rstrip(".!?")
    if clean in HALLUCINATION_PATTERNS:
        return True
    if len(clean) < 5:
        return True
    # Repeated phrases
    words = clean.split()
    if len(words) > 3 and len(set(words)) <= 2:
        return True
    return False


def transcribe(wav_path: Path) -> str | None:
    """Run Whisper on a WAV file. Returns transcript or None."""
    try:
        import whisper
        model = getattr(transcribe, "_model", None)
        if model is None:
            print("Loading Whisper small model (CPU)...", flush=True)
            model = whisper.load_model("small", device="cpu")
            transcribe._model = model

        result = model.transcribe(str(wav_path), language="en")
        text = result.get("text", "").strip()

        if not text or is_hallucination(text):
            return None
        return text
    except Exception as e:
        print(f"Whisper error: {e}", flush=True)
        return None


def run_daemon(jack_port: str | None, alsa_device: str | None) -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    last_transcript = ""
    print(f"Room listener started (jack={jack_port}, alsa={alsa_device})", flush=True)

    while True:
        t0 = time.time()

        if not capture_audio(jack_port, alsa_device):
            write_state({"timestamp": time.time(), "speech_detected": False,
                         "error": "capture_failed"})
            time.sleep(CYCLE_PERIOD)
            continue

        try:
            samples, sr = read_wav_mono(CLIP_FILE)
        except Exception:
            time.sleep(CYCLE_PERIOD)
            continue

        # Pre-classify: only send speech-like audio to Whisper
        classification = classify_audio_content(samples, sr)
        audio_type = classification["type"]

        if audio_type != "speech":
            write_state({
                "timestamp": time.time(),
                "speech_detected": False,
                "audio_type": audio_type,
                "whisper_ran": False,
            })
            print(f"  Audio: {audio_type} (skipping Whisper)", flush=True)
        else:
            # Speech detected — run Whisper
            transcript = transcribe(CLIP_FILE)
            if transcript and transcript != last_transcript:
                last_transcript = transcript
                write_state({
                    "timestamp": time.time(),
                    "speech_detected": True,
                    "transcript": transcript,
                    "audio_type": "speech",
                    "whisper_ran": True,
                })
                print(f'  HEARD: "{transcript}"', flush=True)
            else:
                write_state({
                    "timestamp": time.time(),
                    "speech_detected": False,
                    "audio_type": "speech",
                    "whisper_ran": True,
                    "filtered": True,
                })

        # Cleanup clip
        try:
            CLIP_FILE.unlink(missing_ok=True)
        except OSError:
            pass

        elapsed = time.time() - t0
        time.sleep(max(0, CYCLE_PERIOD - elapsed))


def main() -> None:
    parser = argparse.ArgumentParser(description="Room Listener")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--jack-port", default=DEFAULT_JACK_PORT)
    parser.add_argument("--alsa-device", default=FALLBACK_ALSA_DEVICE)
    parser.add_argument("--no-jack", action="store_true", help="Skip JACK, use ALSA only")
    args = parser.parse_args()

    jack = None if args.no_jack else args.jack_port
    alsa = args.alsa_device

    if args.once:
        if not capture_audio(jack, alsa):
            print("Capture failed")
            return
        samples, sr = read_wav_mono(CLIP_FILE)
        cls = classify_audio_content(samples, sr)
        print(f"Classification: {cls}")
        if cls["type"] == "speech":
            text = transcribe(CLIP_FILE)
            print(f"Transcript: {text}")
    else:
        run_daemon(jack, alsa)


if __name__ == "__main__":
    main()
