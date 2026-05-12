"""Hook schema rewriter — depth-2 module surface for frac-0044.

Originally a one-shot script that ported SenseWeave's hook schema from
``hook_type`` / ``rhythm_cell`` field names to ``hook_class`` / ``rhythm``.
The migration has landed; these helpers preserve the canonical field rename
as an idempotent module so callers can re-apply it safely.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

HOOK_FIELD_RENAMES: tuple[tuple[str, str], ...] = (
    ("hook_type", "hook_class"),
    ("rhythm_cell", "rhythm"),
)

HOOK_TARGET_FILES: tuple[str, ...] = (
    "my-claw/tools/senseweave/score_tree.py",
    "my-claw/tools/senseweave/hook_engine.py",
    "my-claw/tools/senseweave/recursive_composer.py",
    "my-claw/tools/senseweave/generative_scores.py",
    "my-claw/tools/senseweave/repertoire_memory.py",
)


@dataclass(frozen=True, slots=True)
class HookRewriteResult:
    path: Path
    existed: bool
    changed: bool


def apply_field_renames(text: str) -> str:
    rewritten = text
    for old, new in HOOK_FIELD_RENAMES:
        rewritten = rewritten.replace(old, new)
    return rewritten


def migrate_file(path: Path) -> HookRewriteResult:
    if not path.is_file():
        return HookRewriteResult(path=path, existed=False, changed=False)

    original = path.read_text(encoding="utf-8")
    rewritten = apply_field_renames(original)
    if rewritten == original:
        return HookRewriteResult(path=path, existed=True, changed=False)

    path.write_text(rewritten, encoding="utf-8")
    return HookRewriteResult(path=path, existed=True, changed=True)


def apply_hook_rewrites(root: Path) -> list[HookRewriteResult]:
    results: list[HookRewriteResult] = []
    for relative in HOOK_TARGET_FILES:
        results.append(migrate_file(root / relative))
    return results


def main(argv: list[str] | None = None) -> int:
    del argv
    results = apply_hook_rewrites(Path("."))
    for result in results:
        if not result.existed:
            status = "missing"
        elif result.changed:
            status = "rewrote"
        else:
            status = "unchanged"
        print(f"{status}: {result.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
