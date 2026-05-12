"""GlyphWeave DSL — available inside the generation sandbox as `from glyphweave_dsl import *`."""

from __future__ import annotations

import json
import unicodedata
from typing import Iterable

try:
    from wcwidth import wcswidth  # type: ignore[import-untyped]
except ModuleNotFoundError:
    wcswidth = None  # type: ignore[assignment]

_CONT = "\u0000"


def _split_graphemes(text: str) -> list[str]:
    clusters: list[str] = []
    current = ""

    i = 0
    while i < len(text):
        char = text[i]
        if not current:
            current = char
            i += 1
            continue

        codepoint = ord(char)
        if codepoint == 0x200D:  # ZWJ
            current += char
            if i + 1 < len(text):
                i += 1
                current += text[i]
            i += 1
            continue

        if codepoint == 0xFE0F or unicodedata.combining(char):
            current += char
            i += 1
            continue

        clusters.append(current)
        current = char
        i += 1

    if current:
        clusters.append(current)

    return clusters


def _display_width(token: str) -> int:
    if token == "":
        return 0

    if wcswidth is None:
        return 2 if any(ord(ch) > 127 for ch in token) else len(token)

    width = wcswidth(token)
    if width > 0:
        if any(ord(ch) > 127 for ch in token):
            return max(width, 2)
        return width

    return 2 if any(ord(ch) > 127 for ch in token) else 1


def _row_width(tokens: Iterable[str]) -> int:
    return sum(_display_width(token) for token in tokens)


def _is_emoji_like(token: str) -> bool:
    return _display_width(token) > 1 and any(ord(ch) > 127 for ch in token)


