# Task frac-0114 Specification: test_sampler_scheduler Depth 2

## Problem Statement

`tests/test_sampler_scheduler.py` currently verifies the per-mode
sampler density gates (`density_for_mode`, `count_sampler_events`,
`plan_sampler_phrase_indices`) at a focused unit level: floor +
Bernoulli math, density clamps, empty-piece zero, sorted unique
indices, mode-table lookups, and a per-mode separation simulation.

Missing depth-2 coverage is a single realistic end-to-end test path
that proves the scheduler surface produces meaningful diagnostic
output across the three public functions plus the canonical mode
table:

1. `density_for_mode` resolves a known mode name through
   `DEFAULT_SAMPLER_DENSITY_BY_MODE`,
2. `count_sampler_events` produces the documented
   `floor(density * total_phrases) + Bernoulli(density)` count under
   a deterministic RNG,
3. `plan_sampler_phrase_indices` selects sorted, unique, in-range
   indices that match that count,
4. a stable operator-style diagnostic that captures the mode, density,
   total phrases, planned indices, and event count in JSON-safe form.

The production module already implements the one-path scheduler
required by the CCS-023 / T-017 PRD: density clamp, deterministic
floor + Bernoulli bonus, sorted unique sample of phrase indices, and
canonical mode-density table. This task deepens the test surface
unless the red tests expose a concrete source gap.

The generated startup identity hardening bullets target the existing
identity startup subsystem. Current CLI, first-boot, daemon-ordering,
and narrative ASGI tests already cover `bootstrap_identity()` before
`FirstBootAnnouncer` plus standalone/federated identity persistence.
This task keeps those tests as mandatory regression anchors rather
than changing unrelated startup code.

The active ADP process is the task prompt's Explore -> Specify -> Test
-> Implement -> Verify -> Document workflow.

## Technical Approach

- Add `tests/test_test_sampler_scheduler_depth.py` using the recent
  depth-gate pattern. The gate requires:
  - `SamplerSchedulerEndToEndTests` exists in
    `tests/test_sampler_scheduler.py`;
  - the named method
    `test_sampler_scheduler_density_count_plan_round_trip_json_diagnostic`
    exists;
  - `classify_depth("tests/test_sampler_scheduler.py").depth >= 2`.
- Confirm the red phase by running the new depth gate before the
  end-to-end class exists.
- Append `SamplerSchedulerEndToEndTests` to
  `tests/test_sampler_scheduler.py` without modifying existing locked
  assertions. The class drives one deterministic path:
  - resolve `density_for_mode("evening_reflection")` against
    `DEFAULT_SAMPLER_DENSITY_BY_MODE`;
  - call `count_sampler_events(density, 16, rng)` with a seeded RNG
    and confirm the count matches the documented
    `floor + Bernoulli` formula for that seed;
  - call `plan_sampler_phrase_indices(density, 16, rng2)` with the
    same seed and confirm the indices are sorted, unique, in range,
    and the length equals the count from the same seed;
  - build a primitive diagnostic payload and verify
    `json.dumps(..., sort_keys=True)` / `json.loads(...)` round-trips
    it.
- Preserve production behavior unless the red tests reveal a runtime
  gap.
- Introduce no new dependencies, migrations, provider secrets,
  database columns, runtime state directories, HTTP routes, or auth
  behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage.
  Existing focused tests remain responsible for clamps, empty pieces,
  unknown modes, and per-mode statistical separation.
- The diagnostic payload only stores strings, floats, ints, and lists,
  so JSON serialization stays deterministic and hermetic.
- No database schema changes are introduced, so no migration or
  index work is required.
- Startup identity hardening remains a regression anchor and is not
  widened inside the sampler-scheduler tests.

## Acceptance Criteria

1. Existing sampler-scheduler assertions remain green.
   VERIFY: `pytest tests/test_sampler_scheduler.py -q`

2. The depth gate confirms `tests/test_sampler_scheduler.py` reaches
   depth >= 2 and contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_sampler_scheduler_depth.py -q`

3. `SamplerSchedulerEndToEndTests` drives the mode density lookup,
   count formula, planned indices, and JSON-safe diagnostic lifecycle.
   VERIFY: `pytest tests/test_sampler_scheduler.py::SamplerSchedulerEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0114 sampler-scheduler
   test deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0114" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
