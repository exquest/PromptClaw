# Task frac-0056 Specification: test_acoustic_ecology Depth 2

## Problem Statement

`tests/test_acoustic_ecology.py` owns the regression coverage for the
SenseWeave acoustic ecology policy resolver in
`my-claw/tools/senseweave/acoustic_ecology.py`. The production module is
already a pure, stdlib-only policy resolver and currently classifies above the
requested depth: `sdp.fractal.classify_depth(...)` reports depth 4 for the
source module. The affected surface for this task is the test file itself.

The existing test file verifies every major policy rule, but most tests make a
single assertion against one helper call. The fractal classifier therefore
reports `tests/test_acoustic_ecology.py` at depth 1 (`29/35 trivial, 6 real`).
That leaves little end-to-end signal in the same file: nothing walks realistic
presence/cadence/day-phase scenarios as a table, compares policy monotonicity
across a daily arc, validates source-priority invariants for every mode, or
checks that modifier reasons and hard ceilings remain coherent together.

This task deepens `tests/test_acoustic_ecology.py` to depth 2 by adding one
end-to-end test class with looped, multi-step scenarios. Existing assertions
are preserved unchanged.

## Technical Approach

- Preserve the current acoustic ecology source module and all existing tests.
  No source behavior change is required because the resolver already produces
  meaningful policies and the existing policy tests pass.
- Add a separate red-phase depth gate in
  `tests/test_acoustic_ecology_depth.py` that asserts
  `classify_depth("tests/test_acoustic_ecology.py").depth >= 2`. It fails
  before implementation because the file currently reports depth 1.
- Add `TestAcousticEcologyEndToEnd` to `tests/test_acoustic_ecology.py`.
  Each test method contains looped or multi-statement logic so the fractal
  classifier treats the new methods as real logic rather than trivial one-call
  tests.
- Drive the real public API (`resolve_ecology_mode`,
  `resolve_acoustic_ecology`, and `AcousticEcologyPolicy`) through meaningful
  one-path scenarios:
  - daily ecology scenarios from sleep through active day, performance, and
    away practice
  - hard-ceiling tables for sleep and wind-down
  - policy ranges and source priority invariants for every ecology mode
  - dwell-time, room-activity, and day-phase modifier sweeps
  - end-to-end checks from context input through reasons, source ordering,
    ceiling constraints, silence windows, and generated/keynote weighting
- Keep the implementation test-only, stdlib-only, and free of migrations,
  provider secrets, runtime state writes, database columns, or new
  dependencies.
- Treat the generated startup hardening bullets as verification anchors. The
  startup identity subsystem already has dedicated tests for
  `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`
  across standalone/federated startup paths.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact depth string so later
  test-file improvements remain compatible.
- Sleep and wind-down hard ceilings are validated as tables to prevent room
  activity and day-phase modifiers from accidentally relaxing those caps.
- Presence uncertainty continues to resolve to `quiet_occupied`, not
  `away_practice`, so stale presence stays conservative.
- Performance attention continues to override wind-down cadence while remaining
  quieter than away-practice maximum loudness.
- Unknown day phases use the neutral centroid scale path and should match the
  same context under `mid_morning`.
- The `hour` input is retained in scenario calls even though the current source
  module does not branch on it; this preserves the public resolver signature
  and documents the assumption.
- No new dependencies, migrations, provider secrets, runtime state files,
  HTTP routes, auth behavior, or database schema changes are introduced.

## Acceptance Criteria

1. Existing acoustic ecology behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_acoustic_ecology.py -q`

2. The new red-phase depth gate confirms
   `tests/test_acoustic_ecology.py` reaches at least depth 2 after
   implementation.
   VERIFY: `pytest tests/test_acoustic_ecology_depth.py -q`

3. The new end-to-end class covers daily scenarios, policy invariants,
   hard-ceiling tables, modifier sweeps, source ordering, and reason metadata.
   VERIFY: `pytest tests/test_acoustic_ecology.py::TestAcousticEcologyEndToEnd -q`

4. The production acoustic ecology source module remains unchanged in behavior
   and still works through the public resolver API.
   VERIFY: `python -c "import os, sys; sys.path.insert(0, os.path.join(os.getcwd(), 'my-claw', 'tools')); from senseweave.acoustic_ecology import resolve_acoustic_ecology; p = resolve_acoustic_ecology(occupancy_state='occupied_active', cadence_state='occupied_day', day_phase='mid_morning', room_activity='active', attention_state='attending', dwell_time_s=600.0, hour=10); assert p.ecology_mode == 'active_day' and p.max_loudness_db > 0 and p.preferred_sources[0] == 'room_mic'; print(p.ecology_mode, p.max_loudness_db, p.preferred_sources[0])"`

5. Startup identity hardening remains covered for standalone/federated
   persistence and bootstrap-before-announcer ordering.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
