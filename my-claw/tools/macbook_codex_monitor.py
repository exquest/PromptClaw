#!/usr/bin/env python3
"""Persistent MacBook Codex monitor for the CypherClaw event stream."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = PROJECT_ROOT / ".promptclaw" / "macbook_codex_monitor_state.json"
LOG_FILE = PROJECT_ROOT / ".promptclaw" / "macbook_codex_monitor.log"
DEFAULT_INTERVAL_SECONDS = 90
MAX_SEEN_FINGERPRINTS = 200

REMOTE_HOST = "cypherclaw"
REMOTE_EVENT_STREAM = "/run/cypherclaw-tmp/event_stream.jsonl"
REMOTE_INBOX = "/run/cypherclaw-tmp/inbox.jsonl"

DIRECT_MENTION_MARKERS = ("@codex", "macbook codex", "codex ")
ACTIONABLE_MARKERS = (
    "timed out",
    "timeout",
    "spam",
    "failed",
    "error",
    "fix this",
    "want me to fix this",
)


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return {"last_seen_ts": 0.0, "seen_fingerprints": []}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def _fingerprint(event: dict[str, Any]) -> str:
    event_type = str(event.get("type", "")).strip()
    text = str(event.get("text", "")).strip().replace("\n", " ")
    return f"{event_type}:{text[:120]}"


def _is_direct_mention(text: str) -> bool:
    lowered = text.strip().lower()
    return any(marker in lowered for marker in DIRECT_MENTION_MARKERS)


def _is_actionable_issue(text: str) -> bool:
    lowered = text.strip().lower()
    return any(marker in lowered for marker in ACTIONABLE_MARKERS)


def _format_excerpt(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit - 3].rstrip()}..."


def build_inbox_messages(events: list[dict[str, Any]], state: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    seen_fingerprints = list(state.get("seen_fingerprints", []))
    seen_lookup = set(seen_fingerprints)
    messages: list[str] = []
    last_seen_ts = float(state.get("last_seen_ts", 0.0))

    for event in sorted(events, key=lambda item: float(item.get("ts", 0.0))):
        event_ts = float(event.get("ts", 0.0))
        last_seen_ts = max(last_seen_ts, event_ts)
        text = str(event.get("text", "")).strip()
        if not text:
            continue

        fingerprint = _fingerprint(event)
        if fingerprint in seen_lookup:
            continue

        event_type = str(event.get("type", "")).strip()
        if event_type in {"user_message", "chat_anthony"} and _is_direct_mention(text):
            messages.append(f"Direct Telegram mention for Codex: {_format_excerpt(text)}")
            seen_lookup.add(fingerprint)
            seen_fingerprints.append(fingerprint)
            continue

        if event_type in {"chat_cypherclaw", "claw_reply"} and _is_actionable_issue(text):
            messages.append(f"Actionable Telegram issue observed: {_format_excerpt(text)}")
            seen_lookup.add(fingerprint)
            seen_fingerprints.append(fingerprint)

    next_state = {
        "last_seen_ts": last_seen_ts,
        "seen_fingerprints": seen_fingerprints[-MAX_SEEN_FINGERPRINTS:],
    }
    return messages, next_state


def fetch_recent_events(
    *,
    host: str,
    remote_path: str,
    since_ts: float,
) -> list[dict[str, Any]]:
    remote_script = f"""
import json
from pathlib import Path

since_ts = {since_ts!r}
path = Path({remote_path!r})
events = []
if path.exists():
    for raw_line in path.read_text().splitlines():
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        event_ts = float(event.get("ts", 0.0) or 0.0)
        if event_ts > since_ts:
            events.append(event)
print(json.dumps(events))
"""
    result = subprocess.run(
        ["ssh", host, "python3", "-c", remote_script],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = result.stdout.strip() or "[]"
    data = json.loads(payload)
    return data if isinstance(data, list) else []


def send_inbox_message(*, host: str, remote_inbox: str, text: str) -> None:
    remote_script = f"""
import json
import time

message = {{
    "type": "inbox",
    "from": "macbook_codex",
    "text": {text!r},
    "ts": time.time(),
}}
with open({remote_inbox!r}, "a") as handle:
    handle.write(json.dumps(message) + "\\n")
"""
    subprocess.run(
        ["ssh", host, "python3", "-c", remote_script],
        capture_output=True,
        text=True,
        check=True,
    )


def run_once(
    *,
    host: str,
    remote_event_stream: str,
    remote_inbox: str,
    state_file: Path,
    dry_run: bool = False,
) -> int:
    state = load_state(state_file)
    events = fetch_recent_events(
        host=host,
        remote_path=remote_event_stream,
        since_ts=float(state.get("last_seen_ts", 0.0)),
    )
    messages, next_state = build_inbox_messages(events, state)
    for message in messages:
        logging.info("sending inbox message: %s", message)
        if not dry_run:
            send_inbox_message(host=host, remote_inbox=remote_inbox, text=message)
    save_state(state_file, next_state)
    return len(messages)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MacBook Codex event-stream monitor")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS, help="Polling interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run one polling cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Compute reactions without sending inbox messages")
    parser.add_argument("--host", default=REMOTE_HOST, help="SSH host for the CypherClaw server")
    parser.add_argument("--event-stream", default=REMOTE_EVENT_STREAM, help="Remote event stream path")
    parser.add_argument("--inbox", default=REMOTE_INBOX, help="Remote inbox path")
    parser.add_argument("--state-file", type=Path, default=STATE_FILE, help="Local state file path")
    parser.add_argument("--log-file", type=Path, default=LOG_FILE, help="Local log file path")
    return parser.parse_args()


def configure_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )


def main() -> int:
    args = parse_args()
    configure_logging(args.log_file)
    logging.info("MacBook Codex monitor starting (interval=%ss)", args.interval)

    while True:
        try:
            sent_count = run_once(
                host=args.host,
                remote_event_stream=args.event_stream,
                remote_inbox=args.inbox,
                state_file=args.state_file,
                dry_run=args.dry_run,
            )
            logging.info("monitor cycle complete (%s messages)", sent_count)
        except Exception:
            logging.exception("monitor cycle failed")

        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
