#!/usr/bin/env python3
"""Inkplate e-ink status renderer for CypherClaw."""
from __future__ import annotations

from collections.abc import Mapping

from PIL import Image, ImageDraw, ImageFont

from senseweave.portfolio_report import SurfaceSnapshot
from senseweave.sample_status import face_display_sample_status_text

DEFAULT_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
DEFAULT_PADDING_X = 24
DEFAULT_PADDING_Y = 32
DEFAULT_TITLE_FONT_SIZE = 28
DEFAULT_BODY_FONT_SIZE = 22
DEFAULT_STATUS_FONT_SIZE = 22
DEFAULT_LINE_SPACING = 14


def _load_font(font_path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(font_path, size)
    except (OSError, IOError):
        return ImageFont.load_default()


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> int:
    if not text:
        return 0
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    return right - left


def _truncate_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    compact = " ".join(text.split())
    if not compact:
        return ""
    if _text_width(draw, compact, font) <= max_width:
        return compact

    ellipsis = "..."
    if _text_width(draw, ellipsis, font) > max_width:
        return ""

    low = 0
    high = len(compact)
    best = ellipsis
    while low <= high:
        mid = (low + high) // 2
        candidate = compact[:mid].rstrip()
        if not candidate:
            candidate = ellipsis
        else:
            candidate = f"{candidate}{ellipsis}"
        if _text_width(draw, candidate, font) <= max_width:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return best


class InkplateRenderer:
    """Build and render text lines for the e-ink status surface."""

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        *,
        padding_x: int = DEFAULT_PADDING_X,
        padding_y: int = DEFAULT_PADDING_Y,
        font_path: str = DEFAULT_FONT_PATH,
        title_font_size: int = DEFAULT_TITLE_FONT_SIZE,
        body_font_size: int = DEFAULT_BODY_FONT_SIZE,
        status_font_size: int = DEFAULT_STATUS_FONT_SIZE,
        line_spacing: int = DEFAULT_LINE_SPACING,
    ) -> None:
        self.width = width
        self.height = height
        self.padding_x = padding_x
        self.padding_y = padding_y
        self.line_spacing = line_spacing
        self.content_width = max(0, self.width - (self.padding_x * 2))
        self.title_font = _load_font(font_path, title_font_size)
        self.body_font = _load_font(font_path, body_font_size)
        self.status_font = _load_font(font_path, status_font_size)

    def _line_entries(
        self,
        *,
        snapshot: SurfaceSnapshot | None,
        activity: Mapping[str, object] | None,
        playback_state: Mapping[str, object] | None,
        monitor_state: Mapping[str, object] | None,
    ) -> tuple[tuple[str, ImageFont.ImageFont], ...]:
        probe = Image.new("1", (max(self.width, 1), max(self.height, 1)), 1)
        draw = ImageDraw.Draw(probe)

        entries: list[tuple[str, ImageFont.ImageFont]] = []
        if snapshot is not None:
            for text, font in (
                (snapshot.song_title, self.title_font),
                (snapshot.section_caption, self.body_font),
                (snapshot.practice_block, self.body_font),
                (snapshot.artistic_intent, self.body_font),
            ):
                fitted = _truncate_to_width(draw, text, font, self.content_width)
                if fitted:
                    entries.append((fitted, font))

        sample_text = face_display_sample_status_text(
            activity,
            playback_state,
            monitor_state,
        )
        fitted_sample = _truncate_to_width(
            draw,
            sample_text,
            self.status_font,
            self.content_width,
        )
        if fitted_sample:
            entries.append((fitted_sample, self.status_font))

        return tuple(entries)

    def build_lines(
        self,
        *,
        snapshot: SurfaceSnapshot | None = None,
        activity: Mapping[str, object] | None = None,
        playback_state: Mapping[str, object] | None = None,
        monitor_state: Mapping[str, object] | None = None,
    ) -> tuple[str, ...]:
        """Return the text lines that will be drawn on the e-ink surface."""
        return tuple(
            line
            for line, _font in self._line_entries(
                snapshot=snapshot,
                activity=activity,
                playback_state=playback_state,
                monitor_state=monitor_state,
            )
        )

    def render(
        self,
        *,
        snapshot: SurfaceSnapshot | None = None,
        activity: Mapping[str, object] | None = None,
        playback_state: Mapping[str, object] | None = None,
        monitor_state: Mapping[str, object] | None = None,
    ) -> Image.Image:
        """Render the current inkplate status frame to a monochrome PIL image."""
        image = Image.new("1", (self.width, self.height), 1)
        draw = ImageDraw.Draw(image)

        y = self.padding_y
        for line, font in self._line_entries(
            snapshot=snapshot,
            activity=activity,
            playback_state=playback_state,
            monitor_state=monitor_state,
        ):
            draw.text((self.padding_x, y), line, fill=0, font=font)
            _left, top, _right, bottom = draw.textbbox((self.padding_x, y), line, font=font)
            y += (bottom - top) + self.line_spacing
            if y >= self.height:
                break

        return image
