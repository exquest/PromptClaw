# Task frac-0111 Specification: test_sample_record_skeleton Depth 2

## Problem Statement

`tests/test_sample_record_skeleton.py` currently verifies `SampleRecord`
core identity fields (`sample_id`, `path`, `source`, `captured_at`) at
skeleton depth: the dataclass exists, declares those fields, accepts
explicit values, exposes expected Python types, is frozen, and compares
equal for matching identity values.

Missing depth-2 coverage is a single end-to-end path that proves those
core identity fields produce meaningful output across the sample-record
lifecycle: construction, JSON serialization via `to_dict()` /
`from_dict(...)`, SQLite-backed `SampleLibrary` persistence, query
retrieval, and a JSON-safe operator diagnostic. The production
`senseweave.sample_library` module already implements that one-path
behavior: `to_dict()` emits JSON-compatible path and timestamp values,
`from_dict(...)` restores `Path` and `datetime` values, and
`SampleLibrary.add(...)` stores the full serialized record in
`record_json` for `SampleLibrary.find(...)` retrieval.

The generated startup identity hardening bullets target the existing
identity startup subsystem. Current CLI, first-boot, daemon-ordering, and
narrative ASGI tests already cover `bootstrap_identity()` before
`FirstBootAnnouncer` plus standalone/federated identity persistence. This
task keeps those tests as mandatory regression anchors rather than
changing unrelated startup code.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow, as mirrored in
`sdp/templates/candidates/lead_t2/v006.md`.

## Technical Approach

- Add `tests/test_test_sample_record_skeleton_depth.py` using the recent
  sample-record depth-gate pattern. The gate requires:
  - `SampleRecordSkeletonEndToEndTests` exists in
    `tests/test_sample_record_skeleton.py`;
  - the named method
    `test_core_identity_persists_filters_and_round_trips_json_diagnostic`
    exists;
  - `classify_depth("tests/test_sample_record_skeleton.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the
  end-to-end class exists.
- Append `SampleRecordSkeletonEndToEndTests` to
  `tests/test_sample_record_skeleton.py` without modifying existing
  locked assertions. The class drives one deterministic path:
  - create a real temporary WAV file so `SampleLibrary.add(...)`
    exercises the file-presence contract;
  - create a `SampleRecord` with meaningful `sample_id`, `path`,
    `source`, `captured_at`, and a valid tag set;
  - assert `to_dict()` exposes JSON-compatible identity values and
    `SampleRecord.from_dict(json.loads(json.dumps(...)))` preserves
    them;
  - persist the record through `SampleLibrary.add(...)`;
  - retrieve it through `SampleLibrary.find(...)` with source/tag
    filters and assert the stored core identity fields survive;
  - build a primitive diagnostic payload and verify
    `json.dumps(..., sort_keys=True)` / `json.loads(...)` round-trips
    it.
- Preserve production behavior unless the red tests reveal a concrete
  implementation gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage.
  Existing field-level tests remain responsible for type assertions,
  frozen dataclass behavior, and equality semantics.
- The WAV content is only used to satisfy the library's file-presence
  contract; audio feature extraction belongs to the existing
  audio-analysis and generation-storage tests.
- SQLite persistence is temporary and hermetic through `tmp_path`.
- No database schema changes are introduced, so no migration or index
  work is required.
- Startup identity hardening remains a regression anchor and is not
  widened inside the sample-record skeleton tests.

## Acceptance Criteria

1. Existing sample-record skeleton assertions remain green.
   VERIFY: `pytest tests/test_sample_record_skeleton.py -q`

2. The depth gate confirms `tests/test_sample_record_skeleton.py`
   reaches depth >= 2 and contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_sample_record_skeleton_depth.py -q`

3. `SampleRecordSkeletonEndToEndTests` drives construction, JSON
   serialization, `SampleLibrary` persistence/retrieval, and JSON-safe
   diagnostics for meaningful core identity fields.
   VERIFY: `pytest tests/test_sample_record_skeleton.py::SampleRecordSkeletonEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0111 sample-record
   skeleton test deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0111" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
