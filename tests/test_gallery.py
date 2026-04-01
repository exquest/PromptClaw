"""Tests for the GlyphWeave Gallery Display system."""

import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add my-claw/tools to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))


class TestTTYRenderer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="gallery-test-"))
        self.fake_tty = self.temp_dir / "fake_tty"
        self.fake_tty.write_text("")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_import(self):
        from gallery.tty_renderer import TTYRenderer
        renderer = TTYRenderer(str(self.fake_tty))
        self.assertEqual(renderer.width, 160)
        self.assertEqual(renderer.height, 64)

    @patch("gallery.tty_renderer.TTYRenderer._detect_terminal_size", return_value=(240, 67))
    def test_detects_terminal_size_from_tty(self, _mock_detect):
        from gallery.tty_renderer import TTYRenderer
        renderer = TTYRenderer(str(self.fake_tty))
        self.assertEqual(renderer.width, 240)
        self.assertEqual(renderer.height, 67)

    def test_clear_writes_escape_codes(self):
        from gallery.tty_renderer import TTYRenderer
        renderer = TTYRenderer(str(self.fake_tty))
        renderer.clear()
        content = self.fake_tty.read_text()
        self.assertIn("\033[2J", content)
        self.assertIn("\033[H", content)

    def test_render_text_writes_to_tty(self):
        from gallery.tty_renderer import TTYRenderer
        renderer = TTYRenderer(str(self.fake_tty))
        renderer.render_text("Hello World")
        content = self.fake_tty.read_text()
        self.assertIn("Hello World", content)

    def test_render_text_centers(self):
        from gallery.tty_renderer import TTYRenderer
        renderer = TTYRenderer(str(self.fake_tty))
        renderer.render_text("Hi", center=True)
        content = self.fake_tty.read_text()
        # Should contain positioning escape sequences
        self.assertIn("\033[", content)

    def test_render_overlay_includes_overlay_lines(self):
        from gallery.tty_renderer import TTYRenderer
        renderer = TTYRenderer(str(self.fake_tty))
        renderer.render_overlay("ART HERE", ["Model: claude", "Score: 8.5"])
        content = self.fake_tty.read_text()
        self.assertIn("ART HERE", content)
        self.assertIn("Model: claude", content)


class TestFramebufferRenderer(unittest.TestCase):
    def test_import(self):
        from gallery.fb_renderer import FramebufferRenderer
        renderer = FramebufferRenderer(fb_path="/nonexistent/fb0")
        self.assertEqual(renderer.width, 1280)
        self.assertEqual(renderer.height, 1024)

    def test_available_false_when_no_device(self):
        from gallery.fb_renderer import FramebufferRenderer
        renderer = FramebufferRenderer(fb_path="/nonexistent/fb0")
        self.assertFalse(renderer.available)

    def test_detects_geometry_from_sysfs(self):
        from gallery.fb_renderer import FramebufferRenderer

        temp_dir = Path(tempfile.mkdtemp(prefix="fb-sysfs-"))
        try:
            fb_dir = temp_dir / "fb0"
            fb_dir.mkdir()
            (fb_dir / "virtual_size").write_text("3840,2160\n")
            (fb_dir / "bits_per_pixel").write_text("32\n")

            renderer = FramebufferRenderer(
                fb_path="/dev/fb0",
                sysfs_root=temp_dir,
            )
            self.assertEqual(renderer.width, 3840)
            self.assertEqual(renderer.height, 2160)
            self.assertEqual(renderer.bpp, 32)
            self.assertEqual(renderer.screen_size, 3840 * 2160 * 4)
        finally:
            shutil.rmtree(temp_dir)


