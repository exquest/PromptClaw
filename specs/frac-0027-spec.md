# Task frac-0027 Specification: EMSD Performance Depth 2

## Problem Statement

`my-claw/tools/senseweave/emsd_performance.py` owns the note-level playback
translation from an `EMSDLiveContext` into `PerformanceAdjustments`.
`duet_composer.play_voice()` consumes those adjustments directly when
building `/s_new` arguments, so existing fields such as
`amp_multiplier`, `release_multiplier`, `brightness_multiplier`,
`verb_add`, `dly_add`, `detune_add`, `highpass_hz`,
`saturation_add`, `sample_capture_path`, and `dsp_blocks` are part of
the live playback contract.

The module already works end-to-end for the one live path covered by
`tests/test_emsd_performance.py`: it reads the EMSD mix target, role
target, sampling plan, DSP block list, source type, Theramini ducking,
and voice name to produce meaningful render adjustments. It currently
classifies at fractal depth 1 (`3/5 trivial, 2 real`) because the small
math helpers and role-target lookup outnumber the real implementation
path. This task deepens the module to a simple depth-2 implementation by
adding one typed diagnostic/report surface that uses the existing
`render_adjustments_for_event(...)` path and turns a small batch of
resolved events into stable operator-readable output.

The generated startup hardening checks for `bootstrap_identity()` and
`FirstBootAnnouncer` target the daemon identity subsystem, not this pure
playback-shaping module. The current tree already contains startup
identity persistence and wiring tests; this task keeps them as mandatory
regression anchors.

## Technical Approach

Extend `senseweave.emsd_performance` in place with stdlib-only, typed
helpers. No new dependencies, migrations, runtime state files, provider
secrets, database columns, or agent command strings are introduced.

- Preserve `PerformanceAdjustments` and
  `render_adjustments_for_event(...)` behavior so the existing
  `duet_composer` playback path and `tests/test_emsd_performance.py`
  assertions remain unchanged.
- Add frozen dataclass `PerformanceEventSpec` containing the minimum
  event inputs needed for one diagnostic render: `role`, `voice_name`,
  `frequency_hz`, and `theramini_active`.
- Add frozen dataclass `PerformanceEventSnapshot` containing the event
  inputs plus the resolved adjustment diagnostics:
  `amp_multiplier`, `amp_band`, `release_multiplier`, `release_band`,
  `brightness_multiplier`, `brightness_band`, `space_amount`,
  `space_band`, `detune_add`, `highpass_hz`, `saturation_add`,
  `sample_capture_path`, and `dsp_blocks`.
- Add frozen dataclass `PerformanceAdjustmentReport` containing one
  batch summary: `snapshots`, `snapshot_count`, `roles`,
  `voice_names`, `dsp_blocks`, `sample_capture_paths`,
  `mean_amp_multiplier`, `max_release_multiplier`,
  `min_brightness_multiplier`, `space_total`, `frontline_ducked_count`,
  and `highpass_roles`.
- Add `amp_pressure_band(value)`:
  - `value < 0.75` -> `"recessed"`
  - `0.75 <= value <= 1.05` -> `"balanced"`
  - `value > 1.05` -> `"forward"`
- Add `release_shape_band(value)`:
  - `value < 0.95` -> `"tight"`
  - `0.95 <= value <= 1.1` -> `"natural"`
  - `value > 1.1` -> `"bloom"`
- Add `brightness_shape_band(value)`:
  - `value < 0.9` -> `"muted"`
  - `0.9 <= value <= 1.02` -> `"clear"`
  - `value > 1.02` -> `"bright"`
- Add `space_amount_band(value)`:
  - `value <= 0.02` -> `"dry"`
  - `0.02 < value <= 0.07` -> `"open"`
  - `value > 0.07` -> `"washed"`
- Add `build_performance_event_snapshot(spec, *, context)`:
  - Call `render_adjustments_for_event(...)` using the fields from
    `PerformanceEventSpec`.
  - Compute `space_amount` as `verb_add + dly_add`.
  - Classify amp, release, brightness, and space through the new band
    helpers.
  - Copy sample capture path and DSP blocks from the resolved
    `PerformanceAdjustments`.
