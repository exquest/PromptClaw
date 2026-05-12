# Task frac-0043 Specification: PromptClaw Artifacts Run Report

## Problem Statement

`promptclaw/artifacts.py` owns the run artifact transport: task input, routing
metadata, prompts, outputs, handoffs, summaries, state, and JSONL events under
`.promptclaw/runs/<run-id>/`. The module now has a basic event read path from
the earlier artifact depth slice, but it still lacks one meaningful operator
summary that tells a caller which run artifacts exist, which expected files are
missing, and what event log content has been recorded.

This task deepens the artifact surface with the simplest end-to-end report path:
one typed file status, one typed run report, and one `ArtifactManager` method
that builds the report from the canonical path layout and existing event log.
No runtime format changes are required.

## Technical Approach

- Add an `ArtifactFileStatus` dataclass with `name`, `path`, `exists`, and
  `size_bytes` fields plus an `as_dict()` method that serializes the path as a
  string.
- Add an `ArtifactRunReport` dataclass with `run_id`, `root`, `files`,
  `event_count`, and `latest_event_type` fields plus an `as_dict()` method that
  emits JSON-safe output and derives `present_count`, `missing_count`, and
  `missing_files`.
- Add `ArtifactManager.build_run_report(self) -> ArtifactRunReport` that:
  - uses `self.paths.run_layout(self.run_id)` for canonical expected files,
  - checks each expected file with `Path.exists()` and `Path.stat()`,
  - uses existing `read_events()` for event count and latest event type.
- Preserve all existing write method signatures and on-disk file names.
- Use only the standard library. No migrations, provider secrets, new database
  columns, runtime state files, or dependencies.

## Edge Cases

- Missing expected files are reported with `exists=False` and `size_bytes=0`.
- A run with no events reports `event_count=0` and `latest_event_type=""`.
- `as_dict()` output must be JSON-safe without callers needing to convert
  `Path` objects.
- Existing event append/read behavior and filename validation remain unchanged.
- Startup identity hardening is unrelated to this artifact module; existing
  startup tests must still pass to cover the mandatory hardening checks.

## Acceptance Criteria

1. Existing artifact depth behavior remains unchanged.
   VERIFY: `pytest tests/test_promptclaw_artifacts_depth.py -q`

2. `build_run_report` returns meaningful file statuses and event metadata for a
   run with written artifacts.
   VERIFY: `pytest tests/test_promptclaw_artifacts_report.py::test_build_run_report_summarizes_written_artifacts_and_events -q`

3. `ArtifactRunReport.as_dict()` emits JSON-safe output with derived present and
   missing counts.
   VERIFY: `pytest tests/test_promptclaw_artifacts_report.py::test_run_report_as_dict_is_json_safe_and_counts_files -q`

4. Fractal depth for `promptclaw/artifacts.py` remains at least depth 2.
   VERIFY: `pytest tests/test_promptclaw_artifacts_report.py::test_artifacts_module_stays_depth_two_for_frac_0043 -q`

5. Mandatory startup identity hardening anchors remain green for standalone and
   federated startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
