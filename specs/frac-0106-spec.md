# Task frac-0106 Specification: test_render_seed Depth 2

## Problem Statement

`tests/test_render_seed.py` covers the `derive_seed(...)` helper in
`src/cypherclaw/render/seed.py` at depth 1: each test pins a single
property of the helper (return type, 32-bit range, determinism,
sensitivity to root seed, sensitivity to path content, sensitivity to
path order, empty-path handling, negative inputs, large paths, known
value stability, and round-trip via `Event.seed_path`).

The missing frac-0106 work is to deepen the seed test module from
helper-level coverage to a depth-2 contract by adding one named
end-to-end class that drives a realistic deterministic-seed lifecycle
across the public surface (`derive_seed` + `Event.seed_path`) without
modifying any locked existing assertions.

The generated startup identity hardening bullets target the existing
identity startup subsystem, not this pure render-seed helper. Existing
CLI, first-boot, daemon-ordering, and narrative ASGI tests already
cover `bootstrap_identity()` before `FirstBootAnnouncer` and
standalone/federated identity persistence. This task keeps those tests
as mandatory regression anchors rather than add unrelated startup
code without a discovered gap.

## Technical Approach

- Add `tests/test_test_render_seed_depth.py`, matching the recent
  frac depth-gate pattern (frac-0104 / frac-0105), to require:
  - `RenderSeedEndToEndTests` exists in `tests/test_render_seed.py`;
  - the named end-to-end method
    `test_full_seed_derivation_lifecycle_is_json_safe_and_event_round_trip_safe`
    exists;
  - `classify_depth("tests/test_render_seed.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the
  end-to-end class exists.
- Append `RenderSeedEndToEndTests` to `tests/test_render_seed.py`
  without modifying any existing assertions. The class drives one
  meaningful public path:
  - choose a deterministic `root_seed` and a small ordered family of
    `seed_path` tuples that represent a phrase → voice → event walk;
  - derive sub-seeds with `derive_seed(...)` and assert each result is
    in the 32-bit range, deterministic on re-derivation, and unique
    across the family;
  - assert the same family re-derived from a different root seed
    yields a different sub-seed at every position (root-seed
    sensitivity end-to-end);
  - construct `Event` objects (`from cypherclaw.render.events import
    Event`) with each `seed_path` and assert the `Event.seed_path`
    tuple-cast invariant is preserved, and that re-deriving from
    `event.seed_path` reproduces the original sub-seed (closing the
    seed/event round trip);
  - build a JSON-safe diagnostic of `{root_seed, family: [{path, seed,
    event_seed_path}], …}` that round-trips through
    `json.dumps(..., sort_keys=True)` / `json.loads(...)` while
    preserving sub-seed values, event count, and per-position seeds.
- Preserve production behavior in `src/cypherclaw/render/seed.py`
  unless the red phase exposes a concrete gap. Exploration shows the
  helper already implements the simple one-path SHA-256 derivation
  required by CCH-009.
- Introduce no new dependencies, migrations, provider secrets,
  database columns, runtime state directories, HTTP routes, or auth
  behavior.

## Edge Cases

- The end-to-end path covers one realistic deterministic seed family,
  not every property. Existing focused tests continue to own
  per-property pinning (range, order sensitivity, negative inputs,
  empty path).
- The depth gate checks class and method names in addition to
  `sdp.fractal.classify_depth(...)`, so it remains meaningful even in
  checkouts where the fractal classifier is test-doubled.
- The combined diagnostic uses only JSON primitives (ints and lists
  of ints) so seed diagnostics can be consumed by metrics gates and
  operator tooling without custom encoding; tuple `seed_path` values
  are explicitly converted to lists before serialization and back to
  tuples on re-derivation.
- Startup identity hardening remains covered by existing startup
  tests; no startup source changes are expected for this render-seed
  task.
- No database columns, foreign keys, or migrations are introduced.

## Acceptance Criteria

1. Existing render-seed assertions remain green.
   VERIFY: `pytest tests/test_render_seed.py -q`

2. The depth gate confirms `tests/test_render_seed.py` reaches depth
   >= 2 and contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_render_seed_depth.py -q`

3. `RenderSeedEndToEndTests` drives the full public seed lifecycle
   and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_render_seed.py::RenderSeedEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup,
   daemon startup ordering, standalone/federated identity
   persistence, and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0106 render-seed
   test deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0106" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
