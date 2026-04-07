"""Keyboard-to-face Telegram chat. Type on keyboard, see on face display.

Stdlib + PIL only — no pygame dependency. The face_display.py driver
calls into this module, routing pygame key events and rendering the
overlay onto the PIL image before converting to a pygame surface.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class KeyboardChat:
    """Keyboard-to-face Telegram chat. Type on keyboard, see on face display."""

    def __init__(self):
        self.active: bool = False
        self.input_buffer: str = ""
        self.messages: list[dict] = []  # [{role, text, time}]
        self.bot_token: str = ""
        self.chat_id: str = ""
        self._poll_offset: int | None = None
        self._last_poll: float = 0.0
        self._cursor_blink: bool = True
        self._cursor_time: float = 0.0
        self._last_activity: float = 0.0
        self._fade_timeout: float = 20.0

    # ------------------------------------------------------------------
    # Environment loading
    # ------------------------------------------------------------------

    def load_env(self, env_path: str = "/home/user/cypherclaw/.env") -> None:
        """Load TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env file."""
        try:
            with open(env_path) as f:
                lines = f.readlines()
        except (FileNotFoundError, PermissionError):
            return

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            if key == "TELEGRAM_BOT_TOKEN":
                self.bot_token = value
            elif key == "TELEGRAM_CHAT_ID":
                self.chat_id = value

    # ------------------------------------------------------------------
    # Toggle
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        self.active = not self.active
        self._last_activity = time.time()
        if not self.active:
            self.input_buffer = ""

    # ------------------------------------------------------------------
    # Keyboard input
    # ------------------------------------------------------------------

    def handle_keypress(self, key: int, unicode_char: str, mod: int) -> None:
        """Handle pygame keypress.

        key: pygame key constant (K_BACKSPACE=8, K_RETURN=13, K_ESCAPE=27, K_TAB=9)
        unicode_char: the typed character
        mod: modifier state
        """
        K_BACKSPACE = 8
        K_RETURN = 13
        K_ESCAPE = 27
        K_TAB = 9

        self._last_activity = time.time()

        if key == K_BACKSPACE:
            self.input_buffer = self.input_buffer[:-1]
        elif key == K_RETURN:
            self.submit()
        elif key == K_ESCAPE:
            self.toggle()
        elif key == K_TAB:
            self.toggle()
        elif unicode_char and unicode_char.isprintable():
            self.input_buffer += unicode_char

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def submit(self) -> None:
        """Submit input buffer.

        If starts with /: handle as local command.
        Otherwise: send to Telegram.
        """
        text = self.input_buffer.strip()
        self.input_buffer = ""
        if not text:
            return

        now = time.strftime("%H:%M")
        self.messages.append({"role": "user", "text": text, "time": now})

        if text.startswith("/"):
            response = self._handle_command(text)
            if response:
                self.messages.append({
                    "role": "bot",
                    "text": response,
                    "time": time.strftime("%H:%M"),
                })
        else:
            self._send_telegram(f"[keyboard] {text}")

        # Write to face message for non-chat display
        self._write_face_message(text)

        # Keep last 20 messages
        if len(self.messages) > 20:
            self.messages = self.messages[-20:]

    # ------------------------------------------------------------------
    # Local commands
    # ------------------------------------------------------------------

    def _handle_command(self, cmd: str) -> str | None:
        """Handle / commands locally."""
        cmd_lower = cmd.strip().split()[0].lower()
        if cmd_lower == "/mood":
            return self._read_mood()
        elif cmd_lower == "/key":
            return self._read_key()
        elif cmd_lower == "/help":
            return "Commands: /mood /key /help — or just type to chat via Telegram"
        return f"Unknown command: {cmd_lower}"

    def _read_mood(self) -> str:
        try:
            data = json.loads(Path("/tmp/organism_state.json").read_text())
            mood = data.get("organism_mood", {})
            return f"Energy: {mood.get('energy', '?'):.1f} Valence: {mood.get('valence', '?'):.1f}"
        except Exception:
            return "Mood: calm (no sensor data)"

    def _read_key(self) -> str:
        try:
            data = json.loads(Path("/tmp/composer_state.json").read_text())
            return f"Playing: {data.get('key', '?')} major — {data.get('movement', '?')}"
        except Exception:
            return "Key: unknown"

    # ------------------------------------------------------------------
    # Telegram I/O
    # ------------------------------------------------------------------

    def _send_telegram(self, text: str) -> None:
        """Send message to Telegram."""
        if not self.bot_token or not self.chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = json.dumps({"chat_id": self.chat_id, "text": text}).encode()
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    def poll_incoming(self) -> None:
        """Poll Telegram for new messages every 3 seconds."""
        now = time.time()
        if now - self._last_poll < 3.0:
            return
        self._last_poll = now
        if not self.bot_token:
            return

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?timeout=0"
            if self._poll_offset:
                url += f"&offset={self._poll_offset}"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read())
            for update in data.get("result", []):
                self._poll_offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                sender = msg.get("from", {}).get("first_name", "?")
                if text and not text.startswith("[keyboard]"):
                    self.messages.append({
                        "role": "bot",
                        "text": f"{sender}: {text}",
                        "time": time.strftime("%H:%M"),
                    })
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Face message
    # ------------------------------------------------------------------

    def _write_face_message(self, text: str) -> None:
        try:
            msg = {"message": text, "message_until": time.time() + 30}
            tmp = Path("/tmp/face_message.json.tmp")
            tmp.write_text(json.dumps(msg))
            os.replace(str(tmp), "/tmp/face_message.json")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render_overlay(
        self,
        img: Image.Image,
        font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ) -> None:
        """Render chat overlay on a PIL Image. Modifies img in place."""
        if not self.active:
            return
        # Auto-hide after inactivity
        if self._last_activity > 0 and (time.time() - self._last_activity) > self._fade_timeout:
            self.active = False
            return

        draw = ImageDraw.Draw(img, "RGBA")
        w, h = img.size

        # Lighter overlay on bottom 30% with gradient fade-in
        overlay_top = int(h * 0.70)
        gradient_height = 30
        # Gradient band: fades from transparent to overlay opacity
        for i in range(gradient_height):
            alpha = int(100 * i / gradient_height)
            y = overlay_top - gradient_height + i
            if 0 <= y < h:
                draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
        # Main overlay: alpha 100 (was 180) — much lighter
        draw.rectangle([0, overlay_top, w, h], fill=(0, 0, 0, 100))

        try:
            font = ImageFont.truetype(font_path, 22)
            font_sm = ImageFont.truetype(font_path, 16)
        except Exception:
            font = ImageFont.load_default()
            font_sm = font

        # Render messages (bottom up, above input line)
        input_y = h - 40
        msg_y = input_y - 10
        visible = self.messages[-5:]  # last 5 messages
        for msg in reversed(visible):
            role = msg["role"]
            text = msg["text"]
            t = msg.get("time", "")

            if role == "user":
                color = (220, 225, 235)
                prefix = f"[{t}] You: "
            else:
                color = (150, 200, 255)
                prefix = f"[{t}] "

            line = prefix + text
            # Truncate if too long
            if len(line) > 60:
                line = line[:57] + "..."

            msg_y -= 28
            if msg_y < overlay_top + 10:
                break
            draw.text((15, msg_y), line, fill=color, font=font_sm)

        # Input line
        now = time.time()
        if now - self._cursor_time > 0.5:
            self._cursor_blink = not self._cursor_blink
            self._cursor_time = now

        cursor = "_" if self._cursor_blink else " "
        input_text = f"> {self.input_buffer}{cursor}"
        draw.text((15, input_y), input_text, fill=(240, 245, 255), font=font)

        # Hint
        draw.text(
            (w - 120, overlay_top + 5),
            "Tab to close",
            fill=(100, 110, 130),
            font=font_sm,
        )
