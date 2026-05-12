# Task frac-0019 Specification: Punctuation Depth 2

## Problem Statement

`my-claw/tools/senseweave/render/rules/punctuation.py` provides the R6
punctuation-and-breath rule for SenseWeave tracker material. It already walks
`TrackerScene`, `TrackerSong`, and `TrackerPattern` inputs, lengthens terminal
notes at phrase boundaries, inserts seeded breath silences, respects
role-filter gating, preserves grid-locked terminal steps, and returns the
original score for `k=0.0` or unsupported input.

The module still classifies at fractal depth 1 because its public surface is
only the transformation plus small private helpers (`_clamp`,
`_terminal_indices`, `_apply_to_lane`, scene/pattern dispatch, and seeded RNG
plumbing). This task deepens it to a simple depth-2 implementation without
changing existing rule semantics: add one typed analysis/report path that
applies the rule once, compares original and rendered tracker lanes, and
returns stable operator-readable punctuation outcomes.

## Technical Approach

Extend `senseweave.render.rules.punctuation` in place with stdlib-only, typed
helpers. No new dependencies, migrations, runtime state files, provider
secrets, database columns, or agent command strings are introduced.

- Add frozen dataclasses:
  - `LanePunctuationStat(lane_name, role, step_count, terminal_note_count,
    extended_terminal_count, inserted_breath_count,
    mean_terminal_multiplier, mean_breath_ms, applies)` for one lane's R6
    outcome from a single apply pass.
  - `PunctuationReport(score_kind, total_extended_terminals,
    total_inserted_breaths, lane_stats)` for the aggregate outcome of one
    analyzed score.
- Add `lane_punctuation_stat(original, rendered, *, rule)`:
  - Resolve `applies` through the same `PunctuationRule.applies_to()` role
    and lane-metadata gate used by the rule.
  - Detect original terminal notes with the existing phrase grouping helper.
  - Compare original steps with rendered non-breath steps in source order
    because R6 inserts breath rows but does not remove source notes.
  - Count terminal notes whose `length_rows` changed as
    `extended_terminal_count`.
  - Count newly rendered `breath_r6` steps as `inserted_breath_count`.
  - Compute `mean_terminal_multiplier` from rendered/original terminal length
    ratios for positive-length original terminal notes, rounded to three
    decimals; lanes with no positive terminal lengths report `1.0`.
  - Compute `mean_breath_ms` from rendered `breath_ms` metadata, rounded to
    one decimal; lanes without inserted breaths report `0.0`.
- Add `analyze_punctuation(score, *, k=1.0, seeds=None, roles=None,
  rule=None)`:
  - Run `apply_punctuation` once with the same arguments to produce the
    rendered score.
  - Walk scene/song/pattern lanes in source order and build one
    `LanePunctuationStat` per lane.
  - Return `(rendered, report)` so callers can consume both the transformed
    score and the analysis output.
  - Use `score_kind` values `"scene"`, `"song"`, `"pattern"`, and
    `"unsupported"` to mirror existing apply dispatch.
- Add `summarize_punctuation_report(report)`:
  - Return a JSON-safe dictionary containing `score_kind`,
    `total_extended_terminals`, `total_inserted_breaths`, `lane_count`,
    `applied_lane_count`, and per-lane dictionaries with the dataclass fields.
- Export the new public symbols (`LanePunctuationStat`,
  `PunctuationReport`, `analyze_punctuation`, `lane_punctuation_stat`,
  `summarize_punctuation_report`) from `senseweave.render.rules.__init__`.

Existing `DEFAULT_TERMINAL_MULTIPLIER`, `MAX_TERMINAL_MULTIPLIER`,
`PunctuationRule.apply`, and `apply_punctuation` behavior remain unchanged.

## Edge Cases

- Non-melodic or lane-level grid-locked metadata lanes report
  `applies=False`, zero extension/breath counts, and
  `mean_terminal_multiplier=1.0`.
- A lane with a grid-locked terminal step can still report `applies=True` at
  lane level while `extended_terminal_count=0` and
  `inserted_breath_count=0`, matching current R6 behavior.
- A lane with no positive-length terminal notes reports
  `mean_terminal_multiplier=1.0`.
- A rendered lane without `breath_ms` metadata reports `mean_breath_ms=0.0`.
- `TrackerSong` reports flattened lane stats across scenes in scene order.
- Direct `TrackerPattern` inputs use the existing default tempo and
  rows-per-beat fallback from `apply_punctuation`.
- Unsupported score types return the original object and an empty report with
  `score_kind="unsupported"`.
- The auto-generated startup hardening checks target the daemon identity
  subsystem, not R6 punctuation. The current tree already calls
  `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon startup
  paths and has integration coverage for standalone and federated identity
  persistence; this task keeps those as mandatory regression anchors.

## Acceptance Criteria

1. Existing punctuation rule behavior remains unchanged.
   VERIFY: `pytest tests/test_punctuation_rule.py -q`

2. `lane_punctuation_stat` returns a frozen `LanePunctuationStat` with
   correct terminal count, extension count, inserted breath count, mean
   terminal multiplier, mean breath milliseconds, and applies flag for an
   eligible melody lane.
   VERIFY: `pytest tests/test_punctuation_depth.py::test_lane_punctuation_stat_reports_melody_breaths -q`

3. `lane_punctuation_stat` reports non-application for non-melodic and
   lane-level grid-locked lanes.
   VERIFY: `pytest tests/test_punctuation_depth.py::test_lane_punctuation_stat_marks_non_melodic_lane_as_not_applying tests/test_punctuation_depth.py::test_lane_punctuation_stat_marks_grid_locked_lane_as_not_applying -q`

4. `analyze_punctuation` returns the same rendered score as
   `apply_punctuation` and aggregates scene lane stats with the correct
   `score_kind`.
   VERIFY: `pytest tests/test_punctuation_depth.py::test_analyze_punctuation_scene_returns_rendered_and_report -q`

5. `analyze_punctuation` aggregates song scenes in order, supports direct
   `TrackerPattern` inputs, and handles unsupported score types without
   raising.
   VERIFY: `pytest tests/test_punctuation_depth.py::test_analyze_punctuation_song_aggregates_scenes tests/test_punctuation_depth.py::test_analyze_punctuation_pattern_reports_pattern_kind tests/test_punctuation_depth.py::test_analyze_punctuation_handles_unsupported_score -q`

6. `summarize_punctuation_report` returns a stable JSON-safe dictionary.
   VERIFY: `pytest tests/test_punctuation_depth.py::test_summarize_punctuation_report_returns_json_safe_summary -q`

7. Fractal depth for
   `my-claw/tools/senseweave/render/rules/punctuation.py` reaches at least
   depth 2.
   VERIFY: `pytest tests/test_punctuation_depth.py::test_punctuation_reaches_depth_two -q`

8. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

9. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
