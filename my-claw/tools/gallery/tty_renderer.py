"""TTY renderer for GlyphWeave art — writes ANSI escape sequences to a Linux TTY console."""

import fcntl
import os
import struct
import termios
import time
from pathlib import Path
from typing import Final


class TTYRenderer:
    """Renders GlyphWeave text art on a Linux TTY console using ANSI escape codes."""

    DEFAULT_WIDTH: Final[int] = 160
    DEFAULT_HEIGHT: Final[int] = 64

    # ANSI escape sequences
    ESC_CLEAR = "\033[2J"
    ESC_HOME = "\033[H"
    ESC_HIDE_CURSOR = "\033[?25l"
    ESC_SHOW_CURSOR = "\033[?25h"
    ESC_RESET = "\033[0m"

    def __init__(self, tty_path: str = "/dev/tty1"):
        self.tty_path = tty_path
        self.width, self.height = self._detect_terminal_size()

    def _detect_terminal_size(self) -> tuple[int, int]:
        """Read terminal columns/rows from the target TTY, falling back to legacy defaults."""
        tty = Path(self.tty_path)
        if not tty.exists():
            return self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT

        try:
            fd = os.open(self.tty_path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT

        try:
            rows, cols, _, _ = struct.unpack(
                "HHHH",
                fcntl.ioctl(fd, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0)),
            )
        except OSError:
            return self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT
        finally:
            os.close(fd)

        if rows <= 0 or cols <= 0:
            return self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT
        return cols, rows

    def _write(self, data: str) -> None:
        """Write raw string data to the TTY device."""
        try:
            with open(self.tty_path, "w") as tty:
                tty.write(data)
                tty.flush()
        except (PermissionError, FileNotFoundError, OSError) as e:
            # Fall back to stdout if TTY is unavailable (dev/testing)
            import sys
            sys.stderr.write(f"[TTYRenderer] Cannot write to {self.tty_path}: {e}\n")

    def _position(self, row: int, col: int) -> str:
        """Return ANSI escape to position cursor at (row, col). 1-indexed."""
        return f"\033[{row};{col}H"

    def clear(self) -> None:
        """Clear the screen via escape codes."""
        self._write(self.ESC_CLEAR + self.ESC_HOME + self.ESC_HIDE_CURSOR)

    def render_text(self, text: str, center: bool = True) -> None:
        """Render text art centered on screen. Write to tty_path."""
        lines = text.splitlines()
        if not lines:
            return

        buf = []
        buf.append(self.ESC_CLEAR + self.ESC_HOME + self.ESC_HIDE_CURSOR)

        if center:
            # Calculate vertical offset
            art_height = len(lines)
            art_width = max(len(self._strip_ansi(line)) for line in lines) if lines else 0
            v_offset = max(1, (self.height - art_height) // 2 + 1)
            h_offset = max(1, (self.width - art_width) // 2 + 1)

            for i, line in enumerate(lines):
                row = v_offset + i
                if row > self.height:
                    break
                buf.append(self._position(row, h_offset))
                buf.append(line)
        else:
            buf.append(self.ESC_HOME)
            for i, line in enumerate(lines):
                if i >= self.height:
                    break
                buf.append(line)
                if i < len(lines) - 1:
                    buf.append("\n")

        buf.append(self.ESC_RESET)
        self._write("".join(buf))

    def render_ansi(self, ansi_text: str) -> None:
        """Render ANSI-colored text art (pass-through, already has escape codes)."""
        buf = []
        buf.append(self.ESC_CLEAR + self.ESC_HOME + self.ESC_HIDE_CURSOR)
        buf.append(ansi_text)
        buf.append(self.ESC_RESET)
        self._write("".join(buf))

    def render_animation(self, frames: list[str], frame_duration: float = 3.0, loops: int = 3) -> None:
        """Play animation frames on the TTY."""
        if not frames:
            return

        for _ in range(loops):
            for frame in frames:
                self.render_text(frame, center=True)
                time.sleep(frame_duration)

    def render_overlay(self, main_art: str, overlay_lines: list[str]) -> None:
        """Render art with overlay text at the bottom."""
        buf = []
        buf.append(self.ESC_CLEAR + self.ESC_HOME + self.ESC_HIDE_CURSOR)

        # Render main art centered
        art_lines = main_art.splitlines()
        if art_lines:
            art_height = len(art_lines)
            art_width = max(len(self._strip_ansi(line)) for line in art_lines) if art_lines else 0
            # Leave room at bottom for overlay
            available_height = self.height - len(overlay_lines) - 2
            v_offset = max(1, (available_height - art_height) // 2 + 1)
            h_offset = max(1, (self.width - art_width) // 2 + 1)

            for i, line in enumerate(art_lines):
                row = v_offset + i
                if row > available_height:
                    break
                buf.append(self._position(row, h_offset))
                buf.append(line)

        # Render overlay at bottom with dim styling
        overlay_start_row = self.height - len(overlay_lines)
        for i, line in enumerate(overlay_lines):
            row = overlay_start_row + i
            col = max(1, (self.width - len(self._strip_ansi(line))) // 2 + 1)
            buf.append(self._position(row, col))
            buf.append(f"\033[2m{line}\033[0m")  # dim text

        buf.append(self.ESC_RESET)
        self._write("".join(buf))

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Strip ANSI escape codes from text for length calculations."""
        import re
        return re.sub(r"\033\[[0-9;]*[A-Za-z]", "", text)
