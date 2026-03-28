"""Framebuffer renderer for GlyphWeave art — writes pixel data directly to /dev/fb0."""

import struct
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


class FramebufferRenderer:
    """Renders images directly to the Linux framebuffer at /dev/fb0."""

    def __init__(
        self,
        fb_path: str = "/dev/fb0",
        width: int = 1280,
        height: int = 1024,
        bpp: int = 32,
    ):
        self.fb_path = fb_path
        self.width = width
        self.height = height
        self.bpp = bpp
        self.pixel_size = bpp // 8  # bytes per pixel
        self.line_length = width * self.pixel_size
        self.screen_size = width * height * self.pixel_size

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

        resized = img.resize((new_w, new_h), Image.LANCZOS)

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

    def render_image(self, image_path: str) -> None:
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
        self.render_pil_image(img)

    def render_pil_image(self, img: "Image.Image") -> None:
        """Render a PIL Image object directly to framebuffer."""
        if not HAS_PILLOW:
            import sys
            sys.stderr.write("[FramebufferRenderer] Pillow not installed, cannot render\n")
            return

        img = img.convert("RGBA")
        canvas = self._resize_to_fit(img)
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
        font = None
        mono_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
        ]
        for fpath in mono_paths:
            if Path(fpath).exists():
                try:
                    font = ImageFont.truetype(fpath, font_size)
                    break
                except (OSError, IOError):
                    continue

        if font is None:
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

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
                w = bbox[2] - bbox[0]
            else:
                w = len(line) * (font_size // 2)
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
