from __future__ import annotations

import argparse
import os
import struct
import sys
import zlib
from pathlib import Path
from typing import Callable


MODULE_PATH = Path(__file__).resolve()
PROJECT_ROOT = MODULE_PATH.parent.parent
TOOLS_ROOT = None
for candidate in (
    PROJECT_ROOT / "my-claw" / "tools",
    PROJECT_ROOT / "tools",
    PROJECT_ROOT.parent / "tools",
):
    if (candidate / "glyphweave").exists():
        TOOLS_ROOT = candidate
        break
if TOOLS_ROOT is None:
    raise RuntimeError("unable to locate GlyphWeave tools directory")
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from glyphweave.dsl import (  # noqa: E402
    Animation,
    Canvas,
    PALETTE_CUTE,
    PALETTE_DRAGON,
    PALETTE_NIGHT,
    PALETTE_SPACE,
    PALETTE_UI,
    PALETTE_WATER,
    _display_width,
    _split_graphemes,
)


Palette = list[str]
SceneBuilder = Callable[[int, int, Palette], Canvas]

PALETTES: dict[str, Palette] = {
    "water": PALETTE_WATER,
    "space": PALETTE_SPACE,
    "cute": PALETTE_CUTE,
    "dragon": PALETTE_DRAGON,
    "night": PALETTE_NIGHT,
    "ui": PALETTE_UI,
}


def _safe_place_text(canvas: Canvas, x: int, y: int, text: str) -> None:
    if y < 0 or y >= canvas.height or x >= canvas.width:
        return
    cursor = max(0, x)
    for token in _split_graphemes(text):
        width = max(1, _display_width(token))
        if cursor + width > canvas.width:
            break
        if token.strip():
            if width > 1:
                canvas.place_emoji(cursor, y, token)
            else:
                canvas.place(cursor, y, token)
        cursor += width


def _safe_place_emoji(canvas: Canvas, x: int, y: int, emoji: str) -> None:
    if y < 0 or y >= canvas.height:
        return
    width = max(2, _display_width(emoji))
    if x < 0 or x + width > canvas.width:
        return
    canvas.place_emoji(x, y, emoji)


def _build_starfield(width: int, height: int, palette: Palette) -> Canvas:
    canvas = Canvas(width, height)
    for idx in range(min(width, height)):
        x = (idx * 3 + 1) % width
        y = (idx * 2 + 1) % height
        canvas.place(x, y, "." if idx % 2 else "*")
    _safe_place_emoji(canvas, max(0, width - 3), 1 if height > 2 else 0, palette[3] if len(palette) > 3 else "🪐")
    _safe_place_text(canvas, 1, max(0, height - 2), "starfield")
    return canvas


def _build_ocean(width: int, height: int, palette: Palette) -> Canvas:
    canvas = Canvas(width, height)
    waterline = max(0, height - 3)
    for y in range(waterline, height):
        canvas.fill_row(y, "~")
    _safe_place_emoji(canvas, 1, waterline, palette[0])
    _safe_place_emoji(canvas, max(0, width - 3), max(0, height - 2), palette[1] if len(palette) > 1 else "💧")
    _safe_place_text(canvas, 2, max(0, waterline - 1), "ocean depths")
    return canvas


