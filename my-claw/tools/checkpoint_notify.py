"""Notify Anthony of a feature checkpoint and pause the task queue.

Used after :mod:`session_archiver` uploads a checkpoint artifact (T-056b)
to:

* send a Telegram message containing the archive URL (per the
  ``feedback_telegram_length`` 300-char cap), and
* drop a ``.sdp/CHECKPOINT_PAUSE`` flag so the sdp-cli runner halts new
  task pickup until Anthony reviews and the flag is cleared.

The flag is intentionally lighter than ``maintenance_mode``: it does not
drain or kill the runner, it only signals "do not advance past this
checkpoint". An operator (or follow-up tool) clears it once Anthony
replies via Telegram.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, TextIO

_REPO_TOOLS_DIR = Path(__file__).resolve().parent
if str(_REPO_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_REPO_TOOLS_DIR))

import telegram  # noqa: E402

DEFAULT_FLAG_RELPATH = Path(".sdp/CHECKPOINT_PAUSE")
DEFAULT_ACTOR = "checkpoint_notify"
DEFAULT_REASON = "checkpoint review pending Anthony's response"
TELEGRAM_MAX_CHARS = 300

SendMessageFn = Callable[..., dict]


@dataclass(frozen=True)
class CheckpointDetails:
    """Inputs needed to compose the notification and pause flag."""

    slug: str
    archive_url: str
    metadata_url: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    timestamp: str | None = None

    def to_flag_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "slug": self.slug,
            "archive_url": self.archive_url,
        }
        if self.metadata_url:
            payload["metadata_url"] = self.metadata_url
        if self.sha256:
            payload["sha256"] = self.sha256
        if self.size_bytes is not None:
            payload["size_bytes"] = int(self.size_bytes)
        if self.timestamp:
            payload["timestamp"] = self.timestamp
        return payload


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def compose_message(details: CheckpointDetails) -> str:
    """Build the Telegram body, capped at ``TELEGRAM_MAX_CHARS``.

    The archive URL is always preserved (operator needs to click it); when the
    composed message overflows, the slug is truncated instead.
    """

    prefix = "**Checkpoint:** "
    slug_section = details.slug
    url_section = f"\nURL: {details.archive_url}"
    tail = "\nQueue paused — reply to resume."
    message = prefix + slug_section + url_section + tail
    if len(message) <= TELEGRAM_MAX_CHARS:
        return message
    overflow = len(message) - TELEGRAM_MAX_CHARS + 3  # "..."
    trimmed_slug = slug_section[: max(0, len(slug_section) - overflow)]
    return f"{prefix}{trimmed_slug}...{url_section}{tail}"


def write_pause_flag(
    flag_path: Path,
    details: CheckpointDetails,
    *,
    reason: str,
    actor: str,
    now: datetime | None = None,
) -> dict[str, object]:
    """Write the JSON pause flag and return its payload."""

    requested_at = (now or datetime.now(tz=UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    payload: dict[str, object] = {
        "active": True,
        "reason": reason,
        "actor": actor,
        "requested_at": requested_at,
        "checkpoint": details.to_flag_payload(),
        "release_hint": (
            "rm this file after Anthony confirms the checkpoint via Telegram"
        ),
    }
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    flag_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def send_checkpoint_notification(
    details: CheckpointDetails,
    *,
    send_message: SendMessageFn | None = None,
) -> dict[str, object]:
    """Send the Telegram checkpoint notification (Markdown, capped).

    ``send_message`` is resolved at call time so test monkeypatches on
    ``checkpoint_notify.telegram.send_message`` take effect.
    """

    body = compose_message(details)
    sender = send_message or telegram.send_message
    response = sender(body, parse_mode="Markdown")
    return {"text": body, "response": response}


def _load_upload_json(path: Path | str) -> dict[str, object]:
    """Read a JSON payload from a path (``-`` reads stdin)."""

    if str(path) == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"upload JSON is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("upload JSON must be an object")
    return data


def details_from_upload_json(payload: dict[str, object]) -> CheckpointDetails:
    """Build :class:`CheckpointDetails` from a session_archiver JSON payload."""

    checkpoint = payload.get("checkpoint")
    if not isinstance(checkpoint, dict):
        raise ValueError("upload JSON missing 'checkpoint' object")
    slug = checkpoint.get("slug")
    archive_url = checkpoint.get("audio_url") or checkpoint.get("archive_url")
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError("upload JSON 'checkpoint.slug' is required")
    if not isinstance(archive_url, str) or not archive_url.strip():
        raise ValueError("upload JSON 'checkpoint.audio_url' is required")
    metadata_url = checkpoint.get("metadata_url")
    sha256 = checkpoint.get("sha256")
    size_bytes_raw = checkpoint.get("size_bytes")
    timestamp = checkpoint.get("timestamp")
    return CheckpointDetails(
        slug=slug.strip(),
        archive_url=archive_url.strip(),
        metadata_url=metadata_url.strip() if isinstance(metadata_url, str) else None,
        sha256=sha256.strip() if isinstance(sha256, str) else None,
        size_bytes=int(size_bytes_raw)
        if isinstance(size_bytes_raw, int)
        or (isinstance(size_bytes_raw, str) and size_bytes_raw.isdigit())
        else None,
        timestamp=timestamp.strip() if isinstance(timestamp, str) else None,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send a Telegram checkpoint notification with the archive URL and "
            "pause the sdp-cli task queue pending Anthony's response."
        ),
    )
    parser.add_argument(
        "--from-upload-json",
        help=(
            "Path to the JSON payload emitted by `session_archiver.py "
            "--checkpoint-source ...`; use '-' to read from stdin."
        ),
    )
    parser.add_argument("--slug")
    parser.add_argument("--archive-url")
    parser.add_argument("--metadata-url")
    parser.add_argument("--sha256")
    parser.add_argument("--size-bytes", type=int)
    parser.add_argument("--timestamp")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--flag-path", type=Path)
    parser.add_argument("--reason", default=DEFAULT_REASON)
    parser.add_argument("--actor", default=DEFAULT_ACTOR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Skip writing the .sdp/CHECKPOINT_PAUSE flag.",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Skip the Telegram send (e.g. for replaying flag updates).",
    )
    return parser.parse_args(argv)


def _resolve_flag_path(args: argparse.Namespace) -> Path:
    if args.flag_path is not None:
        return args.flag_path
    return args.project_root / DEFAULT_FLAG_RELPATH


def _details_from_args(args: argparse.Namespace) -> CheckpointDetails:
    if args.from_upload_json:
        return details_from_upload_json(_load_upload_json(args.from_upload_json))
    if not args.slug or not args.archive_url:
        raise ValueError(
            "either --from-upload-json or both --slug and --archive-url are required"
        )
    return CheckpointDetails(
        slug=args.slug.strip(),
        archive_url=args.archive_url.strip(),
        metadata_url=(args.metadata_url or None),
        sha256=(args.sha256 or None),
        size_bytes=args.size_bytes,
        timestamp=(args.timestamp or None),
    )


def _print_json(payload: object, *, file: TextIO | None = None) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True), file=file or sys.stdout)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        details = _details_from_args(args)
    except ValueError as exc:
        _print_json({"ok": False, "error": str(exc)}, file=sys.stderr)
        return 2

    flag_path = _resolve_flag_path(args)
    composed = compose_message(details)
    result: dict[str, object] = {
        "ok": True,
        "checkpoint": details.to_flag_payload(),
        "telegram": {"text": composed, "sent": False},
        "pause": {"path": str(flag_path), "written": False},
    }

    if args.dry_run:
        result["dry_run"] = True
        _print_json(result)
        return 0

    if not args.no_telegram:
        try:
            sent = send_checkpoint_notification(details)
        except Exception as exc:  # noqa: BLE001 — surface any send failure
            _print_json({"ok": False, "error": str(exc)}, file=sys.stderr)
            return 1
        result["telegram"] = {"text": sent["text"], "sent": True, "response": sent["response"]}

    if not args.no_pause:
        payload = write_pause_flag(
            flag_path,
            details,
            reason=args.reason,
            actor=args.actor,
        )
        result["pause"] = {"path": str(flag_path), "written": True, "payload": payload}

    _print_json(result)
    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


__all__ = [
    "DEFAULT_FLAG_RELPATH",
    "TELEGRAM_MAX_CHARS",
    "CheckpointDetails",
    "compose_message",
    "details_from_upload_json",
    "parse_args",
    "run",
    "send_checkpoint_notification",
    "write_pause_flag",
]


if __name__ == "__main__":
    main()
