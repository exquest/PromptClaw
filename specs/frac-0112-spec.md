# Task frac-0112 Specification: test_sample_status Depth 2

## Problem Statement

`tests/test_sample_status.py` currently verifies the
`senseweave.sample_status` helpers (`sample_status_text`,
`face_display_sample_status_text`) at depth 1: each existing test
exercises one isolated branch (legacy active capture phrasing, inactive
capture, legacy playback override, combined activity+playback, monitor
failure precedence) without driving the full helper surface through a
single end-to-end lifecycle.

Missing depth-2 coverage is one realistic path that proves the public
helpers produce meaningful, JSON-safe output across the lifecycle a
face-display / operator surface actually consumes:

1. legacy mode where playback dominates,
2. legacy mode where capture is the only active sub-system,
3. combined mode where both capture and playback are active,
4. combined mode where the monitor reports a `no_capture` failure,
5. the `face_display_sample_status_text` wrapper agreeing with combined
   `sample_status_text(...)` output, and
6. a JSON-safe diagnostic of the rendered status lines round-tripping
   through `json.dumps(..., sort_keys=True)`.

The production `senseweave.sample_status` module already implements that
behavior. This task locks one happy-path end-to-end test plus a depth
gate.

The generated startup identity hardening bullets target the existing
identity startup subsystem. Current CLI, first-boot, daemon-ordering,
and narrative ASGI tests already cover `bootstrap_identity()` before
`FirstBootAnnouncer` plus standalone/federated identity persistence.
This task keeps those tests as mandatory regression anchors rather than
changing unrelated startup code.

## Technical Approach

- Add `tests/test_test_sample_status_depth.py` using the recent
  depth-gate pattern. The gate requires:
  - `SampleStatusEndToEndTests` exists in
    `tests/test_sample_status.py`;
  - the named method
    `test_sample_status_helpers_render_lifecycle_and_round_trip_json_diagnostic`
    exists;
  - `classify_depth("tests/test_sample_status.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the
  end-to-end class exists.
- Append `SampleStatusEndToEndTests` to `tests/test_sample_status.py`
  without modifying existing locked assertions. The class drives one
  deterministic end-to-end path:
  - call `sample_status_text(activity, playback)` in legacy mode where
    `playing=True` and assert the rendered text includes a `playing`
    phrase, the playback source, and the playback mode;
  - call `sample_status_text(activity)` in legacy mode where capture is
    active but playback is silent and assert the rendered text reports
    the requested+actual source plus activity mode in `holding`/
    `sampling` phrasing;
  - call `sample_status_text(activity, playback,
    combine_activity_and_playback=True)` for a real combined lifecycle
    and assert both `currently sampling …` and `playing sample …`
    fragments appear, separated by ` · `;
  - call `sample_status_text(activity, playback, monitor_state,
    combine_activity_and_playback=True)` with a `no_capture` monitor
    error and assert the rendered text starts with `monitor offline`
    while preserving the combined fragments;
  - confirm `face_display_sample_status_text(activity, playback,
    monitor_state)` agrees with the combined-mode call;
  - build a primitive diagnostic of the rendered lines and verify
    `json.dumps(..., sort_keys=True)` / `json.loads(...)` round-trips
    it.
- Preserve production behavior unless the red tests reveal a concrete
  implementation gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage.
  Existing per-branch tests remain responsible for inactive-capture,
  legacy-playback-override, and monitor-failure-precedence semantics.
- The diagnostic payload only captures rendered text and minimal
  metadata; `sample_status_text` already returns `str`, so JSON
  serialization is intrinsically safe.
- No database schema changes are introduced, so no migration or index
  work is required.
- Startup identity hardening remains a regression anchor and is not
  widened inside the sample-status tests.

## Acceptance Criteria

1. Existing sample-status assertions remain green.
   VERIFY: `pytest tests/test_sample_status.py -q`

2. The depth gate confirms `tests/test_sample_status.py` reaches
   depth >= 2 and contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_sample_status_depth.py -q`

3. `SampleStatusEndToEndTests` drives the legacy, combined, monitor-
   failure, face-display wrapper, and JSON-safe diagnostic lifecycle
   for `senseweave.sample_status`.
   VERIFY: `pytest tests/test_sample_status.py::SampleStatusEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0112 sample-status test
   deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0112" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
