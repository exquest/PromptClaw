# Task frac-0005 Specification: Archive Paths Depth 2

## Problem Statement

`my-claw/tools/archive_paths.py` centralizes the storage-root contract for
large CypherClaw artifacts, but the fractal scanner still classifies it at
depth 1 because five of six functions are direct path projections. Existing
callers already use the module for archive daemon output, sample-event renders,
camera capture rings, and Litestream backups. The module needs a simple
depth-2 layer that resolves the complete archive layout, returns meaningful
operator output, and can prepare the directories needed for an end-to-end run
without changing the current resolver API.

## Technical Approach

Extend `archive_paths.py` in place with a small typed layout surface:

- `ArchivePathLayout` dataclass with the selected storage root, source label,
  archive recordings root, sample-event directory, camera root, named camera
  capture directories, and Litestream backup root.
- `resolve_archive_layout(anchor, ...)` that reuses the existing root-selection
  order (`CYPHERCLAW_ARCHIVE_ROOT`, writable archive mount, writable legacy
  storage root, project-local fallback) and derives all standard paths from the
  selected root.
- `archive_layout_summary(layout)` that returns a stable string dictionary for
  logs, diagnostics, and tests.
- `prepare_archive_layout(anchor, ...)` that resolves the layout and creates
  the standard directories in one straightforward path.

Existing functions (`resolve_archive_storage_root`,
`resolve_archive_recordings_root`, `resolve_sample_events_dir`,
`resolve_camera_capture_dir`, and `resolve_litestream_backup_root`) remain
available and keep returning the same paths.

## Edge Cases

- Env root remains the highest-priority override and does not need to exist
  before resolution.
- A writable archive mount resolves to `<mount>/cypherclaw`.
- A writable legacy root is used only when no env root or writable mount is
  available.
- Project-local fallback still resolves beneath
  `<runtime-root>/.promptclaw/archive-storage`.
- Custom camera names derive `<name>_captures` directories under `camera/`.
- No database migration is required; this is filesystem path logic only.
- No new dependency is required; the implementation is stdlib-only.
- Startup identity hardening remains a regression anchor. Existing tests cover
  `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`
  for standalone and federated startup paths.

## Acceptance Criteria

1. Archive layout resolution returns meaningful standard paths and source
   metadata from the existing storage-root priority order.
   VERIFY: `pytest tests/test_archive_paths.py::test_archive_layout_reports_all_standard_paths_and_source -q`

2. Archive layout summaries expose stable operator-readable output.
   VERIFY: `pytest tests/test_archive_paths.py::test_archive_layout_summary_contains_meaningful_operator_output -q`

3. Preparing an archive layout creates the standard end-to-end directories,
   including named camera capture directories.
   VERIFY: `pytest tests/test_archive_paths.py::test_prepare_archive_layout_creates_end_to_end_directories -q`

4. Existing derived resolver functions remain compatible with the new layout
   surface.
   VERIFY: `pytest tests/test_archive_paths.py::test_existing_derived_resolvers_match_layout -q`

5. Fractal depth for `my-claw/tools/archive_paths.py` reaches at least depth 2.
   VERIFY: `python - <<'PY'
import sys
sys.path.insert(0, "/Users/anthony/Programming/sdp-cli/src")
from sdp.fractal import classify_depth
result = classify_depth("my-claw/tools/archive_paths.py")
print(result.depth, result.reason)
assert result.depth >= 2
PY`

6. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
