# Task frac-0044 Specification: rewrite_hook depth 2

## Problem Statement

`rewrite_hook.py` at the project root is the one-shot script that ported the
SenseWeave hook schema from the old `hook_type` / `rhythm_cell` field names
to the current `hook_class` / `rhythm` names across `score_tree.py`,
`hook_engine.py`, `recursive_composer.py`, `generative_scores.py`, and
`repertoire_memory.py`.

The migration already landed and the senseweave modules are on the new shape,
so the script body is now a sequence of unconditional file reads and writes
with no functions. The fractal classifier scores it at depth 0 ("no
functions found"), which is the lowest band on the report and the reason
this task was generated.

This task deepens `rewrite_hook.py` to a simple depth-2 module: the canonical
hook field rename becomes a pure string-in / string-out function, file I/O
is wrapped in a single `migrate_file` helper that only writes when the
content actually changes, and one orchestrator walks the canonical target
list. The result is naturally idempotent — re-running on an already-migrated
tree is a clean no-op.

## Technical Approach

- Add a `HOOK_FIELD_RENAMES: tuple[tuple[str, str], ...]` table with the two
  canonical field-name pairs: `("hook_type", "hook_class")` and
  `("rhythm_cell", "rhythm")`. These are the only renames the original
  script depended on after stripping its non-idempotent regex injections.
- Add `HOOK_TARGET_FILES: tuple[str, ...]` listing the five canonical
  senseweave file paths (project-relative) the script wrote to.
- Add a frozen `HookRewriteResult` dataclass with `path: Path`,
  `existed: bool`, and `changed: bool`.
- Add `apply_field_renames(text: str) -> str` that loops over
  `HOOK_FIELD_RENAMES` and applies each rename via `str.replace`. Pure,
  idempotent (no occurrences left after the first pass).
- Add `migrate_file(path: Path) -> HookRewriteResult` that reads the file,
  runs the renames, writes back only when the produced text differs from
  the on-disk text, and reports whether the file existed and changed.
  Missing files report `existed=False` / `changed=False` without raising.
- Add `apply_hook_rewrites(root: Path) -> list[HookRewriteResult]` that
  walks `HOOK_TARGET_FILES` in declared order, calls `migrate_file`, and
  returns one result per target.
- Add `main(argv: list[str] | None = None) -> int` that runs
  `apply_hook_rewrites(Path('.'))`, prints one summary line per result, and
  returns `0`. Preserve the existing module entry point shape
  (`if __name__ == "__main__": main()`).
- Use only the standard library. No new dependencies, runtime state files,
  database columns, or migrations. All file I/O routes through `pathlib`.

## Edge Cases

- `apply_field_renames` on already-migrated text returns it unchanged.
- `migrate_file` on a missing path reports `existed=False` and does not
  raise.
- `migrate_file` on an already-migrated file reports `existed=True` /
  `changed=False` and does not write (file mtime is preserved).
- `apply_hook_rewrites` preserves the declared order of `HOOK_TARGET_FILES`
  so callers can correlate results to canonical file names.
- Re-running `main()` against an already-migrated tree exits 0 with no
  writes.

## Acceptance Criteria

1. `apply_field_renames` rewrites canonical pre-migration field names to the
   migrated names.
   VERIFY: `pytest tests/test_rewrite_hook_depth.py::test_apply_field_renames_rewrites_canonical_fields -q`

2. `apply_field_renames` is idempotent on already-migrated text.
   VERIFY: `pytest tests/test_rewrite_hook_depth.py::test_apply_field_renames_is_idempotent -q`

3. `migrate_file` writes the migrated content for a pre-migration file and
   reports `existed=True` / `changed=True`.
   VERIFY: `pytest tests/test_rewrite_hook_depth.py::test_migrate_file_writes_pre_migration_file -q`

4. `migrate_file` reports `existed=True` / `changed=False` on an
   already-migrated file and does not modify it.
   VERIFY: `pytest tests/test_rewrite_hook_depth.py::test_migrate_file_is_no_op_on_migrated_file -q`

5. `migrate_file` reports `existed=False` / `changed=False` on a missing
   file without raising.
   VERIFY: `pytest tests/test_rewrite_hook_depth.py::test_migrate_file_handles_missing_file -q`

6. `apply_hook_rewrites` returns one result per `HOOK_TARGET_FILES` entry in
   declared order and migrates a pre-migration tree end-to-end.
   VERIFY: `pytest tests/test_rewrite_hook_depth.py::test_apply_hook_rewrites_migrates_tree_in_declared_order -q`

7. `apply_hook_rewrites` is idempotent on an already-migrated tree.
   VERIFY: `pytest tests/test_rewrite_hook_depth.py::test_apply_hook_rewrites_is_idempotent_on_migrated_tree -q`

8. Fractal depth for `rewrite_hook.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_rewrite_hook_depth.py::test_rewrite_hook_module_reaches_depth_two -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
