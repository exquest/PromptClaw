"""MIDI intake daemon — skeleton.

Watches a MIDI inbox directory for incoming ``*.mid``/``*.midi`` files. This
revision establishes the scaffolding only: argparse, a structured key=value
logger, graceful SIGINT/SIGTERM shutdown via a stop event, and a single-pass
``scan_once`` helper. The watching loop is deliberately deferred to a
follow-up task.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

try:
    from cypherclaw.first_boot import FirstBootAnnouncer, bootstrap_identity
except ImportError:
    try:
        from first_boot import FirstBootAnnouncer, bootstrap_identity
    except ImportError:
        def bootstrap_identity(*args, **kwargs) -> object:
            return None

        class FirstBootAnnouncer:
            def maybe_announce(self) -> object:
                return None


DEFAULT_WATCH_DIR = Path("/home/user/cypherclaw/midi-inbox/")
MIDI_EXTENSIONS: tuple[str, ...] = (".mid", ".midi")

LOGGER = logging.getLogger("cypherclaw.midi_intake_daemon")


def configure_logging(level: int = logging.INFO) -> None:
    """Install a key=value structured formatter on the root logger."""

    logging.basicConfig(
        level=level,
        format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
    )


def scan_once(watch_dir: Path | str) -> list[Path]:
    """Return MIDI files currently present in ``watch_dir``.

    Files are matched by case-insensitive suffix against
    :data:`MIDI_EXTENSIONS`. Subdirectories are not recursed. Missing
    directories return an empty list rather than raising — the inbox may not
    yet exist on first boot.
    """

    watch_path = Path(watch_dir)
    if not watch_path.is_dir():
        LOGGER.info("scan_skipped watch_dir=%s reason=missing", watch_path)
        return []

    found = sorted(
        p
        for p in watch_path.iterdir()
        if p.is_file() and p.suffix.lower() in MIDI_EXTENSIONS
    )
    LOGGER.info("scan_complete watch_dir=%s found=%d", watch_path, len(found))
    return found


def install_signal_handlers(stop_event: threading.Event) -> None:
    """Wire SIGINT/SIGTERM to set ``stop_event``."""

    def _handle(signum: int, _frame: object) -> None:
        LOGGER.info("shutdown_signal signal=%d", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CypherClaw MIDI intake daemon (skeleton).",
    )
    parser.add_argument(
        "--watch-dir",
        type=Path,
        default=DEFAULT_WATCH_DIR,
        help=(
            "Directory to watch for MIDI files "
            f"(default: {DEFAULT_WATCH_DIR})."
        ),
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()

    # Ensure identity exists before anything that depends on it (Hardening)
    bootstrap_identity()

    # Federated clones announce on first boot (FEDREAD-004)
    FirstBootAnnouncer().maybe_announce()

    stop_event = threading.Event()
    install_signal_handlers(stop_event)

    LOGGER.info("midi_intake_daemon_started watch_dir=%s", args.watch_dir)
    scan_once(args.watch_dir)
    LOGGER.info("midi_intake_daemon_exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
