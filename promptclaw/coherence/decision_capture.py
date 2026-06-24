"""Decision auto-capture — parse ```decision fenced blocks an agent declares in its output.

The coherence engine's decision store stays empty unless something records decisions. Rather
than auto-recording every routing/lead action (which would pollute the "DO NOT VIOLATE" injection
block), agents declare a decision explicitly in a fenced block, and the engine captures it:

    ```decision
    title: Use Redis vector sets instead of ChromaDB
    what: Store embeddings in Redis vector sets.
    context: We need sub-ms similarity search.
    rationale: Already running Redis; one fewer dependency.
    unlocks: semantic decision search; retrieval cache
    constrains: must keep Redis >= 7.2; embeddings stay <= 1536d
    files: src/store.py, src/config.py
    tags: storage, embeddings
    ```

Separators: ``unlocks``/``constrains`` split on ``;`` (a phrase may contain commas without
fragmenting); ``files``/``tags`` split on ``,``. A block without a ``title`` is skipped;
``decision_text`` defaults to ``title``. See docs/Shadowland2/promptclaw-integration-proposal.md (P2).
"""

from __future__ import annotations

from typing import Any

from ._blocks import parse_fenced_blocks

# Key aliases → canonical Decision kwarg.
_SCALAR_KEYS = {
    "title": "title",
    "what": "decision_text",
    "decision": "decision_text",
    "context": "context",
    "why": "context",
    "rationale": "rationale",
    "because": "rationale",
}
# Token list fields → comma-separated.
_LIST_COMMA_KEYS = {"files": "file_paths", "affects": "file_paths", "tags": "tags"}
# Phrase list fields (may contain commas) → semicolon-separated.
_LIST_SEMI_KEYS = {"unlocks": "unlocks", "constrains": "constrains", "constrain": "constrains"}


def parse_decision_blocks(text: str) -> list[dict[str, Any]]:
    """Extract declared decisions from ```decision fenced blocks.

    Returns dicts whose keys match ``CoherenceEngine.record_decision`` kwargs. A block
    without a ``title`` is skipped; ``decision_text`` defaults to ``title``.
    """
    blocks: list[dict[str, Any]] = []
    for fields in parse_fenced_blocks(
        text,
        label="decision",
        scalar_keys=_SCALAR_KEYS,
        comma_keys=_LIST_COMMA_KEYS,
        semi_keys=_LIST_SEMI_KEYS,
    ):
        if not fields["title"]:
            continue
        if not fields["decision_text"]:
            fields["decision_text"] = fields["title"]
        blocks.append(fields)
    return blocks
