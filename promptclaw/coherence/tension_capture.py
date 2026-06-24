"""Tension auto-capture — parse ```tension fenced blocks an agent declares in its output.

Parallel to decision_capture: agents declare a held contradiction explicitly, and the engine
records it as an open tension (surfaced, not blocked):

    ```tension
    statement: Operational simplicity vs. horizontal scale
    state: open — leaning simple while concurrency stays < 20
    resolves: a load test that exceeds 20 concurrent users
    between: dec-001, T-042
    ```

A block without a ``statement`` is skipped. ``between`` is comma-separated refs.
See docs/Shadowland2/promptclaw-integration-proposal.md (P1).
"""

from __future__ import annotations

from typing import Any

from ._blocks import parse_fenced_blocks

_SCALAR_KEYS = {
    "statement": "statement",
    "tension": "statement",
    "state": "dialectic_state",
    "dialectic": "dialectic_state",
    "resolves": "resolution_criterion",
    "resolution": "resolution_criterion",
}
_LIST_COMMA_KEYS = {"between": "between"}
_LIST_SEMI_KEYS: dict[str, str] = {}


def parse_tension_blocks(text: str) -> list[dict[str, Any]]:
    """Extract declared tensions from ```tension fenced blocks (statement required)."""
    blocks: list[dict[str, Any]] = []
    for fields in parse_fenced_blocks(
        text,
        label="tension",
        scalar_keys=_SCALAR_KEYS,
        comma_keys=_LIST_COMMA_KEYS,
        semi_keys=_LIST_SEMI_KEYS,
    ):
        if not fields["statement"]:
            continue
        blocks.append(fields)
    return blocks
