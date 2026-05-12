# Task frac-0018 Specification: Duration Contrast Depth 2

## Problem Statement

`my-claw/tools/senseweave/render/rules/duration_contrast.py` provides the R4
duration-contrast rule for SenseWeave tracker material. It walks
`TrackerScene`, `TrackerSong`, and `TrackerPattern` inputs, computes a per-lane
median note length, and rescales each note's `length_rows` toward a clamped
log-scaled multiplier so short notes get shorter and long notes get longer.
The rule is wired into the render pipeline and existing tests in
`tests/test_duration_contrast_rule.py` pin the short-shortened/long-lengthened
behavior, the `MIN_MULTIPLIER`/`MAX_MULTIPLIER` cap, role gating
(ostinato/percussion unchanged), `k=0` short-circuit, grid-locked step
preservation, and the equal-durations no-op.

The module still classifies at fractal depth 1 because its public surface is
the transformation plus small private helpers (`_clamp`,
`_duration_multiplier`, `_apply_contrast_to_lane`, `_apply_contrast_to_step`,
`_apply_to_pattern`, `_apply_to_scene`) and there is no public seam that
applies the rule once and reports back per-lane shaping outcomes. This task
deepens the module to a simple depth-2 implementation without changing any
existing rule semantics: add one typed analysis/report path that compares the
original and rendered tracker lanes and produces stable operator-readable
output about which lanes were shaped and how strongly.

## Technical Approach

Extend `senseweave.render.rules.duration_contrast` in place with stdlib-only,
typed helpers. No new dependencies, migrations, runtime state files, provider
secrets, database columns, or agent commands are introduced.

- Add frozen dataclasses:
  - `LaneDurationContrastStat(lane_name, role, step_count,
    shaped_step_count, mean_multiplier, longest_row, shortest_row, applies)`
    for one lane's duration-contrast outcome from a single apply pass.
  - `DurationContrastReport(score_kind, total_shaped_steps, lane_stats)` for
    the aggregate outcome of one analyzed score.
- Add `lane_duration_contrast_stat(original, rendered, *, rule)`:
  - Resolve `applies` through the same `DurationContrastRule.applies_to()`
    role and metadata gate used by the rule.
  - Compare original/rendered steps by their existing order; duration
    contrast does not insert or remove steps.
  - Count steps whose `length_rows` differ between rendered and original as
    `shaped_step_count`.
  - Compute `mean_multiplier` from rendered/original length ratios for
    positive-length original steps, rounded to three decimals; lanes with no
    positive-length original steps report `mean_multiplier=1.0`.
  - Resolve `longest_row` as the row of the step with the highest
    rendered/original ratio (the most lengthened step), and `shortest_row`
    as the row with the lowest ratio (the most shortened step). Lanes with
    no positive-length original steps report both as `None`.
- Add `analyze_duration_contrast(score, *, k=1.0, seeds=None, roles=None,
  rule=None)`:
  - Run `apply_duration_contrast` once with the same arguments to produce the
    rendered score (`seeds` is accepted and discarded to mirror the existing
    `DurationContrastRule.apply()` signature).
  - Walk scene/song/pattern lanes in source order and build one
    `LaneDurationContrastStat` per lane.
  - Return `(rendered, report)` so callers can consume both the transformed
    score and the analysis output.
  - Use `score_kind` values `"scene"`, `"song"`, `"pattern"`, and
    `"unsupported"` to mirror the existing apply dispatch.
- Add `summarize_duration_contrast_report(report)`:
  - Return a JSON-safe dictionary containing `score_kind`,
    `total_shaped_steps`, `lane_count`, `applied_lane_count`, and per-lane
    dictionaries with the dataclass fields (`lane_name`, `role`,
    `step_count`, `shaped_step_count`, `mean_multiplier`, `longest_row`,
    `shortest_row`, `applies`).
