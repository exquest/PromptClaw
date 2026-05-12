# Task frac-0029 Specification: Accompaniment Depth 2

## Problem Statement

`my-claw/tools/senseweave/synthesis/accompaniment.py` owns the
Korsakov-style accompaniment helpers used by the live composer: a
sliding-window `DensityTracker`, inverse-density accompaniment type
selection, six pattern generators (`sustained`, `repeated_chords`,
`tremolo`, `arpeggiated`, `broken_figure`, `ostinato_cell`), pedal
point checks, breathing swells, and gradual/abrupt transition decisions.
Existing callers and `tests/test_accompaniment.py` rely on those helpers
returning concrete note tuples shaped as `(frequency, amp, release,
wait_after)` and a pedal tuple shaped as `(frequency, amp, release)`.

The module already works end-to-end for the one live path: a density
value selects a type, `get_pattern(...)` returns meaningful events, and
the pedal/transition helpers provide phrase-level behavior. It currently
classifies at fractal depth 1 (`13/18 trivial, 5 real`) because the
small one-return pattern and predicate helpers outnumber the real
tracking/selection logic. This task deepens the module to a simple
depth-2 implementation by adding a typed diagnostic/report surface that
delegates to the existing accompaniment path and produces stable
operator-readable output.

The generated startup hardening checks for `bootstrap_identity()` and
`FirstBootAnnouncer` target the daemon identity subsystem, not this
accompaniment pattern module. The current tree already calls
`bootstrap_identity()` before `FirstBootAnnouncer` in both daemon startup
paths and contains integration coverage for standalone/federated
identity persistence. This task keeps those tests as mandatory
regression anchors.

## Technical Approach

Extend `senseweave.synthesis.accompaniment` in place with stdlib-only,
typed helpers. No new dependencies, migrations, runtime state files,
provider secrets, database columns, or agent command strings are
introduced.

- Preserve `DensityTracker`, `select_accompaniment_type`,
  `make_scale`, every pattern helper, `PATTERNS`, `get_pattern`,
  `pedal_note`, `should_pedal`, `breathing_swell`, and
  `should_transition_gradually` behavior so `tests/test_accompaniment.py`
  remains unchanged.
- Add frozen dataclass `AccompanimentPatternSnapshot` containing one
  resolved pattern view: `pattern_type`, `pattern_name`, `energy_band`,
  `root_hz`, `fifth_hz`, `beat_seconds`, `loud`, `events`,
  `event_count`, `total_wait_seconds`, `max_release_seconds`,
  `mean_amp`, `min_frequency_hz`, `max_frequency_hz`, and
  `register_band_counts`.
- Add frozen dataclass `AccompanimentPlanReport` containing one
  accompaniment decision: `melody_density`, `melody_resting`,
  `density_band`, `current_type`, `selected_type`, `target_type`,
  `transition_mode`, `pedal_enabled`, `pedal_event`, `pattern`,
  `total_event_count`, `total_wait_seconds`, `max_release_seconds`,
  `mean_amp`, `lowest_frequency_hz`, `highest_frequency_hz`, and
  `active_pattern_names`.
- Add `accompaniment_density_band(melody_density, melody_resting)`:
  - `melody_resting` -> `"resting"`
  - `melody_density <= 1.0` -> `"sparse"`
  - `1.0 < melody_density <= 2.0` -> `"balanced"`
  - `2.0 < melody_density <= 3.0` -> `"busy"`
  - `melody_density > 3.0` -> `"dense"`
- Add `accompaniment_pattern_name(pattern_type)` returning the canonical
  names `"sustained"`, `"repeated_chords"`, `"tremolo"`,
  `"arpeggiated"`, `"broken_figure"`, and `"ostinato_cell"`, with
  `"repeated_chords"` as the fallback name to match `get_pattern`.
- Add `accompaniment_energy_band(pattern_type)`:
  - type 1 -> `"thin"`
  - types 2-3 -> `"supporting"`
  - types 4-5 -> `"filling"`
  - type 6 -> `"foreground"`
  - unknown values -> `"supporting"` because unknown types fall back to
    repeated chords.
- Add `frequency_register_band(frequency_hz)`:
  - `< 65.4` -> `"pedal"`
  - `65.4 <= value < 130.8` -> `"bass"`
  - `130.8 <= value < 523.3` -> `"middle"`
  - `>= 523.3` -> `"upper"`