def _build_garden(width: int, height: int, palette: Palette) -> Canvas:
    canvas = Canvas(width, height)
    ground = max(0, height - 2)
    if height >= 2:
        canvas.fill_row(ground, ".")
    _safe_place_emoji(canvas, 1, max(0, ground - 1), palette[2] if len(palette) > 2 else "🌸")
    _safe_place_emoji(canvas, max(0, width // 2), max(0, ground - 1), palette[0])
    _safe_place_emoji(canvas, max(0, width - 3), max(0, ground - 1), palette[1] if len(palette) > 1 else "💖")
    _safe_place_text(canvas, 1, 0, "cozy garden")
    return canvas


def _build_dragon(width: int, height: int, palette: Palette) -> Canvas:
    canvas = Canvas(width, height)
    _safe_place_text(canvas, 1, 1 if height > 2 else 0, "/\\__/\\\\")
    _safe_place_text(canvas, 1, min(height - 1, 2), "(  ^^ )")
    _safe_place_emoji(canvas, max(0, width - 3), 1 if height > 2 else 0, palette[0])
    _safe_place_emoji(canvas, max(0, width - 5), min(height - 1, 2), palette[1] if len(palette) > 1 else "🔥")
    _safe_place_text(canvas, 1, max(0, height - 2), "dragon lair")
    return canvas


def _build_night(width: int, height: int, palette: Palette) -> Canvas:
    canvas = Canvas(width, height)
    _safe_place_emoji(canvas, 1, 1 if height > 2 else 0, palette[0])
    for idx in range(2, width, 4):
        y = 1 + (idx // 4) % max(1, min(height - 1, 3))
        if y < height:
            _safe_place_emoji(canvas, idx, y, palette[1] if len(palette) > 1 else "✨")
    _safe_place_text(canvas, 1, max(0, height - 2), "moonlit forest")
    return canvas


def _build_ui(width: int, height: int, palette: Palette) -> Canvas:
    canvas = Canvas(width, height)
    for x in range(width):
        canvas.place(x, 0, "=")
        canvas.place(x, height - 1, "=")
    for y in range(1, height - 1):
        canvas.place(0, y, "|")
        canvas.place(width - 1, y, "|")
    _safe_place_text(canvas, 2, 1 if height > 2 else 0, "cyber city")
    _safe_place_text(canvas, 2, min(height - 2, 3), "status: live")
    _safe_place_emoji(canvas, max(0, width - 3), min(height - 2, 3), palette[0])
    return canvas


SCENES: dict[str, tuple[str, SceneBuilder]] = {
    "starfield": ("space", _build_starfield),
    "ocean-depths": ("water", _build_ocean),
    "cozy-garden": ("cute", _build_garden),
    "dragon-lair": ("dragon", _build_dragon),
    "moonlit-forest": ("night", _build_night),
    "cyber-city": ("ui", _build_ui),
    "ocean": ("water", _build_ocean),
    "garden": ("cute", _build_garden),
    "dragon": ("dragon", _build_dragon),
    "night": ("night", _build_night),
}


def _load_dsl(path: Path, width: int, height: int, palette: Palette) -> Canvas | Animation | str:
    namespace: dict[str, object] = {
        "__name__": "__glyphweave_preview__",
        "Canvas": Canvas,
        "Animation": Animation,
        "PALETTE_WATER": PALETTE_WATER,
        "PALETTE_SPACE": PALETTE_SPACE,
        "PALETTE_CUTE": PALETTE_CUTE,
        "PALETTE_DRAGON": PALETTE_DRAGON,
        "PALETTE_NIGHT": PALETTE_NIGHT,
        "PALETTE_UI": PALETTE_UI,
        "ACTIVE_PALETTE": palette,
        "width": width,
        "height": height,
        "canvas": Canvas(width, height),
    }
    code = compile(path.read_text(), str(path), "exec")
    exec(code, namespace, namespace)
    builder = namespace.get("build")
    renderer = namespace.get("render")
    if callable(builder):
        return builder(width, height, palette)  # type: ignore[misc]
    if callable(renderer):
        return renderer(width, height, palette)  # type: ignore[misc]
    for key in ("canvas", "result", "animation"):
        value = namespace.get(key)
        if isinstance(value, (Canvas, Animation, str)):
            return value
    raise ValueError(f"DSL file {path} did not produce a canvas, animation, or string result")


def _preview_text(renderable: Canvas | Animation | str) -> str:
    if isinstance(renderable, Canvas):
        return renderable.to_string()
    if isinstance(renderable, Animation):
        if renderable.frames:
            return renderable.frames[0].to_string()
        return ""
    return renderable


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)


def _write_block_png(text: str, output_path: Path) -> None:
    lines = text.splitlines() or [""]
    cell_w = 10
    cell_h = 16
    padding = 8
    token_lines: list[list[tuple[str, int]]] = []
    max_width = 0
    for line in lines:
        row: list[tuple[str, int]] = []
        width = 0
        for token in _split_graphemes(line):
            token_width = max(1, _display_width(token))
            row.append((token, token_width))
            width += token_width
        token_lines.append(row)
        max_width = max(max_width, width)

    img_w = max(1, max_width * cell_w + padding * 2)
    img_h = max(1, len(token_lines) * cell_h + padding * 2)
    pixels = bytearray([18, 18, 24, 255] * img_w * img_h)

    def fill_rect(x0: int, y0: int, w: int, h: int, rgba: tuple[int, int, int, int]) -> None:
        r, g, b, a = rgba
        for y in range(max(0, y0), min(img_h, y0 + h)):
            offset = (y * img_w + max(0, x0)) * 4
            for _ in range(max(0, x0), min(img_w, x0 + w)):
                pixels[offset:offset + 4] = bytes((r, g, b, a))
                offset += 4

    for row_index, row in enumerate(token_lines):
        cursor = padding
        for token, token_width in row:
            if token.strip():
                color_seed = sum(ord(ch) for ch in token)
                rgba = (
                    80 + color_seed % 120,
                    70 + (color_seed // 3) % 120,
                    110 + (color_seed // 7) % 110,
                    255,
                )
                fill_rect(cursor, padding + row_index * cell_h, token_width * cell_w - 1, cell_h - 2, rgba)
            cursor += token_width * cell_w

    raw = bytearray()
    stride = img_w * 4
    for y in range(img_h):
        raw.append(0)
        start = y * stride
        raw.extend(pixels[start:start + stride])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(_png_chunk(b"IHDR", struct.pack(">IIBBBBB", img_w, img_h, 8, 6, 0, 0, 0)))
        handle.write(_png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9)))
        handle.write(_png_chunk(b"IEND", b""))


def _write_png(text: str, output_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        _write_block_png(text, output_path)
        return

    lines = text.splitlines() or [""]
    font = None
    for font_path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
    ):
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, 18)
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default()

    sample = "M" * max(1, max(len(line) for line in lines))
    bbox = font.getbbox(sample)
    line_bbox = font.getbbox("Mg")
    char_w = max(8, bbox[2] - bbox[0]) // max(1, len(sample))
    line_h = max(18, line_bbox[3] - line_bbox[1] + 6)
    padding = 16
    img_w = max(1, max(len(line) for line in lines) * char_w + padding * 2)
    img_h = max(1, len(lines) * line_h + padding * 2)
    image = Image.new("RGBA", (img_w, img_h), (18, 18, 24, 255))
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((padding, padding + index * line_h), line, font=font, fill=(230, 232, 240, 255))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG")


def preview_command(args: argparse.Namespace) -> int:
    if bool(args.scene) == bool(args.dsl):
        raise SystemExit("choose exactly one of --scene or --dsl")

    if args.scene:
        scene_key = args.scene.strip().lower()
        if scene_key not in SCENES:
            raise SystemExit(f"unknown scene: {args.scene}")
        default_palette_name, builder = SCENES[scene_key]
        palette_name = args.palette or default_palette_name
        palette = PALETTES.get(palette_name)
        if palette is None:
            raise SystemExit(f"unknown palette: {palette_name}")
        renderable = builder(args.width, args.height, palette)
    else:
        palette_name = args.palette or "ui"
        palette = PALETTES.get(palette_name)
        if palette is None:
            raise SystemExit(f"unknown palette: {palette_name}")
        renderable = _load_dsl(Path(args.dsl), args.width, args.height, palette)

    text = _preview_text(renderable)
    output_path = Path(args.output)
    _write_png(text, output_path)
    print(text)
    print(f"\n[PNG] {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GlyphWeave CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview = subparsers.add_parser("preview", help="Render a single scene or DSL file to terminal and PNG.")
    preview.add_argument("--scene", help="Built-in GlyphWeave scene name.")
    preview.add_argument("--dsl", help="Path to a Python DSL file that returns or mutates a Canvas.")
    preview.add_argument("--palette", choices=sorted(PALETTES), help="Palette override.")
    preview.add_argument("--width", type=int, default=24)
    preview.add_argument("--height", type=int, default=12)
    preview.add_argument("--output", default="glyphweave-preview.png")
    preview.set_defaults(func=preview_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