class Canvas:
    """Fixed-size character grid with layer support."""

    def __init__(self, width: int, height: int):
        """Create a canvas of width x height cells."""
        if width <= 0 or height <= 0:
            raise ValueError("Canvas width and height must be positive")
        self.width = int(width)
        self.height = int(height)
        self._rows: list[list[str]] = [[" " for _ in range(self.width)] for _ in range(self.height)]

    def _validate_write(self, x: int, y: int, token_width: int) -> None:
        if token_width <= 0:
            raise ValueError("Token width must be positive")
        if x < 0 or y < 0 or y >= self.height:
            raise ValueError("Coordinates out of bounds")
        if x + token_width > self.width:
            raise ValueError("Placement exceeds canvas bounds")

    def _erase_cluster_at(self, x: int, y: int) -> None:
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return

        row = self._rows[y]
        if row[x] == " ":
            return

        start = x
        while start > 0 and row[start] == _CONT:
            start -= 1

        token = row[start]
        token_width = max(1, _display_width(token))
        row[start] = " "
        for idx in range(1, token_width):
            if start + idx < self.width:
                row[start + idx] = " "

    def _write_token(self, x: int, y: int, token: str, token_width: int) -> None:
        self._validate_write(x, y, token_width)

        for cursor in range(x, x + token_width):
            self._erase_cluster_at(cursor, y)

        self._rows[y][x] = token
        for idx in range(1, token_width):
            self._rows[y][x + idx] = _CONT

    def place(self, x: int, y: int, char: str) -> "Canvas":
        """Place a single-width ASCII character at (x, y)."""
        if not isinstance(char, str) or len(char) == 0:
            raise ValueError("char must be a non-empty string")
        graphemes = _split_graphemes(char)
        if len(graphemes) != 1:
            raise ValueError("place expects a single character")
        token = graphemes[0]
        if _display_width(token) != 1:
            raise ValueError("place only accepts single-width characters")

        self._write_token(int(x), int(y), token, 1)
        return self

    def place_emoji(self, x: int, y: int, emoji: str) -> "Canvas":
        """Place an emoji at (x, y), consuming wcwidth(emoji) cells."""
        if not isinstance(emoji, str) or len(emoji) == 0:
            raise ValueError("emoji must be a non-empty string")

        graphemes = _split_graphemes(emoji)
        if len(graphemes) != 1:
            raise ValueError("place_emoji expects a single grapheme")

        token = graphemes[0]
        width = _display_width(token)
        width = 2 if width <= 1 else width

        self._write_token(int(x), int(y), token, width)
        return self

    def place_text(self, x: int, y: int, text: str) -> "Canvas":
        """Place a string starting at (x, y), auto-advancing x by character width."""
        if not isinstance(text, str):
            raise ValueError("text must be a string")

        cursor = int(x)
        row = int(y)
        for token in _split_graphemes(text):
            token_width = _display_width(token)
            if token_width <= 0:
                continue
            self._write_token(cursor, row, token, token_width)
            cursor += token_width

        return self

    def fill_row(self, y: int, char: str) -> "Canvas":
        """Fill an entire row with a repeated character."""
        if _display_width(char) != 1:
            raise ValueError("fill_row requires a single-width character")
        row = int(y)
        if row < 0 or row >= self.height:
            raise ValueError("Row out of bounds")

        for x in range(self.width):
            self._write_token(x, row, char, 1)
        return self

    def fill_region(self, x: int, y: int, w: int, h: int, char: str) -> "Canvas":
        """Fill a rectangular region with a character."""
        if _display_width(char) != 1:
            raise ValueError("fill_region requires a single-width character")
        if w <= 0 or h <= 0:
            raise ValueError("w and h must be positive")
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            raise ValueError("Region out of bounds")

        for row in range(y, y + h):
            for col in range(x, x + w):
                self._write_token(col, row, char, 1)
        return self

    def composite(self, other: "Canvas", offset_x: int = 0, offset_y: int = 0) -> "Canvas":
        """Overlay another canvas onto this one. Spaces are transparent."""
        if not isinstance(other, Canvas):
            raise ValueError("other must be a Canvas")

        for y in range(other.height):
            for x in range(other.width):
                token = other._rows[y][x]
                if token in {" ", _CONT}:
                    continue
                width = _display_width(token)
                self._write_token(x + offset_x, y + offset_y, token, width)

        return self

    def _iter_row_tokens(self, row: Iterable[str]) -> list[str]:
        tokens: list[str] = []
        for token in row:
            if token == _CONT:
                continue
            tokens.append(token)
        return tokens

    def to_string(self) -> str:
        """Render canvas to plain text string with newlines."""
        lines: list[str] = []
        for row in self._rows:
            tokens = self._iter_row_tokens(row)
            rendered = "".join(tokens)
            row_width = _row_width(tokens)
            if row_width < self.width:
                rendered += " " * (self.width - row_width)
            lines.append(rendered)
        return "\n".join(lines)

    def to_ansi(self, color_map: dict | None = None) -> str:
        """Render canvas to ANSI-colored string."""
        color_map = color_map or {}
        lines: list[str] = []
        for row in self._rows:
            tokens = self._iter_row_tokens(row)
            parts: list[str] = []
            for token in tokens:
                color = color_map.get(token)
                if color:
                    parts.append(f"\x1b[{color}m{token}\x1b[0m")
                else:
                    parts.append(token)
            rendered = "".join(parts)
            row_width = _row_width(tokens)
            if row_width < self.width:
                rendered += " " * (self.width - row_width)
            lines.append(rendered)
        return "\n".join(lines)

    def validate(self, max_emoji_per_row: int = 2, max_emoji_total: int = 15) -> list[str]:
        """Return list of validation errors, empty if valid."""
        errors: list[str] = []
        total_emoji = 0

        for row_index, row in enumerate(self._rows):
            tokens = self._iter_row_tokens(row)
            row_width = _row_width(tokens)
            if row_width != self.width:
                errors.append(
                    f"Row {row_index} has width {row_width}; expected {self.width}"
                )

            row_emoji = sum(1 for token in tokens if _is_emoji_like(token))
            total_emoji += row_emoji
            if row_emoji > max_emoji_per_row:
                errors.append(
                    f"Row {row_index} has {row_emoji} emoji; max is {max_emoji_per_row}"
                )

        if total_emoji > max_emoji_total:
            errors.append(f"Canvas has {total_emoji} emoji; max is {max_emoji_total}")

        return errors


