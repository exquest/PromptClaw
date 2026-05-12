# Task frac-0063 Specification: test_cast_planner Depth 2

## Problem Statement

`tests/test_cast_planner.py` owns regression coverage for
`my-claw/tools/senseweave/cast_planner.py`, the CypherClaw cast-selection helper
that picks a balanced cast of characters (core melody/rhythm/harmony plus
support roles), promotes preferred-synth voices, optionally attaches a
`sw_sampler`-driven sample summary, and assembles the final cast entries used
by the tracker orchestration layer.

The production module already provides a simple one-path implementation:
`select_cast_ids()` ranks characters by recency, pulls in the canonical core
roles, fills with one support role, then top-up extras up to the cast size.
`assemble_cast()` derives sampler-selector kwargs from a piece-like input,
delegates to `select_cast_ids()`, and returns assembled cast entries plus the
sampler metadata. The production source classifies above this task's target
depth: `sdp.fractal.classify_depth("my-claw/tools/senseweave/cast_planner.py")`
reports depth 3.

The affected surface for this task is the test file itself. The current test
file verifies the public functions across many short checks, but the fractal
scanner reports `tests/test_cast_planner.py` at depth 1 (`11/21 trivial,
10 real`). This task deepens the cast-planner test file to depth 2 by adding a
focused red-phase depth gate and a one-path end-to-end test class that asserts
meaningful output across the existing public API. Existing assertions are
preserved unchanged.

## Technical Approach

- Preserve `my-claw/tools/senseweave/cast_planner.py` behavior unless new
  tests expose a real regression. The source module already produces
  meaningful output and needs no planned production change.
- Add `tests/test_cast_planner_depth.py` with a red-phase assertion that
  `classify_depth("tests/test_cast_planner.py").depth >= 2`.
- Add a `TestCastPlannerEndToEnd` class to `tests/test_cast_planner.py`. The
  methods use looped and table-driven assertions so the scanner records real
  integration test logic rather than trivial one-call checks.
- Drive one simple public path through the existing API:
  - Verify `select_cast_ids()` returns the canonical melody/rhythm/harmony
    core roles in order across a table of cast histories and energy levels,
    each result containing at least one support-role entry.
  - Verify `voice_count_target` overrides energy-derived sizing across a table
    of `(target, expected_size)` pairs while keeping the core roles intact.
  - Verify `preferred_synths` promotes the matching characters to the front of
    the ranked cast across multiple preferred-synth selections.
  - Verify cast-history rotation pushes recently used characters to lower
    priority across a multi-step rotation simulation.
  - Verify `assemble_cast()` returns piece-derived sampler-selector kwargs and
    propagates the sampler summary into both the assembled cast entry and the
    metadata mapping for a multi-piece run.
  - Verify cast entries can be serialized into a JSON-safe diagnostic payload
    (id, role, synth, optional sample record) without depending on
    implementation internals.
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
- Existing tests and assertions in `tests/test_cast_planner.py` remain
  unchanged; new coverage is appended in a separate class.
- Production source changes are not expected because `select_cast_ids()` and
  `assemble_cast()` already return complete cast plans with meaningful
  collaborator outputs.
- Cast-history rotation assertions check directional behavior (recently used
  characters drop in rank) rather than exact tie-breaking implementation
  details beyond the public return list.
- JSON-safe diagnostic assertions build explicit dictionaries from public
  fields instead of serializing arbitrary entry objects.
- No startup identity source changes are expected because the existing tree
  already has dedicated regression anchors for the generated hardening items.

## Acceptance Criteria

1. Existing cast-planner behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_cast_planner.py -q`

2. The new red-phase depth gate confirms `tests/test_cast_planner.py`
   reaches at least depth 2 after the end-to-end tests are added.
   VERIFY: `pytest tests/test_cast_planner_depth.py -q`

3. The new end-to-end class covers canonical core/support coverage,
   voice-count target sizing, preferred-synth promotion, cast-history
   rotation, piece-driven sampler routing through `assemble_cast`, and
   JSON-safe diagnostics from the existing public API.
   VERIFY: `pytest tests/test_cast_planner.py::TestCastPlannerEndToEnd -q`

4. The production cast-planner source remains unchanged in behavior and still
   works through the public API.
   VERIFY: `python -c "import os, sys; sys.path.insert(0, os.path.join(os.getcwd(), 'my-claw', 'tools')); from senseweave.cast_planner import select_cast_ids, assemble_cast; chars={'mel':{'voice':{'role':'melody','synth':'sw_bowed'}},'rhythm':{'voice':{'role':'rhythm','synth':'sw_tabla_ge'}},'harm':{'voice':{'role':'harmony','synth':'sw_choir'}},'color':{'voice':{'role':'color','synth':'sw_bell'}}}; cast=select_cast_ids(chars, [], mood_energy=0.5, max_chars=4); assert cast[:3]==['mel','rhythm','harm']; entries, meta = assemble_cast(chars, [], piece={'mood':{'energy':0.5}}); assert entries[0]['id']=='mel'; print(cast, [e['id'] for e in entries])"`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2 cast
   planner test coverage.
   VERIFY: `grep -n "frac-0063" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
