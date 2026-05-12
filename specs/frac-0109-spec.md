# Task frac-0109 Specification: test_sample_record_audio_analysis Depth 2

## Problem Statement

`tests/test_sample_record_audio_analysis.py` currently verifies the
`SampleRecord` audio-analysis fields at field depth: the dataclass declares
`rms`, `peak`, and `transient_density`; defaults are zero; typical values are
accepted; invalid negative values and `peak < rms` are rejected; and a direct
dataclass-field reconstruction preserves the metrics.

Missing depth-2 coverage is a single end-to-end path that proves those audio
metrics produce meaningful output across the sample-record lifecycle:
construction, JSON serialization, SQLite-backed `SampleLibrary` persistence,
query retrieval, and a JSON-safe operator diagnostic. The production
`senseweave.sample_library` module already implements that one-path behavior,
so this task should deepen the test surface unless the red tests expose a
concrete implementation gap.

The generated startup identity hardening bullets target the existing identity
startup subsystem. Exploration found current CLI, daemon, first-boot, and
narrative ASGI tests already cover `bootstrap_identity()` before
`FirstBootAnnouncer` and standalone/federated identity persistence. This task
keeps those tests as mandatory regression anchors rather than changing
unrelated startup code.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow, as mirrored in
`sdp/templates/candidates/lead_t2/v006.md`.

## Technical Approach

- Add `tests/test_test_sample_record_audio_analysis_depth.py` using the recent
  depth-gate pattern. The gate requires:
  - `SampleRecordAudioAnalysisEndToEndTests` exists in
    `tests/test_sample_record_audio_analysis.py`;
  - the named method
    `test_audio_metrics_persist_filter_and_round_trip_json_diagnostic` exists;
  - `classify_depth("tests/test_sample_record_audio_analysis.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `SampleRecordAudioAnalysisEndToEndTests` to
  `tests/test_sample_record_audio_analysis.py` without modifying existing
  locked assertions. The class drives one deterministic path:
  - create a real temporary WAV file so `SampleLibrary.add(...)` exercises the
    file-presence contract;
  - create a `SampleRecord` with meaningful `duration`, `rms`, `peak`, and
    `transient_density` values plus source, tags, pitch, arc phase, mood, and
    capture timestamp;
  - assert `to_dict()` exposes JSON-compatible metric values and
    `SampleRecord.from_dict(...)` preserves them;
  - persist the record through `SampleLibrary.add(...)`;
  - retrieve it through `SampleLibrary.find(...)` with source/tag/mood filters
    and assert the stored metrics, path, source, and tags survive;
  - build a primitive diagnostic payload and verify
    `json.dumps(..., sort_keys=True)` / `json.loads(...)` round-trips it.
- Preserve production behavior unless the red tests reveal a runtime gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage. Existing
  field-level tests remain responsible for negative metrics, zero boundaries,
  and `peak >= rms` validation.
- The WAV content is only used to satisfy the library's file-presence contract;
  audio feature extraction belongs to the existing generation-storage tests.
- SQLite persistence is temporary and hermetic through `tmp_path`.
- No database schema changes are introduced, so no migration or index work is
  required.
- Startup identity hardening remains a regression anchor and is not widened
  inside the sample-record audio-analysis tests.

## Acceptance Criteria

1. Existing sample-record audio-analysis assertions remain green.
   VERIFY: `pytest tests/test_sample_record_audio_analysis.py -q`

2. The depth gate confirms `tests/test_sample_record_audio_analysis.py` reaches
   depth >= 2 and contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_sample_record_audio_analysis_depth.py -q`

3. `SampleRecordAudioAnalysisEndToEndTests` drives construction,
   JSON serialization, `SampleLibrary` persistence/retrieval, and JSON-safe
   diagnostics for meaningful audio metrics.
   VERIFY: `pytest tests/test_sample_record_audio_analysis.py::SampleRecordAudioAnalysisEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0109 sample-record
   audio-analysis test deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0109" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
