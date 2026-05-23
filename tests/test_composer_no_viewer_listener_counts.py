"""CC-027 negative-assertion: composer source contains no viewer/listener-count consumers.

Per cypherclaw v2 PRD requirement CC-027 and the directive at line 198 of
`sdp/prd-cypherclaw-v2-2026-05-22.md`:

    "Listener count is not surfaced to the composer under any conditions,
     per CypherClaw's directive."

This test grep-scans the composer source tree for known count-consumer
patterns and asserts zero matches.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

COMPOSER_SOURCES: tuple[Path, ...] = (
    REPO_ROOT / "my-claw" / "tools" / "duet_composer.py",
    REPO_ROOT / "src" / "cypherclaw" / "composer_vocabulary_bridge.py",
)

FORBIDDEN_PATTERNS: tuple[str, ...] = (
    r"\bviewer_count\b",
    r"\bviewer_counts\b",
    r"\bview_count\b",
    r"\bnum_viewers\b",
    r"\bn_viewers\b",
    r"\blive_viewers\b",
    r"\bstream_viewers\b",
    r"\bviewers_total\b",
    r"\btotal_viewers\b",
    r"\bcurrent_viewers\b",
    r"\bviewers\b",
    r"\blistener_count\b",
    r"\blistener_counts\b",
    r"\bnum_listeners\b",
    r"\bn_listeners\b",
    r"\blive_listeners\b",
    r"\bhls_listeners\b",
    r"\blisteners_total\b",
    r"\btotal_listeners\b",
    r"\bcurrent_listeners\b",
    r"\baudience_count\b",
    r"\baudience_size\b",
    r"\baudience_total\b",
    r"\bnum_audience\b",
    r"\bpopularity\b",
)


def test_composer_sources_exist() -> None:
    """Guard: if the composer tree moves, the assertion below silently passes."""
    for path in COMPOSER_SOURCES:
        assert path.is_file(), f"composer source not found: {path}"


def test_composer_has_no_viewer_or_listener_count_consumers() -> None:
    compiled = [(pat, re.compile(pat)) for pat in FORBIDDEN_PATTERNS]
    findings: list[str] = []
    for path in COMPOSER_SOURCES:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat, regex in compiled:
                if regex.search(line):
                    findings.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno}: matches {pat!r}: {line.strip()}"
                    )
    assert not findings, (
        "CC-027 violation — composer code must not consume viewer/listener counts:\n"
        + "\n".join(findings)
    )
