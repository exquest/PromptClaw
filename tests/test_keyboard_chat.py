"""Tests for keyboard_chat.py — keyboard-to-face Telegram chat overlay."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from keyboard_chat import KeyboardChat


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def chat():
    """Return a fresh KeyboardChat instance with active=True."""
    c = KeyboardChat()
    c.active = True
    return c


@pytest.fixture
def chat_with_creds(chat):
    """Return a chat instance with fake Telegram credentials."""
    chat.bot_token = "123:FAKE"
    chat.chat_id = "999"
    return chat


# ---------------------------------------------------------------------------
# toggle
# ---------------------------------------------------------------------------

class TestToggle:
    def test_toggle_on(self):
        c = KeyboardChat()
        assert c.active is False
        c.toggle()
        assert c.active is True

    def test_toggle_off_clears_buffer(self):
        c = KeyboardChat()
        c.active = True
        c.input_buffer = "hello"
        c.toggle()
        assert c.active is False
        assert c.input_buffer == ""

    def test_toggle_double_returns_to_off(self):
        c = KeyboardChat()
        c.toggle()
        c.toggle()
        assert c.active is False


# ---------------------------------------------------------------------------
# handle_keypress
# ---------------------------------------------------------------------------

K_BACKSPACE = 8
K_RETURN = 13
K_ESCAPE = 27
K_TAB = 9

class TestHandleKeypress:
    def test_printable_char_appended(self, chat):
        chat.handle_keypress(ord("a"), "a", 0)
        assert chat.input_buffer == "a"

    def test_multiple_chars(self, chat):
        for ch in "hi":
            chat.handle_keypress(ord(ch), ch, 0)
        assert chat.input_buffer == "hi"

    def test_backspace_deletes_last(self, chat):
        chat.input_buffer = "abc"
        chat.handle_keypress(K_BACKSPACE, "", 0)
        assert chat.input_buffer == "ab"

    def test_backspace_on_empty(self, chat):
        chat.handle_keypress(K_BACKSPACE, "", 0)
        assert chat.input_buffer == ""

    def test_enter_triggers_submit(self, chat):
        chat.input_buffer = "test"
        with patch.object(chat, "submit") as mock_submit:
            chat.handle_keypress(K_RETURN, "\r", 0)
            mock_submit.assert_called_once()

    def test_escape_toggles_off(self, chat):
        chat.handle_keypress(K_ESCAPE, "", 0)
        assert chat.active is False

    def test_tab_toggles_off(self, chat):
        chat.handle_keypress(K_TAB, "", 0)
        assert chat.active is False

    def test_non_printable_ignored(self, chat):
        """Control characters (non-printable) should not be appended."""
        chat.handle_keypress(1, "\x01", 0)  # Ctrl-A
        assert chat.input_buffer == ""

    def test_space_appended(self, chat):
        chat.handle_keypress(32, " ", 0)
        assert chat.input_buffer == " "


# ---------------------------------------------------------------------------
# submit — local commands
# ---------------------------------------------------------------------------

class TestSubmitCommands:
    def test_empty_submit_noop(self, chat):
        chat.input_buffer = "   "
        chat.submit()
        assert len(chat.messages) == 0

    def test_help_command(self, chat):
        chat.input_buffer = "/help"
        chat.submit()
        assert len(chat.messages) == 2  # user + bot response
        assert chat.messages[0]["role"] == "user"
        assert chat.messages[1]["role"] == "bot"
        assert "/mood" in chat.messages[1]["text"]

    def test_unknown_command(self, chat):
        chat.input_buffer = "/foobar"
        chat.submit()
        assert len(chat.messages) == 2
        assert "Unknown" in chat.messages[1]["text"]

    def test_mood_command_with_data(self, chat, tmp_path):
        state = {"organism_mood": {"energy": 0.7, "valence": 0.3}}
        state_file = tmp_path / "organism_state.json"
        state_file.write_text(json.dumps(state))

        with patch("keyboard_chat.Path") as mock_path_cls:
            # Only intercept the /tmp/organism_state.json read
            original_path = Path

            def side_effect(p):
                if p == "/tmp/organism_state.json":
                    return state_file
                return original_path(p)

            mock_path_cls.side_effect = side_effect

            chat.input_buffer = "/mood"
            chat.submit()

        assert len(chat.messages) == 2
        assert "0.7" in chat.messages[1]["text"]

    def test_mood_command_no_data(self, chat):
        """When no sensor file exists, return calm fallback."""
        chat.input_buffer = "/mood"
        # Ensure /tmp/organism_state.json does not exist for this test
        with patch("keyboard_chat.Path") as mock_path_cls:
            mock_path_cls.return_value.read_text.side_effect = FileNotFoundError
            chat.input_buffer = "/mood"
            chat.submit()

        assert "calm" in chat.messages[1]["text"].lower() or "no sensor" in chat.messages[1]["text"].lower()

    def test_key_command_with_data(self, chat, tmp_path):
        state = {"key": "C", "movement": "andante"}
        state_file = tmp_path / "composer_state.json"
        state_file.write_text(json.dumps(state))

        with patch("keyboard_chat.Path") as mock_path_cls:
            original_path = Path

            def side_effect(p):
                if p == "/tmp/composer_state.json":
                    return state_file
                return original_path(p)

            mock_path_cls.side_effect = side_effect

            chat.input_buffer = "/key"
            chat.submit()

        assert "C" in chat.messages[1]["text"]
        assert "andante" in chat.messages[1]["text"]

    def test_key_command_no_data(self, chat):
        with patch("keyboard_chat.Path") as mock_path_cls:
            mock_path_cls.return_value.read_text.side_effect = FileNotFoundError
            chat.input_buffer = "/key"
            chat.submit()

        assert "unknown" in chat.messages[1]["text"].lower()

    def test_submit_clears_buffer(self, chat):
        chat.input_buffer = "/help"
        chat.submit()
        assert chat.input_buffer == ""


# ---------------------------------------------------------------------------
# submit — free text sends to Telegram
# ---------------------------------------------------------------------------

class TestSubmitTelegram:
    def test_free_text_calls_send_telegram(self, chat_with_creds):
        with patch.object(chat_with_creds, "_send_telegram") as mock_send:
            chat_with_creds.input_buffer = "hello world"
            chat_with_creds.submit()
            mock_send.assert_called_once_with("[keyboard] hello world")

    def test_free_text_appends_user_message(self, chat_with_creds):
        with patch.object(chat_with_creds, "_send_telegram"):
            chat_with_creds.input_buffer = "hello"
            chat_with_creds.submit()

        assert chat_with_creds.messages[0]["role"] == "user"
        assert chat_with_creds.messages[0]["text"] == "hello"

    def test_message_list_capped_at_20(self, chat):
        for i in range(25):
            chat.messages.append({"role": "user", "text": f"msg{i}", "time": "00:00"})

        with patch.object(chat, "_send_telegram"):
            chat.input_buffer = "overflow"
            chat.submit()

        assert len(chat.messages) <= 20


# ---------------------------------------------------------------------------
# _send_telegram
# ---------------------------------------------------------------------------

class TestSendTelegram:
    def test_send_posts_to_api(self, chat_with_creds):
        with patch("keyboard_chat.urllib.request.urlopen") as mock_urlopen:
            chat_with_creds._send_telegram("test message")
            mock_urlopen.assert_called_once()
            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            assert "sendMessage" in req.full_url
            body = json.loads(req.data)
            assert body["text"] == "test message"
            assert body["chat_id"] == "999"

    def test_send_no_creds_noop(self, chat):
        """Without credentials, _send_telegram should do nothing."""
        with patch("keyboard_chat.urllib.request.urlopen") as mock_urlopen:
            chat._send_telegram("test")
            mock_urlopen.assert_not_called()

    def test_send_swallows_errors(self, chat_with_creds):
        with patch("keyboard_chat.urllib.request.urlopen", side_effect=Exception("network")):
            # Should not raise
            chat_with_creds._send_telegram("test")


# ---------------------------------------------------------------------------
# poll_incoming
# ---------------------------------------------------------------------------

class TestPollIncoming:
    def _make_update_response(self, updates):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"ok": True, "result": updates}).encode()
        return resp

    def test_poll_receives_message(self, chat_with_creds):
        updates = [{
            "update_id": 100,
            "message": {
                "text": "hey from phone",
                "from": {"first_name": "Anthony"}
            }
        }]
        chat_with_creds._last_poll = 0  # force poll

        with patch("keyboard_chat.urllib.request.urlopen", return_value=self._make_update_response(updates)):
            chat_with_creds.poll_incoming()

        assert len(chat_with_creds.messages) == 1
        assert "Anthony" in chat_with_creds.messages[0]["text"]
        assert chat_with_creds.messages[0]["role"] == "bot"
        assert chat_with_creds._poll_offset == 101

    def test_poll_skips_keyboard_echo(self, chat_with_creds):
        """Messages starting with [keyboard] should be ignored (echo prevention)."""
        updates = [{
            "update_id": 200,
            "message": {
                "text": "[keyboard] my own message",
                "from": {"first_name": "CypherClaw"}
            }
        }]
        chat_with_creds._last_poll = 0

        with patch("keyboard_chat.urllib.request.urlopen", return_value=self._make_update_response(updates)):
            chat_with_creds.poll_incoming()

        assert len(chat_with_creds.messages) == 0
        assert chat_with_creds._poll_offset == 201  # still advances offset

    def test_poll_respects_3s_throttle(self, chat_with_creds):
        chat_with_creds._last_poll = time.time()  # just polled

        with patch("keyboard_chat.urllib.request.urlopen") as mock_urlopen:
            chat_with_creds.poll_incoming()
            mock_urlopen.assert_not_called()

    def test_poll_no_creds_noop(self, chat):
        chat._last_poll = 0
        with patch("keyboard_chat.urllib.request.urlopen") as mock_urlopen:
            chat.poll_incoming()
            mock_urlopen.assert_not_called()

    def test_poll_swallows_errors(self, chat_with_creds):
        chat_with_creds._last_poll = 0
        with patch("keyboard_chat.urllib.request.urlopen", side_effect=Exception("timeout")):
            chat_with_creds.poll_incoming()  # should not raise

    def test_poll_uses_offset(self, chat_with_creds):
        chat_with_creds._last_poll = 0
        chat_with_creds._poll_offset = 42

        with patch("keyboard_chat.urllib.request.urlopen", return_value=self._make_update_response([])) as mock_urlopen:
            chat_with_creds.poll_incoming()
            req = mock_urlopen.call_args[0][0]
            assert "offset=42" in req.full_url


# ---------------------------------------------------------------------------
# load_env
# ---------------------------------------------------------------------------

class TestLoadEnv:
    def test_load_env_parses_file(self, chat, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# comment line\n"
            "TELEGRAM_BOT_TOKEN=abc123\n"
            "TELEGRAM_CHAT_ID=456\n"
            "OTHER_VAR=ignored\n"
        )
        chat.load_env(str(env_file))
        assert chat.bot_token == "abc123"
        assert chat.chat_id == "456"

    def test_load_env_handles_quotes(self, chat, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            'TELEGRAM_BOT_TOKEN="quoted_token"\n'
            "TELEGRAM_CHAT_ID='quoted_id'\n"
        )
        chat.load_env(str(env_file))
        assert chat.bot_token == "quoted_token"
        assert chat.chat_id == "quoted_id"

    def test_load_env_missing_file(self, chat):
        """Missing file should not raise."""
        chat.load_env("/nonexistent/.env")
        assert chat.bot_token == ""

    def test_load_env_empty_file(self, chat, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        chat.load_env(str(env_file))
        assert chat.bot_token == ""

    def test_load_env_handles_spaces(self, chat, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("  TELEGRAM_BOT_TOKEN = spaced_token  \n")
        chat.load_env(str(env_file))
        assert chat.bot_token == "spaced_token"


# ---------------------------------------------------------------------------
# _write_face_message
# ---------------------------------------------------------------------------

class TestWriteFaceMessage:
    def test_write_face_message(self, chat, tmp_path):
        target = tmp_path / "face_message.json"
        with patch("keyboard_chat.os.replace") as mock_replace:
            # Redirect the tmp write to our tmp_path
            chat._write_face_message("hello face")
            # Should have attempted os.replace
            mock_replace.assert_called_once()


# ---------------------------------------------------------------------------
# render_overlay
# ---------------------------------------------------------------------------

class TestRenderOverlay:
    def _make_image(self, w=800, h=480):
        from PIL import Image
        return Image.new("RGBA", (w, h), (255, 255, 255, 255))

    def test_inactive_noop(self):
        c = KeyboardChat()
        img = self._make_image()
        original_data = img.tobytes()
        c.render_overlay(img)
        assert img.tobytes() == original_data

    def test_active_modifies_image(self, chat):
        img = self._make_image()
        original_data = img.tobytes()
        chat.render_overlay(img)
        assert img.tobytes() != original_data

    def test_overlay_darkens_bottom(self, chat):
        img = self._make_image()
        chat.render_overlay(img)
        # Sample a pixel in the bottom overlay region — should be dark
        w, h = img.size
        px = img.getpixel((w // 2, h - 20))
        # Alpha-composited pixel should be darker than pure white
        assert px[0] < 200 or px[3] < 255  # either darker or transparent

    def test_overlay_is_not_too_dark(self, chat):
        """Overlay alpha should be <=120 (lighter than the old 180)."""
        img = self._make_image()
        chat.render_overlay(img)
        w, h = img.size
        # PIL draws raw RGBA — check the alpha in the overlay region directly
        px = img.getpixel((w // 2, h - 5))
        assert px[3] <= 120, f"overlay alpha too high: A={px[3]} (was 180, should be ~100)"

    def test_overlay_covers_bottom_30_percent(self, chat):
        """Overlay should cover bottom 30% not 45%."""
        img = self._make_image()
        chat.render_overlay(img)
        w, h = img.size
        # Pixel at 60% height should be untouched (white)
        above = img.getpixel((w // 2, int(h * 0.60)))
        assert above == (255, 255, 255, 255), f"overlay bleeds too high: {above}"

    def test_overlay_with_messages(self, chat):
        chat.messages = [
            {"role": "user", "text": "hello", "time": "12:00"},
            {"role": "bot", "text": "Anthony: hi back", "time": "12:01"},
        ]
        chat.input_buffer = "typing..."
        img = self._make_image()
        chat.render_overlay(img)
        # Should not crash — visual correctness is best checked manually

    def test_overlay_with_many_messages(self, chat):
        """Rendering with > 5 messages should only show last 5."""
        for i in range(10):
            chat.messages.append({"role": "user", "text": f"msg {i}", "time": "00:00"})
        img = self._make_image()
        chat.render_overlay(img)  # should not crash

    def test_overlay_missing_font_fallback(self, chat):
        """When font path doesn't exist, should fall back to default."""
        img = self._make_image()
        chat.render_overlay(img, font_path="/nonexistent/font.ttf")
        # Should not crash — falls back to default font

    def test_fade_timeout_hides_overlay(self):
        """Overlay auto-hides after _fade_timeout seconds of inactivity."""
        c = KeyboardChat()
        c.active = True
        c._last_activity = time.time() - 25  # 25s ago, past 20s timeout
        img = self._make_image()
        original = img.tobytes()
        c.render_overlay(img)
        assert img.tobytes() == original  # no changes — faded out
        assert c.active is False

    def test_no_fade_during_activity(self, chat):
        """Overlay stays visible while _last_activity is recent."""
        chat._last_activity = time.time()  # just now
        img = self._make_image()
        original = img.tobytes()
        chat.render_overlay(img)
        assert img.tobytes() != original  # overlay rendered
        assert chat.active is True


