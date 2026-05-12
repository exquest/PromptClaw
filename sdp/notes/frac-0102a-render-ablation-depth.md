# frac-0102a Render-Ablation Depth Notes

## Location And Current State

- Test file: `tests/test_render_ablation.py`
- Production file: `my-claw/tools/senseweave/render/ablation.py`
- Current `HEAD` already includes `RenderAblationEndToEndTests` from the parent
  frac-0102 work. These notes document the pre-depth-2 baseline at the parent of
  commit `8e43ac3`, where the file was still focused helper coverage rather
  than one connected lifecycle.

## Pre-Depth-2 Baseline

The baseline test surface used `DummyRule` plus `_render_trace(...)` to exercise
rule filtering and structured ablation outputs without invoking live
SenseWeave render rules, audio rendering, the debugger CLI, or provider-backed
services. It checked individual helper behavior, but it did not drive
`rule_identifiers`, `filter_active_rules`, `ablate`, `build_ablation_cases`,
`run_ablation_suite`, and `summarize_ablation_suite` through one shared
baseline-to-summary scenario.

## Exercised Paths

- `ablate(...)`: single-rule removal, pair removal, all-rules-disabled baseline
  equivalence, and unknown disabled-rule rejection through an injected renderer.
- `build_ablation_cases(...)`: default single-rule planning, explicit pair
  planning, remaining-rule ordering, removed-rule ordering, and unknown-rule
  rejection.
- `run_ablation_suite(...)`: baseline render, requested case execution,
  per-result disabled-rule metadata, first-result `remaining_rule_ids`,
  first-result rendered events, `changed=True`, and human summary formatting.
- `summarize_ablation_suite(...)`: JSON-shaped dict/list output with rule IDs,
  case counts, changed/unchanged counts, per-case disabled/remaining/removed
  rule IDs, changed flags, and summary strings.
- `test_render_ablation_reaches_depth_two(...)`: scanner gate for the production
  module path, not a coverage assertion for the test file itself.

## Smoke-Checked Outputs

- Pair ablation only checked `rendered["rule_ids"]` and `rendered["events"]`;
  it did not reassert the full rendered payload, score, or seed preservation.
- `run_ablation_suite(...)` checked the baseline rule IDs and first result in
  detail, while later requested results were only partially checked through
  their disabled-rule tuple.
- Summary output was compared to a JSON-shaped Python dict, but the baseline did
  not round-trip the diagnostic through `json.dumps(...)` / `json.loads(...)`.
- `_render_trace(...)` proved rule IDs were filtered from synthetic events; it
  did not prove any real render rule changed musical material.

## Concrete Gaps

- Gap: add one connected lifecycle test class named
  `RenderAblationEndToEndTests` that uses one rule stack and one score across
  identification, filtering, ablation, case planning, suite execution, summary,
  and JSON serialization.
- Gap: directly assert `rule_identifiers(...)` and `filter_active_rules(...)`
  in the test file, since the baseline reached them mostly through higher-level
  helpers.
- Gap: assert every requested suite result, including pair ablations and
  unchanged-render cases, instead of checking only the first result deeply.
- Gap: add a JSON round-trip assertion for the combined diagnostic payload so
  operator-facing summaries are proven serializable, not merely dict-shaped.
- Gap: add coverage for duplicate active rule IDs, duplicate disabled IDs, and
  the no-rule default-renderer path if future work wants stronger edge-case
  confidence beyond the depth-2 lifecycle.

## Depth-2 Completion

Depth-2 coverage of the render-ablation surface in
`my-claw/tools/senseweave/render/ablation.py` is complete. The locked test
class `RenderAblationEndToEndTests` in `tests/test_render_ablation.py` drives
one shared baseline through the full public pipeline
(`rule_identifiers`, `filter_active_rules`, `ablate`, `build_ablation_cases`,
`run_ablation_suite`, and `summarize_ablation_suite`), and the named method
`test_full_pipeline_final_rendered_artifact_shape_and_content` pins the final
rendered artifact's shape and content (with the `phrase_arch` and
`microtiming` rules disabled and only `metric_accent` active) plus a JSON
round-trip through `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
The depth gate `tests/test_test_render_ablation_depth.py` requires the class
and that named method to keep existing.

Gap closures by task ID:

- Closed: connected lifecycle test class `RenderAblationEndToEndTests` driving
  `rule_identifiers`, `filter_active_rules`, `ablate`,
  `build_ablation_cases`, `run_ablation_suite`, and
  `summarize_ablation_suite` from one shared rule stack and one shared score
  — landed by frac-0102.
- Closed: direct in-test assertions on `rule_identifiers(...)` and
  `filter_active_rules(...)` rather than only reaching them through higher
  helpers — landed by frac-0102.
- Closed: assertion of every requested suite result, including pair ablations
  and unchanged-render cases, instead of only the first result — landed by
  frac-0102.
- Closed: JSON round-trip assertion for the combined diagnostic payload of
  rule IDs, case counts, changed/unchanged counts, per-case summaries, and
  the final rendered artifact via `json.dumps(..., sort_keys=True)` and
  `json.loads(...)` — landed by frac-0102 (diagnostic payload) and deepened
  by frac-0102c (final artifact round-trip in
  `test_full_pipeline_final_rendered_artifact_shape_and_content`).
- Closed: structured final-render artifact assertion with
  `schema_version`, `score_id`, `seed_signature`, `active_rule_ids`,
  `sections`, `events`, and `metadata` — landed by frac-0102c.

Intentionally still open (not required for depth-2 closure, available for
future deepening):

- Open: duplicate active rule IDs and duplicate disabled IDs.
- Open: the no-rule default-renderer path.

The frac-0102d task ran the full validation gate
(`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
mypy src/`) on top of the merged frac-0102/0102a/0102b/0102c work and recorded
the result in `ESCALATIONS.md`.
