"""Record a checkpoint decision and resume the sdp-cli task queue.

T-056c writes a ``.sdp/CHECKPOINT_PAUSE`` flag whose presence signals "do
not advance past this checkpoint". This tool is the other side of that
loop: it accepts an ``APPROVE``, ``REWORK``, or ``REJECT`` decision,
appends a JSONL audit entry, removes the pause flag (so sdp-cli resumes
new task pickup), and optionally sends a Telegram acknowledgement.

All three decisions clear the flag — the differentiating record is what
Lead sees in the decisions log so it can route the next action (proceed,
re-attempt, or abandon).
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
from checkpoint_notify import DEFAULT_FLAG_RELPATH, TELEGRAM_MAX_CHARS  # noqa: E402

DEFAULT_DECISIONS_RELPATH = Path(".sdp/CHECKPOINT_DECISIONS.jsonl")
DEFAULT_ACTOR = "checkpoint_approve"
DECISIONS = ("APPROVE", "REWORK", "REJECT")

SendMessageFn = Callable[..., dict]


@dataclass(frozen=True)
class ApprovalRecord:
    """The persisted shape of one APPROVE/REWORK/REJECT decision."""

    decision: str
    actor: str
    decided_at: str
    note: str | None
    checkpoint: dict[str, object]

    def to_jsonl_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "decision": self.decision,
            "actor": self.actor,
            "decided_at": self.decided_at,
            "checkpoint": self.checkpoint,
        }
        if self.note:
            payload["note"] = self.note
        return payload


def _utcnow_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(tz=UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")


def read_pause_flag(flag_path: Path) -> dict[str, object]:
    """Load the JSON pause flag written by ``checkpoint_notify``."""

    if not flag_path.exists():
        raise FileNotFoundError(f"no pause flag at {flag_path}")
    try:
        data = json.loads(flag_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"pause flag is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("pause flag must be a JSON object")
    return data


def append_decision(
    decisions_path: Path,
    record: ApprovalRecord,
) -> dict[str, object]:
    """Append a JSON-line decision record and return its payload."""

    payload = record.to_jsonl_payload()
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    with decisions_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return payload


def compose_ack_message(record: ApprovalRecord) -> str:
    """Compose a Telegram acknowledgement, capped at ``TELEGRAM_MAX_CHARS``."""

    slug = str(record.checkpoint.get("slug") or "<unknown>")
    prefix = f"**Checkpoint {record.decision}:** "
    tail = "\nQueue resumed."
    note_section = f"\nNote: {record.note}" if record.note else ""
    message = prefix + slug + note_section + tail
    if len(message) <= TELEGRAM_MAX_CHARS:
        return message
    overflow = len(message) - TELEGRAM_MAX_CHARS + 3  # "..."
    if note_section:
        trimmed_note = note_section[: max(0, len(note_section) - overflow)]
        return f"{prefix}{slug}{trimmed_note}...{tail}"
    trimmed_slug = slug[: max(0, len(slug) - overflow)]
    return f"{prefix}{trimmed_slug}...{tail}"


def send_ack(
    record: ApprovalRecord,
    *,
    send_message: SendMessageFn | None = None,
) -> dict[str, object]:
    """Send the Telegram acknowledgement (Markdown, capped)."""

    body = compose_ack_message(record)
    sender = send_message or telegram.send_message
    response = sender(body, parse_mode="Markdown")
    return {"text": body, "response": response}


def approve_checkpoint(
    *,
    decision: str,
    flag_path: Path,
    decisions_path: Path,
    actor: str,
    note: str | None,
    now: datetime | None = None,
) -> ApprovalRecord:
    """Record the decision, then remove the pause flag to resume the queue."""

    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")
    flag_payload = read_pause_flag(flag_path)
    checkpoint = flag_payload.get("checkpoint")
    if not isinstance(checkpoint, dict):
        checkpoint = {}
    record = ApprovalRecord(
        decision=decision,
        actor=actor,
        decided_at=_utcnow_iso(now),
        note=note,
        checkpoint=checkpoint,
    )
    append_decision(decisions_path, record)
    flag_path.unlink()
    return record


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record APPROVE/REWORK/REJECT on the active checkpoint and clear "
            "the .sdp/CHECKPOINT_PAUSE flag so sdp-cli resumes task pickup."
        ),
    )
    parser.add_argument("decision", choices=list(DECISIONS))
    parser.add_argument("--actor", default=DEFAULT_ACTOR)
    parser.add_argument("--note")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--flag-path", type=Path)
    parser.add_argument("--decisions-path", type=Path)
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Skip the Telegram acknowledgement.",
    )
    return parser.parse_args(argv)


def _resolve_flag_path(args: argparse.Namespace) -> Path:
    return args.flag_path or (args.project_root / DEFAULT_FLAG_RELPATH)


def _resolve_decisions_path(args: argparse.Namespace) -> Path:
    return args.decisions_path or (args.project_root / DEFAULT_DECISIONS_RELPATH)


def _print_json(payload: object, *, file: TextIO | None = None) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True), file=file or sys.stdout)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    flag_path = _resolve_flag_path(args)
    decisions_path = _resolve_decisions_path(args)

    try:
        record = approve_checkpoint(
            decision=args.decision,
            flag_path=flag_path,
            decisions_path=decisions_path,
            actor=args.actor,
            note=args.note,
        )
    except FileNotFoundError as exc:
        _print_json({"ok": False, "error": str(exc)}, file=sys.stderr)
        return 2
    except ValueError as exc:
        _print_json({"ok": False, "error": str(exc)}, file=sys.stderr)
        return 2

    result: dict[str, object] = {
        "ok": True,
        "decision": record.decision,
        "actor": record.actor,
        "decided_at": record.decided_at,
        "checkpoint": record.checkpoint,
        "flag_cleared": str(flag_path),
        "decisions_log": str(decisions_path),
        "telegram": {"sent": False},
    }
    if record.note:
        result["note"] = record.note

    if not args.no_telegram:
        try:
            sent = send_ack(record)
        except Exception as exc:  # noqa: BLE001 — surface send failures
            result["telegram"] = {"sent": False, "error": str(exc)}
            _print_json(result)
            return 1
        result["telegram"] = {"sent": True, "text": sent["text"], "response": sent["response"]}

    _print_json(result)
    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


__all__ = [
    "DECISIONS",
    "DEFAULT_DECISIONS_RELPATH",
    "ApprovalRecord",
    "append_decision",
    "approve_checkpoint",
    "compose_ack_message",
    "parse_args",
    "read_pause_flag",
    "run",
    "send_ack",
]


if __name__ == "__main__":
    main()
