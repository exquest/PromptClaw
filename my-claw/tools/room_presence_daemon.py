"""Low-overhead room presence daemon for CypherClaw."""

from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image


FRAME_PATH = Path("/tmp/room_frame.jpg")
OUTPUT_PATH = Path("/tmp/room_presence.json")
OBSERVER_FRAME_PATH = Path("/tmp/observer_frame.jpg")
DEFAULT_VIDEO_DEVICE = "/dev/video0"
DEFAULT_INTERVAL = 15.0
MOTION_THRESHOLD = 0.02
PRESENCE_BRIGHTNESS_THRESHOLD = 0.15
MIN_FRAME_BYTES = 256


def capture_frame(video_device: str, frame_path: Path) -> bool:
    """Capture a single frame from the room camera."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "v4l2",
                "-video_size",
                "640x480",
                "-i",
                video_device,
                "-frames:v",
                "1",
                "-update",
                "1",
                str(frame_path),
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
    if getattr(result, "returncode", 1) != 0:
        return False
    return frame_path.exists() and frame_path.stat().st_size > MIN_FRAME_BYTES


def analyze_frame(
    frame_path: Path,
    *,
    previous_pixels: list[int] | None,
) -> tuple[dict[str, object], list[int]]:
    """Analyze brightness and motion from a captured frame."""
    image = Image.open(frame_path)
    gray = image.resize((80, 60)).convert("L")
    pixels = list(gray.tobytes())
    brightness = sum(pixels) / (len(pixels) * 255.0)

    motion_amount = 0.0
    motion = False
    if previous_pixels and len(previous_pixels) == len(pixels):
        diff = sum(abs(a - b) for a, b in zip(pixels, previous_pixels))
        motion_amount = diff / (len(pixels) * 255.0)
        motion = motion_amount > MOTION_THRESHOLD

    if brightness < 0.05:
        lighting = "dark"
    elif brightness < 0.15:
        lighting = "dim"
    elif brightness < 0.4:
        lighting = "moderate"
    else:
        lighting = "bright"

    state = {
        "ok": True,
        "brightness": round(brightness, 4),
        "lighting": lighting,
        "motion": motion,
        "motion_amount": round(motion_amount, 4),
        "someone_here": motion or brightness >= PRESENCE_BRIGHTNESS_THRESHOLD,
    }
    return state, pixels


def write_state(output_path: Path, state: dict[str, object]) -> None:
    """Atomically write room presence state."""
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(state))
    os.replace(tmp_path, output_path)


def load_fallback_observer_frame(
    *,
    previous_pixels: list[int] | None,
    observer_frame_path: Path | None = None,
    mirror_frame_path: Path | None = None,
) -> tuple[dict[str, object], list[int]] | None:
    """Reuse the shared observer frame when the single room camera is busy."""
    observer_frame_path = OBSERVER_FRAME_PATH if observer_frame_path is None else observer_frame_path
    mirror_frame_path = FRAME_PATH if mirror_frame_path is None else mirror_frame_path
    if not observer_frame_path.exists() or observer_frame_path.stat().st_size <= MIN_FRAME_BYTES:
        return None

    state, pixels = analyze_frame(observer_frame_path, previous_pixels=previous_pixels)
    if observer_frame_path != mirror_frame_path:
        shutil.copyfile(observer_frame_path, mirror_frame_path)
    state["frame_path"] = str(mirror_frame_path)
    state["capture_source"] = "observer_frame"
    return state, pixels


def run_daemon(
    *,
    interval: float = DEFAULT_INTERVAL,
    video_device: str = DEFAULT_VIDEO_DEVICE,
    max_iterations: int = 0,
    observer_frame_only: bool = False,
) -> None:
    """Run the low-overhead room presence loop."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    previous_pixels: list[int] | None = None
    iteration = 0
    while True:
        now = time.time()
        if observer_frame_only:
            fallback = load_fallback_observer_frame(previous_pixels=previous_pixels)
            if fallback is not None:
                state, previous_pixels = fallback
                state["timestamp"] = now
                state["ok"] = True
            else:
                state = {"timestamp": now, "ok": False, "error": "capture_failed"}
        elif capture_frame(video_device, FRAME_PATH):
            try:
                state, previous_pixels = analyze_frame(FRAME_PATH, previous_pixels=previous_pixels)
                state["timestamp"] = now
                state["frame_path"] = str(FRAME_PATH)
                state["capture_source"] = "camera"
            except Exception as exc:
                state = {"timestamp": now, "ok": False, "error": str(exc)[:80]}
        else:
            fallback = load_fallback_observer_frame(previous_pixels=previous_pixels)
            if fallback is not None:
                state, previous_pixels = fallback
                state["timestamp"] = now
                state["ok"] = True
            else:
                state = {"timestamp": now, "ok": False, "error": "capture_failed"}

        write_state(OUTPUT_PATH, state)
        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            break
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="CypherClaw room presence daemon")
    parser.add_argument("--video-device", default=DEFAULT_VIDEO_DEVICE)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--observer-frame-only", action="store_true")
    args = parser.parse_args()
    run_daemon(interval=args.interval, video_device=args.video_device, observer_frame_only=args.observer_frame_only)


if __name__ == "__main__":
    main()
