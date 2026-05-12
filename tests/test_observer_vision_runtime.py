"""Tests for observer_vision.py runtime behavior."""

from __future__ import annotations

import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

import observer_vision as mod


def test_description_suggests_person_detection() -> None:
    assert mod.description_suggests_person("A person is standing near the monitor.") is True
    assert mod.description_suggests_person("Empty room with cables and shelves.") is False


def test_detect_visual_person_cue_without_cv2_is_safe_false() -> None:
    result = mod.detect_visual_person_cue("/tmp/nonexistent.jpg", cv2_module=None)

    assert result["visual_person_cue"] is False
    assert result["face_count"] == 0


def test_detect_visual_person_cue_counts_faces_with_cv2() -> None:
    class FakeCascade:
        def __init__(self, path: str) -> None:
            self.empty = False

        def empty(self) -> bool:  # pragma: no cover - fake API shape
            return False

        def detectMultiScale(self, image, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24)):
            return [(1, 2, 30, 30)]

    fake_cv2 = SimpleNamespace(
        data=SimpleNamespace(haarcascades="/tmp/"),
        imread=lambda path: object(),
        cvtColor=lambda image, code: image,
        COLOR_BGR2GRAY=6,
        CascadeClassifier=lambda path: FakeCascade(path),
    )

    result = mod.detect_visual_person_cue("/tmp/frame.jpg", cv2_module=fake_cv2)

    assert result["visual_person_cue"] is True
    assert result["face_count"] == 1


