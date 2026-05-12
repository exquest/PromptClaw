# Task frac-0023 Specification: Sampler Dispatch Depth 2

## Problem Statement

`my-claw/tools/senseweave/sampler_dispatch.py` owns the OSC dispatch path for
the `sw_sampler` granular voice. It already loads buffers through
`BufferLoader`, sends `/s_new sw_sampler ...`, folds `record.gain_db` into
linear amplitude, releases gates through `SamplerHandle`, schedules
fire-and-forget releases, applies per-mode FX presets through `EffectsBus`,
and computes pitch transposition through `transpose_to_key`.

The module currently classifies at fractal depth 1 (`9/17 trivial, 8 real`).
The shallow score comes from small Protocol methods, properties, and lifecycle
wrappers outnumbering the real dispatch helpers. This task deepens the module
to a simple depth-2 implementation without changing the existing OSC contract:
add one typed dispatch planning/report path that turns a concrete sample,
mode, key, and grain parameters into meaningful operator-readable output and
reuses the same synth argument builder as the live dispatch path.

## Technical Approach

Extend `senseweave.sampler_dispatch` in place with stdlib-only, typed helpers.
No new dependencies, migrations, runtime state files, provider secrets,
database columns, or agent command strings are introduced.

- Add frozen dataclass `SamplerDispatchPlan` containing:
  - sample identity and state: `sample_path`, `mode`, `key_name`,
    `buffer_id`, `buffer_loaded`.
  - grain/lifecycle parameters: `position`, `position_rate`,
    `grain_size_ms`, `density`, `density_band`, `pitch_transpose`,
    `effective_amp`, `fx_send`.
  - resolved outputs: ordered `fx_preset` key/value pairs and ordered
    `synth_arg_pairs` for the `/s_new sw_sampler` control surface.
- Add `grain_density_band(density)`:
  - Map grain density to `"sparse"`, `"moderate"`, `"dense"`, or
    `"saturated"` with fixed cutpoints at 8, 16, and 28 grains/sec.
- Add `sampler_synth_arg_pairs(...)`:
  - Return the canonical ordered key/value pairs for `bufnum`, `amp`,
    `grain_size_ms`, `density`, `position`, `position_rate`,
    `pitch_transpose_semitones`, and `fx_send`.
- Add `build_s_new_args(...)`:
  - Build the complete `/s_new` argument list by prefixing synth name,
    node id, add action, and target group, then appending
    `sampler_synth_arg_pairs`.
  - `SamplerDispatcher.dispatch_sample` should call this helper so the
    report path and live OSC path share the same argument ordering.
- Add `build_sampler_dispatch_plan(record, *, mode, key_name, position,
  position_rate, grain_size_ms, density, pitch_transpose=None, amp, fx_send)`:
  - Resolve `pitch_transpose` through `transpose_to_key(record, key_name)`
    when not explicitly supplied.
  - Resolve `effective_amp` through the existing gain-db correlation.
  - Resolve the mode preset through `get_fx_preset(mode)`.
  - Mark whether the record already has a loaded buffer.
- Add `summarize_sampler_dispatch_plan(plan)`:
  - Return a JSON-safe dictionary with the plan's source/mode/key, buffer
    state, density band, grain controls, effective amplitude, transposition,
    FX preset dict, and synth-argument dict.
- Keep `FX_PRESETS_BY_MODE`, `DEFAULT_FX_PRESET`, `get_fx_preset`,
  `EffectsBus`, `SamplerHandle`, `transpose_to_key`,
  `SamplerDispatcher.dispatch_sample`, `play_sampler`, `start_sampler`, and
  `stop_sampler` behavior compatible with existing tests.

## Edge Cases

- Density values at or below 8 grains/sec report `"sparse"`; values above 8
  through 16 report `"moderate"`; above 16 through 28 report `"dense"`; above
  28 report `"saturated"`.
- `build_sampler_dispatch_plan` reports `buffer_loaded=False` and
  `buffer_id=None` for unloaded records without loading the file; dispatch
  remains responsible for buffer acquisition.
- `build_sampler_dispatch_plan` reports `buffer_loaded=True` and the assigned
  buffer id after `SamplerDispatcher.dispatch_sample` has loaded the sample.
- `pitch_transpose=None` means "derive from record pitch and key"; an explicit
  numeric `pitch_transpose` is carried through unchanged.
- Unknown or `None` modes use `get_fx_preset`'s default preset in the report,
  matching `EffectsBus` fallback semantics.
- The generated startup hardening checks target the daemon identity
  subsystem, not sampler dispatch. The current tree already calls
  `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon startup
  paths and has integration coverage for standalone and federated identity
  persistence; this task keeps those tests as mandatory regression anchors.

## Acceptance Criteria

1. Existing sampler dispatch, handle release, lifecycle, FX preset, and
   transposition behavior remains unchanged.
   VERIFY: `pytest tests/test_sampler_dispatch.py -q`

2. `grain_density_band` maps densities to stable named bands at the documented
   cutpoints.
   VERIFY: `pytest tests/test_sampler_dispatch_depth.py::test_grain_density_band_maps_values_to_named_bands -q`

3. `build_sampler_dispatch_plan` returns a frozen `SamplerDispatchPlan` with
   effective gain-db amplitude, key-derived transposition, FX preset, density
   band, and canonical synth argument pairs for a loaded record.
   VERIFY: `pytest tests/test_sampler_dispatch_depth.py::test_build_sampler_dispatch_plan_resolves_loaded_record -q`

4. `build_s_new_args` emits the same ordered `/s_new sw_sampler` argument
   surface consumed by the live dispatcher.
   VERIFY: `pytest tests/test_sampler_dispatch_depth.py::test_build_s_new_args_uses_canonical_arg_order -q`

5. `summarize_sampler_dispatch_plan` returns a stable JSON-safe operator
   summary.
   VERIFY: `pytest tests/test_sampler_dispatch_depth.py::test_summarize_sampler_dispatch_plan_returns_json_safe_summary -q`

6. The plan output drives the existing end-to-end dispatch path: an unloaded
   record plans as pending, dispatch loads it and emits `/s_new`, and the
   post-dispatch plan's synth pairs match the actual OSC message.
   VERIFY: `pytest tests/test_sampler_dispatch_depth.py::test_sampler_dispatch_plan_drives_end_to_end_dispatch -q`

7. Fractal depth for `my-claw/tools/senseweave/sampler_dispatch.py` reaches at
   least depth 2.
   VERIFY: `pytest tests/test_sampler_dispatch_depth.py::test_sampler_dispatch_reaches_depth_two -q`

8. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
