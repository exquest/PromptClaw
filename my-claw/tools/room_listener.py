"""Room Listener — speech detection via Perform-VE mic + Whisper.

Pre-classifies audio to avoid Whisper hallucinations on non-speech.
Captures from Perform-VE Analog Surround 7.1:capture_FL via JACK (or webcam mic fallback).
Writes /tmp/room_speech.json atomically.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from audio_analysis import classify_audio_content
from capture_alias import persist_capture_alias

STATE_FILE = Path("/tmp/room_speech.json")
CLIP_FILE = Path("/tmp/room_clip.wav")
SAMPLE_CAPTURE_FILE = Path("/tmp/room_capture.wav")
CAPTURE_DURATION = 8  # seconds
CYCLE_PERIOD = 10  # seconds

# Prefer Perform-VE mic via JACK, fall back to webcam mic via ALSA
DEFAULT_JACK_PORT = "Perform-VE Analog Surround 7.1:capture_FL"
DEFAULT_PIPEWIRE_TARGET = "Perform-VE"
FALLBACK_JACK_PORTS = ("system:capture_1", "PipeWire:capture_FL")
FALLBACK_ALSA_DEVICE = "auto"
ALSA_CAPTURE_FORMATS = ("S16_LE", "S32_LE")

# Known Whisper hallucination patterns
HALLUCINATION_PATTERNS = [
    "thank you", "thanks for watching", "subscribe",
    "like and subscribe", "see you next time", "bye",
    "the end", "music", "applause", "♪",
    "subtitles by", "amara.org", "captions by",
    "you", "...", ".", "oh", "hmm",
    "thanks", "okay", "so",
]

ARECORD_CAPTURE_RE = re.compile(
    r"card\s+(?P<card>\d+):\s+(?P<card_id>[^\[]+)\[(?P<card_name>[^\]]+)\],\s+device\s+"
    r"(?P<device>\d+):\s+(?P<device_id>[^\[]+)\[(?P<device_name>[^\]]+)\]"
)
PIPEWIRE_TARGET_RE = re.compile(r"(?P<id>\d+)\.\s+(?P<name>.+?)\s+\[alsa\]")


def resolve_pipewire_target(
    status: str | None = None,
    preferred_name: str = DEFAULT_PIPEWIRE_TARGET,
) -> str | None:
    """Resolve a PipeWire target id for the preferred device name."""
    if status is None:
        try:
            result = subprocess.run(
                ["wpctl", "status"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            status = result.stdout
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return None
    preferred = preferred_name.lower()
    for line in status.splitlines():
        if preferred not in line.lower():
            continue
        match = PIPEWIRE_TARGET_RE.search(line)
        if match:
            return match.group("id")
    return None


def list_alsa_capture_devices(listing: str | None = None) -> list[str]:
    """Choose viable ALSA capture devices ordered by preference."""
    if listing is None:
        try:
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            listing = result.stdout
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return []

    devices: list[tuple[int, int, int, str]] = []
    for line in listing.splitlines():
        match = ARECORD_CAPTURE_RE.search(line)
        if not match:
            continue
        card = int(match.group("card"))
        device = int(match.group("device"))
        label = " ".join(
            (
                match.group("card_id"),
                match.group("card_name"),
                match.group("device_id"),
                match.group("device_name"),
            )
        ).lower()
        if "perform" in label:
            priority = 0
        elif "c920" in label or "webcam" in label:
            priority = 1
        elif "pch" in label or "analog" in label:
            priority = 2
        else:
            priority = 3
        devices.append((priority, card, device, f"hw:{card},{device}"))

    if not devices:
        return []
    devices.sort()
    return [device[3] for device in devices]


def select_alsa_capture_device(listing: str | None = None) -> str | None:
    """Choose the top-ranked ALSA capture device."""
    devices = list_alsa_capture_devices(listing)
    return devices[0] if devices else None


def resolve_alsa_device(alsa_device: str | None) -> str | None:
    """Resolve an explicit or auto-selected ALSA device."""
    if not alsa_device:
        return None
    if alsa_device != "auto":
        return alsa_device
    return select_alsa_capture_device()


def resolve_alsa_devices(alsa_device: str | None) -> list[str]:
    """Resolve one or more ALSA devices to try in order."""
    if not alsa_device:
        return []
    if alsa_device != "auto":
        return [alsa_device]
    return list_alsa_capture_devices()


def resolve_jack_capture_ports(jack_port: str | None) -> list[str]:
    """Return JACK capture ports to try, preserving explicit preference first."""
    if not jack_port:
        return []
    ports: list[str] = []
    for port in (jack_port, *FALLBACK_JACK_PORTS):
        if port and port not in ports:
            ports.append(port)
    return ports


def jack_capture_port_exists(port: str) -> bool:
    """Best-effort JACK port probe.

    If probing itself fails or returns no usable listing, stay optimistic so
    mocked tests and unusual JACK wrappers can still attempt capture.
    """
    try:
        result = subprocess.run(
            ["jack_lsp"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return True
    listing = result.stdout or ""
    if result.returncode != 0 or not listing.strip():
        return True
    return port in set(listing.splitlines())


def _jack_record_commands(port: str) -> list[list[str]]:
    return [
        ["jack_rec", "-f", str(CLIP_FILE), "-d", str(CAPTURE_DURATION), "-b", "16", port],
        ["pw-jack", "jack_rec", "-f", str(CLIP_FILE), "-d", str(CAPTURE_DURATION), "-b", "16", port],
    ]


def capture_audio(
    jack_port: str | None,
    alsa_device: str | None,
) -> tuple[bool, str | None, str | None]:
    """Capture audio from PipeWire, JACK, or ALSA fallback."""
    pipewire_target = resolve_pipewire_target()
    if pipewire_target:
        cmd = [
            "timeout",
            str(CAPTURE_DURATION + 1),
            "pw-record",
            "--target",
            pipewire_target,
            "--channels",
            "1",
            "--rate",
            "16000",
            "--format",
            "s16",
            str(CLIP_FILE),
        ]
        try:
            CLIP_FILE.unlink(missing_ok=True)
            subprocess.run(cmd, capture_output=True, timeout=CAPTURE_DURATION + 5)
            if CLIP_FILE.exists() and CLIP_FILE.stat().st_size > 1000:
                return True, "pipewire", pipewire_target
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    for resolved_jack_port in resolve_jack_capture_ports(jack_port):
        if not jack_capture_port_exists(resolved_jack_port):
            continue
        for cmd in _jack_record_commands(resolved_jack_port):
            try:
                CLIP_FILE.unlink(missing_ok=True)
                subprocess.run(cmd, capture_output=True, timeout=CAPTURE_DURATION + 5)
                if CLIP_FILE.exists() and CLIP_FILE.stat().st_size > 1000:
                    return True, "jack", resolved_jack_port
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

    # Fallback to ALSA webcam mic
    for resolved_alsa_device in resolve_alsa_devices(alsa_device):
        for sample_format in ALSA_CAPTURE_FORMATS:
            cmd = ["arecord", "-D", resolved_alsa_device, "-f", sample_format, "-r", "16000",
                   "-c", "2", "-d", str(CAPTURE_DURATION), str(CLIP_FILE)]
            try:
                CLIP_FILE.unlink(missing_ok=True)
                subprocess.run(cmd, capture_output=True, timeout=CAPTURE_DURATION + 5)
                if CLIP_FILE.exists() and CLIP_FILE.stat().st_size > 1000:
                    return True, "alsa", resolved_alsa_device
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
    return False, None, None


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

        captured, capture_backend, capture_source = capture_audio(jack_port, alsa_device)
        if not captured:
            write_state(
                {
                    "timestamp": time.time(),
                    "speech_detected": False,
                    "capture_backend": capture_backend,
                    "capture_source": capture_source,
                    "error": "capture_failed",
                }
            )
            time.sleep(CYCLE_PERIOD)
            continue
        persist_capture_alias(CLIP_FILE, SAMPLE_CAPTURE_FILE)

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
                "capture_backend": capture_backend,
                "capture_source": capture_source,
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
                    "capture_backend": capture_backend,
                    "capture_source": capture_source,
                })
                print(f'  HEARD: "{transcript}"', flush=True)
            else:
                write_state({
                    "timestamp": time.time(),
                    "speech_detected": False,
                    "audio_type": "speech",
                    "whisper_ran": True,
                    "filtered": True,
                    "capture_backend": capture_backend,
                    "capture_source": capture_source,
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