class TestInitAttributes:
    def test_has_fade_timeout(self):
        c = KeyboardChat()
        assert c._fade_timeout == 20.0

    def test_has_last_activity(self):
        c = KeyboardChat()
        assert c._last_activity == 0.0

    def test_keypress_refreshes_activity(self):
        c = KeyboardChat()
        c.active = True
        before = c._last_activity
        c.handle_keypress(ord("a"), "a", 0)
        assert c._last_activity > before


# ---------------------------------------------------------------------------
# _read_mood / _read_key with real tmp files
# ---------------------------------------------------------------------------

class TestReadStateFiles:
    def test_read_mood_with_file(self, chat, tmp_path):
        state = {"organism_mood": {"energy": 0.85, "valence": -0.2}}
        state_file = tmp_path / "organism_state.json"
        state_file.write_text(json.dumps(state))

        with patch("keyboard_chat.Path") as mock_path_cls:
            mock_path_cls.return_value = state_file
            result = chat._read_mood()

        assert "0.8" in result  # 0.85 formatted as .1f = 0.8 or 0.9
        assert "-0.2" in result

    def test_read_mood_missing_file(self, chat):
        with patch("keyboard_chat.Path") as mock_path_cls:
            mock_path_cls.return_value.read_text.side_effect = FileNotFoundError
            result = chat._read_mood()
        assert "calm" in result.lower() or "no sensor" in result.lower()

    def test_read_key_with_file(self, chat, tmp_path):
        state = {"key": "D", "movement": "allegro"}
        state_file = tmp_path / "composer_state.json"
        state_file.write_text(json.dumps(state))

        with patch("keyboard_chat.Path") as mock_path_cls:
            mock_path_cls.return_value = state_file
            result = chat._read_key()

        assert "D" in result
        assert "allegro" in result

    def test_read_key_missing_file(self, chat):
        with patch("keyboard_chat.Path") as mock_path_cls:
            mock_path_cls.return_value.read_text.side_effect = FileNotFoundError
            result = chat._read_key()
        assert "unknown" in result.lower()
