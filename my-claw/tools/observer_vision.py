"""Observer camera loop with fast local analysis and slower vision summaries."""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from PIL import Image


FRAME = "/tmp/observer_frame.jpg"
STATE = "/tmp/observer_state.json"
VIDEO_DEVICE = os.environ.get("OBSERVER_VIDEO_DEVICE", "/dev/video0")
OLLAMA_URLS = tuple(
    url.strip()
    for url in os.environ.get(
        "OBSERVER_OLLAMA_URLS",
        os.environ.get("OBSERVER_OLLAMA_URL", "http://127.0.0.1:11434/api/chat"),
    ).split(",")
    if url.strip()
)
OLLAMA_URL = OLLAMA_URLS[0]
VISION_MODEL = os.environ.get("OBSERVER_VISION_MODEL", "gemma3:4b")
FAST_INTERVAL = 15.0
VISION_INTERVAL = 120.0
VISION_BUSY_RETRY_S = 300.0
MAX_ERROR_CHARS = 240
MOTION_THRESHOLD = 0.02

PROMPT = (
    "You are CypherClaw, an AI art installation looking at your room. "
    "Describe what you see in under 30 words. "
    "Note people, lighting, your face monitor, anything interesting."
)

PERSON_TOKENS = (
    "person",
    "people",
    "guest",
    "visitor",
    "human",
    "someone",
    "man",
    "woman",
    "standing",
    "watching",
    "looking at",
    "looking toward",
)


def capture(video_device: str = VIDEO_DEVICE, frame_path: str = FRAME) -> bool:
    """Capture a single observer frame."""
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
                frame_path,
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
    if getattr(result, "returncode", 1) != 0:
        return False
    return os.path.exists(frame_path) and os.path.getsize(frame_path) > 1000


def fast_analyze(
    frame_path: str,
    previous_pixels: list[int] | None = None,
) -> tuple[dict[str, Any], list[int]]:
    """Run cheap local image analysis for freshness and motion."""
    img = Image.open(frame_path)
    small = img.resize((80, 60))
    gray = small.convert("L")
    pixels = list(gray.tobytes())
    brightness = sum(pixels) / (len(pixels) * 255.0)

    rgb = small.convert("RGB")
    rgb_bytes = list(rgb.tobytes())
    channels = len(rgb_bytes) // 3
    r_avg = sum(rgb_bytes[0::3]) / channels
    g_avg = sum(rgb_bytes[1::3]) / channels
    b_avg = sum(rgb_bytes[2::3]) / channels

    if max(r_avg, g_avg, b_avg) < 30:
        dominant = "dark"
    elif r_avg > g_avg and r_avg > b_avg:
        dominant = "warm"
    elif b_avg > r_avg and b_avg > g_avg:
        dominant = "cool"
    elif g_avg > r_avg:
        dominant = "natural"
    else:
        dominant = "neutral"

    motion = False
    motion_amount = 0.0
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

    result = {
        "brightness": round(brightness, 4),
        "lighting": lighting,
        "dominant_color": dominant,
        "motion": motion,
        "motion_amount": round(motion_amount, 4),
        # Bright static rooms produced false positives before; motion or vision text must confirm people.
        "someone_here": bool(motion and brightness > 0.08),
        "rgb_avg": [int(r_avg), int(g_avg), int(b_avg)],
    }
    return result, pixels


def description_suggests_person(description: str) -> bool:
    """Infer whether the slow vision model likely saw a person."""
    text = description.lower()
    return any(token in text for token in PERSON_TOKENS)


def is_ollama_busy_error(error: str) -> bool:
    """Return whether an error string indicates Ollama queue saturation."""
    text = error.lower()
    return "503" in text and ("server busy" in text or "pending requests exceeded" in text)


def local_scene_description(
    fast_state: dict[str, Any],
    *,
    visual_person_cue: bool = False,
) -> str:
    """Create a compact local summary when slow multimodal vision is unavailable."""
    lighting = str(fast_state.get("lighting", "unknown")).strip() or "unknown"
    dominant = str(fast_state.get("dominant_color", "neutral")).strip() or "neutral"
    motion = bool(fast_state.get("motion"))

    if visual_person_cue:
        presence = "possible person in view"
    elif motion:
        presence = "movement in the room"
    else:
        presence = "no clear people"

    return f"{lighting} {dominant} room, {presence}."


def error_text(exc: Exception) -> str:
    """Normalize error text for state files without hiding the actual cause."""
    return str(exc).strip()[:MAX_ERROR_CHARS]


def normalize_vision_description(text: str) -> str:
    """Trim low-signal model chatter from scene descriptions."""
    cleaned = text.replace("\r", "").strip()
    for prefix in (
        "Okay, processing…",
        "Okay, processing...",
        "Okay, processing",
        "Processing…",
        "Processing...",
    ):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].lstrip()
    return " ".join(part.strip() for part in cleaned.splitlines() if part.strip())


def parse_http_error(exc: urllib.error.HTTPError) -> RuntimeError:
    """Preserve useful Ollama error details from an HTTP response."""
    detail = ""
    try:
        raw = exc.read().decode()
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            detail = str(parsed.get("error", "")).strip()
        if not detail:
            detail = raw.strip()
    except Exception:
        detail = ""
    suffix = f" {detail}" if detail else ""
    return RuntimeError(f"HTTP Error {exc.code}: {exc.reason}{suffix}")


def _load_cv2():
    """Load cv2 lazily so local development without OpenCV still works."""
    try:
        return importlib.import_module("cv2")
    except Exception:
        return None


