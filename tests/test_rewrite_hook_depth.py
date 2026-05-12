"""Depth-2 tests for rewrite_hook [frac-0044]."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rewrite_hook import (  # noqa: E402
    HOOK_FIELD_RENAMES,
    HOOK_TARGET_FILES,
    HookRewriteResult,
    apply_field_renames,
    apply_hook_rewrites,
    migrate_file,
)


REWRITE_HOOK_MODULE_PATH = REPO_ROOT / "rewrite_hook.py"


PRE_TEXT = (
    "@dataclass\n"
    "class HookRow:\n"
    "    hook_type: str\n"
    "    rhythm_cell: tuple[float, ...]\n"
    "\n"
    "row = HookRow(hook_type='lyric', rhythm_cell=(1.0, 1.0))\n"
)

POST_TEXT = (
    "@dataclass\n"
    "class HookRow:\n"
    "    hook_class: str\n"
    "    rhythm: tuple[float, ...]\n"
    "\n"
    "row = HookRow(hook_class='lyric', rhythm=(1.0, 1.0))\n"
)


def test_apply_field_renames_rewrites_canonical_fields() -> None:
    assert apply_field_renames(PRE_TEXT) == POST_TEXT


def test_apply_field_renames_is_idempotent() -> None:
    once = apply_field_renames(PRE_TEXT)
    twice = apply_field_renames(once)

    assert once == twice == POST_TEXT


def test_migrate_file_writes_pre_migration_file(tmp_path: Path) -> None:
    target = tmp_path / "score_tree.py"
    target.write_text(PRE_TEXT, encoding="utf-8")

    result = migrate_file(target)

    assert isinstance(result, HookRewriteResult)
    assert result.path == target
    assert result.existed is True
    assert result.changed is True
    assert target.read_text(encoding="utf-8") == POST_TEXT


def test_migrate_file_is_no_op_on_migrated_file(tmp_path: Path) -> None:
    target = tmp_path / "score_tree.py"
    target.write_text(POST_TEXT, encoding="utf-8")
    original_mtime = target.stat().st_mtime_ns

    result = migrate_file(target)

    assert result.existed is True
    assert result.changed is False
    assert target.read_text(encoding="utf-8") == POST_TEXT
    assert target.stat().st_mtime_ns == original_mtime


def test_migrate_file_handles_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.py"

    result = migrate_file(missing)

    assert result.existed is False
    assert result.changed is False
    assert not missing.exists()


def test_apply_hook_rewrites_migrates_tree_in_declared_order(tmp_path: Path) -> None:
    for relative in HOOK_TARGET_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PRE_TEXT, encoding="utf-8")

    results = apply_hook_rewrites(tmp_path)

    assert [r.path for r in results] == [tmp_path / rel for rel in HOOK_TARGET_FILES]
    assert all(r.existed and r.changed for r in results)
    for relative in HOOK_TARGET_FILES:
        assert (tmp_path / relative).read_text(encoding="utf-8") == POST_TEXT


def test_apply_hook_rewrites_is_idempotent_on_migrated_tree(tmp_path: Path) -> None:
    for relative in HOOK_TARGET_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(POST_TEXT, encoding="utf-8")

    results = apply_hook_rewrites(tmp_path)

    assert all(r.existed for r in results)
    assert not any(r.changed for r in results)
    for relative in HOOK_TARGET_FILES:
        assert (tmp_path / relative).read_text(encoding="utf-8") == POST_TEXT


def test_hook_field_renames_table_is_canonical() -> None:
    assert ("hook_type", "hook_class") in HOOK_FIELD_RENAMES
    assert ("rhythm_cell", "rhythm") in HOOK_FIELD_RENAMES


def test_rewrite_hook_module_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(REWRITE_HOOK_MODULE_PATH)

    assert result.depth >= 2, result.reason
