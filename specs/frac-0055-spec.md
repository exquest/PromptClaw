# Task frac-0055 Specification: test_accompaniment Depth 2

## Problem Statement

`tests/test_accompaniment.py` owns the regression coverage for the
Korsakov-style accompaniment helpers in
`my-claw/tools/senseweave/synthesis/accompaniment.py`: the sliding-window
`DensityTracker`, inverse-density `select_accompaniment_type`, the six
pattern generators, `pedal_note` / `should_pedal`, `breathing_swell`, and
`should_transition_gradually`. Each existing pytest method makes one or
two assertions on a single helper call, so the file currently classifies
at fractal depth 1 (`22/27 trivial, 5 real`) — most public test methods
are short, branchless calls that the fractal classifier counts as
trivial.

That leaves no end-to-end test surface in the same file: nothing covers
the realistic `density → selection → breathing → pattern → events` flow
in one place, nothing iterates the full Korsakov type table to check
shape invariants, and nothing verifies the inverse-density rule across a
density sweep. The depth-2 surface added by frac-0029 lives in
`tests/test_accompaniment_depth.py` and pins the typed report helpers,
not the original behavioral file.

This task deepens `tests/test_accompaniment.py` to a simple depth-2
implementation by adding one new `TestAccompanimentEndToEnd` class with
end-to-end pytest methods that drive the real public helpers through
multi-step scenarios and loops. The new tests are "real" by the
classifier (each contains a loop or more than three statements), do not
modify the existing locked behavioral assertions, and document the live
end-to-end flow in pytest form.

The auto-generated startup hardening bullets (narrative HTTP `/healthz`
+ `/readyz` endpoints, bearer-token `Authorization` header, and the
`tests/test_smoke_narrative_script.py` acceptance probe) target the
narrative HTTP service subsystem, not this accompaniment test file.
This task keeps those tests as mandatory regression anchors.

## Technical Approach

Extend `tests/test_accompaniment.py` in place with stdlib-only,
typed pytest test methods. No new dependencies, source-module changes,
migrations, runtime state files, provider secrets, database columns, or
agent command strings are introduced.

- Preserve every existing test class (`TestDensityTracker`,
  `TestSelectAccompanimentType`, `TestPatterns`, `TestPedalPoint`,
  `TestBreathing`, `TestTransition`) so the locked behavioral surface
  remains unchanged.
- Add a new `TestAccompanimentEndToEnd` class with end-to-end pytest
  methods. Each test method contains either a `for` loop or at least
  four statements so the fractal classifier counts it as "real" rather
  than trivial.
- The new tests drive the real public helpers — `DensityTracker`,
  `select_accompaniment_type`, `breathing_swell`,
  `should_transition_gradually`, `should_pedal`, `pedal_note`,
  `get_pattern`, and the six pattern generators — through realistic
  scenarios:
    - Sweep the documented density bands and verify the selection rule
      maps each band to the documented type.
    - Iterate every supported pattern type 1–6 and verify each
      generates a non-empty event list with positive amps and releases.
    - Sweep `breathing_swell` over rest / active / mid-density inputs
      and verify the monotonic adjustment.
    - Iterate adjacent / non-adjacent type pairs and verify
      `should_transition_gradually` matches the documented small-jump
      rule.
    - Walk a multi-bar phrase and verify `should_pedal` only fires at
      phrase boundaries and `pedal_note` returns a low, long-ringing
      tuple at every boundary.
    - Drive a synthetic melody through `DensityTracker`, then run the
      density into `select_accompaniment_type` and `get_pattern` to
      verify the dense-melody → sustained accompaniment inverse rule
      end-to-end.
- Add a single `test_test_accompaniment_reaches_depth_two` gate test
  that loads `sdp.fractal.classify_depth(...)` against
  `tests/test_accompaniment.py` and asserts the depth is at least 2.
- Use only `pytest`, `random`, and the existing accompaniment imports.
  No new imports beyond what the file already uses plus
  `sdp.fractal.classify_depth` for the depth gate.

## Edge Cases

- The selection rule is non-deterministic at low density (returns one of
  `{2, 4}`) and at rest (returns one of `{4, 5}`). Tests that exercise
  those bands seed `random.seed(0)` before calling so the loop
  outcomes are deterministic.
- `breathing_swell` caps at type 5 when resting and at type 1 when
  active, so the sweep test only asserts the in-range adjustment
  direction at each boundary.
- The pedal-walk test covers `bar_number` 0..7 with the default
  `bars_per_phrase=4`; phrase boundaries land on 0 and 4 only.
- The dense-melody end-to-end test injects a fixed timestamp window
  through `DensityTracker._timestamps` rather than calling `time.time()`
  in a loop, so the test stays deterministic without sleeping.
- The depth gate test asserts `result.depth >= 2`; it does not pin the
  exact depth string so future refactors that push the file to depth 3
  remain green.
- The narrative HTTP startup hardening bullets target the narrative API
  service. This task keeps `tests/test_smoke_narrative_script.py` plus
  the startup identity anchors as mandatory regression coverage.

## Acceptance Criteria

1. Existing accompaniment behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_accompaniment.py::TestDensityTracker tests/test_accompaniment.py::TestSelectAccompanimentType tests/test_accompaniment.py::TestPatterns tests/test_accompaniment.py::TestPedalPoint tests/test_accompaniment.py::TestBreathing tests/test_accompaniment.py::TestTransition -q`

2. The new end-to-end test class covers the documented density bands,
   pattern table, breathing sweep, transition adjacency, pedal walk,
   and dense-melody inverse rule end-to-end.
   VERIFY: `pytest tests/test_accompaniment.py::TestAccompanimentEndToEnd -q`

3. Fractal depth for `tests/test_accompaniment.py` reaches at least
   depth 2.
   VERIFY: `pytest tests/test_accompaniment.py::TestAccompanimentEndToEnd::test_test_accompaniment_reaches_depth_two -q`

4. The depth-2 helper surface added by frac-0029 remains green.
   VERIFY: `pytest tests/test_accompaniment_depth.py -q`

5. Narrative HTTP smoke acceptance probe and startup identity anchors
   remain covered.
   VERIFY: `pytest tests/test_smoke_narrative_script.py tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
