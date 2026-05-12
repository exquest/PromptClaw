"""Tests for keyboard_chat.py — CypherClaw face terminal.

The face terminal mirrors the Telegram daemon. Messages typed on the
keyboard go through the daemon inbox (same as MacBook Claude).
Responses come back via the shared message bus.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from keyboard_chat import ChatBubble, KeyboardChat, ROLE_COLORS


@pytest.fixture
def chat():
    return KeyboardChat()


# ---------------------------------------------------------------------------
# ChatBubble
# ---------------------------------------------------------------------------

class TestChatBubble:
    def test_alive(self):
        b = ChatBubble("user", "hello")
        assert b.alive and b.alpha >= 250

    def test_fades(self):
        b = ChatBubble("user", "hello", 1.0)
        b.created_at = time.time() - 0.5
        assert b.alive and 100 < b.alpha < 200

    def test_dies(self):
        b = ChatBubble("user", "hello", 1.0)
        b.created_at = time.time() - 2.0
        assert not b.alive

    def test_all_roles_have_colors(self):
        for role in ("user", "bot", "deep", "system", "remote"):
            assert role in ROLE_COLORS


# ---------------------------------------------------------------------------
# Keyboard input
# ---------------------------------------------------------------------------

class TestKeypress:
    def test_typing(self, chat):
        chat.handle_keypress(ord("a"), "a", 0)
        assert chat.input_buffer == "a"

    def test_backspace(self, chat):
        chat.input_buffer = "abc"
        chat.handle_keypress(8, "", 0)
        assert chat.input_buffer == "ab"

    def test_enter_submits(self, chat):
        chat.input_buffer = "test"
        with patch.object(chat, "submit") as m:
            chat.handle_keypress(13, "\r", 0)
            m.assert_called_once()

    def test_escape_clears(self, chat):
        chat.input_buffer = "hello"
        chat.handle_keypress(27, "", 0)
        assert chat.input_buffer == ""

    def test_non_printable_ignored(self, chat):
        assert not chat.handle_keypress(1, "\x01", 0)


# ---------------------------------------------------------------------------
# Submit → daemon inbox
# ---------------------------------------------------------------------------

class TestSubmit:
    def test_writes_to_daemon_inbox(self, chat, tmp_path):
        inbox = tmp_path / "inbox.jsonl"
        chat.daemon_inbox = str(inbox)
        chat.input_buffer = "hello"
        chat.submit()
        assert chat.bubbles[0].role == "user"
        assert chat.bubbles[0].text == "hello"
        lines = inbox.read_text().strip().split("\n")
        msg = json.loads(lines[0])
        assert msg["text"] == "hello"
        assert msg["source"] == "keyboard"

    def test_empty_noop(self, chat, tmp_path):
        inbox = tmp_path / "inbox.jsonl"
        chat.daemon_inbox = str(inbox)
        chat.input_buffer = "   "
        chat.submit()
        assert len(chat.bubbles) == 0
        assert not inbox.exists()

    def test_clears_buffer(self, chat, tmp_path):
        chat.daemon_inbox = str(tmp_path / "inbox.jsonl")
        chat.input_buffer = "test"
        chat.submit()
        assert chat.input_buffer == ""


# ---------------------------------------------------------------------------
# Message bus (daemon writes here, face reads)
# ---------------------------------------------------------------------------

class TestMessageBus:
    def test_reads_new_messages(self, chat, tmp_path):
        bus = tmp_path / "messages.jsonl"
        bus.write_text(
            json.dumps({"text": "Hello from daemon", "role": "bot", "time": time.time()}) + "\n"
        )
        with patch("keyboard_chat.MESSAGE_BUS", bus):
            chat.poll_message_bus()
        assert len(chat.bubbles) == 1
        assert chat.bubbles[0].text == "Hello from daemon"
        assert chat.bubbles[0].role == "bot"

    def test_skips_already_read(self, chat, tmp_path):
        bus = tmp_path / "messages.jsonl"
        bus.write_text(
            json.dumps({"text": "old", "role": "bot", "time": time.time()}) + "\n"
        )
        with patch("keyboard_chat.MESSAGE_BUS", bus):
            chat.poll_message_bus()
            chat.poll_message_bus()  # second call
        assert len(chat.bubbles) == 1  # no duplicate

    def test_handles_missing_file(self, chat):
        with patch("keyboard_chat.MESSAGE_BUS", Path("/nonexistent")):
            chat.poll_message_bus()  # no crash

    def test_write_to_bus(self, tmp_path):
        bus = tmp_path / "messages.jsonl"
        with patch("keyboard_chat.MESSAGE_BUS", bus):
            KeyboardChat.write_to_bus("test message", "system")
        msg = json.loads(bus.read_text().strip())
        assert msg["text"] == "test message"
        assert msg["role"] == "system"


# ---------------------------------------------------------------------------
# System monitor
# ---------------------------------------------------------------------------

class TestSystemMonitor:
    def test_key_change(self, chat, tmp_path):
        state = tmp_path / "composer.json"
        state.write_text(json.dumps({"key": "D", "movement": "andante"}))
        chat._last_key = "C"
        chat._last_system_poll = 0
        with patch.dict("keyboard_chat.STATE_FILES", {"composer": state, "organism": Path("/dev/null"), "art": Path("/dev/null"), "theramini": Path("/dev/null")}):
            chat.poll_system()
        assert any("D major" in b.text for b in chat.bubbles)

    def test_no_bubble_first_read(self, chat, tmp_path):
        state = tmp_path / "composer.json"
        state.write_text(json.dumps({"key": "D"}))
        chat._last_system_poll = 0
        with patch.dict("keyboard_chat.STATE_FILES", {"composer": state, "organism": Path("/dev/null"), "art": Path("/dev/null"), "theramini": Path("/dev/null")}):
            chat.poll_system()
        assert len(chat.bubbles) == 0

    def test_song_title_change_adds_system_bubble(self, chat, tmp_path):
        state = tmp_path / "composer.json"
        state.write_text(json.dumps({"key": "D", "song_title": "Quiet Machines"}))
        chat._last_key = "D"
        chat._last_system_poll = 0
        with patch.dict("keyboard_chat.STATE_FILES", {"composer": state, "organism": Path("/dev/null"), "art": Path("/dev/null"), "theramini": Path("/dev/null")}):
            chat.poll_system()
        assert any("Quiet Machines" in b.text for b in chat.bubbles)

    def test_system_fades_faster(self, chat):
        chat._add_bubble("system", "test")
        assert chat.bubbles[0].fade_duration == chat.system_fade


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

class TestThinking:
    def test_submit_starts_thinking(self, chat, tmp_path):
        chat.daemon_inbox = str(tmp_path / "inbox.jsonl")
        chat.input_buffer = "hello"
        chat.submit()
        assert chat.is_thinking
        assert chat.expression_override == "curious"

    def test_bus_response_stops_thinking(self, chat, tmp_path):
        chat.daemon_inbox = str(tmp_path / "inbox.jsonl")
        chat.input_buffer = "hello"
        chat.submit()
        assert chat.is_thinking
        bus = tmp_path / "bus.jsonl"
        bus.write_text(json.dumps({"text": "hi back", "role": "bot", "time": time.time()}) + "\n")
        with patch("keyboard_chat.MESSAGE_BUS", bus):
            chat.poll_message_bus()
        assert not chat.is_thinking
        assert chat.expression_override is None

    def test_thinking_times_out(self, chat):
        chat._thinking_since = time.time() - 70  # past 60s timeout
        assert not chat.is_thinking

    def test_not_thinking_when_idle(self, chat):
        assert not chat.is_thinking
        assert chat.expression_override is None

    def test_thinking_has_visible_content(self, chat, tmp_path):
        chat.daemon_inbox = str(tmp_path / "inbox.jsonl")
        chat.input_buffer = "hello"
        chat.submit()
        assert chat.has_visible_content

    def test_thinking_renders(self, chat, tmp_path):
        chat.daemon_inbox = str(tmp_path / "inbox.jsonl")
        chat.input_buffer = "hello"
        chat.submit()
        img = Image.new("RGBA", (800, 480), (20, 20, 40, 255))
        chat.render(img)  # should not crash, should show thinking animation


class TestRender:
    def _img(self):
        return Image.new("RGBA", (800, 480), (20, 20, 40, 255))

    def test_no_content_noop(self, chat):
        img = self._img()
        original = img.tobytes()
        chat.render(img)
        assert img.tobytes() == original

    def test_typing_renders(self, chat):
        chat.input_buffer = "hello"
        img = self._img()
        chat.render(img)
        assert img.tobytes() != self._img().tobytes()

    def test_all_roles_render(self, chat):
        for role in ("user", "bot", "deep", "system", "remote"):
            chat._add_bubble(role, f"test {role}")
        chat.render(self._img())  # no crash

    def test_wrap(self):
        assert len(KeyboardChat._wrap("a b c d e f g h i j k l", 10)) >= 2
        assert KeyboardChat._wrap("", 50) == [""]
