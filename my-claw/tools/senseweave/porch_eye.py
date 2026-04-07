"""SenseWeave Porch Eye — camera frame capture and environmental analysis.

Captures frames from UniFi cameras via RTSPS and performs:
  - Brightness analysis (average luminance)
  - Motion detection (frame-to-frame pixel diff)
  - Weather/lighting classification (day, night, dawn, dusk, overcast)

Writes:
  /tmp/porch_eye_state.json — Current porch state (atomic)
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional PIL import — fall back to file-size heuristic if unavailable
# ---------------------------------------------------------------------------

try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_STATE_FILE = "/tmp/porch_eye_state.json"


# ---------------------------------------------------------------------------
# PorchEyeState dataclass
# ---------------------------------------------------------------------------


@dataclass
class PorchEyeState:
    brightness: float = 0.0
    weather: str = "unknown"
    motion_detected: bool = False
    last_capture_time: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# capture_frame
# ---------------------------------------------------------------------------


def capture_frame(rtsp_url: str, output_path: str, timeout: int = 10) -> bool:
    """Capture a single frame from an RTSP stream using ffmpeg.

    Returns True on success (file exists after capture), False otherwise.
    """
    cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-frames:v", "1",
        "-update", "1",
        "-y",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        if result.returncode != 0:
            return False
        return os.path.isfile(output_path)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


# ---------------------------------------------------------------------------
# analyze_brightness
# ---------------------------------------------------------------------------


def analyze_brightness(image_path: str) -> float:
    """Calculate average brightness of an image (0.0=black, 1.0=white).

    Uses PIL if available; otherwise falls back to a file-size heuristic
    (larger JPEG = more data = likely brighter, rough estimate only).
    """
    if not os.path.isfile(image_path):
        return 0.0

    if _HAS_PIL:
        try:
            img = Image.open(image_path).convert("L")  # grayscale
            pixels = list(
                img.get_flattened_data()
                if hasattr(img, "get_flattened_data")
                else img.getdata()
            )
            if not pixels:
                return 0.0
            return sum(pixels) / (len(pixels) * 255.0)
        except Exception:
            return 0.0
    else:
        # File-size heuristic: JPEG compression makes dark images smaller.
        # This is very rough — a 1x1 black JPEG ~ 340 bytes, white ~ 340 bytes
        # For larger images, brighter images tend to compress slightly larger.
        try:
            size = os.path.getsize(image_path)
            # Clamp to [0, 1] range with a rough scale.
            # Typical JPEG: 10KB-500KB for a 1080p frame.
            # Use a sigmoid-like mapping.
            if size < 100:
                return 0.0
            # Rough: small files = dark, large = bright (very approximate)
            ratio = min(size / 50000.0, 1.0)
            return max(0.0, min(1.0, ratio))
        except OSError:
            return 0.0


# ---------------------------------------------------------------------------
# detect_motion
# ---------------------------------------------------------------------------


def detect_motion(
    frame_a_path: str, frame_b_path: str, threshold: float = 0.05
) -> dict:
    """Compare two frames for motion.

    Returns {"motion_detected": bool, "change_ratio": float}.
    change_ratio is the fraction of pixels that changed significantly.
    """
    no_motion = {"motion_detected": False, "change_ratio": 0.0}

    if not os.path.isfile(frame_a_path) or not os.path.isfile(frame_b_path):
        return no_motion

    if _HAS_PIL:
        try:
            img_a = Image.open(frame_a_path).convert("L")
            img_b = Image.open(frame_b_path).convert("L")

            # Resize to common dimensions if needed
            if img_a.size != img_b.size:
                target = (min(img_a.width, img_b.width), min(img_a.height, img_b.height))
                img_a = img_a.resize(target)
                img_b = img_b.resize(target)

            _get = "get_flattened_data" if hasattr(img_a, "get_flattened_data") else "getdata"
            pixels_a = list(getattr(img_a, _get)())
            pixels_b = list(getattr(img_b, _get)())
            total = len(pixels_a)
            if total == 0:
                return no_motion

            # Count pixels where absolute difference exceeds a per-pixel threshold
            # (30/255 ~ 12% brightness change per pixel is "changed")
            pixel_threshold = 30
            changed = sum(
                1 for a, b in zip(pixels_a, pixels_b)
                if abs(a - b) > pixel_threshold
            )
            change_ratio = changed / total
            return {
                "motion_detected": change_ratio > threshold,
                "change_ratio": change_ratio,
            }
        except Exception:
            return no_motion
    else:
        # Without PIL: compare raw file bytes (very rough)
        try:
            data_a = Path(frame_a_path).read_bytes()
            data_b = Path(frame_b_path).read_bytes()
            if not data_a or not data_b:
                return no_motion
            # Compare byte lengths as a rough proxy
            max_len = max(len(data_a), len(data_b))
            diff = abs(len(data_a) - len(data_b))
            change_ratio = diff / max_len if max_len > 0 else 0.0
            return {
                "motion_detected": change_ratio > threshold,
                "change_ratio": change_ratio,
            }
        except OSError:
            return no_motion


# ---------------------------------------------------------------------------
# classify_weather
# ---------------------------------------------------------------------------


def classify_weather(brightness: float, hour: int) -> str:
    """Classify weather/lighting based on brightness and hour of day.

    Returns one of: "day", "night", "dawn", "dusk", "overcast".

    Rules:
      - Dawn:     5 <= hour <= 7  (transitional)
      - Dusk:     18 <= hour <= 20 (transitional)
      - Night:    brightness < 0.15 and not dawn/dusk hours
      - Day:      brightness >= 0.5 and daytime hours (8-17)
      - Overcast: dim (< 0.5) during daytime hours (8-17)
    """
    is_dawn_hour = 5 <= hour <= 7
    is_dusk_hour = 18 <= hour <= 20
    is_daytime_hour = 8 <= hour <= 17

    if is_dawn_hour:
        return "dawn"
    if is_dusk_hour:
        return "dusk"
    if brightness < 0.15:
        return "night"
    if is_daytime_hour:
        if brightness >= 0.5:
            return "day"
        return "overcast"
    # Bright outside daytime (e.g. hour 21+ with bright light = still "day")
    if brightness >= 0.5:
        return "day"
    return "night"


# ---------------------------------------------------------------------------
# run_porch_eye (daemon loop)
# ---------------------------------------------------------------------------


def run_porch_eye(
    rtsp_url: str,
    capture_dir: str,
    interval: float = 30.0,
    max_iterations: int = 0,
) -> None:
    """Daemon loop: capture, analyze, detect motion, classify, write state.

    If *max_iterations* > 0, stop after that many iterations (for testing).
    If *max_iterations* == 0, run forever.
    """
    capture_path = Path(capture_dir)
    capture_path.mkdir(parents=True, exist_ok=True)

    prev_frame: str | None = None
    iteration = 0

    while True:
        state = PorchEyeState()
        now = time.time()
        frame_file = str(capture_path / f"frame_{iteration % 2}.jpg")

        try:
            ok = capture_frame(rtsp_url, frame_file)
            if not ok:
                state.error = "capture_failed"
                state.last_capture_time = now
                _write_state(state)
                iteration += 1
                if max_iterations > 0 and iteration >= max_iterations:
                    break
                if interval > 0:
                    time.sleep(interval)
                continue

            state.last_capture_time = now
            state.brightness = analyze_brightness(frame_file)

            # Motion detection against previous frame
            if prev_frame is not None and os.path.isfile(prev_frame):
                motion = detect_motion(prev_frame, frame_file)
                state.motion_detected = motion["motion_detected"]
            else:
                state.motion_detected = False

            # Weather classification
            current_hour = datetime.now().hour
            state.weather = classify_weather(state.brightness, current_hour)

            prev_frame = frame_file

        except Exception as exc:
            state.error = str(exc)

        _write_state(state)

        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            break
        if interval > 0:
            time.sleep(interval)


# ---------------------------------------------------------------------------
# _write_state — atomic JSON write
# ---------------------------------------------------------------------------


def _write_state(state: PorchEyeState, output_path: str = "") -> None:
    """Atomically write PorchEyeState to JSON file."""
    path = output_path or DEFAULT_STATE_FILE
    tmp_path = path + ".tmp"
    data = asdict(state)
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SenseWeave Porch Eye daemon")
    parser.add_argument("url", help="RTSPS camera URL")
    parser.add_argument(
        "--capture-dir",
        default="/tmp/porch_eye_captures",
        help="Directory for captured frames (default: /tmp/porch_eye_captures)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        help="Seconds between capture cycles (default: 30.0)",
    )
    args = parser.parse_args()

    print(f"[porch_eye] Starting porch eye daemon (interval={args.interval}s)")
    print(f"  url:         {args.url}")
    print(f"  capture_dir: {args.capture_dir}")
    print(f"  state:       {DEFAULT_STATE_FILE}")

    try:
        run_porch_eye(args.url, args.capture_dir, interval=args.interval)
    except KeyboardInterrupt:
        print("\n[porch_eye] Stopped.")
