"""Shared parser for ```<label> fenced key:value blocks (decisions, tensions, ...).

Both decision auto-capture and tension auto-capture declare structured blocks an agent
emits in its output. The fence-finding and key:value parsing are identical; only the label,
the recognized keys, and the required/default rules differ. Those domain rules live in the
caller (decision_capture, tension_capture); the mechanics live here.

Separators: ``comma_keys`` split on ``,`` (tokens like file paths/tags); ``semi_keys`` split on
``;`` (phrases that may themselves contain commas). Any list key may be repeated on multiple
lines and the items accumulate. Both fences must sit at the start of a line, so an inline
triple-backtick in a value does not close the block early.
"""

from __future__ import annotations

import re
from typing import Any


def fence_regex(label: str) -> re.Pattern[str]:
    """Compile the anchored fence regex for ```<label> ... ``` blocks."""
    return re.compile(
        r"^[ \t]*```[ \t]*" + re.escape(label) + r"[ \t]*\n(.*?)^[ \t]*```",
        re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )


def parse_fenced_blocks(
    text: str,
    *,
    label: str,
    scalar_keys: dict[str, str],
    comma_keys: dict[str, str],
    semi_keys: dict[str, str],
) -> list[dict[str, Any]]:
    """Parse every ```<label> block into a dict of canonical fields.

    Each returned dict has every canonical scalar key (default "") and every canonical
    list key (default []). Domain rules (required keys, cross-field defaults) are applied
    by the caller.
    """
    scalar_canon = set(scalar_keys.values())
    list_canon = set(comma_keys.values()) | set(semi_keys.values())

    blocks: list[dict[str, Any]] = []
    for match in fence_regex(label).finditer(text or ""):
        fields: dict[str, Any] = {k: "" for k in scalar_canon}
        for k in list_canon:
            fields[k] = []
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            raw_key, raw_val = line.split(":", 1)
            key = raw_key.strip().lower()
            val = raw_val.strip()
            if key in scalar_keys:
                fields[scalar_keys[key]] = val
            elif key in comma_keys:
                fields[comma_keys[key]].extend(_split(val, ","))
            elif key in semi_keys:
                fields[semi_keys[key]].extend(_split(val, ";"))
        blocks.append(fields)
    return blocks


def _split(value: str, sep: str) -> list[str]:
    return [item.strip() for item in value.split(sep) if item.strip()]
