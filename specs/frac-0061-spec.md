# Task frac-0061 Specification: test_breath_to_filter Depth 2

## Problem Statement

`tests/test_breath_to_filter.py` owns regression coverage for
`my-claw/tools/senseweave/breath_to_filter.py`, the pure stdlib helper that
maps the house's contact-mic breath rhythm (RMS envelope) to audio filter
sweep parameters and a face-display visual breathing animation. The
production module already provides one-path implementations of
`estimate_breath_rate`, `breath_phase`, `breath_to_filter_params`, and
`breath_to_visual_params`.

The current test file verifies the public functions with synthetic RMS
histories, but most assertions are short, single-call checks. The fractal
scanner reports `tests/test_breath_to_filter.py` at depth 1
(`24/32 trivial, 8 real`).

This task deepens `tests/test_breath_to_filter.py` to depth 2 by adding a
focused depth gate and a one-path end-to-end test class that exercises the
real public breath-to-filter API across complete synthetic breath cycles.
Existing assertions are preserved unchanged.

## Technical Approach

- Preserve `my-claw/tools/senseweave/breath_to_filter.py` behavior unless
  the new tests expose a real regression. The source module already produces
  meaningful output and needs no planned production changes.
- Add `tests/test_breath_to_filter_depth.py` with a red-phase assertion
  that `classify_depth("tests/test_breath_to_filter.py").depth >= 2`.
- Add a `TestBreathToFilterEndToEnd` class to
  `tests/test_breath_to_filter.py`. The methods use looped and table-driven
  assertions so the scanner records real test logic rather than trivial
  one-call checks.
- Drive one simple public path through the existing API:
  - Sweep multiple synthetic sine breath rates (3, 6, 12 BPM) through
    `estimate_breath_rate` → `breath_phase` →
    `breath_to_filter_params` → `breath_to_visual_params`, asserting
    rate detection within tolerance, valid phase, filter param ranges,
    visual param ranges, and that `mix` and visual amplitudes track rate.
  - Drive a flat/empty RMS signal end-to-end through the same pipeline
    and assert the neutral output contract (rate=0.0, mix=0.0,
    scale_factor=1.0, brightness_offset=0).
  - Sweep a phase table (0.0, 0.25, 0.5, 0.75, 1.0) through both
    `breath_to_filter_params` and `breath_to_visual_params` at a fixed
    rate, checking the documented inhale-opens-filter, resonance-at-
    extremes, scale-peaks-at-inhale, and brightness-mirrors-scale
    contracts in a single loop.
  - Verify the rate-driven `mix` saturation curve by stepping rate from
    0 BPM to >15 BPM and checking monotone non-decreasing mix that
    saturates at 1.0.
  - Confirm the public functions emit JSON-safe scalar/dict output that
    can feed downstream face-display and sampler diagnostics.
- Keep this test-only change stdlib-only. No new dependencies, migrations,
  provider secrets, runtime state files, database columns, HTTP routes, or
  auth changes are required.
- Treat the generated startup hardening bullets as mandatory verification
  anchors. Existing startup identity tests cover `bootstrap_identity()`
  persistence, standalone/federated reuse, CLI startup invocation,
  bootstrap-before-`FirstBootAnnouncer` ordering, and ASGI app import
  persistence; those tests are re-run in this task.

## Edge Cases

- The depth gate asserts `depth >= 2` rather than an exact depth or reason
  so later test improvements remain compatible.
- Existing tests and assertions in `tests/test_breath_to_filter.py` remain
  unchanged; new coverage is appended in a separate class.
- Synthetic sine breath rate assertions use tolerances (~1.5–2.0 BPM) to
  match the source module's autocorrelation precision.
- The flat-signal end-to-end path exercises the documented zero-rate
  fallback: cutoff returns to mid-band, mix=0.0, visual neutral.
- The phase sweep uses values at 0.0/0.25/0.5/0.75/1.0; resonance is
  checked with `>=` because cosine is exactly equal at 0.0 and 0.5
  (numerically zero at 0.25/0.75).
- Mix saturation is checked monotonically (non-decreasing) rather than
  strictly increasing, so the documented `min(rate/15, 1.0)` saturation
  plateau is acceptable.
- No startup identity source changes are expected because the existing
  tree already has dedicated regression anchors for the generated
  hardening items.

## Acceptance Criteria

1. Existing breath-to-filter behavioral tests remain unchanged and green.
   VERIFY: `pytest tests/test_breath_to_filter.py -q`

2. The new red-phase depth gate confirms
   `tests/test_breath_to_filter.py` reaches at least depth 2 after the
   end-to-end tests are added.
   VERIFY: `pytest tests/test_breath_to_filter_depth.py -q`

3. The new end-to-end class covers multi-BPM sine breath pipelines, flat-
   signal neutral output, phase-sweep filter/visual contracts, mix-rate
   saturation, and JSON-safe diagnostic output from the existing public
   API.
   VERIFY: `pytest tests/test_breath_to_filter.py::TestBreathToFilterEndToEnd -q`

4. The production breath-to-filter source remains unchanged in behavior
   and still works through the public API.
   VERIFY: `python -c "import os, sys, math; sys.path.insert(0, os.path.join(os.getcwd(), 'my-claw', 'tools', 'senseweave')); from breath_to_filter import estimate_breath_rate, breath_phase, breath_to_filter_params, breath_to_visual_params; hist=[0.15+0.1*math.sin(2*math.pi*6*i/600) for i in range(600)]; rate=estimate_breath_rate(hist, 0.1); phase=breath_phase(hist); fp=breath_to_filter_params(phase, rate); vp=breath_to_visual_params(phase, rate); assert abs(rate-6.0)<1.5 and 0.0<=phase<=1.0 and 200<=fp['cutoff_hz']<=2000 and 0.0<=fp['resonance']<=0.5 and 0.0<fp['mix']<=1.0 and 1.0-0.008<=vp['scale_factor']<=1.0+0.008 and -5<=vp['brightness_offset']<=5; print(round(rate,2), round(phase,3), fp, vp)"`

5. Startup identity hardening remains covered for first-run identity
   persistence, standalone/federated reuse, CLI startup invocation,
   bootstrap-before-announcer ordering, and ASGI app import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing progress and changelog notes mention the depth-2
   breath-to-filter test coverage.
   VERIFY: `grep -n "frac-0061" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
