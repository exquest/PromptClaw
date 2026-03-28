#!/usr/bin/env python3
"""GlyphWeave Gallery Display -- auto-rotating art on the physical server monitor."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from tty_renderer import TTYRenderer
from fb_renderer import FramebufferRenderer


class GalleryDisplay:
    """Main gallery loop that cycles through GlyphWeave art pieces."""

    STATIC_DURATION = 60       # seconds per static piece
    ANIMATION_LOOPS = 3        # times to loop animations
    OVERLAY_ENABLED = True     # toggled with 'i' key

    # Recognized art file extensions
    TEXT_EXTENSIONS = {".txt", ".ans", ".ansi", ".asc"}
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".svg"}
    ANIMATION_EXTENSIONS = {".frames"}  # directory of numbered frame files

    def __init__(
        self,
        art_dir: str = "/home/user/cypherclaw/gallery/renders/",
        tty_path: str = "/dev/tty1",
        fb_path: str = "/dev/fb0",
    ):
        self.art_dir = Path(art_dir)
        self.tty_renderer = TTYRenderer(tty_path)
        self.fb_renderer = FramebufferRenderer(fb_path) if os.path.exists(fb_path) else None
        self.playlist: list[dict] = []
        self.current_index = 0
        self.paused = False
        self.running = True
        self.overlay_visible = True
        self.theme_filter: str | None = None  # None = all themes
        self.render_mode = "auto"  # auto, ansi, fb
        self._skip_event = threading.Event()
        self._prev_event = threading.Event()
        self._themes: list[str] = []
        self._theme_index = -1  # -1 means "all"
        self._favorites: set[str] = set()
        self._favorites_path = self.art_dir / ".favorites.json"
        self._load_favorites()

    # -- Favorites persistence --------------------------------------------------

    def _load_favorites(self) -> None:
        """Load favorites set from disk."""
        try:
            if self._favorites_path.exists():
                self._favorites = set(json.loads(self._favorites_path.read_text()))
        except (json.JSONDecodeError, OSError):
            self._favorites = set()

    def _save_favorites(self) -> None:
        """Persist favorites set to disk."""
        try:
            self._favorites_path.write_text(json.dumps(sorted(self._favorites), indent=2))
        except OSError:
            pass

    # -- Art scanning -----------------------------------------------------------

    def scan_art(self) -> None:
        """Scan art directory for pieces, build playlist sorted newest first."""
        self.playlist.clear()

        if not self.art_dir.exists():
            return

        for path in self.art_dir.iterdir():
            piece = self._classify_piece(path)
            if piece:
                self.playlist.append(piece)

        # Also scan subdirectories one level deep
        for subdir in self.art_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("."):
                for path in subdir.iterdir():
                    piece = self._classify_piece(path)
                    if piece:
                        self.playlist.append(piece)

        # Sort newest first
        self.playlist.sort(key=lambda p: p.get("created_at", 0), reverse=True)

        # Apply theme filter
        if self.theme_filter:
            self.playlist = [
                p for p in self.playlist
                if p.get("theme", "").lower() == self.theme_filter.lower()
            ]

        # Collect unique themes for cycling
        all_themes = set()
        for p in self.playlist:
            t = p.get("theme", "")
            if t:
                all_themes.add(t)
        self._themes = sorted(all_themes)

    def _classify_piece(self, path: Path) -> dict | None:
        """Classify a file/directory as an art piece and return metadata dict."""
        if path.name.startswith("."):
            return None

        piece: dict = {
            "path": str(path),
            "title": path.stem.replace("_", " ").replace("-", " ").title(),
            "model": "unknown",
            "score": 0.0,
            "theme": "",
            "created_at": path.stat().st_mtime if path.exists() else 0,
            "favorite": str(path) in self._favorites,
        }

        suffix = path.suffix.lower()

        # Animation directory (contains numbered frames)
        if path.is_dir() and path.suffix == ".frames":
            piece["type"] = "animation"
            return piece

        # Text / ANSI art
        if suffix in self.TEXT_EXTENSIONS:
            piece["type"] = "ansi" if suffix in {".ans", ".ansi"} else "text"
            return piece

        # Image files
        if suffix in self.IMAGE_EXTENSIONS:
            piece["type"] = "image"
            return piece

        # JSON metadata sidecar (not an art piece itself)
        if suffix == ".json" and not path.name.startswith("."):
            return None

        return None

    def _load_metadata_sidecar(self, piece: dict) -> dict:
        """Load optional .json sidecar for a piece to get title/model/score/theme."""
        art_path = Path(piece["path"])
        sidecar = art_path.with_suffix(".json")
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text())
                piece["title"] = meta.get("title", piece["title"])
                piece["model"] = meta.get("model", piece["model"])
                piece["score"] = meta.get("score", piece["score"])
                piece["theme"] = meta.get("theme", piece["theme"])
            except (json.JSONDecodeError, OSError):
                pass
        return piece

    # -- Display ----------------------------------------------------------------

    def _display_piece(self, piece: dict) -> None:
        """Display a single art piece using appropriate renderer."""
        piece = self._load_metadata_sidecar(piece)
        art_path = Path(piece["path"])
        art_type = piece.get("type", "text")

        # Determine which renderer to use
        use_fb = (
            self.render_mode == "fb"
            or (self.render_mode == "auto" and art_type == "image" and self.fb_renderer and self.fb_renderer.available)
        )

        if art_type == "animation":
            self._display_animation(piece)
        elif art_type == "image" and use_fb and self.fb_renderer and self.fb_renderer.available:
            self.fb_renderer.render_image(str(art_path))
            if self.overlay_visible:
                overlay = self._build_overlay(piece)
                # For fb mode, render overlay via TTY on top
                self.tty_renderer.render_overlay("", overlay)
        elif art_type in ("text", "ansi"):
            self._display_text_art(piece)
        elif art_type == "image":
            # Fallback: render image as text via fb_renderer.render_text_as_image
            # or just show the filename
            if self.fb_renderer and self.fb_renderer.available:
                self.fb_renderer.render_image(str(art_path))
            else:
                self.tty_renderer.render_text(
                    f"[Image: {art_path.name}]\n\n(Framebuffer unavailable, cannot display pixel art)"
                )
        else:
            self.tty_renderer.render_text(f"[Unknown format: {art_path.name}]")

    def _display_text_art(self, piece: dict) -> None:
        """Display text/ANSI art on the TTY."""
        art_path = Path(piece["path"])
        try:
            content = art_path.read_text(errors="replace")
        except OSError:
            content = f"[Error reading {art_path.name}]"

        if self.overlay_visible:
            overlay = self._build_overlay(piece)
            self.tty_renderer.render_overlay(content, overlay)
        else:
            if piece.get("type") == "ansi":
                self.tty_renderer.render_ansi(content)
            else:
                self.tty_renderer.render_text(content)

    def _display_animation(self, piece: dict) -> None:
        """Display animation frames."""
        frames_dir = Path(piece["path"])
        frame_files = sorted(frames_dir.glob("*"))
        frames = []
        for f in frame_files:
            if f.suffix.lower() in self.TEXT_EXTENSIONS:
                try:
                    frames.append(f.read_text(errors="replace"))
                except OSError:
                    continue

        if frames:
            self.tty_renderer.render_animation(
                frames,
                frame_duration=3.0,
                loops=self.ANIMATION_LOOPS,
            )
        else:
            self.tty_renderer.render_text(f"[Animation: {frames_dir.name} - no frames found]")

    def _display_no_art(self) -> None:
        """Show a message when no art is available."""
        msg = (
            "\n"
            "    +-----------------------------------------+\n"
            "    |                                         |\n"
            "    |       GlyphWeave Gallery Display        |\n"
            "    |                                         |\n"
            "    |          No art pieces yet.             |\n"
            "    |                                         |\n"
            "    |   Drop .txt, .ans, or .png files in:    |\n"
            "    |   {art_dir:<33s}       |\n"
            "    |                                         |\n"
            "    |   Waiting for art...                    |\n"
            "    |                                         |\n"
            "    +-----------------------------------------+\n"
        ).format(art_dir=str(self.art_dir)[:33])
        self.tty_renderer.render_text(msg)

    def _display_stats(self) -> None:
        """Show gallery statistics on the TTY."""
        total = len(self.playlist)
        favs = sum(1 for p in self.playlist if p.get("favorite"))
        themes = len(self._themes)
        current = self.playlist[self.current_index % max(1, total)] if total else {}
        stats = (
            f"\n"
            f"  GlyphWeave Gallery Stats\n"
            f"  ========================\n"
            f"  Total pieces:  {total}\n"
            f"  Favorites:     {favs}\n"
            f"  Themes:        {themes}\n"
            f"  Theme filter:  {self.theme_filter or 'all'}\n"
            f"  Render mode:   {self.render_mode}\n"
            f"  Current:       {current.get('title', 'N/A')}\n"
            f"  Paused:        {'yes' if self.paused else 'no'}\n"
            f"\n"
            f"  Keys: n/p=nav  space=pause  i=overlay  t=theme\n"
            f"        f=fav  a=mode  s=stats  g=generate  q=quit\n"
        )
        self.tty_renderer.render_text(stats)

    # -- Overlay ----------------------------------------------------------------

    def _build_overlay(self, piece: dict) -> list[str]:
        """Build overlay lines: title, model, score, favorite, index."""
        title = piece.get("title", "Untitled")
        model = piece.get("model", "unknown")
        score = piece.get("score", 0.0)
        fav = " *" if piece.get("favorite") else ""
        theme = piece.get("theme", "")
        idx = self.current_index + 1
        total = len(self.playlist)

        lines = []
        lines.append(f"{title}{fav}")
        detail_parts = []
        if model != "unknown":
            detail_parts.append(f"model: {model}")
        if score > 0:
            detail_parts.append(f"score: {score:.1f}")
        if theme:
            detail_parts.append(f"theme: {theme}")
        if detail_parts:
            lines.append("  ".join(detail_parts))
        lines.append(f"[{idx}/{total}]  {'PAUSED' if self.paused else ''}")
        return lines

    # -- Keyboard ---------------------------------------------------------------

    def _keyboard_loop(self) -> None:
        """Read raw keypresses from TTY. Non-blocking using termios."""
        tty_path = self.tty_renderer.tty_path

        try:
            tty_fd = os.open(tty_path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            # Cannot open TTY for reading -- keyboard disabled
            return

        import select
        import termios

        try:
            old_settings = termios.tcgetattr(tty_fd)
        except termios.error:
            os.close(tty_fd)
            return

        try:
            # Set raw mode
            new_settings = termios.tcgetattr(tty_fd)
            new_settings[3] = new_settings[3] & ~(termios.ICANON | termios.ECHO)
            new_settings[6][termios.VMIN] = 0
            new_settings[6][termios.VTIME] = 0
            termios.tcsetattr(tty_fd, termios.TCSANOW, new_settings)

            while self.running:
                ready, _, _ = select.select([tty_fd], [], [], 0.2)
                if not ready:
                    continue

                try:
                    ch = os.read(tty_fd, 8)
                except OSError:
                    continue

                if not ch:
                    continue

                self._handle_key(ch)
        finally:
            try:
                termios.tcsetattr(tty_fd, termios.TCSANOW, old_settings)
            except termios.error:
                pass
            os.close(tty_fd)

    def _handle_key(self, ch: bytes) -> None:
        """Process a keypress byte sequence."""
        # Arrow keys come as escape sequences: ESC [ A/B/C/D
        if ch == b"\x1b[C" or ch in (b"n", b"N"):
            # Right arrow or 'n': next
            self._skip_event.set()
        elif ch == b"\x1b[D" or ch in (b"p", b"P"):
            # Left arrow or 'p': previous
            self._prev_event.set()
        elif ch == b" ":
            # Space: pause/resume
            self.paused = not self.paused
        elif ch in (b"f", b"F"):
            # Favorite toggle
            if self.playlist:
                piece = self.playlist[self.current_index % len(self.playlist)]
                path_str = piece["path"]
                if path_str in self._favorites:
                    self._favorites.discard(path_str)
                    piece["favorite"] = False
                else:
                    self._favorites.add(path_str)
                    piece["favorite"] = True
                self._save_favorites()
                # Re-display with updated overlay
                self._display_piece(piece)
        elif ch in (b"i", b"I"):
            # Toggle overlay
            self.overlay_visible = not self.overlay_visible
            if self.playlist:
                self._display_piece(self.playlist[self.current_index % len(self.playlist)])
        elif ch in (b"t", b"T"):
            # Cycle theme filter
            if self._themes:
                self._theme_index += 1
                if self._theme_index >= len(self._themes):
                    self._theme_index = -1
                    self.theme_filter = None
                else:
                    self.theme_filter = self._themes[self._theme_index]
                self.scan_art()
                self.current_index = 0
                if self.playlist:
                    self._display_piece(self.playlist[0])
                else:
                    self._display_no_art()
            else:
                self.theme_filter = None
        elif ch in (b"a", b"A"):
            # Toggle render mode: auto -> ansi -> fb -> auto
            modes = ["auto", "ansi", "fb"]
            idx = modes.index(self.render_mode)
            self.render_mode = modes[(idx + 1) % len(modes)]
            if self.playlist:
                self._display_piece(self.playlist[self.current_index % len(self.playlist)])
        elif ch in (b"s", b"S"):
            # Show stats
            self._display_stats()
            time.sleep(5)
        elif ch in (b"g", b"G"):
            # Trigger art generation (placeholder -- would signal GlyphWeave engine)
            self.tty_renderer.render_text(
                "\n  Triggering art generation...\n  (Signal sent to GlyphWeave engine)\n"
            )
            time.sleep(2)
        elif ch in (b"q", b"Q", b"\x03"):
            # Quit (q or Ctrl-C)
            self.running = False
            self._skip_event.set()

    # -- Timing -----------------------------------------------------------------

    def _wait_or_skip(self, duration: float) -> None:
        """Wait for duration, but break early if next/prev pressed."""
        self._skip_event.clear()
        self._prev_event.clear()

        interval = 0.25
        elapsed = 0.0
        while elapsed < duration and self.running and not self.paused:
            if self._skip_event.is_set():
                self._skip_event.clear()
                return
            if self._prev_event.is_set():
                self._prev_event.clear()
                # Go back two so the main loop's +1 lands on previous
                self.current_index = (self.current_index - 2) % max(1, len(self.playlist))
                return
            time.sleep(interval)
            elapsed += interval

    # -- Screen blanking --------------------------------------------------------

    def _disable_screen_blanking(self) -> None:
        """Disable console blanking and DPMS."""
        tty = self.tty_renderer.tty_path
        try:
            subprocess.run(
                ["setterm", "-blank", "0", "-powerdown", "0"],
                stdout=open(tty, "w"),
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except (FileNotFoundError, OSError):
            pass

    def _restore_screen_blanking(self) -> None:
        """Restore default screen blanking."""
        tty = self.tty_renderer.tty_path
        try:
            subprocess.run(
                ["setterm", "-blank", "15", "-powerdown", "60"],
                stdout=open(tty, "w"),
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except (FileNotFoundError, OSError):
            pass
        # Show cursor again
        self.tty_renderer._write(TTYRenderer.ESC_SHOW_CURSOR)

    # -- Signal handlers --------------------------------------------------------

    def _setup_signal_handlers(self) -> None:
        """Handle SIGTERM/SIGINT gracefully."""
        def _shutdown(signum, frame):
            self.running = False
            self._skip_event.set()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

    # -- Main loop --------------------------------------------------------------

    def run(self) -> None:
        """Main gallery loop."""
        self._disable_screen_blanking()
        self._setup_signal_handlers()

        self.scan_art()

        # Start keyboard listener
        keyboard_thread = threading.Thread(target=self._keyboard_loop, daemon=True)
        keyboard_thread.start()

        # Start file watcher
        watcher = ArtWatcher(self.art_dir, callback=self._on_new_art)
        watcher.start()

        try:
            while self.running:
                if not self.playlist:
                    self._display_no_art()
                    # Wait and rescan
                    self._wait_or_skip(10)
                    self.scan_art()
                    continue

                if not self.paused:
                    piece = self.playlist[self.current_index % len(self.playlist)]
                    self._display_piece(piece)
                    self._wait_or_skip(self.STATIC_DURATION)
                    if not self.paused and self.running:
                        self.current_index = (self.current_index + 1) % len(self.playlist)
                else:
                    time.sleep(0.5)
        finally:
            self._restore_screen_blanking()

    def _on_new_art(self, new_files: list[str]) -> None:
        """Callback when ArtWatcher finds new files -- rescan playlist."""
        self.scan_art()


class ArtWatcher(threading.Thread):
    """Watches art directory for new pieces and notifies gallery."""

    def __init__(self, art_dir: Path, callback, poll_interval: float = 5.0):
        super().__init__(daemon=True)
        self.art_dir = art_dir
        self.callback = callback
        self.poll_interval = poll_interval
        self.known_files: set[str] = set()
        self._scan_existing()

    def _scan_existing(self) -> None:
        """Record all currently existing files."""
        if not self.art_dir.exists():
            return
        for path in self.art_dir.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                self.known_files.add(str(path))

    def run(self) -> None:
        """Poll for new files every poll_interval seconds."""
        while True:
            time.sleep(self.poll_interval)
            if not self.art_dir.exists():
                continue

            current_files: set[str] = set()
            for path in self.art_dir.rglob("*"):
                if path.is_file() and not path.name.startswith("."):
                    current_files.add(str(path))

            new_files = current_files - self.known_files
            if new_files:
                self.known_files = current_files
                self.callback(sorted(new_files))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GlyphWeave Gallery Display")
    parser.add_argument(
        "--art-dir",
        default="/home/user/cypherclaw/gallery/renders/",
        help="Path to art directory",
    )
    parser.add_argument("--tty", default="/dev/tty1", help="TTY device path")
    parser.add_argument("--fb", default="/dev/fb0", help="Framebuffer device path")
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Seconds per piece (default: 60)",
    )
    args = parser.parse_args()

    gallery = GalleryDisplay(
        art_dir=args.art_dir,
        tty_path=args.tty,
        fb_path=args.fb,
    )
    gallery.STATIC_DURATION = args.duration
    gallery.run()
