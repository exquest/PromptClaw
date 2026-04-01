#!/usr/bin/env python3
"""CypherClaw Telegram integration.

Send messages, files, and check for replies via the Telegram Bot API.

Usage:
    # Send a message
    python telegram.py send "Hello from CypherClaw"

    # Send a file
    python telegram.py file /path/to/report.md "Here's the report"

    # Check for new messages from Anthony
    python telegram.py check

    # Send markdown-formatted message
    python telegram.py send --md "**Deploy complete** ✅\n\nAll tests passing."
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error

# Track last seen update to avoid re-reading old messages
STATE_FILE = os.path.join(os.path.dirname(__file__), ".telegram_state.json")


def get_telegram_config() -> tuple[str, str]:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID environment variable is required")
    return bot_token, chat_id


def _api(method: str, data: dict | None = None, files: dict | None = None) -> dict:
    """Call Telegram Bot API."""
    bot_token, _ = get_telegram_config()
    api_base = f"https://api.telegram.org/bot{bot_token}"
    url = f"{api_base}/{method}"

    if files:
        # Multipart form upload
        import mimetypes
        boundary = "----CypherClawBoundary"
        parts: list[bytes] = []

        for key, val in (data or {}).items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{val}\r\n".encode()
            )

        for key, filepath in files.items():
            filename = os.path.basename(filepath)
            mime = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"{key}\"; filename=\"{filename}\"\r\n"
                    f"Content-Type: {mime}\r\n\r\n"
                ).encode()
            )
            with open(filepath, "rb") as f:
                parts.append(f.read())
            parts.append(b"\r\n")

        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(url, data=b"".join(parts))
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    else:
        payload = json.dumps(data or {}).encode()
        req = urllib.request.Request(url, data=payload)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())


def send_message(text: str, parse_mode: str | None = None) -> dict:
    """Send a text message."""
    _, chat_id = get_telegram_config()
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    return _api("sendMessage", data)


def send_file(filepath: str, caption: str = "") -> dict:
    """Send a file (document)."""
    _, chat_id = get_telegram_config()
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    return _api("sendDocument", data, files={"document": filepath})


def get_updates(offset: int | None = None) -> list[dict]:
    """Get new messages."""
    data: dict = {"timeout": 0}
    if offset is not None:
        data["offset"] = offset
    result = _api("getUpdates", data)
    return result.get("result", [])


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def check_messages() -> list[dict]:
    """Check for new messages from Anthony, advancing the offset."""
    _, chat_id = get_telegram_config()
    state = _load_state()
    offset = state.get("last_update_id")
    if offset is not None:
        offset += 1

    updates = get_updates(offset)
    messages = []
    for update in updates:
        msg = update.get("message", {})
        if msg.get("chat", {}).get("id") == int(chat_id):
            messages.append({
                "date": msg.get("date"),
                "text": msg.get("text", ""),
                "from": msg.get("from", {}).get("first_name", ""),
            })
        state["last_update_id"] = update["update_id"]

    _save_state(state)
    return messages


def main():
    parser = argparse.ArgumentParser(description="CypherClaw Telegram Bot")
    sub = parser.add_subparsers(dest="command", required=True)

    # send
    p_send = sub.add_parser("send", help="Send a text message")
    p_send.add_argument("text", help="Message text")
    p_send.add_argument("--md", action="store_true", help="Parse as Markdown")

    # file
    p_file = sub.add_parser("file", help="Send a file")
    p_file.add_argument("path", help="File path")
    p_file.add_argument("caption", nargs="?", default="", help="Caption")

    # check
    sub.add_parser("check", help="Check for new messages")

    args = parser.parse_args()

    if args.command == "send":
        mode = "Markdown" if args.md else None
        result = send_message(args.text, parse_mode=mode)
        if result.get("ok"):
            print("Sent.")
        else:
            print(f"Error: {result}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "file":
        if not os.path.isfile(args.path):
            print(f"File not found: {args.path}", file=sys.stderr)
            sys.exit(1)
        result = send_file(args.path, args.caption)
        if result.get("ok"):
            print(f"Sent: {os.path.basename(args.path)}")
        else:
            print(f"Error: {result}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "check":
        messages = check_messages()
        if not messages:
            print("No new messages.")
        else:
            for msg in messages:
                print(f"[{msg['from']}] {msg['text']}")


if __name__ == "__main__":
    main()
