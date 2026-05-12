# Task frac-0017 Specification: Metric Accent Depth 2

## Problem Statement

`my-claw/tools/senseweave/render/rules/metric_accent.py` provides the R1
metric-accent rule for SenseWeave tracker material. It already applies a
meter-position velocity table to eligible melodic lanes for `TrackerScene`,
`TrackerSong`, and `TrackerPattern` inputs, and existing tests pin the 4/4
table, meter table sizing, role gating, and grid-lock behavior.

The module still classifies at fractal depth 1 because its public surface is
mostly the transformation and small private helpers. The task is to deepen it
to a simple depth-2 implementation without changing existing rule semantics:
add one typed analysis/report path that applies the rule once, compares the
original and rendered tracker lanes, and produces stable operator-readable
output about which lanes were shaped and how strongly.

## Technical Approach

Extend `senseweave.render.rules.metric_accent` in place with stdlib-only,
typed helpers. No new dependencies, migrations, runtime state files, provider
secrets, database columns, or agent commands are introduced.

- Add frozen dataclasses:
  - `LaneMetricAccentStat(lane_name, role, meter, step_count,
    shaped_step_count, mean_multiplier, strongest_row, applies)` for one
    lane's metric-accent outcome from a single apply pass.
  - `MetricAccentReport(score_kind, total_shaped_steps, lane_stats)` for the
    aggregate outcome of one analyzed score.
- Add `lane_metric_accent_stat(original, rendered, *, meter, rule)`:
  - Resolve `applies` through the same `MetricAccentRule.applies_to()` role
    and metadata gate used by the rule.
  - Compare original/rendered steps by their existing order; metric accent
    does not insert or remove steps.
  - Count changed velocities as `shaped_step_count`.
  - Compute `mean_multiplier` from rendered/original velocity ratios for
    positive-velocity original steps, rounded to three decimals.
  - Resolve `strongest_row` from the highest rendered/original multiplier.
- Add `analyze_metric_accent(score, *, k=1.0, seeds=None, roles=None,
  rule=None)`:
  - Run `apply_metric_accent` once with the same arguments.
  - Walk scene/song/pattern lanes in source order and build one
    `LaneMetricAccentStat` per lane.
  - Return `(rendered, report)` so callers can consume both the transformed
    score and the analysis output.
  - Use `score_kind` values `"scene"`, `"song"`, `"pattern"`, and
    `"unsupported"` to mirror the existing apply dispatch.
- Add `summarize_metric_accent_report(report)`:
  - Return a JSON-safe dictionary containing `score_kind`,
    `total_shaped_steps`, `lane_count`, `applied_lane_count`, and per-lane
    dictionaries with the dataclass fields.
- Export the new public symbols from `senseweave.render.rules.__init__`.

Existing `METRIC_ACCENT_4_4`, `metric_accent_table`,
`MetricAccentRule.apply`, and `apply_metric_accent` behavior remain unchanged.

## Edge Cases

- Non-melodic or grid-locked lanes report `applies=False`,
  `shaped_step_count=0`, and `mean_multiplier=1.0`.
- A lane with no positive-velocity original steps reports
  `mean_multiplier=1.0` and `strongest_row=None`.
- `TrackerSong` reports flatten lane stats across scenes in scene order while
  preserving each scene's meter in the lane stat.
- Direct `TrackerPattern` inputs use the existing default `"4/4"` meter.
- Unsupported score types return the original object and an empty report with
  `score_kind == "unsupported"`.
- Startup identity hardening belongs to the daemon startup subsystem; the
  current tree already calls `bootstrap_identity()` before
  `FirstBootAnnouncer` in both daemon entrypoints, so this task re-runs the
  existing standalone/federated startup tests as regression anchors.

## Acceptance Criteria

1. Existing metric-accent rule behavior remains unchanged.
   VERIFY: `pytest tests/test_metric_accent_rule.py -q`

2. `lane_metric_accent_stat` returns a frozen `LaneMetricAccentStat` with
   correct shaped-step count, mean multiplier, strongest row, and applies flag
   for an eligible melody lane.
   VERIFY: `pytest tests/test_metric_accent_depth.py::test_lane_metric_accent_stat_reports_melody_shaping -q`

3. `lane_metric_accent_stat` reports non-application for grid-locked and
   non-melodic lanes.
   VERIFY: `pytest tests/test_metric_accent_depth.py::test_lane_metric_accent_stat_marks_non_melodic_lane_as_not_applying tests/test_metric_accent_depth.py::test_lane_metric_accent_stat_marks_grid_locked_lane_as_not_applying -q`

4. `analyze_metric_accent` returns the same rendered score as
   `apply_metric_accent` and aggregates scene lane stats with the correct
   `score_kind`.
   VERIFY: `pytest tests/test_metric_accent_depth.py::test_analyze_metric_accent_scene_returns_rendered_and_report -q`

5. `analyze_metric_accent` aggregates song scenes in order and handles
   unsupported score types without raising.
   VERIFY: `pytest tests/test_metric_accent_depth.py::test_analyze_metric_accent_song_aggregates_scene_meters tests/test_metric_accent_depth.py::test_analyze_metric_accent_handles_unsupported_score -q`

6. `summarize_metric_accent_report` returns a stable JSON-safe dictionary.
   VERIFY: `pytest tests/test_metric_accent_depth.py::test_summarize_metric_accent_report_returns_json_safe_summary -q`

7. Fractal depth for `my-claw/tools/senseweave/render/rules/metric_accent.py`
   reaches at least depth 2.
   VERIFY: `pytest tests/test_metric_accent_depth.py::test_metric_accent_reaches_depth_two -q`

8. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