def test_run_loop_writes_fast_state_before_slow_vision(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "observer_frame.jpg"
    state_path = tmp_path / "observer_state.json"
    frame.write_bytes(b"0" * 2048)

    monkeypatch.setattr(mod, "FRAME", str(frame))
    monkeypatch.setattr(mod, "STATE", str(state_path))
    monkeypatch.setattr(mod, "VISION_INTERVAL", 0)
    monkeypatch.setattr(mod, "capture", lambda *args, **kwargs: True)
    monkeypatch.setattr(mod, "detect_visual_person_cue", lambda frame_path: {"visual_person_cue": False, "face_count": 0})
    monkeypatch.setattr(
        mod,
        "fast_analyze",
        lambda frame_path, previous_pixels=None: (
            {
                "brightness": 0.18,
                "lighting": "moderate",
                "dominant_color": "neutral",
                "motion": False,
                "motion_amount": 0.0,
                "someone_here": False,
                "rgb_avg": [100, 100, 100],
            },
            [1, 2, 3],
        ),
    )

    def fake_vision(frame_path: str) -> str:
        written = json.loads(state_path.read_text())
        assert written["ok"] is True
        assert written["vision_backend"] == "local_fallback"
        assert written["description"]
        return "A person is standing in the room."

    monkeypatch.setattr(mod, "vision_analyze", fake_vision)

    mod.run_loop(interval=0.01, max_iterations=3)

    written = json.loads(state_path.read_text())
    assert written["description"] == "A person is standing in the room."
    assert written["someone_here"] is True


def test_run_loop_does_not_block_on_slow_vision(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "observer_frame.jpg"
    state_path = tmp_path / "observer_state.json"
    frame.write_bytes(b"0" * 2048)

    monkeypatch.setattr(mod, "FRAME", str(frame))
    monkeypatch.setattr(mod, "STATE", str(state_path))
    monkeypatch.setattr(mod, "VISION_INTERVAL", 0)
    monkeypatch.setattr(mod, "capture", lambda *args, **kwargs: True)
    monkeypatch.setattr(mod, "detect_visual_person_cue", lambda frame_path: {"visual_person_cue": False, "face_count": 0})
    monkeypatch.setattr(
        mod,
        "fast_analyze",
        lambda frame_path, previous_pixels=None: (
            {
                "brightness": 0.18,
                "lighting": "moderate",
                "dominant_color": "neutral",
                "motion": False,
                "motion_amount": 0.0,
                "someone_here": False,
                "rgb_avg": [100, 100, 100],
            },
            [1, 2, 3],
        ),
    )

    def slow_vision(frame_path: str) -> str:
        time.sleep(0.2)
        return "Empty room."

    monkeypatch.setattr(mod, "vision_analyze", slow_vision)

    started = time.monotonic()
    mod.run_loop(interval=0.0, max_iterations=2)
    elapsed = time.monotonic() - started

    written = json.loads(state_path.read_text())
    assert written["ok"] is True
    assert elapsed < 0.15


def test_run_loop_promotes_explicit_visual_person_cue(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "observer_frame.jpg"
    state_path = tmp_path / "observer_state.json"
    frame.write_bytes(b"0" * 2048)

    monkeypatch.setattr(mod, "FRAME", str(frame))
    monkeypatch.setattr(mod, "STATE", str(state_path))
    monkeypatch.setattr(mod, "capture", lambda *args, **kwargs: True)
    monkeypatch.setattr(mod, "detect_visual_person_cue", lambda frame_path: {"visual_person_cue": True, "face_count": 1})
    monkeypatch.setattr(
        mod,
        "fast_analyze",
        lambda frame_path, previous_pixels=None: (
            {
                "brightness": 0.11,
                "lighting": "dim",
                "dominant_color": "neutral",
                "motion": False,
                "motion_amount": 0.0,
                "someone_here": False,
                "rgb_avg": [90, 90, 90],
            },
            [1, 2, 3],
        ),
    )

    mod.run_loop(interval=0.0, max_iterations=1)

    written = json.loads(state_path.read_text())
    assert written["someone_here"] is True
    assert written["visual_person_cue"] is True
    assert written["face_count"] == 1


def test_capture_rejects_failed_ffmpeg_even_when_stale_frame_exists(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "observer_frame.jpg"
    frame.write_bytes(b"0" * 4096)

    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    assert mod.capture(video_device="/dev/video0", frame_path=str(frame)) is False


def test_is_ollama_busy_error_detects_queue_saturation() -> None:
    assert mod.is_ollama_busy_error("HTTP Error 503: server busy, please try again. maximum pending requests exceeded")
    assert not mod.is_ollama_busy_error("HTTP Error 404: model not found")


def test_local_scene_description_summarizes_fast_state() -> None:
    description = mod.local_scene_description(
        {
            "lighting": "dim",
            "dominant_color": "dark",
            "motion": False,
        },
        visual_person_cue=False,
    )

    assert "dim" in description
    assert "dark" in description
    assert "no clear people" in description


def test_normalize_vision_description_strips_processing_preamble() -> None:
    text = mod.normalize_vision_description(
        "Okay, processing…\n\nDark kitchen, a patterned blind casts shadows."
    )

    assert text == "Dark kitchen, a patterned blind casts shadows."


def test_run_loop_uses_local_fallback_description_when_vision_server_is_busy(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "observer_frame.jpg"
    state_path = tmp_path / "observer_state.json"
    frame.write_bytes(b"0" * 2048)

    monkeypatch.setattr(mod, "FRAME", str(frame))
    monkeypatch.setattr(mod, "STATE", str(state_path))
    monkeypatch.setattr(mod, "VISION_INTERVAL", 0)
    monkeypatch.setattr(mod, "VISION_BUSY_RETRY_S", 60.0)
    monkeypatch.setattr(mod, "capture", lambda *args, **kwargs: True)
    monkeypatch.setattr(mod, "detect_visual_person_cue", lambda frame_path: {"visual_person_cue": False, "face_count": 0})
    monkeypatch.setattr(
        mod,
        "fast_analyze",
        lambda frame_path, previous_pixels=None: (
            {
                "brightness": 0.09,
                "lighting": "dim",
                "dominant_color": "dark",
                "motion": False,
                "motion_amount": 0.0,
                "someone_here": False,
                "rgb_avg": [20, 20, 20],
            },
            [1, 2, 3],
        ),
    )
    monkeypatch.setattr(
        mod,
        "vision_analyze",
        lambda frame_path: (_ for _ in ()).throw(RuntimeError("HTTP Error 503: server busy, maximum pending requests exceeded")),
    )

    mod.run_loop(interval=0.0, max_iterations=3)

    written = json.loads(state_path.read_text())
    assert written["vision_backend"] == "local_fallback"
    assert "HTTP Error 503" in written["vision_error"]
    assert "dim" in written["description"]
    assert "no clear people" in written["description"]


def test_run_loop_preserves_detailed_busy_error_text(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "observer_frame.jpg"
    state_path = tmp_path / "observer_state.json"
    frame.write_bytes(b"0" * 2048)

    monkeypatch.setattr(mod, "FRAME", str(frame))
    monkeypatch.setattr(mod, "STATE", str(state_path))
    monkeypatch.setattr(mod, "VISION_INTERVAL", 0)
    monkeypatch.setattr(mod, "capture", lambda *args, **kwargs: True)
    monkeypatch.setattr(mod, "detect_visual_person_cue", lambda frame_path: {"visual_person_cue": False, "face_count": 0})
    monkeypatch.setattr(
        mod,
        "fast_analyze",
        lambda frame_path, previous_pixels=None: (
            {
                "brightness": 0.09,
                "lighting": "dim",
                "dominant_color": "dark",
                "motion": False,
                "motion_amount": 0.0,
                "someone_here": False,
                "rgb_avg": [20, 20, 20],
            },
            [1, 2, 3],
        ),
    )
    monkeypatch.setattr(
        mod,
        "vision_analyze",
        lambda frame_path: (_ for _ in ()).throw(
            RuntimeError(
                "HTTP Error 503: Service Unavailable server busy, please try again. "
                "maximum pending requests exceeded"
            )
        ),
    )

    mod.run_loop(interval=0.0, max_iterations=3)

    written = json.loads(state_path.read_text())
    assert "maximum pending requests exceeded" in written["vision_error"]


def test_vision_analyze_preserves_http_error_body(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "observer_frame.jpg"
    frame.write_bytes(b"0" * 2048)

    def fake_urlopen(*args, **kwargs):
        raise HTTPError(
            mod.OLLAMA_URL,
            503,
            "Service Unavailable",
            hdrs=None,
            fp=BytesIO(b'{\"error\":\"server busy, please try again. maximum pending requests exceeded\"}'),
        )

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    try:
        mod.vision_analyze(str(frame))
    except RuntimeError as exc:
        text = str(exc)
    else:
        raise AssertionError("vision_analyze should raise RuntimeError")

    assert "HTTP Error 503" in text
    assert "maximum pending requests exceeded" in text


def test_vision_analyze_fails_over_to_secondary_url_when_primary_is_busy(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "observer_frame.jpg"
    frame.write_bytes(b"0" * 2048)
    calls: list[str] = []

    def fake_urlopen(req, timeout=90):
        calls.append(req.full_url)
        if req.full_url.endswith(":11435/api/chat"):
            raise HTTPError(
                req.full_url,
                503,
                "Service Unavailable",
                hdrs=None,
                fp=BytesIO(b'{\"error\":\"server busy, please try again. maximum pending requests exceeded\"}'),
            )
        return BytesIO(b'{\"message\":{\"content\":\"observer summary\"}}')

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    text = mod.vision_analyze(
        str(frame),
        urls=("http://127.0.0.1:11435/api/chat", "http://127.0.0.1:11434/api/chat"),
    )

    assert text == "observer summary"
    assert calls == [
        "http://127.0.0.1:11435/api/chat",
        "http://127.0.0.1:11434/api/chat",
    ]
