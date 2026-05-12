"""GlyphWeave thermal sticker printer integration.

Print GlyphWeave ASCII art on USB thermal printers (58mm ESC/POS printers
like ZJ-5890K). Works with or without the python-escpos library installed --
falls back to raw ESC/POS byte commands written directly to the device file.
"""
from __future__ import annotations

import glob
import os
from typing import Any, Protocol, cast


# ESC/POS control codes (raw bytes)
_ESC = b"\x1b"
_GS = b"\x1d"
_INIT = _ESC + b"\x40"          # ESC @ — initialise printer
_CENTER = _ESC + b"\x61\x01"    # ESC a 1 — centre alignment
_LEFT = _ESC + b"\x61\x00"      # ESC a 0 — left alignment
_BOLD_ON = _ESC + b"\x45\x01"   # ESC E 1 — bold on
_BOLD_OFF = _ESC + b"\x45\x00"  # ESC E 0 — bold off
_DOUBLE_H = _GS + b"\x21\x01"   # GS ! 0x01 — double height
_NORMAL_SIZE = _GS + b"\x21\x00"  # GS ! 0x00 — normal size
_FEED_LINES = _ESC + b"\x64\x04"  # ESC d 4 — feed 4 lines
_CUT = _GS + b"\x56\x00"        # GS V 0 — full cut


class EscposPrinter(Protocol):
    def set(self, **kwargs: object) -> object: ...
    def text(self, text: str) -> object: ...
    def cut(self) -> object: ...
    def image(self, image: object) -> object: ...


