# Task frac-0022 Specification: Sample Lab Depth 2

## Problem Statement

`my-claw/tools/senseweave/sample_lab.py` owns the EMSD environmental
sampling plans. It exposes `SAMPLE_SOURCES`, the `SAMPLE_SOURCE_ALIASES`
table, the `SAMPLE_FALLBACKS` table, and the public helpers
`canonical_sample_source_name`, `sample_source`, `sample_bank`, and
`plan_environmental_sampling`. Downstream callers in
`sample_dsp_activity.py`, `capstone_engine.py`, and `emsd_runtime.py`
consume those values directly.

The module currently classifies at fractal depth 1
(`4/6 trivial, 2 real`) because most public helpers are short pass-throughs
over the source/alias/fallback tables. This task deepens the module to a
simple depth-2 implementation by adding one typed report path that turns a
`SamplePlan` plus the resolved `SampleBank` into stable operator-readable
sampling diagnostics, while preserving every existing source, alias,
fallback rule, and `plan_environmental_sampling` outcome.

## Technical Approach

Extend `senseweave.sample_lab` in place with stdlib-only, typed helpers.
No new dependencies, migrations, runtime state files, provider secrets,
database columns, or agent command strings are introduced.

- Add frozen dataclasses:
  - `SamplePlanReport(source_name, hardware_label, source_type,
    capture_path, refresh_seconds, freshness_seconds, fallback_sources,
    cadence_state, section_function, transforms, transform_count, density,
    density_band, buffer_seconds, trigger_threshold, threshold_band,
    intensity, intensity_band, study_focus)` for one resolved sampling
    plan plus its bank/freshness view.
- Add `density_band(value)`:
  - Map a sample density to one of `"sparse"`, `"moderate"`, `"dense"`,
    or `"saturated"` using fixed cutpoints (0.20, 0.45, 0.70).
- Add `threshold_band(value)`:
  - Map a trigger threshold to one of `"hair"`, `"soft"`, `"firm"`, or
    `"guarded"` using fixed cutpoints (0.12, 0.18, 0.24).
- Add `intensity_band(value)`:
  - Map an intensity input to one of `"subtle"`, `"balanced"`, or
    `"vivid"` using fixed cutpoints (0.34, 0.67).
- Add `build_sample_plan_report(plan, *, intensity=0.5)`:
  - Resolve the same `SampleBank` as `sample_bank(plan.source.name)` so
    `freshness_seconds` and `fallback_sources` mirror the existing bank
    rule for the canonical source.
  - Carry the plan's transforms, density, buffer, threshold, study focus,
    cadence state, and section function through unchanged.
  - Compute `density_band`, `threshold_band`, and `intensity_band`
    through the public helpers above so callers see the same band
    boundaries.
- Add `summarize_sample_plan_report(report)`:
  - Return a JSON-safe dictionary containing the source identity
    (`source_name`, `hardware_label`, `source_type`, `capture_path`),
    refresh and freshness seconds, fallback list, plan shape (cadence
    state, section function, transforms tuple, transform count, density,
    density band, buffer seconds, trigger threshold, threshold band,
    intensity, intensity band, study focus). All values must be
    primitives or lists of primitives.
- Keep `SAMPLE_SOURCES`, `SAMPLE_SOURCE_ALIASES`, `SAMPLE_FALLBACKS`,
  `canonical_sample_source_name`, `sample_source`, `sample_bank`, and
  `plan_environmental_sampling` semantics unchanged so current
  `sample_dsp_activity`, `capstone_engine`, and `emsd_runtime` paths
  remain compatible.

## Edge Cases

- Density values at or below 0.20 report `"sparse"`; values above 0.20
  through 0.45 report `"moderate"`; through 0.70 report `"dense"`; above
  that report `"saturated"`. Boundary values land in the lower band.
- Threshold values at or below 0.12 report `"hair"`; through 0.18 report
  `"soft"`; through 0.24 report `"firm"`; above that report `"guarded"`.
- Intensity values at or below 0.34 report `"subtle"`; through 0.67 report
  `"balanced"`; above that report `"vivid"`.
- `build_sample_plan_report` resolves freshness and fallbacks through the
  canonical source name, so an alias-resolved plan (for example
  `perform_ve_condenser` → `room_mic`) sees the `room_mic` fallback list.
- Section function is carried through normalized to the same lowercase
  string `plan_environmental_sampling` already stores.
- Contact-source plans (e.g. `contact_mic`) keep the rule's threshold and
  density adjustments; the report only describes the resulting plan and
  does not reapply the contact bias.
- The auto-generated startup hardening checks target the daemon identity
  subsystem and the `cypherclaw.narrative_api` HTTP service, not
  environmental sampling. The current tree already calls
  `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon
  startup paths and has integration coverage for standalone and federated
  identity persistence; this task keeps those tests as mandatory
  regression anchors.

## Acceptance Criteria

1. Existing sample-lab behavior remains unchanged (sources, aliases,
   fallback banks, and `plan_environmental_sampling` cadence and
   section-function shaping).
   VERIFY: `pytest tests/test_sample_lab.py -q`

2. `density_band`, `threshold_band`, and `intensity_band` map values to
   stable named bands at their documented cutpoints.
   VERIFY: `pytest tests/test_sample_lab_depth.py::test_density_band_maps_values_to_named_bands tests/test_sample_lab_depth.py::test_threshold_band_maps_values_to_named_bands tests/test_sample_lab_depth.py::test_intensity_band_maps_values_to_named_bands -q`

3. `build_sample_plan_report` returns a frozen `SamplePlanReport` whose
   plan-shape fields match the resolved `SamplePlan` and whose
   bank/freshness fields match `sample_bank` for the canonical source.
   VERIFY: `pytest tests/test_sample_lab_depth.py::test_build_sample_plan_report_matches_plan_and_bank -q`

4. `build_sample_plan_report` carries section-function transforms and
   focus through the report when the plan has a section function.
   VERIFY: `pytest tests/test_sample_lab_depth.py::test_build_sample_plan_report_carries_section_function -q`

5. `build_sample_plan_report` resolves freshness and fallbacks through
   the canonical source when the plan was built from an alias.
   VERIFY: `pytest tests/test_sample_lab_depth.py::test_build_sample_plan_report_resolves_alias_to_canonical_bank -q`

6. `summarize_sample_plan_report` returns a stable JSON-safe operator
   summary.
   VERIFY: `pytest tests/test_sample_lab_depth.py::test_summarize_sample_plan_report_returns_json_safe_summary -q`

7. The report output can drive existing downstream behavior end-to-end
   without rebuilding the plan or re-resolving the bank.
   VERIFY: `pytest tests/test_sample_lab_depth.py::test_sample_plan_report_drives_existing_behavior -q`

8. Fractal depth for `my-claw/tools/senseweave/sample_lab.py` reaches at
   least depth 2.
   VERIFY: `pytest tests/test_sample_lab_depth.py::test_sample_lab_reaches_depth_two -q`

9. Startup identity hardening remains covered for standalone and
   federated startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

10. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
