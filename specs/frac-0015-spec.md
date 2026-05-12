# Task frac-0015 Specification: Render Ablation Depth 2

## Problem Statement

`my-claw/tools/senseweave/render/ablation.py` provides the core CCH-010
ablation seam: filter selected active render rules, call an injected renderer,
and return the alternate render output. That one-path engine works and is
already used by the render debugger, but the module still classifies at
fractal depth 1 because its public surface only performs one render at a time
and does not produce a meaningful end-to-end report on its own.

This task deepens the ablation module to a simple depth-2 implementation while
preserving the existing `ablate()` contract. The new surface should build a
small ablation plan, execute that plan against the same renderer, preserve the
full-stack baseline, and return stable operator-readable summaries that tests
and future diagnostics can consume without reaching into debugger internals.

## Technical Approach

Extend `senseweave.render.ablation` in place with typed, stdlib-only helpers.
No new dependencies, migrations, runtime state files, provider secrets, or
agent commands are introduced.

- Add frozen dataclasses:
  - `AblationCase(disabled_rules, remaining_rule_ids, removed_rule_ids)` for
    one planned ablation run.
  - `AblationResult(disabled_rules, remaining_rule_ids, removed_rule_ids,
    rendered, changed, summary)` for one rendered ablation compared with the
    full-stack baseline.
  - `AblationSuite(rule_ids, baseline, results)` for a full baseline plus all
    requested ablation results.
- Add `rule_identifiers(active_rules)`:
  - Resolve each active rule through the same string / `.rule_id` / `.id`
    convention used by `filter_active_rules`.
  - Return rule IDs in active order.
- Add `build_ablation_cases(active_rules, disabled_rule_sets=None)`:
  - Default to one single-rule case per active rule.
  - Accept explicit iterable disabled-rule sets for pair or custom runs.
  - Deduplicate disabled IDs within a case while preserving caller order.
  - Validate unknown disabled IDs before returning cases.
  - Preserve remaining rule order from the active stack.
- Add `run_ablation_suite(score, seeds, *, active_rules, renderer,
  disabled_rule_sets=None)`:
  - Render the full active rule stack once as `baseline`.
  - Build cases and call the existing `ablate()` for each case.
  - Compare each ablated output to the baseline with equality and record a
    stable text summary.
- Add `summarize_ablation_suite(suite)`:
  - Return a JSON-safe dictionary with rule IDs, case counts, changed counts,
    unchanged counts, and per-case summaries.
- Export the new API from `senseweave.render.__init__`.

Existing `AblationRenderer`, `filter_active_rules`, and `ablate()` signatures
and behavior remain unchanged.

## Edge Cases

- Empty active rules produce an empty case list, a baseline render, and a suite
  summary with zero cases.
- Explicit empty disabled-rule sets are allowed and render the full rule stack;
  the result should normally be unchanged from baseline.
- Unknown disabled IDs raise `ValueError`, matching existing single-render
  ablation behavior.
- Rule objects without a non-empty string ID still raise `TypeError` through
  the shared identifier resolver.
- Startup identity hardening targets the daemon startup subsystem, not this
  pure render utility. The current tree already wires `bootstrap_identity()`
  before `FirstBootAnnouncer` in both daemon entrypoints; the existing
  standalone/federated identity tests remain mandatory regression anchors.

## Acceptance Criteria

1. Existing single-render ablation behavior remains unchanged.
   VERIFY: `pytest tests/test_render_ablation.py::TestAblate -q`

2. `build_ablation_cases` produces one single-rule case per active rule by
   default, preserving remaining-rule order and removed-rule IDs.
   VERIFY: `pytest tests/test_render_ablation.py::TestAblationSuite::test_build_ablation_cases_defaults_to_single_rule_plan -q`

3. `build_ablation_cases` accepts explicit pair/custom disabled sets and
   rejects unknown IDs.
   VERIFY: `pytest tests/test_render_ablation.py::TestAblationSuite::test_build_ablation_cases_accepts_custom_pairs tests/test_render_ablation.py::TestAblationSuite::test_build_ablation_cases_rejects_unknown_rule -q`

4. `run_ablation_suite` renders the full baseline once, executes each case
   through `ablate()`, and returns meaningful changed summaries.
   VERIFY: `pytest tests/test_render_ablation.py::TestAblationSuite::test_run_ablation_suite_returns_baseline_and_results -q`

5. `summarize_ablation_suite` returns a stable JSON-safe aggregate with case,
   changed, unchanged, and per-case summary fields.
   VERIFY: `pytest tests/test_render_ablation.py::TestAblationSuite::test_summarize_ablation_suite_returns_json_safe_counts -q`

6. Existing debugger and listener-review integration tests still pass.
   VERIFY: `pytest tests/test_render_debugger.py tests/test_listener_review.py -q`

7. Fractal depth for `my-claw/tools/senseweave/render/ablation.py` reaches at
   least depth 2.
   VERIFY: `pytest tests/test_render_ablation.py::test_render_ablation_reaches_depth_two -q`

8. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
