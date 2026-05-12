# Task frac-0102c Specification: Render-Ablation Final Artifact Assertion

## Problem Statement

`tests/test_render_ablation.py` already contains depth-2 coverage for the
render-ablation public surface in
`my-claw/tools/senseweave/render/ablation.py`. The existing end-to-end class
drives rule identification, filtering, single-rule ablation, case planning,
suite execution, summary generation, and JSON-safe diagnostics. It verifies
rendered trace events, but the final ablated render is still only checked as a
small event tuple.

The missing frac-0102c work is to add a depth-2 end-to-end assertion that
exercises the full ablation pipeline and pins the final rendered artifact's
shape and content. The production ablation API already preserves arbitrary
renderer output in `AblationSuite.results[*].rendered`, so this task should
deepen the test contract rather than change runtime behavior unless the red
test exposes a concrete gap.

The generated startup identity hardening bullets target the existing identity
startup subsystem, not this pure render-ablation utility. Current tests already
cover `bootstrap_identity()` invocation before `FirstBootAnnouncer` and identity
persistence for standalone and federated modes. This task keeps those tests as
mandatory hardening anchors.

## Technical Approach

- Extend `tests/test_test_render_ablation_depth.py` with a deterministic
  contract requiring `RenderAblationEndToEndTests` to contain a method named
  `test_full_pipeline_final_rendered_artifact_shape_and_content`.
- Confirm the red phase by running that depth/contract test before the method
  exists.
- Add the method to `RenderAblationEndToEndTests` in
  `tests/test_render_ablation.py` without modifying existing assertions.
- Use a deterministic test-only renderer that returns a JSON-shaped rendered
  artifact with:
  - `schema_version`;
  - `score_id`;
  - `seed_signature`;
  - `active_rule_ids`;
  - `sections`;
  - `events`;
  - `metadata`.
- Drive the full public ablation pipeline through the same scenario:
  `rule_identifiers(...)`, `filter_active_rules(...)`, `ablate(...)`,
  `build_ablation_cases(...)`, `run_ablation_suite(...)`, and
  `summarize_ablation_suite(...)`.
- Assert the final suite result's rendered artifact exactly matches the
  expected shape and content after disabling `phrase_arch` and `microtiming`,
  leaving only `metric_accent` active.
- Round-trip the final rendered artifact through
  `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Introduce no dependencies, migrations, provider secrets, database columns,
  runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The artifact renderer is synthetic and hermetic; it proves the ablation
  pipeline preserves a realistic structured artifact, not live audio rendering
  or real SenseWeave rule execution.
- Existing focused tests continue to own unknown disabled IDs, pair ordering,
  all-rules-off baseline equivalence, changed/unchanged counts, and summary
  shape.
- The final artifact uses only JSON primitives so operator-facing artifacts can
  be persisted or replayed without custom encoders.
- Startup identity hardening remains covered by existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests.

## Acceptance Criteria

1. The render-ablation depth gate requires the final-artifact end-to-end
   assertion method.
   VERIFY: `pytest tests/test_test_render_ablation_depth.py -q`

2. The new end-to-end assertion exercises the full public ablation pipeline and
   verifies the final rendered artifact shape/content.
   VERIFY: `pytest tests/test_render_ablation.py::RenderAblationEndToEndTests::test_full_pipeline_final_rendered_artifact_shape_and_content -q`

3. Existing render-ablation regression assertions remain green.
   VERIFY: `pytest tests/test_render_ablation.py tests/test_test_render_ablation_depth.py -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0102c render-ablation artifact
   assertion.
   VERIFY: `grep -n "frac-0102c" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
