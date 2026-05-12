# Task frac-0058 Specification: test_arrangement_engine Depth 2

## Problem Statement

`tests/test_arrangement_engine.py` owns the regression coverage for
`my-claw/tools/senseweave/arrangement_engine.py`, the SenseWeave section
arrangement planner used by `music_tracker.py` to attach scene entry intent,
groove family, density, master amplitude, lane timelines, register bands, and
automation curves to tracker forms.

The production arrangement module already implements the SWE-009 time-based
arrangement contract and currently classifies above this task's target:
`sdp.fractal.classify_depth("my-claw/tools/senseweave/arrangement_engine.py")`
reports depth 4. The affected surface for this task is the test file itself.
The current test file verifies the main helper behavior, but many tests are
single-call assertions. The fractal scanner therefore reports
`tests/test_arrangement_engine.py` at depth 1 (`24/39 trivial, 15 real`).

This task deepens `tests/test_arrangement_engine.py` to depth 2 by adding a
focused depth gate and a one-path end-to-end test class that exercises the real
public arrangement API across complete tracker forms. Existing assertions are
preserved unchanged.

## Technical Approach

- Preserve `my-claw/tools/senseweave/arrangement_engine.py` behavior unless the
  new tests expose a real regression. The source module already produces
  meaningful arrangement output.
- Add `tests/test_arrangement_engine_depth.py` with a red-phase assertion that
  `classify_depth("tests/test_arrangement_engine.py").depth >= 2`.
- Add a `TestArrangementEngineEndToEnd` class to
  `tests/test_arrangement_engine.py`. The methods use looped and table-driven
  assertions so the scanner records real test logic rather than trivial
  one-call checks.
- Drive one simple public path through the existing API:
  - Build a tracker form with `tracker_form_for_family`.
  - Build an `ArrangementPlan` with `build_arrangement_plan`.
  - Inspect every scene's `ArrangementScenePlan` and `ArrangementTimeline`.
  - Verify staged entries, density arcs, register safety, thinning behavior,
    automation interpolation, payoff shaping, and cadence quieting end-to-end.
- Keep this test-only change stdlib-only. No new dependencies, migrations,
  provider secrets, runtime state files, database columns, HTTP routes, or auth
  changes are required.
- Treat the generated startup hardening bullets as mandatory verification
  anchors. Existing startup identity tests cover `bootstrap_identity()`
  persistence, standalone/federated modes, CLI startup invocation,
  bootstrap-before-`FirstBootAnnouncer` ordering in both daemon entrypoints, and
  ASGI app import persistence; those tests are re-run in this task.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact depth or reason so
  later test improvements remain compatible.
- Existing tests and assertions in `tests/test_arrangement_engine.py` remain
  unchanged; new coverage is appended in a separate class.
- Payoff checks use relative comparisons against a base plan so the test stays
  aligned with existing density and amplitude clamp behavior.
- Automation interpolation is checked at representative points across each
  scene rather than exact full-curve equality, avoiding brittle coupling to
  every point value.
- Thinning assertions preserve primary voices and ensure support voices can be
  removed without erasing density gates or automation curves.
- Cadence quieting is validated with the same form and patch family while only
  changing `cadence_state`, isolating the intended behavior.
- No startup identity source changes are expected because the existing tree
  already has dedicated regression anchors for the generated hardening items.

## Acceptance Criteria

1. Existing arrangement-engine behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_arrangement_engine.py -q`

2. The new red-phase depth gate confirms
   `tests/test_arrangement_engine.py` reaches at least depth 2 after the
   end-to-end tests are added.
   VERIFY: `pytest tests/test_arrangement_engine_depth.py -q`

3. The new end-to-end class covers complete form planning, staged scene
   timelines, active-voice growth, support thinning, non-flat automation,
   payoff shaping, cadence quieting, register safety, and JSON-safe public
   dataclass output.
   VERIFY: `pytest tests/test_arrangement_engine.py::TestArrangementEngineEndToEnd -q`

4. The production arrangement source remains unchanged in behavior and still
   works through the public arrangement API.
   VERIFY: `python -c "import os, sys; sys.path.insert(0, os.path.join(os.getcwd(), 'my-claw', 'tools')); from senseweave.arrangement_engine import build_arrangement_plan; from senseweave.music_tracker import tracker_form_for_family; plan = build_arrangement_plan(patch_name='house_garden', family_name='bloom', cadence_state='occupied_day', progression_profile='open_day', form_templates=tracker_form_for_family('bloom', song_num=1)); assert plan.scenes['Development'].timeline is not None; print(plan.groove_family, len(plan.scenes))"`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2
   arrangement-engine test coverage.
   VERIFY: `grep -n "frac-0058" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
