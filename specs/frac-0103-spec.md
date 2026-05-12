# Task frac-0103 Specification: test_render_antipatterns Depth 2

## Problem Statement

`tests/test_render_antipatterns.py` covers the focused behavior of
`my-claw/tools/senseweave/render/antipatterns.py`: quantization ghosting,
dynamic compression, motif ossification, random-as-expression, symmetric arc
uncanny, dead-silence failure, generated-content dominance, sampler dominance,
and silent sampler-quintet-member detection. The production module already
implements the simple one-path detector functions required by the humanization,
generation, and sampler PRDs, and those functions return meaningful
`AntiPatternResult` records.

The missing frac-0103 work is to deepen the test module itself from helper-level
coverage to an explicit depth-2 contract. The test file needs a deterministic
depth gate and one named end-to-end class that drives a realistic rendered-piece
diagnostic through the public detector battery, warning/failure filtering, and
JSON-safe reporting.

The generated startup identity hardening bullets target the existing identity
startup subsystem, not this pure render-diagnostics module. Current regression
tests already cover `bootstrap_identity()` before `FirstBootAnnouncer`, CLI and
narrative ASGI startup, and standalone/federated identity persistence. This task
keeps those tests as mandatory hardening anchors rather than changing unrelated
startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_render_antipatterns_depth.py` with a deterministic depth
  gate requiring `tests/test_render_antipatterns.py` to contain
  `RenderAntipatternsEndToEndTests` and the method
  `test_full_antipattern_battery_reports_meaningful_json_safe_diagnostics`.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `RenderAntipatternsEndToEndTests` to
  `tests/test_render_antipatterns.py` without modifying existing assertions.
- Drive one meaningful public path through the existing detector surface:
  - build a synthetic rendered-piece mapping that intentionally trips a mix of
    failing and warning detectors while leaving other detectors green;
  - call `detect_antipatterns(...)` and assert the complete ordered detector
    battery returns non-empty `AntiPatternResult` records with populated names,
    details, severities, values, and thresholds where expected;
  - call `failing_antipatterns(...)` and assert it returns the same failed
    subset reported by the full battery;
  - assert warning severity remains non-blocking for
    `generated_content_dominance` and `sampler_dominating`, while blocking
    failures remain severity `fail`;
  - round-trip a combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Preserve existing production behavior unless the red tests expose a concrete
  gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one realistic mixed-result piece,
  not every threshold branch. Existing focused tests continue to own each
  detector's pass/fail thresholds and rolling-window behavior.
- The depth gate checks class and method names in addition to
  `sdp.fractal.classify_depth(...)`, so it remains meaningful even in checkouts
  where the fractal classifier is test-doubled.
- The synthetic rendered-piece mapping uses only JSON primitives so diagnostics
  can be consumed by metrics gates and operator tooling without custom encoding.
- Startup identity hardening remains covered by existing startup tests; no
  startup source changes are expected for this render-antipattern task.

## Acceptance Criteria

1. Existing render-antipattern detector assertions remain green.
   VERIFY: `pytest tests/test_render_antipatterns.py -q`

2. The depth gate confirms `tests/test_render_antipatterns.py` reaches depth
   >= 2 and contains the named end-to-end class/method.
   VERIFY: `pytest tests/test_test_render_antipatterns_depth.py -q`

3. `RenderAntipatternsEndToEndTests` drives the full public antipattern battery,
   failure filtering, warning/failure severity contract, and JSON-safe
   diagnostics.
   VERIFY: `pytest tests/test_render_antipatterns.py::RenderAntipatternsEndToEndTests -q`

4. The integrated metrics gate still sees anti-pattern failures through
   `evaluate_render_gate(...)`.
   VERIFY: `pytest tests/test_render_metrics.py::test_broken_render_fails_ci_gate -q`

5. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing task notes mention the frac-0103 render-antipattern test
   deepening.
   VERIFY: `grep -n "frac-0103" CHANGELOG.md progress.md ESCALATIONS.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
