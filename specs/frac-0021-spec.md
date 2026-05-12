# Task frac-0021 Specification: Rollout Controls Depth 2

## Problem Statement

`my-claw/tools/senseweave/rollout_controls.py` owns the runtime gates for
staged SenseWeave behavior. It already loads four independent environment
flags, preserves enabled-by-default behavior, and exposes
`effective_self_critique` so revision behavior only runs when preview metrics
and self-critique are both enabled. Downstream callers in
`practice_curriculum.py`, `self_critique.py`, `piece_commission.py`, and
`operator_diagnostics.py` consume those flags directly.

The module currently classifies at fractal depth 1 (`4/5 trivial, 1 real`)
because the public surface only resolves booleans and returns compact status
strings. This task deepens it to a simple depth-2 implementation by adding one
typed report path that turns an environment snapshot into meaningful
operator-readable rollout diagnostics while preserving existing flag semantics.

## Technical Approach

Extend `senseweave.rollout_controls` in place with stdlib-only, typed helpers.
No new dependencies, migrations, runtime state files, provider secrets,
database columns, or agent command strings are introduced.

- Add frozen dataclasses:
  - `RolloutFlagState(name, env_var, enabled, raw_value, default_enabled,
    source)` for one resolved rollout flag.
  - `RolloutControlReport(flags, flag_states, enabled_count,
    disabled_count, effective_self_critique)` for one environment snapshot.
- Add `flag_state(...)`:
  - Resolve one flag through the same truthy/falsy parser used by
    `load_feature_flags`.
  - Preserve `raw_value` for diagnostics.
  - Set `source` to `"default"` when unset, `"env"` when a recognized raw
    value is supplied, and `"defaulted"` when an unrecognized raw value falls
    back to the default.
- Add `rollout_control_report(env=None)`:
  - Build the same `SenseWeaveFeatureFlags` values as `load_feature_flags`.
  - Return per-flag state entries in stable rollout order: curriculum,
    preview, critique, suite.
  - Include enabled/disabled counts and `effective_self_critique`.
- Add `summarize_rollout_controls(report)`:
  - Return a JSON-safe dictionary with flag status, counts, effective
    critique state, and per-flag diagnostic records.
- Keep `SenseWeaveFeatureFlags.to_status_dict()` and `load_feature_flags()`
  behavior unchanged so current `/status`, practice selection, revision, and
  commissioning paths remain compatible.

## Edge Cases

- Missing environment values resolve to the existing default `True` and report
  `source="default"`.
- Recognized false values (`0`, `false`, `no`, `off`, `disabled`) turn only
  their own flag off and report `source="env"`.
- Recognized true values turn only their own flag on and report
  `source="env"`.
- Unrecognized values fall back to the default and report
  `source="defaulted"` so operators can see a typo without behavior changing.
- `effective_self_critique` is false when either preview render or
  self-critique is disabled, even if the raw self-critique flag is enabled.
- The generated startup hardening checks target the daemon identity subsystem,
  not rollout controls. The current tree already calls `bootstrap_identity()`
  before `FirstBootAnnouncer` in both daemon startup paths and has integration
  coverage for standalone and federated identity persistence; this task keeps
  those tests as mandatory regression anchors.

## Acceptance Criteria

1. Existing SenseWeave rollout flag behavior remains unchanged.
   VERIFY: `pytest tests/test_senseweave_rollout_controls.py -q`

2. `flag_state` returns a frozen `RolloutFlagState` with correct raw value,
   resolved boolean, default, and source for recognized environment values.
   VERIFY: `pytest tests/test_rollout_controls.py::test_flag_state_reports_env_value -q`

3. `flag_state` reports default and defaulted sources for missing and
   unrecognized environment values without changing defaults.
   VERIFY: `pytest tests/test_rollout_controls.py::test_flag_state_reports_default_and_defaulted_sources -q`

4. `rollout_control_report` builds the same flags as `load_feature_flags` and
   returns stable per-flag counts and effective self-critique state.
   VERIFY: `pytest tests/test_rollout_controls.py::test_rollout_control_report_matches_loaded_flags -q`

5. `summarize_rollout_controls` returns a stable JSON-safe operator summary.
   VERIFY: `pytest tests/test_rollout_controls.py::test_summarize_rollout_controls_returns_json_safe_summary -q`

6. The report output can drive the existing downstream behavior end-to-end
   without a second environment read.
   VERIFY: `pytest tests/test_rollout_controls.py::test_rollout_report_flags_drive_existing_behavior -q`

7. Fractal depth for `my-claw/tools/senseweave/rollout_controls.py` reaches
   at least depth 2.
   VERIFY: `pytest tests/test_rollout_controls.py::test_rollout_controls_reaches_depth_two -q`

8. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
