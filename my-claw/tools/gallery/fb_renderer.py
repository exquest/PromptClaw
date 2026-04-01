"""Framebuffer renderer for GlyphWeave art — writes pixel data directly to /dev/fb0."""

import struct
from pathlib import Path
from typing import Final

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    Image = ImageDraw = ImageFont = None  # type: ignore[assignment]

RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1)


class FramebufferRenderer:
    """Renders images directly to the Linux framebuffer at /dev/fb0."""

    DEFAULT_WIDTH: Final[int] = 1280
    DEFAULT_HEIGHT: Final[int] = 1024
    DEFAULT_BPP: Final[int] = 32

    def __init__(
        self,
        fb_path: str = "/dev/fb0",
        width: int | None = None,
        height: int | None = None,
        bpp: int | None = None,
        sysfs_root: str | Path = "/sys/class/graphics",
    ):
        self.fb_path = fb_path
        detected_width, detected_height, detected_bpp = self._detect_geometry(sysfs_root)
        self.width = width or detected_width
        self.height = height or detected_height
        self.bpp = bpp or detected_bpp
        self.pixel_size = self.bpp // 8  # bytes per pixel
        self.line_length = self.width * self.pixel_size
        self.screen_size = self.width * self.height * self.pixel_size

    def _detect_geometry(self, sysfs_root: str | Path) -> tuple[int, int, int]:
        """Read framebuffer geometry from sysfs, falling back to legacy defaults."""
        fb_name = Path(self.fb_path).name
        fb_dir = Path(sysfs_root) / fb_name

        try:
            virtual_size = (fb_dir / "virtual_size").read_text().strip()
            width_str, height_str = virtual_size.split(",", maxsplit=1)
            width = int(width_str)
            height = int(height_str)
        except (OSError, ValueError):
            width = self.DEFAULT_WIDTH
            height = self.DEFAULT_HEIGHT

        try:
            bpp = int((fb_dir / "bits_per_pixel").read_text().strip())
        except (OSError, ValueError):
            bpp = self.DEFAULT_BPP

        return width, height, bpp

    @property
    def available(self) -> bool:
        """Check if framebuffer device exists and Pillow is installed."""
        return HAS_PILLOW and Path(self.fb_path).exists()

    def _write_raw(self, data: bytes) -> None:
        """Write raw bytes to the framebuffer device."""
        try:
            with open(self.fb_path, "wb") as fb:
                fb.write(data)
        except (PermissionError, FileNotFoundError, OSError) as e:
            import sys
            sys.stderr.write(f"[FramebufferRenderer] Cannot write to {self.fb_path}: {e}\n")

    def _rgba_to_bgra(self, img: "Image.Image") -> bytes:
        """Convert a PIL RGBA image to BGRA byte buffer for the framebuffer.

        Linux framebuffers with 32bpp typically use BGRA pixel format.
        """
        pixels = img.tobytes("raw", "RGBA")
        # Swap R and B channels: RGBA -> BGRA
        buf = bytearray(len(pixels))
        for i in range(0, len(pixels), 4):
            buf[i] = pixels[i + 2]      # B
            buf[i + 1] = pixels[i + 1]  # G
            buf[i + 2] = pixels[i]      # R
            buf[i + 3] = pixels[i + 3]  # A
        return bytes(buf)

    def _resize_to_fit(self, img: "Image.Image") -> "Image.Image":
        """Resize image to fit screen while maintaining aspect ratio.

        Centers the image on a black background.
        """
        img_w, img_h = img.size
        scale = min(self.width / img_w, self.height / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)

        resized = img.resize((new_w, new_h), RESAMPLE_LANCZOS)

        # Paste onto black canvas, centered
        canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 255))
        x_offset = (self.width - new_w) // 2
        y_offset = (self.height - new_h) // 2
        canvas.paste(resized, (x_offset, y_offset))

        return canvas

    def clear(self, color: tuple[int, int, int] = (0, 0, 0)) -> None:
        """Fill screen with solid color."""
        r, g, b = color
        # BGRA format
        pixel = struct.pack("BBBB", b, g, r, 255)
        data = pixel * (self.width * self.height)
        self._write_raw(data)

    def _load_font(self, font_size: int) -> "ImageFont.ImageFont | ImageFont.FreeTypeFont | None":
        """Load a readable font for framebuffer overlays."""
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
        ]
        for font_path in font_paths:
            if Path(font_path).exists():
                try:
                    return ImageFont.truetype(font_path, font_size)
                except (OSError, IOError):
                    continue
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _draw_overlay(self, canvas: "Image.Image", overlay_lines: list[str]) -> "Image.Image":
        """Draw a translucent bottom overlay directly into the framebuffer image."""
        if not overlay_lines:
            return canvas

        draw = ImageDraw.Draw(canvas, "RGBA")
        font_size = max(28, min(72, self.height // 32))
        font = self._load_font(font_size)
        padding_x = max(24, font_size)
        padding_y = max(16, font_size // 2)
        line_gap = max(8, font_size // 5)

        line_metrics: list[tuple[str, int, int]] = []
        max_width = 0
        total_height = 0
        for line in overlay_lines:
            if font:
                bbox = draw.textbbox((0, 0), line, font=font)
                width = int(bbox[2] - bbox[0])
                height = int(bbox[3] - bbox[1])
            else:
                width = int(len(line) * (font_size // 2))
                height = font_size
            line_metrics.append((line, width, height))
            max_width = max(max_width, width)
            total_height += height
        total_height += line_gap * max(0, len(line_metrics) - 1)

        band_height = total_height + (padding_y * 2)
        top = max(0, self.height - band_height)
        draw.rectangle((0, top, self.width, self.height), fill=(0, 0, 0, 180))
        draw.line((0, top, self.width, top), fill=(255, 255, 255, 70), width=2)

        y = top + padding_y
        for line, width, height in line_metrics:
            x = max(padding_x, (self.width - width) // 2)
            draw.text((x + 2, y + 2), line, fill=(0, 0, 0, 180), font=font)
            draw.text((x, y), line, fill=(245, 245, 245, 255), font=font)
            y += height + line_gap

        return canvas

    def render_image(self, image_path: str, overlay_lines: list[str] | None = None) -> None:
        """Render a PNG/JPG image scaled to fill screen. Uses Pillow."""
        if not HAS_PILLOW:
            import sys
            sys.stderr.write("[FramebufferRenderer] Pillow not installed, cannot render image\n")
            return

        path = Path(image_path)
        if not path.exists():
            import sys
            sys.stderr.write(f"[FramebufferRenderer] Image not found: {image_path}\n")
            return

        img = Image.open(path).convert("RGBA")
        self.render_pil_image(img, overlay_lines=overlay_lines)

    def render_pil_image(
        self,
        img: "Image.Image",
        overlay_lines: list[str] | None = None,
    ) -> None:
        """Render a PIL Image object directly to framebuffer."""
        if not HAS_PILLOW:
            import sys
            sys.stderr.write("[FramebufferRenderer] Pillow not installed, cannot render\n")
            return

        img = img.convert("RGBA")
        canvas = self._resize_to_fit(img)
        if overlay_lines:
            canvas = self._draw_overlay(canvas, overlay_lines)
        data = self._rgba_to_bgra(canvas)
        self._write_raw(data)

    def render_text_as_image(self, text: str, font_size: int = 16) -> None:
        """Render text art as a pixel image on the framebuffer.

        Uses Pillow ImageDraw to render monospace text onto a black canvas,
        then writes to fb0.
        """
        if not HAS_PILLOW:
            import sys
            sys.stderr.write("[FramebufferRenderer] Pillow not installed, cannot render text\n")
            return

        # Try to load a monospace font
        font = self._load_font(font_size)

        canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 255))
        draw = ImageDraw.Draw(canvas)

        lines = text.splitlines()
        if not lines:
            self._write_raw(self._rgba_to_bgra(canvas))
            return

        # Measure line height
        if font:
            bbox = draw.textbbox((0, 0), "Xg", font=font)
            line_height = bbox[3] - bbox[1] + 4
        else:
            line_height = font_size + 4

        total_text_height = len(lines) * line_height

        # Find widest line for horizontal centering
        max_line_width = 0
        for line in lines:
            if font:
                bbox = draw.textbbox((0, 0), line, font=font)
                w = int(bbox[2] - bbox[0])
            else:
                w = int(len(line) * (font_size // 2))
            max_line_width = max(max_line_width, w)

        y_start = max(0, (self.height - total_text_height) // 2)
        x_start = max(0, (self.width - max_line_width) // 2)

        # Draw each line
        for i, line in enumerate(lines):
            y = y_start + i * line_height
            if y > self.height:
                break
            if font:
                draw.text((x_start, y), line, fill=(255, 255, 255, 255), font=font)
            else:
                draw.text((x_start, y), line, fill=(255, 255, 255, 255))

        data = self._rgba_to_bgra(canvas)
        self._write_raw(data)
