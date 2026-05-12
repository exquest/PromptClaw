# Task frac-0062 Specification: test_capstone_engine Depth 2

## Problem Statement

`tests/test_capstone_engine.py` owns regression coverage for
`my-claw/tools/senseweave/capstone_engine.py`, the EMSD capstone-cycle planner
that composes a five-phase 30-minute living-composition plan from the
procedural arc, sound palette, mix, environmental sampling, DSP scene, and
artistic-identity modules.

The production module already provides a simple one-path implementation:
`build_capstone_cycle()` walks the canonical `ARC_PHASES`, selects phase
families, patches, sample sources, palette studies, mix profiles, sample plans,
DSP scenes, and repertoire-derived identity, then returns a typed
`CapstoneCyclePlan`. The production source classifies above this task's target
depth: `sdp.fractal.classify_depth("my-claw/tools/senseweave/capstone_engine.py")`
reports depth 3.

The affected surface for this task is the test file itself. The current test
file verifies the public function with three short checks, but the fractal
scanner reports `tests/test_capstone_engine.py` at depth 1 (`2/3 trivial,
1 real`). This task deepens the capstone test file to depth 2 by adding a
focused red-phase depth gate and a one-path end-to-end test class that asserts
meaningful output across the existing public API. Existing assertions are
preserved unchanged.

## Technical Approach

- Preserve `my-claw/tools/senseweave/capstone_engine.py` behavior unless new
  tests expose a real regression. The source module already produces
  meaningful output and needs no planned production change.
- Add `tests/test_capstone_engine_depth.py` with a red-phase assertion that
  `classify_depth("tests/test_capstone_engine.py").depth >= 2`.
- Add a `TestCapstoneCycleEndToEnd` class to `tests/test_capstone_engine.py`.
  The methods use looped and table-driven assertions so the scanner records
  real integration test logic rather than trivial one-call checks.
- Drive one simple public path through the existing API:
  - Verify all five canonical phase plans expose the expected family, patch,
    arc, palette, mix, sampling, and DSP scene contracts.
  - Verify occupied active cycles route Conversation through Theramini-aware
    sampling/DSP/mix behavior while keeping late lived-in phases on room mic.
  - Verify away-practice cycles switch late sampling and DSP focus to
    `self_bus` and include practice-oriented sample transforms.
  - Verify sleep or wind-down cycles produce quieter mix targets and lower arc
    densities than occupied cycles for the same phases.
  - Verify repertoire songs drive identity families, patches, imagery, and
    statement text through the returned `CapstoneCyclePlan`.
  - Verify phase output can be serialized into a JSON-safe diagnostic payload
    without depending on dataclass internals.
- Keep this test-only change stdlib-only. No new dependencies, migrations,
  provider secrets, runtime state files, database columns, HTTP routes, or
  auth changes are required.
- Treat the generated startup hardening bullets as mandatory verification
  anchors. Existing startup identity tests cover `bootstrap_identity()`
  persistence, standalone/federated reuse, CLI startup invocation,
  bootstrap-before-`FirstBootAnnouncer` ordering, and ASGI app import
  persistence; those tests are re-run in this task.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact depth or reason so
  later test improvements remain compatible.
- Existing tests and assertions in `tests/test_capstone_engine.py` remain
  unchanged; new coverage is appended in a separate class.
- Production source changes are not expected because `build_capstone_cycle()`
  already builds a complete five-phase plan with meaningful collaborator
  outputs.
- Cadence comparisons check directional behavior (sleep/wind-down quieter and
  lower density than occupied) rather than exact implementation details beyond
  the public dataclass fields.
- JSON-safe diagnostic assertions build explicit dictionaries from public
  fields instead of serializing arbitrary dataclass objects.
- No startup identity source changes are expected because the existing tree
  already has dedicated regression anchors for the generated hardening items.

## Acceptance Criteria

1. Existing capstone-engine behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_capstone_engine.py -q`

2. The new red-phase depth gate confirms `tests/test_capstone_engine.py`
   reaches at least depth 2 after the end-to-end tests are added.
   VERIFY: `pytest tests/test_capstone_engine_depth.py -q`

3. The new end-to-end class covers canonical phase output, occupied Theramini
   routing, away-practice late self-bus routing, quiet-cadence density/mix
   behavior, repertoire identity propagation, and JSON-safe diagnostics from
   the existing public API.
   VERIFY: `pytest tests/test_capstone_engine.py::TestCapstoneCycleEndToEnd -q`

4. The production capstone source remains unchanged in behavior and still
   works through the public API.
   VERIFY: `python -c "import os, sys; sys.path.insert(0, os.path.join(os.getcwd(), 'my-claw', 'tools')); from senseweave.capstone_engine import build_capstone_cycle; p=build_capstone_cycle(cadence_state='occupied_day', occupancy_state='occupied_active', theramini_present=True, repertoire_songs=[{'family':'bloom','patch_name':'house_garden','title':'Quiet Rooms','hook_text':'keep the room open'}]); assert len(p.phases)==5 and p.phases[2].sampling.source.name=='theramini_in' and p.phases[2].mix.theramini_duck_db > 0 and p.identity.statement; print([ph.phase_name for ph in p.phases], p.identity.statement)"`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2 capstone
   engine test coverage.
   VERIFY: `grep -n "frac-0062" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