class Animation:
    """Frame-based animation container (AEAF format)."""

    def __init__(self, width: int, height: int, frame_ms: int = 120, loop: bool = True):
        """Create animation with fixed canvas size and timing."""
        if width <= 0 or height <= 0:
            raise ValueError("Animation width and height must be positive")
        if frame_ms <= 0:
            raise ValueError("frame_ms must be positive")

        self.width = int(width)
        self.height = int(height)
        self.frame_ms = int(frame_ms)
        self.loop = bool(loop)
        self.frames: list[Canvas] = []

    def add_frame(self, canvas: Canvas) -> "Animation":
        """Append a frame."""
        if canvas.width != self.width or canvas.height != self.height:
            raise ValueError("Frame size mismatch")
        self.frames.append(canvas)
        return self

    def to_aeaf(self) -> str:
        """Export as AEAF v1 text block."""
        frame_blocks = "\n---frame---\n".join(frame.to_string() for frame in self.frames)
        return (
            "AEAF:1\n"
            f"width={self.width}\n"
            f"height={self.height}\n"
            f"frame_ms={self.frame_ms}\n"
            f"loop={str(self.loop).lower()}\n"
            "---frame---\n"
            f"{frame_blocks}"
        )

    def to_string(self) -> str:
        """Alias for to_aeaf()."""
        return self.to_aeaf()


class Motif:
    """A small reusable art component."""

    def __init__(self, width: int, height: int, base_layer: str, accent_layer: str = ""):
        """Create motif from pre-defined layer strings."""
        if width <= 0 or height <= 0:
            raise ValueError("Motif width and height must be positive")
        self.width = int(width)
        self.height = int(height)
        self.base_layer = base_layer
        self.accent_layer = accent_layer

    def _layer_lines(self, layer: str) -> list[str]:
        if "\n" in layer:
            lines = layer.splitlines()
        else:
            lines = [layer[i : i + self.width] for i in range(0, len(layer), self.width)]

        if len(lines) < self.height:
            lines.extend([""] * (self.height - len(lines)))
        return lines[: self.height]

    def to_canvas(self) -> Canvas:
        """Convert motif to a Canvas for compositing."""
        c = Canvas(self.width, self.height)

        for y, line in enumerate(self._layer_lines(self.base_layer)):
            if line:
                c.place_text(0, y, line)

        for y, line in enumerate(self._layer_lines(self.accent_layer)):
            if not line:
                continue
            for x, token in enumerate(_split_graphemes(line)):
                if token == " ":
                    continue
                width = _display_width(token)
                if x + width > self.width:
                    break
                c._write_token(x, y, token, width)

        return c


# Convenience constructors

def canvas(w: int, h: int) -> Canvas:
    return Canvas(w, h)


def animation(w: int, h: int, frame_ms: int = 120, loop: bool = True) -> Animation:
    return Animation(w, h, frame_ms=frame_ms, loop=loop)


def motif(w: int, h: int, base: str, accent: str = "") -> Motif:
    return Motif(w, h, base, accent)


# Palette constants
PALETTE_WATER = ["🌊", "💧", "🫧", "✨"]
PALETTE_SPACE = ["🌌", "✨", "🌟", "🪐", "☄️"]
PALETTE_CUTE = ["🐱", "🐭", "🌸", "💖", "✨"]
PALETTE_DRAGON = ["🐉", "🔥", "✨", "💨"]
PALETTE_NIGHT = ["🌙", "✨", "🌟", "💫"]
PALETTE_UI = ["✨", "▸", "⏳", "🕒"]


def to_json(value: dict) -> str:
    """Helper available to generated programs for deterministic JSON dumps."""
    return json.dumps(value, ensure_ascii=False)
