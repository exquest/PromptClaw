"""Tests for the MacBook Codex event-stream monitor."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "my-claw" / "tools"))

from macbook_codex_monitor import build_inbox_messages


def test_direct_codex_mention_generates_inbox_message() -> None:
    events = [
        {"type": "user_message", "text": "@codex can you inspect this timeout?", "ts": 10.0},
    ]
    state = {"last_seen_ts": 0.0, "seen_fingerprints": []}

    messages, next_state = build_inbox_messages(events, state)

    assert len(messages) == 1
    assert "Direct Telegram mention" in messages[0]
    assert next_state["last_seen_ts"] == 10.0
    assert len(next_state["seen_fingerprints"]) == 1


def test_actionable_cypherclaw_error_generates_inbox_message() -> None:
    events = [
        {
            "type": "chat_cypherclaw",
            "text": "Found it: sdp-cli timed out again. Want me to fix this?",
            "ts": 20.0,
        },
    ]
    state = {"last_seen_ts": 0.0, "seen_fingerprints": []}

    messages, next_state = build_inbox_messages(events, state)

    assert len(messages) == 1
    assert "Actionable Telegram issue" in messages[0]
    assert next_state["last_seen_ts"] == 20.0


def test_duplicate_event_fingerprint_is_not_resent() -> None:
    events = [
        {"type": "user_message", "text": "@codex please verify this patch", "ts": 30.0},
    ]
    state = {
        "last_seen_ts": 0.0,
        "seen_fingerprints": ["user_message:@codex please verify this patch"],
    }

    messages, next_state = build_inbox_messages(events, state)

    assert messages == []
    assert next_state["last_seen_ts"] == 30.0
    assert next_state["seen_fingerprints"] == ["user_message:@codex please verify this patch"]


def test_irrelevant_events_are_ignored() -> None:
    events = [
        {"type": "chat_cypherclaw", "text": "Here is the PRD summary.", "ts": 40.0},
        {"type": "user_message", "text": "thanks", "ts": 41.0},
    ]
    state = {"last_seen_ts": 0.0, "seen_fingerprints": []}

    messages, next_state = build_inbox_messages(events, state)

    assert messages == []
    assert next_state["last_seen_ts"] == 41.0