- Add `build_performance_adjustment_report(snapshots)`:
  - Preserve snapshot order.
  - Raise `ValueError` for an empty sequence.
  - Compute first-seen ordered `roles`, `voice_names`,
    `sample_capture_paths`, and `dsp_blocks`.
  - Compute `mean_amp_multiplier`, `max_release_multiplier`,
    `min_brightness_multiplier`, and `space_total`, rounded to 4
    decimal places.
  - Count ducked frontline snapshots where `theramini_active` is true,
    role is one of `melody`, `counter`, or `color`, and
    `amp_multiplier < 1.0`.
  - Expose ordered `highpass_roles` for snapshots with
    `highpass_hz > 0.0`.
- Add `summarize_performance_adjustment_report(report)`:
  - Return a JSON-safe dictionary containing the aggregate report fields
    and a `snapshots` list whose entries mirror each snapshot field.
- Keep the implementation simple and one-path: the diagnostic surface
  delegates to the existing live adjustment function rather than
  introducing a second adjustment algorithm.

## Edge Cases

- Band helper cutpoints are inclusive as documented above.
- `build_performance_adjustment_report` raises `ValueError` for an empty
  sequence because there is no event to summarize.
- First-seen ordered tuples should de-duplicate roles, voices, sample
  capture paths, DSP blocks, and highpass roles without sorting.
- The null-context playback path remains unchanged:
  `render_adjustments_for_event(..., context=None, ...)` returns default
  neutral `PerformanceAdjustments`.
- Startup identity hardening is owned by the daemon identity subsystem
  and remains a regression anchor through
  `tests/test_first_boot.py::TestStartupIdentityPersistence` and
  `tests/test_governor_integration.py::TestStartupIdentityWiring`.

## Acceptance Criteria

1. Existing EMSD note-level playback adjustment behavior remains
   unchanged.
   VERIFY: `pytest tests/test_emsd_performance.py -q`

2. Band helpers map amp, release, brightness, and space values to the
   documented named bands at their cutpoints.
   VERIFY: `pytest tests/test_emsd_performance_depth.py::test_performance_band_helpers_map_values_to_named_bands -q`

3. `build_performance_event_snapshot` returns a frozen
   `PerformanceEventSnapshot` whose diagnostic fields match the existing
   live `render_adjustments_for_event(...)` output for one event.
   VERIFY: `pytest tests/test_emsd_performance_depth.py::test_build_performance_event_snapshot_matches_live_adjustments -q`

4. `build_performance_adjustment_report` returns a frozen
   `PerformanceAdjustmentReport` with ordered event snapshots, de-duplicated
   role/voice/DSP/sample metadata, and aggregate amp/release/brightness
   and space statistics.
   VERIFY: `pytest tests/test_emsd_performance_depth.py::test_build_performance_adjustment_report_summarizes_events -q`

5. `build_performance_adjustment_report` rejects an empty sequence.
   VERIFY: `pytest tests/test_emsd_performance_depth.py::test_build_performance_adjustment_report_rejects_empty_sequence -q`

6. `summarize_performance_adjustment_report` returns a stable JSON-safe
   operator summary that round-trips through `json.dumps`.
   VERIFY: `pytest tests/test_emsd_performance_depth.py::test_summarize_performance_adjustment_report_returns_json_safe_summary -q`

7. The new diagnostic path works end-to-end with `build_live_emsd_context`
   and the existing render-adjustment path, including Theramini frontline
   ducking and DSP block propagation.
   VERIFY: `pytest tests/test_emsd_performance_depth.py::test_performance_report_uses_live_context_end_to_end -q`

8. Fractal depth for `my-claw/tools/senseweave/emsd_performance.py`
   reaches at least depth 2.
   VERIFY: `pytest tests/test_emsd_performance_depth.py::test_emsd_performance_reaches_depth_two -q`

9. Startup identity hardening remains covered for first-boot persistence
   and startup wiring.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

10. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
