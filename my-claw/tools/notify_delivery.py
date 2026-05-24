"""Notify delivery of a live reference capture via Telegram."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add the directory containing telegram.py to the path
sys.path.insert(0, str(Path(__file__).parent))

import telegram


def send_delivery_notification(public_url: str, capture_path: str) -> dict:
    """Send the Telegram notification for a successful capture."""
    message = (
        f"**Live Capture Delivered** ✅\n\n"
        f"Public Page: {public_url}\n"
        f"Capture Path: {capture_path}"
    )
    if len(message) > 300:
        # truncate safely
        message = message[:297] + "..."
    return telegram.send_message(message, parse_mode="Markdown")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notify delivery of a live capture")
    parser.add_argument("--public-url", required=True, help="The public page URL")
    parser.add_argument("--capture-path", required=True, help="The path to the capture artifact")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = send_delivery_notification(args.public_url, args.capture_path)
        if result.get("ok"):
            print("Notification sent successfully.")
            return 0
        else:
            print(f"Failed to send notification: {result}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