- Export the new public symbols (`LaneDurationContrastStat`,
  `DurationContrastReport`, `analyze_duration_contrast`,
  `lane_duration_contrast_stat`, `summarize_duration_contrast_report`) from
  `senseweave.render.rules.__init__`.

Existing `MIN_MULTIPLIER`, `MAX_MULTIPLIER`, `DurationContrastRule.apply`,
and `apply_duration_contrast` behavior remain unchanged.

## Edge Cases

- Non-melodic or grid-locked-metadata lanes report `applies=False`,
  `shaped_step_count=0`, and `mean_multiplier=1.0` so callers can
  distinguish gated lanes from no-op shaping.
- A lane with no positive-length original steps reports
  `mean_multiplier=1.0`, `longest_row=None`, and `shortest_row=None`.
- A lane with only one positive-length step (where `_apply_contrast_to_lane`
  short-circuits and returns the lane unchanged) reports
  `shaped_step_count=0`, `mean_multiplier=1.0`, and `longest_row` /
  `shortest_row` resolved from the single ratio (1.0 by definition).
- `TrackerSong` reports flatten lane stats across scenes in scene order.
- Direct `TrackerPattern` inputs report `score_kind="pattern"`.
- Unsupported score types return the original object and an empty report
  with `score_kind="unsupported"`.
- The auto-generated narrative API hardening checks (`/healthz` + `/readyz`,
  `X-Narrative-Auth` shared-secret header) are scoped to
  `cypherclaw.narrative_api`; they are not relevant to this SenseWeave
  render-rule module and are addressed as anchors via the existing narrative
  smoke test in `tests/test_smoke_narrative_script.py`. The
  `bootstrap_identity()` startup identity hardening is covered by re-running
  `tests/test_first_boot.py::TestStartupIdentityPersistence` and
  `tests/test_governor_integration.py::TestStartupIdentityWiring`.

## Acceptance Criteria

1. Existing duration-contrast rule behavior remains unchanged.
   VERIFY: `pytest tests/test_duration_contrast_rule.py -q`

2. `lane_duration_contrast_stat` returns a frozen
   `LaneDurationContrastStat` with correct shaped-step count, mean
   multiplier, longest row, shortest row, and applies flag for an eligible
   melody lane.
   VERIFY: `pytest tests/test_duration_contrast_depth.py::test_lane_duration_contrast_stat_reports_melody_shaping -q`

3. `lane_duration_contrast_stat` reports non-application for non-melodic
   and grid-locked-metadata lanes.
   VERIFY: `pytest tests/test_duration_contrast_depth.py::test_lane_duration_contrast_stat_marks_non_melodic_lane_as_not_applying tests/test_duration_contrast_depth.py::test_lane_duration_contrast_stat_marks_grid_locked_lane_as_not_applying -q`

4. `analyze_duration_contrast` returns the same rendered score as
   `apply_duration_contrast` and aggregates scene lane stats with the
   correct `score_kind`.
   VERIFY: `pytest tests/test_duration_contrast_depth.py::test_analyze_duration_contrast_scene_returns_rendered_and_report -q`

5. `analyze_duration_contrast` aggregates song scenes in order and handles
   unsupported score types without raising.
   VERIFY: `pytest tests/test_duration_contrast_depth.py::test_analyze_duration_contrast_song_aggregates_scenes tests/test_duration_contrast_depth.py::test_analyze_duration_contrast_handles_unsupported_score -q`

6. `summarize_duration_contrast_report` returns a stable JSON-safe
   dictionary.
   VERIFY: `pytest tests/test_duration_contrast_depth.py::test_summarize_duration_contrast_report_returns_json_safe_summary -q`

7. Fractal depth for
   `my-claw/tools/senseweave/render/rules/duration_contrast.py` reaches at
   least depth 2.
   VERIFY: `pytest tests/test_duration_contrast_depth.py::test_duration_contrast_reaches_depth_two -q`

8. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