class TestGalleryDisplay(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="gallery-test-"))
        self.art_dir = self.temp_dir / "art"
        self.art_dir.mkdir()
        self.fake_tty = self.temp_dir / "fake_tty"
        self.fake_tty.write_text("")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_import(self):
        from gallery.gallery_display import GalleryDisplay
        gallery = GalleryDisplay(
            art_dir=str(self.art_dir),
            tty_path=str(self.fake_tty),
            fb_path="/nonexistent",
        )
        self.assertFalse(gallery.paused)
        self.assertTrue(gallery.running)

    def test_scan_empty_directory(self):
        from gallery.gallery_display import GalleryDisplay
        gallery = GalleryDisplay(
            art_dir=str(self.art_dir),
            tty_path=str(self.fake_tty),
            fb_path="/nonexistent",
        )
        gallery.scan_art()
        self.assertEqual(len(gallery.playlist), 0)

    def test_scan_finds_text_files(self):
        from gallery.gallery_display import GalleryDisplay
        (self.art_dir / "piece1.txt").write_text("Hello art")
        (self.art_dir / "piece2.txt").write_text("More art")
        gallery = GalleryDisplay(
            art_dir=str(self.art_dir),
            tty_path=str(self.fake_tty),
            fb_path="/nonexistent",
        )
        gallery.scan_art()
        self.assertEqual(len(gallery.playlist), 2)

    def test_scan_finds_png_files(self):
        from gallery.gallery_display import GalleryDisplay
        (self.art_dir / "piece.png").write_bytes(b"\x89PNG\r\n")
        gallery = GalleryDisplay(
            art_dir=str(self.art_dir),
            tty_path=str(self.fake_tty),
            fb_path="/nonexistent",
        )
        gallery.scan_art()
        self.assertEqual(len(gallery.playlist), 1)

    def test_sidecar_metadata_loaded_at_display(self):
        from gallery.gallery_display import GalleryDisplay
        (self.art_dir / "myart.txt").write_text("Art content")
        (self.art_dir / "myart.json").write_text(json.dumps({
            "title": "Custom Title",
            "model": "claude",
            "score": 8.5,
        }))
        gallery = GalleryDisplay(
            art_dir=str(self.art_dir),
            tty_path=str(self.fake_tty),
            fb_path="/nonexistent",
        )
        gallery.scan_art()
        self.assertEqual(len(gallery.playlist), 1)
        # Sidecar is loaded at display time, not scan time
        piece = gallery._load_metadata_sidecar(dict(gallery.playlist[0]))
        self.assertEqual(piece["title"], "Custom Title")
        self.assertEqual(piece["model"], "claude")

    def test_playlist_sorted_newest_first(self):
        from gallery.gallery_display import GalleryDisplay
        import time
        (self.art_dir / "old.txt").write_text("old")
        time.sleep(0.1)
        (self.art_dir / "new.txt").write_text("new")
        gallery = GalleryDisplay(
            art_dir=str(self.art_dir),
            tty_path=str(self.fake_tty),
            fb_path="/nonexistent",
        )
        gallery.scan_art()
        self.assertEqual(len(gallery.playlist), 2)
        # Newest should be first
        self.assertIn("new", gallery.playlist[0]["path"])

    def test_image_mode_renders_overlay_in_framebuffer(self):
        from gallery.gallery_display import GalleryDisplay

        image_path = self.art_dir / "piece.png"
        image_path.write_bytes(b"\x89PNG\r\n")
        gallery = GalleryDisplay(
            art_dir=str(self.art_dir),
            tty_path=str(self.fake_tty),
            fb_path="/nonexistent",
        )
        gallery.fb_renderer = MagicMock()
        gallery.fb_renderer.available = True
        gallery.tty_renderer = MagicMock()
        gallery.overlay_visible = True

        piece = {
            "path": str(image_path),
            "type": "image",
            "title": "Piece",
            "model": "codex",
            "score": 8.0,
            "theme": "demo",
            "favorite": False,
        }
        gallery.playlist = [piece]
        gallery._display_piece(piece)

        gallery.fb_renderer.render_image.assert_called_once()
        _, kwargs = gallery.fb_renderer.render_image.call_args
        self.assertIn("overlay_lines", kwargs)
        self.assertTrue(kwargs["overlay_lines"])
        gallery.tty_renderer.render_overlay.assert_not_called()


class TestArtWatcher(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="watcher-test-"))
        self.art_dir = self.temp_dir / "art"
        self.art_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_import(self):
        from gallery.gallery_display import ArtWatcher
        callback = MagicMock()
        watcher = ArtWatcher(self.art_dir, callback)
        self.assertEqual(watcher.art_dir, self.art_dir)


class TestThermalPrinter(unittest.TestCase):
    def test_import(self):
        from thermal_printer import ThermalPrinter
        printer = ThermalPrinter(device="/nonexistent/lp0")
        self.assertEqual(printer.width, 48)

    def test_center_text(self):
        from thermal_printer import ThermalPrinter
        printer = ThermalPrinter(device="/nonexistent/lp0", width=20)
        result = printer._center_text("Hi")
        lines = result.split("\n")
        for line in lines:
            if line.strip():
                # Should be left-padded to center within width
                self.assertGreater(len(line), len("Hi"))
                self.assertIn("Hi", line)

    def test_connect_returns_false_for_nonexistent_device(self):
        from thermal_printer import ThermalPrinter
        printer = ThermalPrinter(device="/nonexistent/lp0")
        self.assertFalse(printer.connect())

    def test_detect_printers_returns_list(self):
        from thermal_printer import ThermalPrinter
        printers = ThermalPrinter.detect_printers()
        self.assertIsInstance(printers, list)


class TestArtPrintWatcher(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="print-watcher-"))
        self.art_dir = self.temp_dir / "art"
        self.art_dir.mkdir()
        self.state_file = self.temp_dir / "state.json"

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_import(self):
        from art_print_watcher import ArtPrintWatcher
        watcher = ArtPrintWatcher(
            art_dir=str(self.art_dir),
            printer_device="/nonexistent",
            state_file=str(self.state_file),
        )
        self.assertEqual(len(watcher.printed), 0)

    def test_scan_new_art_finds_files(self):
        from art_print_watcher import ArtPrintWatcher
        (self.art_dir / "piece.txt").write_text("art")
        watcher = ArtPrintWatcher(
            art_dir=str(self.art_dir),
            printer_device="/nonexistent",
            state_file=str(self.state_file),
        )
        new = watcher.scan_new_art()
        self.assertEqual(len(new), 1)

    def test_scan_excludes_already_printed(self):
        from art_print_watcher import ArtPrintWatcher
        (self.art_dir / "piece.txt").write_text("art")
        watcher = ArtPrintWatcher(
            art_dir=str(self.art_dir),
            printer_device="/nonexistent",
            state_file=str(self.state_file),
        )
        watcher.printed.add(str(self.art_dir / "piece.txt"))
        new = watcher.scan_new_art()
        self.assertEqual(len(new), 0)


if __name__ == "__main__":
    unittest.main()
