# Task frac-0074 Specification: test_garden_watcher Depth 2

## Problem Statement

`tests/test_garden_watcher.py` covers the individual garden watcher helpers,
but the suite does not yet prove the module works as one deterministic path:
take a camera brightness reading, resolve the observed light and season, derive
art/music guidance, write the runtime JSON state, and expose a compact
operator-readable summary. The production module already contains the small
classification maps and atomic writer, but the wall-clock-only
`update_garden_state()` path makes the end-to-end behavior hard to pin in a
locked test.

The task deepens the test surface to depth 2 by adding a deterministic
one-path snapshot builder plus an end-to-end test class. Existing helper
assertions remain unchanged.

## Technical Approach

- Preserve all existing assertions in `tests/test_garden_watcher.py`.
- Add a depth gate in `tests/test_test_garden_watcher_depth.py` requiring
  `tests/test_garden_watcher.py` to contain `GardenWatcherEndToEndTests` and
  classify at depth >= 2.
- Append `GardenWatcherEndToEndTests` to the existing garden watcher tests.
  The new tests will drive:
  - deterministic state building from brightness and an explicit `datetime`;
  - JSON-safe summary generation from the resulting `GardenState`;
  - full build-and-write behavior into a temporary `garden_state.json`;
  - downstream compatibility for the fields consumed by composer/gallery paths
    (`light`, `season`, `palette`, `music_key`, `last_update`).
- Implement the smallest production surface needed:
  - `build_garden_state(brightness, observed_at)` for deterministic snapshots;
  - `summarize_garden_state(state)` for compact JSON-safe diagnostics;
  - `write_current_garden_state(brightness, path, observed_at=None)` for the
    one-path build/write cycle.
- Keep `update_garden_state()` behavior compatible by delegating through the
  deterministic builder with `datetime.now()`.
- Treat the generated startup identity hardening checks as regression anchors.
  Existing CLI, daemon, first-boot, and narrative ASGI tests already cover
  `bootstrap_identity()` before `FirstBootAnnouncer` and identity persistence
  across standalone/federated boots, so this task re-runs those anchors rather
  than changing unrelated startup code.

## Edge Cases

- This depth-2 pass intentionally exercises one deterministic happy path rather
  than broad edge-case matrices.
- Unknown light/season combinations still use the existing neutral palette/key
  fallback behavior.
- `observed_at` timestamps are used directly for reproducible tests; callers
  that do not pass one get the current wall-clock snapshot.
- The runtime JSON payload must remain compatible with existing consumers that
  read `/tmp/garden_state.json`.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state directories, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing garden watcher helper assertions remain green.
   VERIFY: `pytest tests/test_garden_watcher.py -q`

2. The new depth gate confirms `tests/test_garden_watcher.py` reaches depth >=
   2 and contains `GardenWatcherEndToEndTests`.
   VERIFY: `pytest tests/test_test_garden_watcher_depth.py -q`

3. `GardenWatcherEndToEndTests` drives deterministic snapshot building,
   summary generation, and build/write persistence through the public API.
   VERIFY: `pytest tests/test_garden_watcher.py::GardenWatcherEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, standalone and
   federated identity persistence, daemon bootstrap-before-announcer ordering,
   and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0074 garden watcher depth-2 work.
   VERIFY: `grep -n "frac-0074" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
