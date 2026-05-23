"""MIDI intake daemon — skeleton.

Watches a MIDI inbox directory for incoming ``*.mid``/``*.midi`` files. This
revision establishes the scaffolding only: argparse, a structured key=value
logger, graceful SIGINT/SIGTERM shutdown via a stop event, and a single-pass
``scan_once`` helper. The watching loop is deliberately deferred to a
follow-up task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import signal
import sys
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
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


try:
    from watchdog.events import FileSystemEventHandler  # type: ignore[import-untyped]
    from watchdog.observers import Observer  # type: ignore[import-untyped]

    _HAS_WATCHDOG = True
except ImportError:  # pragma: no cover - exercised via fallback path
    _HAS_WATCHDOG = False

    class FileSystemEventHandler:  # type: ignore[no-redef]
        """Fallback stub when watchdog is unavailable."""

    Observer = None  # type: ignore[assignment,misc]


DEFAULT_WATCH_DIR = Path("/home/user/cypherclaw/midi-inbox/")
MIDI_EXTENSIONS: tuple[str, ...] = (".mid", ".midi")
MIDI_HEADER_MAGIC: bytes = b"MThd"
PROCESSED_SUBDIR: str = "processed"
REJECTED_SUBDIR: str = "rejected"

LOGGER = logging.getLogger("cypherclaw.midi_intake_daemon")


def _is_midi_path(path: Path | str) -> bool:
    return Path(path).suffix.lower() in MIDI_EXTENSIONS


def wait_for_stable_size(
    path: Path | str,
    *,
    poll_interval: float = 0.25,
    stable_for: float = 0.5,
    timeout: float = 30.0,
) -> bool:
    """Block until ``path``'s size is unchanged for ``stable_for`` seconds.

    Returns ``True`` when the file size settles, or ``False`` if the file
    disappears or the ``timeout`` elapses before that happens.
    """

    target = Path(path)
    deadline = time.monotonic() + timeout
    last_size: int | None = None
    last_change = time.monotonic()

    while time.monotonic() < deadline:
        try:
            size = target.stat().st_size
        except FileNotFoundError:
            return False

        now = time.monotonic()
        if size != last_size:
            last_size = size
            last_change = now
        elif now - last_change >= stable_for:
            return True

        time.sleep(poll_interval)

    return False


class MidiEventHandler(FileSystemEventHandler):
    """Dispatch MIDI files seen via ``on_created``/``on_moved`` events."""

    def __init__(
        self,
        *,
        dispatch: Callable[[Path], None],
        wait_for_stable: Callable[[Path], bool] = wait_for_stable_size,
    ) -> None:
        super().__init__()
        self._dispatch = dispatch
        self._wait_for_stable = wait_for_stable

    def _handle(self, raw_path: str) -> None:
        path = Path(raw_path)
        if not _is_midi_path(path):
            return
        if not self._wait_for_stable(path):
            LOGGER.info("midi_skipped path=%s reason=unstable_or_missing", path)
            return
        LOGGER.info("midi_detected path=%s", path)
        self._dispatch(path)

    def on_created(self, event: object) -> None:
        if getattr(event, "is_directory", False):
            return
        self._handle(getattr(event, "src_path", ""))

    def on_moved(self, event: object) -> None:
        if getattr(event, "is_directory", False):
            return
        dest = getattr(event, "dest_path", None) or getattr(event, "src_path", "")
        self._handle(str(dest))


def validate_midi_header(path: Path | str) -> bool:
    """Return ``True`` when ``path`` begins with the ``MThd`` magic bytes."""

    try:
        with Path(path).open("rb") as fh:
            header = fh.read(len(MIDI_HEADER_MAGIC))
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return False
    return header == MIDI_HEADER_MAGIC


def read_mthd_header(path: Path | str) -> dict[str, int] | None:
    """Parse the 14-byte MThd chunk and return ``{format, track_count, division}``.

    Returns ``None`` when the file is missing, unreadable, too short, or not
    prefixed with the ``MThd`` magic.
    """

    try:
        with Path(path).open("rb") as fh:
            chunk = fh.read(14)
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None
    if len(chunk) < 14 or chunk[:4] != MIDI_HEADER_MAGIC:
        return None
    return {
        "format": int.from_bytes(chunk[8:10], "big"),
        "track_count": int.from_bytes(chunk[10:12], "big"),
        "division": int.from_bytes(chunk[12:14], "big"),
    }


def build_manifest(
    file_path: Path | str,
    *,
    extracted_metadata: dict[str, object] | None = None,
    processed_at: datetime | None = None,
) -> dict[str, object]:
    """Return a JSON-serializable sidecar manifest for a processed MIDI file.

    ``extracted_metadata`` should contain whatever the intake stage was able to
    pull from the file; callers typically pass the output of
    :func:`read_mthd_header`. Recognized keys are ``format``, ``track_count``,
    and ``division`` (folded into the ``mthd_header`` block, with
    ``track_count`` also promoted to the top level for convenience).
    """

    src = Path(file_path)
    stamp = (processed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    metadata = extracted_metadata or {}

    mthd_header: dict[str, object] | None
    if any(k in metadata for k in ("format", "track_count", "division")):
        mthd_header = {
            "format": metadata.get("format"),
            "track_count": metadata.get("track_count"),
            "division": metadata.get("division"),
        }
    else:
        mthd_header = None

    track_count = metadata.get("track_count") if metadata else None

    return {
        "original_filename": src.name,
        "processed_at": stamp.isoformat(),
        "file_size": src.stat().st_size,
        "sha256": _sha256_of(src),
        "mthd_header": mthd_header,
        "track_count": track_count,
    }


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_destination(target_dir: Path, name: str) -> Path:
    candidate = target_dir / name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        candidate = target_dir / f"{stem}.{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def process_midi_file(
    path: Path | str,
    *,
    processed_dir: Path | str | None = None,
    rejected_dir: Path | str | None = None,
) -> dict[str, object]:
    """Validate ``path``, move it to ``processed/`` or ``rejected/``, emit event.

    For valid MIDI files moved to the ``processed/`` directory, a JSON sidecar
    manifest is written next to the destination path (using a ``.json``
    suffix).

    Returns the JSON event record describing the outcome. The record contains
    the original path, file size, sha256, ISO8601 UTC timestamp, status
    (``processed`` or ``rejected``), and the destination path. The same
    record is emitted to :data:`LOGGER` as a JSON line prefixed with
    ``midi_intake_event ``.
    """

    src = Path(path)
    parent = src.parent
    processed = Path(processed_dir) if processed_dir else parent / PROCESSED_SUBDIR
    rejected = Path(rejected_dir) if rejected_dir else parent / REJECTED_SUBDIR

    size = src.stat().st_size
    sha256 = _sha256_of(src)
    header_info = read_mthd_header(src)
    valid = validate_midi_header(src)
    target_dir = processed if valid else rejected
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination(target_dir, src.name)
    shutil.move(str(src), str(destination))

    if valid:
        manifest = build_manifest(destination, extracted_metadata=header_info)
        manifest_path = destination.with_suffix(destination.suffix + ".json")
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

    event: dict[str, object] = {
        "path": str(src),
        "size": size,
        "sha256": sha256,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "processed" if valid else "rejected",
        "destination": str(destination),
    }
    LOGGER.info("midi_intake_event %s", json.dumps(event, sort_keys=True))
    return event


def _default_dispatch(path: Path) -> None:
    process_midi_file(path)


def watch_loop(
    watch_dir: Path | str,
    stop_event: threading.Event,
    *,
    dispatch: Callable[[Path], None] = _default_dispatch,
    poll_interval: float = 1.0,
    wait_for_stable: Callable[[Path], bool] = wait_for_stable_size,
) -> None:
    """Watch ``watch_dir`` until ``stop_event`` is set.

    Uses ``watchdog.Observer`` when available; otherwise falls back to a
    poll-based scan that tracks previously seen paths so existing files are
    not re-dispatched.
    """

    watch_path = Path(watch_dir)
    watch_path.mkdir(parents=True, exist_ok=True)

    if _HAS_WATCHDOG:
        handler = MidiEventHandler(
            dispatch=dispatch, wait_for_stable=wait_for_stable
        )
        observer = Observer()
        observer.schedule(handler, str(watch_path), recursive=False)
        observer.start()
        LOGGER.info("watch_started backend=watchdog watch_dir=%s", watch_path)
        try:
            while not stop_event.is_set():
                stop_event.wait(timeout=poll_interval)
        finally:
            observer.stop()
            observer.join()
            LOGGER.info("watch_stopped backend=watchdog")
        return

    LOGGER.info("watch_started backend=poll watch_dir=%s", watch_path)
    seen: set[Path] = {p for p in scan_once(watch_path)}
    while not stop_event.is_set():
        for path in scan_once(watch_path):
            if path in seen:
                continue
            if not wait_for_stable(path):
                LOGGER.info("midi_skipped path=%s reason=unstable_or_missing", path)
                continue
            seen.add(path)
            LOGGER.info("midi_detected path=%s", path)
            dispatch(path)
        stop_event.wait(timeout=poll_interval)
    LOGGER.info("watch_stopped backend=poll")


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
