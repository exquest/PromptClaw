# Task frac-0072 Specification: test_functional_harmony Depth 2

## Problem Statement

`tests/test_functional_harmony.py` currently verifies functional harmony in
small pieces: harmonic-function labels, cadence targets, pivot/common-tone
helpers, section tension, transition intents, and score-tree serialization of
new section fields. The depth-2 task requires an end-to-end test surface that
drives the public harmony path as one working flow and proves the outputs are
meaningful, JSON-safe, and usable by downstream score-tree persistence.

Exploration confirmed the affected production path is already implemented in
`my-claw/tools/senseweave/reharmonizer.py`,
`my-claw/tools/senseweave/harmonic_planner.py`, and
`my-claw/tools/senseweave/score_tree.py`. `resolve_harmonic_plan()` selects a
canonical key, scene keys, reharm strategy, section functions/cadences,
progression roots, triad degree sets, harmonic functions, and transition
intents. `SectionHarmony` and `SectionNode` already carry the functional
harmony fields. This task therefore preserves production behavior and adds a
depth gate plus an end-to-end test class around the existing public API.

## Technical Approach

- Preserve existing assertions in `tests/test_functional_harmony.py`.
- Add `tests/test_test_functional_harmony_depth.py` requiring
  `tests/test_functional_harmony.py` to contain
  `FunctionalHarmonyEndToEndTests` and classify at depth >= 2 through the
  local `sdp.fractal.classify_depth` helper.
- Append `FunctionalHarmonyEndToEndTests` to `tests/test_functional_harmony.py`.
  The class will drive:
  - `resolve_harmonic_plan()` from live-like MIDI, garden, outdoor, and inner
    state inputs,
  - `reharm_plan_for_song()` and `progression_bank_for_section()` for the same
    progression family,
  - `common_tones()` / `pivot_degree()` across the resolved modulation path,
  - `ScoreTree` / `SectionNode` JSON round-trip using section fields derived
    from the resolved `HarmonicPlan`.
- Verify that the public output is meaningful: scene keys are populated,
  section functions/cadences/progressions line up, chord-degree triads are
  bounded to scale degrees 1-7, transition intents are present, tension changes
  are coherent across the section arc, and JSON summaries round-trip without
  custom encoders.
- Treat the generated startup identity hardening bullets as regression anchors.
  Existing CLI startup, daemon startup, and narrative ASGI import paths already
  invoke `bootstrap_identity()` before dependent first-boot work, so this task
  re-runs those anchors instead of broadening the harmony scope.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state files, HTTP routes, or auth behavior are introduced.

## Edge Cases

- The end-to-end path uses one deterministic live-like input path rather than
  adding broad edge-case matrices.
- Stale garden/inner/MIDI fallback behavior remains covered by
  `tests/test_harmonic_planner.py`; this task only asserts that fresh
  meaningful input produces a coherent harmonic plan.
- Existing per-function tests remain the authority for individual labels,
  cadence families, and defaults.
- Tuple-heavy harmony structures must still serialize through normal
  `json.dumps` / `json.loads` conversions.
- Score-tree round-trip must preserve harmonic function and transition intent
  fields derived from the resolved plan.

## Acceptance Criteria

1. Existing functional harmony assertions remain green.
   VERIFY: `pytest tests/test_functional_harmony.py -q`

2. The new depth gate confirms `tests/test_functional_harmony.py` reaches
   depth >= 2 and contains `FunctionalHarmonyEndToEndTests`.
   VERIFY: `pytest tests/test_test_functional_harmony_depth.py -q`

3. `FunctionalHarmonyEndToEndTests` drives the resolved harmony path through
   plan generation, reharm lookup, modulation continuity checks, score-tree
   section construction, and JSON-safe round-trip output.
   VERIFY: `pytest tests/test_functional_harmony.py::FunctionalHarmonyEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, standalone and
   federated identity persistence, daemon bootstrap-before-announcer ordering,
   and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0072 functional harmony depth-2 work.
   VERIFY: `grep -n "frac-0072" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