def detect_visual_person_cue(frame_path: str, cv2_module=None) -> dict[str, Any]:
    """Detect explicit face/person cues with OpenCV when available."""
    cv2_module = _load_cv2() if cv2_module is None else cv2_module
    if cv2_module is None:
        return {"visual_person_cue": False, "face_count": 0}

    try:
        image = cv2_module.imread(frame_path)
        if image is None:
            return {"visual_person_cue": False, "face_count": 0}
        gray = cv2_module.cvtColor(image, cv2_module.COLOR_BGR2GRAY)
        cascade = cv2_module.CascadeClassifier(
            os.path.join(cv2_module.data.haarcascades, "haarcascade_frontalface_default.xml")
        )
        empty_method = getattr(cascade, "empty", None)
        if callable(empty_method) and empty_method():
            return {"visual_person_cue": False, "face_count": 0}
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24))
        face_count = len(faces)
        return {"visual_person_cue": face_count > 0, "face_count": face_count}
    except Exception:
        return {"visual_person_cue": False, "face_count": 0}


def vision_analyze(frame_path: str, urls: tuple[str, ...] | None = None) -> str:
    """Run the slow multimodal scene description."""
    with open(frame_path, "rb") as handle:
        img_b64 = base64.b64encode(handle.read()).decode()
    payload = json.dumps(
        {
            "model": VISION_MODEL,
            "messages": [{"role": "user", "content": PROMPT, "images": [img_b64]}],
            "stream": False,
            "options": {"num_predict": 60},
        }
    ).encode()
    urls = OLLAMA_URLS if urls is None else urls
    last_error: RuntimeError | None = None
    for index, url in enumerate(urls):
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=90)
        except urllib.error.HTTPError as exc:
            parsed = parse_http_error(exc)
            if is_ollama_busy_error(str(parsed)) and index < len(urls) - 1:
                last_error = parsed
                continue
            raise parsed from exc
        except urllib.error.URLError as exc:
            last_error = RuntimeError(f"URL Error: {exc.reason}")
            if index < len(urls) - 1:
                continue
            raise last_error from exc
        except OSError as exc:
            last_error = RuntimeError(str(exc))
            if index < len(urls) - 1:
                continue
            raise last_error from exc
        text = json.loads(resp.read()).get("message", {}).get("content", "").strip()
        return normalize_vision_description(text)
    if last_error is not None:
        raise last_error
    raise RuntimeError("No observer vision URLs configured")


def write_state(state: dict[str, Any], state_path: str | None = None) -> None:
    """Atomically write the observer state."""
    state_path = STATE if state_path is None else state_path
    tmp = state_path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(state, handle)
    os.replace(tmp, state_path)


def _start_vision_worker(frame_path: str) -> tuple[threading.Thread, dict[str, Any]]:
    """Run slow vision off the fast loop thread."""
    result: dict[str, Any] = {"done": False, "description": "", "error": ""}

    def worker() -> None:
        try:
            result["description"] = vision_analyze(frame_path)
        except Exception as exc:
            result["error"] = error_text(exc)
        finally:
            result["done"] = True

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread, result


def run_loop(
    *,
    interval: float = FAST_INTERVAL,
    vision_interval: float = VISION_INTERVAL,
    max_iterations: int = 0,
    video_device: str = VIDEO_DEVICE,
) -> None:
    """Run the observer loop continuously."""
    previous_pixels: list[int] | None = None
    last_vision = 0.0
    last_description = ""
    last_vision_error = ""
    vision_retry_after = 0.0
    vision_thread: threading.Thread | None = None
    vision_result: dict[str, Any] | None = None
    iteration = 0

    print("Observer (fast vision + slow scene summary) started", flush=True)
    while True:
        try:
            if vision_thread and not vision_thread.is_alive() and vision_result:
                if vision_result.get("description"):
                    last_description = str(vision_result["description"])
                    last_vision_error = ""
                    vision_retry_after = 0.0
                    print(f"Vision: {last_description[:60]}", flush=True)
                elif vision_result.get("error"):
                    last_vision_error = str(vision_result["error"])
                    if is_ollama_busy_error(last_vision_error):
                        vision_retry_after = time.time() + VISION_BUSY_RETRY_S
                vision_thread = None
                vision_result = None

            if capture(video_device=video_device, frame_path=FRAME):
                result, previous_pixels = fast_analyze(FRAME, previous_pixels=previous_pixels)
                person_cue = detect_visual_person_cue(FRAME)
                now = time.time()
                someone_here = (
                    result["someone_here"]
                    or bool(person_cue["visual_person_cue"])
                    or description_suggests_person(last_description)
                )
                description = last_description or local_scene_description(
                    result,
                    visual_person_cue=bool(person_cue["visual_person_cue"]),
                )
                state = {
                    "timestamp": now,
                    "ok": True,
                    "frame_path": FRAME,
                    "video_device": video_device,
                    "description": description,
                    "vision_backend": "ollama" if last_description else "local_fallback",
                    "vision_error": last_vision_error,
                    **{**result, **person_cue, "someone_here": someone_here},
                }
                write_state(state)

                if vision_thread is None and now >= vision_retry_after and now - last_vision >= vision_interval:
                    last_vision = now
                    vision_thread, vision_result = _start_vision_worker(FRAME)
            else:
                write_state({"timestamp": time.time(), "ok": False, "error": "capture_failed"})
        except Exception as exc:
            write_state({"timestamp": time.time(), "ok": False, "error": error_text(exc)})

        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            break
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="CypherClaw observer vision loop")
    parser.add_argument("--interval", type=float, default=FAST_INTERVAL)
    parser.add_argument("--vision-interval", type=float, default=VISION_INTERVAL)
    parser.add_argument("--video-device", default=VIDEO_DEVICE)
    args = parser.parse_args()
    run_loop(interval=args.interval, vision_interval=args.vision_interval, video_device=args.video_device)


if __name__ == "__main__":
    main()