- Add `accompaniment_transition_mode(current_type, target_type)`,
  returning `"gradual"` when `should_transition_gradually(...)` is true
  and `"section_cut"` otherwise.
- Add `summarize_pattern_events(events)`:
  - Return total event count, total wait seconds, max release seconds,
    mean amp, lowest/highest frequency, and register-band counts.
  - Round aggregate floats to 4 decimal places.
- Add `build_pattern_snapshot(pattern_type, root, fifth, beat, loud=0.7)`:
  - Resolve events through the existing `get_pattern(...)` helper.
  - Resolve name, energy band, event totals, and register-band counts.
  - Preserve event order as an immutable tuple of event tuples.
- Add `build_accompaniment_plan_report(...)`:
  - Resolve `selected_type` through `select_accompaniment_type(...)`.
  - Resolve `target_type` by applying `breathing_swell(...)` to the
    selected type.
  - Resolve the transition mode from the caller's `current_type` to the
    target type.
  - Resolve the pattern through `build_pattern_snapshot(...)`.
  - Resolve the optional phrase-boundary pedal through `should_pedal(...)`
    and `pedal_note(...)`.
  - Aggregate pattern plus pedal metrics into one plan-level report.
- Add `summarize_accompaniment_plan_report(report)` returning a JSON-safe
  dictionary containing all report fields, the nested pattern snapshot,
  register-band counts, active pattern names, and event tuples as lists.
- Keep the implementation simple and one-path: the report surface uses
  existing pattern generation and selection helpers rather than adding a
  second accompaniment algorithm.

## Edge Cases

- Band helper cutpoints are inclusive as documented above.
- Unknown pattern types report the same fallback name/energy as
  `get_pattern(...)`: repeated chords, `"supporting"`.
- `summarize_pattern_events` is tolerant of an empty sequence and reports
  zero counts/metrics, although the built-in patterns all produce events.
- `pedal_event` is `None` when `should_pedal(...)` is false.
- Plan-level `mean_amp` includes the pedal strike when present because it
  is an audible accompaniment event.
- Plan-level `total_wait_seconds` reflects only the pattern events; the
  pedal tuple has release but no wait-after field.
- Startup identity hardening is owned by the daemon identity subsystem and
  remains a regression anchor through
  `tests/test_first_boot.py::TestStartupIdentityPersistence` and
  `tests/test_governor_integration.py::TestStartupIdentityWiring`.

## Acceptance Criteria

1. Existing accompaniment tracking, selection, pattern, pedal, breathing,
   and transition behavior remains unchanged.
   VERIFY: `pytest tests/test_accompaniment.py -q`

2. Band/name helpers map density, pattern type, register, and transition
   values to the documented named values at their cutpoints.
   VERIFY: `pytest tests/test_accompaniment_depth.py::test_accompaniment_helper_bands_map_values_to_named_outputs -q`

3. `build_pattern_snapshot` returns a frozen
   `AccompanimentPatternSnapshot` whose fields mirror the existing
   `get_pattern(...)` output and event aggregates.
   VERIFY: `pytest tests/test_accompaniment_depth.py::test_build_pattern_snapshot_summarizes_existing_pattern_output -q`

4. `build_accompaniment_plan_report` returns a frozen
   `AccompanimentPlanReport` that performs the existing density selection,
   breathing adjustment, transition decision, pattern generation, and
   phrase-boundary pedal path end-to-end.
   VERIFY: `pytest tests/test_accompaniment_depth.py::test_build_accompaniment_plan_report_resolves_end_to_end_decision -q`

5. `summarize_accompaniment_plan_report` returns a stable JSON-safe
   operator summary that round-trips through `json.dumps`.
   VERIFY: `pytest tests/test_accompaniment_depth.py::test_summarize_accompaniment_plan_report_returns_json_safe_summary -q`

6. The new report path agrees with existing `select_accompaniment_type`,
   `breathing_swell`, `should_transition_gradually`, `should_pedal`,
   `pedal_note`, and `get_pattern` outputs for a deterministic live
   density case.
   VERIFY: `pytest tests/test_accompaniment_depth.py::test_accompaniment_plan_report_agrees_with_existing_helpers -q`

7. Fractal depth for `my-claw/tools/senseweave/synthesis/accompaniment.py`
   reaches at least depth 2.
   VERIFY: `pytest tests/test_accompaniment_depth.py::test_accompaniment_reaches_depth_two -q`

8. Startup identity hardening remains covered for first-boot persistence
   and startup wiring in both daemon entrypoints.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
