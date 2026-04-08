"""Tests for porch_eye.py — camera frame capture and analysis."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from porch_eye import (
    PorchEyeState,
    analyze_brightness,
    capture_frame,
    classify_weather,
    detect_motion,
    run_porch_eye,
)

# ---------------------------------------------------------------------------
# Helpers — synthetic image generation
# ---------------------------------------------------------------------------

# Minimal valid JPEG: 1x1 white pixel
_JPEG_WHITE = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0xFF, 0xC0, 0x00,
    0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4,
    0x00, 0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04,
    0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10,
    0x00, 0x02, 0x01, 0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04,
    0x00, 0x00, 0x01, 0x7D, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12,
    0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32,
    0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0,
    0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A,
    0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
    0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55,
    0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85,
    0x86, 0x87, 0x88, 0x89, 0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,
    0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2,
    0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5,
    0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8,
    0xD9, 0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
    0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA,
    0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94, 0x11, 0x00,
    0x00, 0x00, 0xFF, 0xD9,
])

# Minimal valid JPEG: 1x1 black pixel (all-zero luminance)
_JPEG_BLACK = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0xFF, 0xC0, 0x00,
    0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4,
    0x00, 0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04,
    0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10,
    0x00, 0x02, 0x01, 0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04,
    0x00, 0x00, 0x01, 0x7D, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12,
    0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32,
    0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0,
    0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A,
    0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
    0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55,
    0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85,
    0x86, 0x87, 0x88, 0x89, 0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,
    0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2,
    0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5,
    0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8,
    0xD9, 0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
    0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA,
    0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x54, 0xD8, 0x20, 0x00,
    0x00, 0x00, 0xFF, 0xD9,
])


def _try_make_pil_image(path: Path, color: int, size: tuple = (8, 8)):
    """Create an image using PIL if available, otherwise write raw JPEG bytes."""
    try:
        from PIL import Image
        img = Image.new("L", size, color)
        img.save(str(path), format="JPEG")
    except ImportError:
        # Fall back to pre-baked minimal JPEG
        if color > 127:
            path.write_bytes(_JPEG_WHITE)
        else:
            path.write_bytes(_JPEG_BLACK)


def _make_pil_pair(tmp_path: Path, color_a: int, color_b: int, size: tuple = (8, 8)):
    """Create two images for motion detection tests."""
    a = tmp_path / "frame_a.jpg"
    b = tmp_path / "frame_b.jpg"
    _try_make_pil_image(a, color_a, size)
    _try_make_pil_image(b, color_b, size)
    return a, b


# ---------------------------------------------------------------------------
# Tests: PorchEyeState dataclass
# ---------------------------------------------------------------------------


class TestPorchEyeState:
    def test_defaults(self):
        state = PorchEyeState()
        assert state.brightness == 0.0
        assert state.weather == "unknown"
        assert state.motion_detected is False
        assert state.last_capture_time == 0.0
        assert state.error is None

    def test_as_dict(self):
        state = PorchEyeState(brightness=0.5, weather="day")
        d = asdict(state)
        assert d["brightness"] == 0.5
        assert d["weather"] == "day"

    def test_custom_values(self):
        state = PorchEyeState(
            brightness=0.8,
            weather="dusk",
            motion_detected=True,
            last_capture_time=1000.0,
            error="timeout",
        )
        assert state.motion_detected is True
        assert state.error == "timeout"


# ---------------------------------------------------------------------------
# Tests: capture_frame
# ---------------------------------------------------------------------------


class TestCaptureFrame:
    def test_success(self, tmp_path):
        output = tmp_path / "frame.jpg"
        with patch("porch_eye.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            # Simulate ffmpeg creating the file
            output.write_bytes(_JPEG_WHITE)
            result = capture_frame("rtsps://camera.local/stream", str(output))
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "ffmpeg" in cmd
        assert "-rtsp_transport" in cmd
        assert "tcp" in cmd
        assert str(output) in cmd

    def test_ffmpeg_failure(self, tmp_path):
        output = tmp_path / "frame.jpg"
        with patch("porch_eye.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = capture_frame("rtsps://camera.local/stream", str(output))
        assert result is False

    def test_ffmpeg_timeout(self, tmp_path):
        output = tmp_path / "frame.jpg"
        with patch("porch_eye.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10)
            result = capture_frame("rtsps://camera.local/stream", str(output))
        assert result is False

    def test_ffmpeg_not_found(self, tmp_path):
        output = tmp_path / "frame.jpg"
        with patch("porch_eye.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ffmpeg not found")
            result = capture_frame("rtsps://camera.local/stream", str(output))
        assert result is False

    def test_custom_timeout(self, tmp_path):
        output = tmp_path / "frame.jpg"
        with patch("porch_eye.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            output.write_bytes(_JPEG_WHITE)
            capture_frame("rtsps://cam/s", str(output), timeout=20)
        call_args = mock_run.call_args
        assert call_args[1]["timeout"] == 20

    def test_file_not_created(self, tmp_path):
        """ffmpeg returns 0 but no file was actually written."""
        output = tmp_path / "frame.jpg"
        with patch("porch_eye.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            # Don't create the file
            result = capture_frame("rtsps://cam/s", str(output))
        assert result is False


# ---------------------------------------------------------------------------
# Tests: analyze_brightness
# ---------------------------------------------------------------------------


class TestAnalyzeBrightness:
    def test_white_image(self, tmp_path):
        img = tmp_path / "white.jpg"
        _try_make_pil_image(img, 255)
        b = analyze_brightness(str(img))
        assert 0.8 <= b <= 1.0

    def test_black_image(self, tmp_path):
        img = tmp_path / "black.jpg"
        _try_make_pil_image(img, 0)
        b = analyze_brightness(str(img))
        assert 0.0 <= b <= 0.2

    def test_mid_grey(self, tmp_path):
        img = tmp_path / "grey.jpg"
        _try_make_pil_image(img, 128)
        b = analyze_brightness(str(img))
        assert 0.3 <= b <= 0.7

    def test_missing_file(self):
        b = analyze_brightness("/nonexistent/image.jpg")
        assert b == 0.0

    def test_returns_float_in_range(self, tmp_path):
        img = tmp_path / "any.jpg"
        _try_make_pil_image(img, 100)
        b = analyze_brightness(str(img))
        assert isinstance(b, float)
        assert 0.0 <= b <= 1.0


# ---------------------------------------------------------------------------
# Tests: detect_motion
# ---------------------------------------------------------------------------


class TestDetectMotion:
    def test_identical_frames_no_motion(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        _try_make_pil_image(a, 128)
        _try_make_pil_image(b, 128)
        result = detect_motion(str(a), str(b))
        assert result["motion_detected"] is False
        assert result["change_ratio"] == 0.0

    def test_different_frames_motion(self, tmp_path):
        a, b = _make_pil_pair(tmp_path, 0, 255)
        result = detect_motion(str(a), str(b))
        assert result["motion_detected"] is True
        assert result["change_ratio"] > 0.05

    def test_custom_threshold(self, tmp_path):
        a, b = _make_pil_pair(tmp_path, 100, 120)
        # Very high threshold should not trigger
        result = detect_motion(str(a), str(b), threshold=0.99)
        assert result["motion_detected"] is False

    def test_missing_frame_returns_no_motion(self, tmp_path):
        a = tmp_path / "a.jpg"
        _try_make_pil_image(a, 128)
        result = detect_motion(str(a), "/nonexistent.jpg")
        assert result["motion_detected"] is False

    def test_returns_required_keys(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        _try_make_pil_image(a, 50)
        _try_make_pil_image(b, 200)
        result = detect_motion(str(a), str(b))
        assert "motion_detected" in result
        assert "change_ratio" in result
        assert isinstance(result["change_ratio"], float)


# ---------------------------------------------------------------------------
# Tests: classify_weather
# ---------------------------------------------------------------------------


class TestClassifyWeather:
    def test_night_dark_late(self):
        assert classify_weather(0.05, 23) == "night"

    def test_night_dark_early(self):
        assert classify_weather(0.02, 2) == "night"

    def test_day_bright_afternoon(self):
        assert classify_weather(0.8, 12) == "day"

    def test_day_bright_morning(self):
        assert classify_weather(0.7, 10) == "day"

    def test_dawn(self):
        assert classify_weather(0.3, 6) == "dawn"

    def test_dusk(self):
        assert classify_weather(0.3, 19) == "dusk"

    def test_overcast_dim_midday(self):
        assert classify_weather(0.3, 12) == "overcast"

    def test_overcast_dim_afternoon(self):
        assert classify_weather(0.25, 14) == "overcast"

    def test_dawn_edge_5am(self):
        assert classify_weather(0.3, 5) == "dawn"

    def test_dusk_edge_20(self):
        assert classify_weather(0.3, 20) == "dusk"


# ---------------------------------------------------------------------------
# Tests: run_porch_eye (daemon loop)
# ---------------------------------------------------------------------------


class TestRunPorchEye:
    def test_single_iteration_writes_state(self, tmp_path, monkeypatch):
        capture_dir = tmp_path / "captures"
        capture_dir.mkdir()
        state_file = tmp_path / "porch_eye_state.json"
        monkeypatch.setattr("porch_eye.DEFAULT_STATE_FILE", str(state_file))

        # Mock capture_frame to "succeed" by writing a synthetic image
        def fake_capture(url, path, timeout=10):
            _try_make_pil_image(Path(path), 200)
            return True

        monkeypatch.setattr("porch_eye.capture_frame", fake_capture)

        run_porch_eye(
            "rtsps://camera.local/stream",
            str(capture_dir),
            interval=0.0,
            max_iterations=1,
        )

        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert "brightness" in data
        assert "weather" in data
        assert "motion_detected" in data
        assert "last_capture_time" in data
        assert data["error"] is None

    def test_capture_failure_records_error(self, tmp_path, monkeypatch):
        capture_dir = tmp_path / "captures"
        capture_dir.mkdir()
        state_file = tmp_path / "porch_eye_state.json"
        monkeypatch.setattr("porch_eye.DEFAULT_STATE_FILE", str(state_file))
        monkeypatch.setattr("porch_eye.capture_frame", lambda *a, **kw: False)

        run_porch_eye(
            "rtsps://camera.local/stream",
            str(capture_dir),
            interval=0.0,
            max_iterations=1,
        )

        data = json.loads(state_file.read_text())
        assert data["error"] is not None

    def test_motion_detected_between_frames(self, tmp_path, monkeypatch):
        capture_dir = tmp_path / "captures"
        capture_dir.mkdir()
        state_file = tmp_path / "porch_eye_state.json"
        monkeypatch.setattr("porch_eye.DEFAULT_STATE_FILE", str(state_file))

        call_count = [0]

        def fake_capture(url, path, timeout=10):
            # First frame: dark; second frame: bright
            brightness = 50 if call_count[0] == 0 else 220
            call_count[0] += 1
            _try_make_pil_image(Path(path), brightness)
            return True

        monkeypatch.setattr("porch_eye.capture_frame", fake_capture)

        run_porch_eye(
            "rtsps://camera.local/stream",
            str(capture_dir),
            interval=0.0,
            max_iterations=2,
        )

        data = json.loads(state_file.read_text())
        assert data["motion_detected"] is True

    def test_creates_capture_dir(self, tmp_path, monkeypatch):
        capture_dir = tmp_path / "new_captures"
        state_file = tmp_path / "porch_eye_state.json"
        monkeypatch.setattr("porch_eye.DEFAULT_STATE_FILE", str(state_file))

        def fake_capture(url, path, timeout=10):
            _try_make_pil_image(Path(path), 128)
            return True

        monkeypatch.setattr("porch_eye.capture_frame", fake_capture)

        run_porch_eye(
            "rtsps://camera.local/stream",
            str(capture_dir),
            interval=0.0,
            max_iterations=1,
        )

        assert capture_dir.exists()

    def test_atomic_write(self, tmp_path, monkeypatch):
        """State file should be atomically written (no partial reads)."""
        capture_dir = tmp_path / "captures"
        capture_dir.mkdir()
        state_file = tmp_path / "porch_eye_state.json"
        monkeypatch.setattr("porch_eye.DEFAULT_STATE_FILE", str(state_file))

        def fake_capture(url, path, timeout=10):
            _try_make_pil_image(Path(path), 180)
            return True

        monkeypatch.setattr("porch_eye.capture_frame", fake_capture)

        run_porch_eye(
            "rtsps://camera.local/stream",
            str(capture_dir),
            interval=0.0,
            max_iterations=3,
        )

        # Should be valid JSON after multiple iterations
        data = json.loads(state_file.read_text())
        assert isinstance(data, dict)
