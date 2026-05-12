# Task frac-0059 Specification: test_artist_identity Depth 2

## Problem Statement

`tests/test_artist_identity.py` owns the regression coverage for
`my-claw/tools/senseweave/artist_identity.py`, the SenseWeave module that
encodes CypherClaw's artistic self: the five-voice signature quintet, the
B-rooted `HOME_TONAL_MAP`, the five `ArtistMode` situational states,
`select_mode()` routing, `apply_mode_to_commission()` metadata application,
and `next_tonal_choice()` modulation policy.

The production source already implements meaningful logic and classifies above
this task's target depth: `sdp.fractal.classify_depth(
"my-claw/tools/senseweave/artist_identity.py")` reports depth 3. The affected
surface for this task is the test file itself. The current test file verifies
the public surface but most tests are short, single-call assertions; the
fractal scanner reports `tests/test_artist_identity.py` at depth 1
(`38/51 trivial, 13 real`).

This task deepens `tests/test_artist_identity.py` to depth 2 by adding a
focused depth gate and a one-path end-to-end test class that exercises the
real public artist-identity API through complete, looped, and table-driven
scenarios. Existing assertions are preserved unchanged.

## Technical Approach

- Preserve `my-claw/tools/senseweave/artist_identity.py` behavior. The
  production module already produces meaningful artist-identity output and
  needs no changes for this task.
- Add `tests/test_artist_identity_depth.py` with a red-phase assertion that
  `classify_depth("tests/test_artist_identity.py").depth >= 2`.
- Add a `TestArtistIdentityEndToEnd` class to
  `tests/test_artist_identity.py`. The methods are looped or table-driven so
  the fractal scanner records real test logic rather than trivial one-call
  checks (each method either contains a `for`/`if` control statement or has
  more than three statements in its body).
- Drive one simple end-to-end path through the existing public API:
  - Sweep every `ArtistMode` in `MODES`, confirm `apply_mode_to_commission`
    yields the expected metadata keys and types, that tempo samples land in
    the band, and that mode-tagged dictionaries are JSON-serializable.
  - Sweep every key in `HOME_TONAL_MAP`, confirm distances are non-negative
    integers and that `B` is the unique zero-distance home.
  - Sweep `select_mode` over a presence/time/weather/screen matrix and
    confirm the routing table matches the documented selection order.
  - Sweep many `rng_seed` values through `next_tonal_choice` for every mode
    and confirm modulation_willingness correlates with venturing.
  - Sweep many `rng_seed` values through `apply_mode_to_commission` and
    confirm determinism, immutability of the input dict, and propagation of
    `sampler_density`, `voice_count_*`, `silence_ratio`, `restraint_level`,
    `harmonic_complexity`, `modulation_willingness`, preferred-voices CSV,
    preferred-grooves CSV, preferred modal-scales CSV, and the
    `avoid_attention_pullers` flag.
- Keep this test-only change stdlib-only. No new dependencies, migrations,
  provider secrets, runtime state files, database columns, HTTP routes, or
  auth changes are required.
- Treat the generated startup hardening bullets as mandatory verification
  anchors. Existing startup identity tests cover `bootstrap_identity()`
  persistence, standalone/federated modes, CLI startup invocation,
  bootstrap-before-`FirstBootAnnouncer` ordering in both daemon entrypoints,
  and ASGI app import persistence; those tests are re-run in this task.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact depth or reason
  so later test improvements remain compatible.
- Existing tests and assertions in `tests/test_artist_identity.py` remain
  unchanged; new coverage is appended in a separate class so previously
  locked assertions are not modified.
- Tempo sweep uses bounded random seeds and asserts only that returned
  tempos land in the mode's tempo band, not exact values, avoiding brittle
  coupling to RNG state.
- Modulation-willingness assertions compare aggregate distance counts across
  many seeds rather than per-seed equality, in line with the existing
  `test_low_modulation_willingness_stays_close_to_home` style.
- `select_mode` sweep covers documented inputs only; ambiguous values fall
  through to `COMPANION` per the existing default contract.
- No production-source changes are expected because the existing source
  module already meets functional contracts.

## Acceptance Criteria

1. Existing artist-identity behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_artist_identity.py -q`

2. The new red-phase depth gate confirms
   `tests/test_artist_identity.py` reaches at least depth 2 after the
   end-to-end tests are added.
   VERIFY: `pytest tests/test_artist_identity_depth.py -q`

3. The new end-to-end class covers complete mode application across all
   five modes, the full HOME_TONAL_MAP, the documented `select_mode`
   routing matrix, modulation-willingness behavior across seeds, and
   metadata propagation determinism.
   VERIFY: `pytest tests/test_artist_identity.py::TestArtistIdentityEndToEnd -q`

4. The production artist-identity source remains unchanged in behavior and
   still works through the public API.
   VERIFY: `python -c "import os, sys; sys.path.insert(0, os.path.join(os.getcwd(), 'my-claw', 'tools')); from senseweave.artist_identity import MODES, apply_mode_to_commission, select_mode, next_tonal_choice; m = select_mode(presence='present', time_of_day='evening'); out = apply_mode_to_commission({}, m, rng_seed=7); root, scale = next_tonal_choice(current_key='B minor', artist_mode=m, rng_seed=7); assert out['artist_mode'] == m.name and root and scale; print(m.name, len(MODES), root, scale)"`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2
   artist-identity test coverage.
   VERIFY: `grep -n "frac-0059" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
