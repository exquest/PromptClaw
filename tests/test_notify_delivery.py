"""Tests for the delivery notification trigger (T-058c)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

import notify_delivery


def test_send_delivery_notification_formats_and_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_messages: list[dict[str, str | None]] = []

    def mock_send_message(text: str, parse_mode: str | None = None) -> dict[str, object]:
        captured_messages.append({"text": text, "parse_mode": parse_mode})
        return {"ok": True}

    # We mock telegram.send_message directly on the notify_delivery module
    monkeypatch.setattr(notify_delivery.telegram, "send_message", mock_send_message)

    result = notify_delivery.send_delivery_notification(
        public_url="https://example.com/live",
        capture_path="/path/to/capture.opus"
    )

    assert result == {"ok": True}
    assert len(captured_messages) == 1
    msg = captured_messages[0]
    assert msg["parse_mode"] == "Markdown"
    assert msg["text"] is not None
    assert "https://example.com/live" in msg["text"]
    assert "/path/to/capture.opus" in msg["text"]
    assert len(msg["text"]) <= 300

def test_send_delivery_notification_truncates_long_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_messages: list[str] = []

    def mock_send_message(text: str, parse_mode: str | None = None) -> dict[str, object]:
        captured_messages.append(text)
        return {"ok": True}

    monkeypatch.setattr(notify_delivery.telegram, "send_message", mock_send_message)

    long_path = "/very/long/path/" * 20 + "capture.opus"
    notify_delivery.send_delivery_notification(
        public_url="https://example.com/live",
        capture_path=long_path
    )

    assert len(captured_messages[0]) <= 300
    assert captured_messages[0].endswith("...")
