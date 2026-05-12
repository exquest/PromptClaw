"""Tests for room_presence_daemon.py."""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from pathlib import Path

from PIL import Image


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

import room_presence_daemon as mod


def _write_frame(path: Path, value: int) -> None:
    Image.new("RGB", (64, 48), color=(value, value, value)).save(path)


def test_analyze_frame_marks_bright_room_as_present(tmp_path: Path) -> None:
    frame = tmp_path / "frame.jpg"
    _write_frame(frame, 200)

    state, pixels = mod.analyze_frame(frame, previous_pixels=None)

    assert state["brightness"] > 0.5
    assert state["someone_here"] is True
    assert state["motion"] is False
    assert pixels


def test_analyze_frame_detects_motion_between_frames(tmp_path: Path) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    _write_frame(first, 10)
    _write_frame(second, 220)

    _, previous = mod.analyze_frame(first, previous_pixels=None)
    state, _ = mod.analyze_frame(second, previous_pixels=previous)

    assert state["motion"] is True
    assert state["motion_amount"] > 0.02


def test_run_loop_writes_room_presence_state(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "frame.jpg"
    output = tmp_path / "room_presence.json"
    _write_frame(frame, 180)

    monkeypatch.setattr(mod, "FRAME_PATH", frame)
    monkeypatch.setattr(mod, "OUTPUT_PATH", output)

    def fake_capture(_video_device: str, frame_path: Path) -> bool:
        _write_frame(frame_path, 180)
        return True

    monkeypatch.setattr(mod, "capture_frame", fake_capture)

    mod.run_daemon(interval=0.0, max_iterations=1)

    written = json.loads(output.read_text())
    assert written["ok"] is True
    assert written["someone_here"] is True


def test_run_loop_reuses_fresh_observer_frame_when_camera_is_busy(monkeypatch, tmp_path: Path) -> None:
    observer = tmp_path / "observer_frame.jpg"
    output = tmp_path / "room_presence.json"
    mirrored_room = tmp_path / "room_frame.jpg"
    _write_frame(observer, 160)

    monkeypatch.setattr(mod, "OUTPUT_PATH", output)
    monkeypatch.setattr(mod, "FRAME_PATH", mirrored_room)
    monkeypatch.setattr(mod, "OBSERVER_FRAME_PATH", observer)
    monkeypatch.setattr(mod, "capture_frame", lambda *_args, **_kwargs: False)

    mod.run_daemon(interval=0.0, max_iterations=1)

    written = json.loads(output.read_text())
    assert written["ok"] is True
    assert written["frame_path"] == str(mirrored_room)
    assert written["capture_source"] == "observer_frame"
    assert mirrored_room.exists()


def test_capture_frame_rejects_failed_ffmpeg_even_when_stale_frame_exists(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "room_frame.jpg"
    frame.write_bytes(b"0" * 4096)

    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    assert mod.capture_frame("/dev/video0", frame) is False


def test_run_loop_can_operate_in_observer_frame_only_mode(monkeypatch, tmp_path: Path) -> None:
    observer = tmp_path / "observer_frame.jpg"
    output = tmp_path / "room_presence.json"
    mirrored_room = tmp_path / "room_frame.jpg"
    _write_frame(observer, 170)

    monkeypatch.setattr(mod, "OUTPUT_PATH", output)
    monkeypatch.setattr(mod, "FRAME_PATH", mirrored_room)
    monkeypatch.setattr(mod, "OBSERVER_FRAME_PATH", observer)
    monkeypatch.setattr(
        mod,
        "capture_frame",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("camera capture should not run")),
    )

    mod.run_daemon(interval=0.0, max_iterations=1, observer_frame_only=True)

    written = json.loads(output.read_text())
    assert written["ok"] is True
    assert written["capture_source"] == "observer_frame"
    assert written["frame_path"] == str(mirrored_room)
    assert mirrored_room.exists()
