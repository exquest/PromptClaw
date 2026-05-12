# Task frac-0102 Specification: test_render_ablation Depth 2

## Problem Statement

`tests/test_render_ablation.py` covers the focused behavior of
`my-claw/tools/senseweave/render/ablation.py`: `ablate(...)` filters disabled
rules and reruns the injected renderer, `build_ablation_cases(...)` produces
single-rule and explicit-pair plans, `run_ablation_suite(...)` records
baseline-plus-results renders, and `summarize_ablation_suite(...)` returns a
JSON-safe per-case aggregate. A trailing `test_render_ablation_reaches_depth_two`
function pins the production module's depth, but the test file itself does not
yet have an explicit depth-2 contract or one end-to-end class that drives the
public ablation surface through a complete suite-and-summary flow.

The missing frac-0102 work is to make the depth-2 contract explicit for this
test module. The production module already exposes the simple one-path
implementation requested by the task: each public helper is typed,
deterministic, stdlib-only, and returns meaningful structured output. This task
therefore deepens the test surface with a deterministic depth gate plus one
end-to-end class that drives the existing public render-ablation surface
through a complete baseline → plan → suite → summary lifecycle.

The generated startup identity hardening bullets target the existing identity
startup subsystem, not this pure render utility. This checkout already wires
`bootstrap_identity()` before `FirstBootAnnouncer` in the daemon and
narrative ASGI startup paths, with standalone/federated identity persistence
covered by regression tests. This task keeps those tests as mandatory hardening
anchors rather than changing unrelated startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_render_ablation_depth.py` with a deterministic depth
  gate requiring `tests/test_render_ablation.py` to contain
  `RenderAblationEndToEndTests` and classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before
  `RenderAblationEndToEndTests` exists.
- Append `RenderAblationEndToEndTests` to `tests/test_render_ablation.py`
  without modifying existing locked assertions.
- Drive one meaningful render-ablation lifecycle inside the class:
  - assemble a stable three-rule active stack
    (`metric_accent`, `phrase_arch`, `microtiming`) and a deterministic
    test-only renderer that emits score/seed/rule events;
  - confirm `rule_identifiers(...)` and `filter_active_rules(...)` resolve the
    active stack and a single-rule disable;
  - call `ablate(...)` for the single-rule case and assert the rerendered
    events drop the disabled rule;
  - call `build_ablation_cases(...)` with default and explicit pair inputs and
    assert the planned cases match the active stack;
  - call `run_ablation_suite(...)` with single-rule and pair disabled sets and
    assert the baseline plus per-case rendered outputs, `changed` flags,
    `remaining_rule_ids`, and human-readable summaries;
  - call `summarize_ablation_suite(...)` and assert the JSON-safe aggregate
    matches the suite (rule IDs, case counts, changed/unchanged counts, and
    per-case summary entries);
  - serialize the combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Preserve existing production behavior unless the red tests expose a concrete
  gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one happy three-rule baseline plus
  one single-rule and one pair ablation. Existing focused tests continue to own
  unknown disabled IDs, all-rules-off baseline equivalence, custom pair
  ordering, and JSON-safe summary structure.
- Diagnostics serialize through `json.dumps(..., sort_keys=True)` so the
  payload contains only JSON primitives (lists, dicts, strings, ints, bools).
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests; this task does not change identity
  startup wiring.

## Acceptance Criteria

1. Existing render-ablation regression assertions remain green.
   VERIFY: `pytest tests/test_render_ablation.py -q`

2. The depth gate confirms `tests/test_render_ablation.py` reaches depth >= 2
   and contains `RenderAblationEndToEndTests`.
   VERIFY: `pytest tests/test_test_render_ablation_depth.py -q`

3. `RenderAblationEndToEndTests` drives one meaningful render-ablation
   lifecycle through `rule_identifiers`, `filter_active_rules`, `ablate`,
   `build_ablation_cases`, `run_ablation_suite`, `summarize_ablation_suite`,
   and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_render_ablation.py::RenderAblationEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0102 render-ablation test
   deepening.
   VERIFY: `grep -n "frac-0102" CHANGELOG.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
