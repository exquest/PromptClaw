# Task frac-0087 Specification: test_lung_capacity_rule Depth 2

## Problem Statement

`tests/test_lung_capacity_rule.py` verifies the R11 lung-capacity rule at the
function level: default capacity resolution, override clamping, forced breath
insertion, existing-breath reuse, non-wind passthrough, and weak-step internal
breath tagging. The production module
`my-claw/tools/senseweave/render/rules/lung_capacity.py` already exposes the
depth-2 public reporting surface from frac-0016:

- `LaneBreathStat`
- `LungCapacityReport`
- `lane_breath_stat(...)`
- `analyze_lung_capacity(...)`
- `summarize_lung_capacity_report(...)`

The missing work for frac-0087 is to deepen the test file itself from
function-level checks to a named end-to-end test path proving the public rule
surface can apply the transformation, produce meaningful per-lane output, and
emit JSON-safe summaries in one deterministic path.

The generated startup identity hardening bullets are already represented in
this checkout by CLI, daemon-ordering, first-boot persistence, and narrative
ASGI startup tests. This task treats those as regression anchors rather than
changing unrelated startup flow without a concrete gap.

## Technical Approach

- Add a deterministic depth gate at
  `tests/test_test_lung_capacity_rule_depth.py` that requires
  `tests/test_lung_capacity_rule.py` to contain
  `LungCapacityRuleEndToEndTests` and classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Append `LungCapacityRuleEndToEndTests` to
  `tests/test_lung_capacity_rule.py` using the existing tracker fixtures.
- Exercise one public end-to-end path through:
  - `apply_lung_capacity(...)` and `LungCapacityRule.apply(...)`;
  - `analyze_lung_capacity(...)` for a scene with inserted, tagged, and
    non-applying lanes;
  - `summarize_lung_capacity_report(...)` for a JSON-safe operator summary;
  - song-level aggregation across multiple scenes.
- Preserve existing assertions and production behavior unless the new tests
  expose a concrete implementation gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state files, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end scene intentionally covers the simple happy path: one wind
  lane inserts a breath at the phrase boundary, one weak wind lane becomes a
  tagged internal breath, and one pluck lane does not apply.
- Existing focused tests remain responsible for individual capacity override,
  disabled capacity, existing breath reuse, and non-wind passthrough checks.
- Summary output must remain JSON-safe so render diagnostics can serialize it
  without custom encoders.
- Startup identity hardening remains scoped to the existing startup test
  anchors for CLI, daemon ordering, standalone/federated persistence, and ASGI
  import persistence.

## Acceptance Criteria

1. Existing lung-capacity rule assertions remain green.
   VERIFY: `pytest tests/test_lung_capacity_rule.py -q`

2. The depth gate confirms `tests/test_lung_capacity_rule.py` reaches depth
   >= 2 and contains `LungCapacityRuleEndToEndTests`.
   VERIFY: `pytest tests/test_test_lung_capacity_rule_depth.py -q`

3. `LungCapacityRuleEndToEndTests` drives one meaningful public rule path
   through scene analysis, inserted/tagged breath reporting, JSON-safe summary
   output, direct rule application, and song aggregation.
   VERIFY: `pytest tests/test_lung_capacity_rule.py::LungCapacityRuleEndToEndTests -q`

4. Existing production lung-capacity depth helpers remain green.
   VERIFY: `pytest tests/test_lung_capacity_depth.py -q`

5. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing task notes mention the frac-0087 lung-capacity rule test
   deepening.
   VERIFY: `grep -n "frac-0087" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
