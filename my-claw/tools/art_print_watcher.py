#!/usr/bin/env python3
"""Watch for new GlyphWeave art and auto-print as thermal stickers."""

import os
import sys
import time
import json
import logging
from pathlib import Path

log = logging.getLogger("art_print_watcher")


class ArtPrintWatcher:
    POLL_INTERVAL = 30  # seconds

    def __init__(self, art_dir: str = "/home/user/cypherclaw/gallery/renders/",
                 printer_device: str = "/dev/usb/lp0",
                 state_file: str = "/run/cypherclaw-tmp/print_state.json"):
        self.art_dir = Path(art_dir)
        self.printer_device = printer_device
        self.state_file = Path(state_file)
        self.printed: set[str] = set()
        self._load_state()

    def _load_state(self):
        """Load set of already-printed file paths."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self.printed = set(data.get("printed", []))
                log.info("Loaded %d previously printed entries", len(self.printed))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not load state file: %s", exc)
                self.printed = set()

    def _save_state(self):
        """Persist printed set."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps({
                "printed": sorted(self.printed),
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, indent=2))
        except OSError as exc:
            log.error("Could not save state file: %s", exc)

    def scan_new_art(self) -> list[Path]:
        """Find art files not yet printed."""
        if not self.art_dir.exists():
            return []

        new_files: list[Path] = []
        for ext in ("*.txt", "*.art", "*.ascii"):
            for art_file in sorted(self.art_dir.glob(ext)):
                if str(art_file) not in self.printed:
                    new_files.append(art_file)
        return new_files

    def print_art(self, art_path: Path) -> bool:
        """Print a single art piece as a thermal sticker."""
        # Import ThermalPrinter from the sibling module
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from thermal_printer import ThermalPrinter

        try:
            text = art_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.error("Could not read %s: %s", art_path, exc)
            return False

        # Extract title from sidecar JSON if available
        title = art_path.stem.replace("_", " ").title()
        sidecar = art_path.with_suffix(".json")
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text())
                title = meta.get("title", title)
            except (json.JSONDecodeError, OSError):
                pass

        # Print as sticker with border
        printer = ThermalPrinter(device=self.printer_device)
        if not printer.connect():
            log.error("Printer not available at %s", self.printer_device)
            return False

        success = printer.print_sticker(text, title=title, border=True)
        if not success:
            log.error("Failed to print %s", art_path.name)
        return success

    def run(self):
        """Main watch loop."""
        log.info("Art print watcher started, watching %s", self.art_dir)
        while True:
            new_art = self.scan_new_art()
            for art_path in new_art:
                if self.print_art(art_path):
                    self.printed.add(str(art_path))
                    self._save_state()
                    log.info("Printed: %s", art_path.name)
            time.sleep(self.POLL_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    watcher = ArtPrintWatcher()
    watcher.run()