class ThermalPrinter:
    """Print GlyphWeave art on ESC/POS thermal printers."""

    def __init__(self, device: str = "/dev/usb/lp0", width: int = 48):
        # width = printable characters per line (48 for 58mm paper)
        self.device = device
        self.width = width
        self._printer: EscposPrinter | None = None  # python-escpos printer object, if available

    def connect(self) -> bool:
        """Connect to printer. Try python-escpos first, fall back to raw."""
        try:
            from escpos.printer import File  # type: ignore[import-not-found, import-untyped]
            self._printer = cast(EscposPrinter, File(self.device))
            return True
        except ImportError:
            # python-escpos not installed -- fall back to raw device writes
            pass
        except Exception:
            # Device open failed or similar -- fall back to raw check
            pass
        return os.path.exists(self.device)

    # ------------------------------------------------------------------
    # Public print methods
    # ------------------------------------------------------------------

    def print_art(self, text: str, title: str = "", cut: bool = True) -> bool:
        """Print GlyphWeave art. Centres text, adds title header if provided."""
        if self._printer is not None:
            return self._print_escpos(text, title, cut)
        return self._print_raw(text, title=title, cut=cut)

    def print_art_as_image(self, text: str, title: str = "") -> bool:
        """Render art as monospace bitmap image, then print for pixel-perfect output.

        Requires Pillow *and* python-escpos. Returns False if either is missing.
        """
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-untyped]
        except ImportError:
            return False

        if self._printer is None:
            return False

        # Build the full text block
        lines = text.splitlines()
        if title:
            lines = [title, "=" * len(title), ""] + lines

        # Render to image
        font_size = 12
        font: Any
        try:
            font = ImageFont.truetype("DejaVuSansMono.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        # Measure text extent
        char_w = font_size * 0.6  # approximate monospace char width
        char_h = font_size * 1.4
        img_w = int(char_w * self.width)
        img_h = int(char_h * (len(lines) + 2))

        img = Image.new("1", (img_w, img_h), color=1)  # 1-bit, white bg
        draw = ImageDraw.Draw(img)
        y = int(char_h)
        for line in lines:
            draw.text((0, y), line, font=font, fill=0)  # black text
            y += int(char_h)

        try:
            self._printer.image(img)
            self._printer.cut()
            return True
        except Exception:
            return False

    def print_separator(self) -> None:
        """Print a decorative separator line."""
        sep = "\u2500" * self.width  # ─ horizontal box-drawing char
        if self._printer is not None:
            try:
                self._printer.text(sep + "\n")
            except Exception:
                self._write_raw_bytes(
                    _CENTER + sep.encode("utf-8", errors="replace") + b"\n"
                )
        else:
            self._write_raw_bytes(
                _CENTER + sep.encode("utf-8", errors="replace") + b"\n"
            )

    def print_sticker(self, text: str, title: str = "", border: bool = True) -> bool:
        """Print art as a sticker with optional border frame."""
        if border:
            bordered_text = self._add_border(text)
        else:
            bordered_text = text
        return self.print_art(bordered_text, title=title, cut=True)

    # ------------------------------------------------------------------
    # Private: python-escpos path
    # ------------------------------------------------------------------

    def _print_escpos(self, text: str, title: str, cut: bool) -> bool:
        """Print using python-escpos library."""
        p = self._printer
        if p is None:
            return False
        try:
            p.set(align="center")

            if title:
                p.set(bold=True, double_height=True, align="center")
                p.text(title + "\n")
                p.set(bold=False, double_height=False, align="center")
                p.text("=" * min(len(title) * 2, self.width) + "\n\n")

            centred = self._center_text(text)
            p.text(centred + "\n")

            if cut:
                p.text("\n\n")
                p.cut()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Private: raw ESC/POS path (no python-escpos dependency)
    # ------------------------------------------------------------------

    def _print_raw(self, text: str, title: str = "", cut: bool = True) -> bool:
        """Print using raw ESC/POS commands (no python-escpos dependency).

        Opens the device file directly and writes ESC/POS byte sequences.
        """
        parts: list[bytes] = [_INIT, _CENTER]

        if title:
            parts.append(_BOLD_ON)
            parts.append(_DOUBLE_H)
            parts.append(title.encode("utf-8", errors="replace") + b"\n")
            parts.append(_NORMAL_SIZE)
            parts.append(_BOLD_OFF)
            separator = ("=" * min(len(title) * 2, self.width)).encode("utf-8")
            parts.append(separator + b"\n\n")

        centred = self._center_text(text)
        parts.append(centred.encode("utf-8", errors="replace") + b"\n")

        if cut:
            parts.append(_FEED_LINES)
            parts.append(_CUT)

        return self._write_raw_bytes(b"".join(parts))

    def _write_raw_bytes(self, data: bytes) -> bool:
        """Write raw bytes to the printer device file."""
        try:
            with open(self.device, "wb") as f:
                f.write(data)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _center_text(self, text: str) -> str:
        """Centre each line of text within the print width."""
        centred_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.rstrip()
            if len(stripped) >= self.width:
                centred_lines.append(stripped[: self.width])
            else:
                pad = (self.width - len(stripped)) // 2
                centred_lines.append(" " * pad + stripped)
        return "\n".join(centred_lines)

    def _add_border(self, text: str) -> str:
        """Wrap text in a box-drawing border that fits the print width."""
        inner_w = self.width - 4  # "| " + content + " |"
        lines = text.splitlines()

        bordered: list[str] = []
        bordered.append("+" + "-" * (self.width - 2) + "+")
        for line in lines:
            stripped = line.rstrip()
            if len(stripped) > inner_w:
                stripped = stripped[:inner_w]
            padded = stripped.ljust(inner_w)
            bordered.append("| " + padded + " |")
        bordered.append("+" + "-" * (self.width - 2) + "+")
        return "\n".join(bordered)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_printers() -> list[str]:
        """Detect connected USB thermal printers.

        Checks /dev/usb/lp* and /dev/ttyUSB* on Linux. On macOS, checks
        /dev/cu.usbserial* and /dev/cu.usbmodem* as well.
        """
        candidates: list[str] = []
        for pattern in (
            "/dev/usb/lp*",
            "/dev/ttyUSB*",
            "/dev/cu.usbserial*",
            "/dev/cu.usbmodem*",
        ):
            candidates.extend(sorted(glob.glob(pattern)))
        return candidates
