# Task frac-0052 Specification: temp_sampler_dispatch Depth 2

## Problem Statement

`temp_sampler_dispatch.py` is a root-level scratch copy of the SenseWeave
sampler dispatch module. It can be classified by the fractal scanner, but it
currently reports depth 1 (`7/13 trivial, 6 real`) because most public methods
are lifecycle shims and the module has no typed way to inspect the resolved
sampler dispatch before sending OSC.

The file is also ignored by `.gitignore` via `temp_*.py` and imports
`harmonic_planner` / `sampler_buffers` with package-relative imports, so a
direct `import temp_sampler_dispatch` fails outside the SenseWeave package.

This task deepens the temp module to a simple depth-2 implementation: one path,
meaningful helper output, and an end-to-end plan-to-dispatch test. The
production `my-claw/tools/senseweave/sampler_dispatch.py` behavior remains
unchanged.

## Technical Approach

- Keep the existing `SamplerDispatcher`, `SamplerHandle`, `get_fx_preset`,
  `transpose_to_key`, `play_sampler`, `start_sampler`, and `stop_sampler`
  behavior intact.
- Add import fallbacks so the root-level temp module can import
  `senseweave.harmonic_planner` and `senseweave.sampler_buffers` when loaded
  outside a package.
- Add a frozen `SamplerDispatchPlan` dataclass with the resolved sample path,
  mode, key, buffer state, grain controls, density band, pitch transpose,
  gain-adjusted amp, FX preset pairs, and canonical synth argument pairs.
- Add `grain_density_band(density)`, `sampler_synth_arg_pairs(...)`,
  `build_s_new_args(...)`, `build_sampler_dispatch_plan(...)`, and
  `summarize_sampler_dispatch_plan(...)`.
- Route `SamplerDispatcher.dispatch_sample` through `build_s_new_args` so live
  dispatch and diagnostics share the same `/s_new sw_sampler` argument order.
- Use only existing modules and the standard library. No dependencies,
  migrations, secrets, database columns, runtime state files, routes, or auth
  changes are required.

## Edge Cases

- Unknown or `None` modes use the existing `DEFAULT_FX_PRESET` when building a
  plan summary.
- Records with `buffer_id is None` report `buffer_loaded=False` and
  `buffer_state="pending_load"` in the JSON-safe summary.
- Records with `buffer_id` populated report `buffer_loaded=True` and
  `buffer_state="loaded"`.
- `pitch_transpose=None` derives the semitone value via existing
  `transpose_to_key`; explicit `pitch_transpose` values pass through.
- `record.gain_db` continues to fold into `effective_amp` with
  `amp * 10**(gain_db/20)`.
- Density bands are simple operator labels: `sparse`, `moderate`, `dense`,
  and `saturated`.
- The root temp file remains ignored by default; because the task explicitly
  targets it, the implementation commit will force-add it if needed.
- Startup identity hardening is out of the scratch-module write path and is
  verified through the existing CLI/daemon/first-boot regression anchors.

## Acceptance Criteria

1. The root temp module imports successfully and exposes the new planning
   helper surface.
   VERIFY: `pytest tests/test_temp_sampler_dispatch_depth.py::test_temp_sampler_dispatch_imports_with_planning_surface -q`

2. `grain_density_band` maps representative density values to meaningful
   operator labels.
   VERIFY: `pytest tests/test_temp_sampler_dispatch_depth.py::test_grain_density_band_maps_values_to_named_bands -q`

3. `build_sampler_dispatch_plan` resolves a loaded record into a frozen plan
   with key-derived transposition, gain-adjusted amp, FX preset pairs, and
   canonical synth arg pairs.
   VERIFY: `pytest tests/test_temp_sampler_dispatch_depth.py::test_build_sampler_dispatch_plan_resolves_loaded_record -q`

4. `build_s_new_args` emits the canonical `/s_new sw_sampler` argument order.
   VERIFY: `pytest tests/test_temp_sampler_dispatch_depth.py::test_build_s_new_args_uses_canonical_arg_order -q`

5. `summarize_sampler_dispatch_plan` returns a JSON-safe operator summary for
   unloaded/pending records.
   VERIFY: `pytest tests/test_temp_sampler_dispatch_depth.py::test_summarize_sampler_dispatch_plan_returns_json_safe_summary -q`

6. The dispatch plan drives the existing end-to-end dispatch path: before
   dispatch the buffer is pending, after dispatch the loaded plan's synth args
   match the emitted `/s_new` payload.
   VERIFY: `pytest tests/test_temp_sampler_dispatch_depth.py::test_sampler_dispatch_plan_drives_end_to_end_dispatch -q`

7. Fractal depth for `temp_sampler_dispatch.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_temp_sampler_dispatch_depth.py::test_temp_sampler_dispatch_reaches_depth_two -q`

8. Existing production sampler dispatch behavior remains unchanged.
   VERIFY: `pytest tests/test_sampler_dispatch.py tests/test_sampler_dispatch_depth.py -q`

9. Startup identity hardening remains covered for CLI startup and
   standalone/federated first-boot persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

10. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
