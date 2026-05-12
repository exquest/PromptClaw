# Task frac-0020 Specification: Silence Budget Depth 2

## Problem Statement

`my-claw/tools/senseweave/render/rules/silence_budget.py` provides the R10
silence-budget rule for SenseWeave tracker material. It already walks
`TrackerScene`, `TrackerSong`, and `TrackerPattern` inputs, accumulates a
per-voice rest budget across phrases, and at threshold either extends the
existing inter-phrase breath (`silence_budget_breath_ext`) or zeros the next
phrase's velocities into a tacet block (`silence_budget_tacet`). It respects
role-filter gating, restraint-shaped thresholds, and returns the original
score for `k=0.0` or unsupported input.

The module currently classifies at fractal depth 1 (`6/11 trivial, 5 real`)
because trivial helpers and the `applies_to` / `apply` shims outnumber the
real-logic functions. This task deepens it to a simple depth-2 implementation
without changing existing rule semantics: add one typed analysis/report path
that applies the rule once, compares original and rendered tracker lanes, and
returns stable operator-readable silence-budget outcomes.

## Technical Approach

Extend `senseweave.render.rules.silence_budget` in place with stdlib-only,
typed helpers. No new dependencies, migrations, runtime state files, provider
secrets, database columns, or agent command strings are introduced.

- Add frozen dataclasses:
  - `LaneSilenceBudgetStat(lane_name, role, step_count, phrase_count,
    breath_extension_count, tacet_step_count, tacet_phrase_count, applies)`
    for one lane's R10 outcome from a single apply pass.
  - `SilenceBudgetReport(score_kind, total_breath_extensions,
    total_tacet_steps, lane_stats)` for the aggregate outcome of one
    analyzed score.
- Add `lane_silence_budget_stat(original, rendered, *, rule)`:
  - Resolve `applies` through the same `SilenceBudgetRule.applies_to()`
    role-and-metadata gate used by the rule.
  - Count distinct `phrase_id` values in the original lane (the rule
    operates per-phrase).
  - Count rendered steps tagged `silence_budget_breath_ext == "true"` as
    `breath_extension_count`.
  - Count rendered steps tagged `silence_budget_tacet == "true"` as
    `tacet_step_count`, and the number of distinct `phrase_id`s those
    tacet steps belong to as `tacet_phrase_count`.
  - Use the rendered lane's name and role for the output (R10 does not
    rename lanes).
- Add `analyze_silence_budget(score, *, k=1.0, seeds=None, roles=None,
  rule=None)`:
  - Run `apply_silence_budget` once with the same arguments to produce the
    rendered score.
  - Walk scene/song/pattern lanes in source order and build one
    `LaneSilenceBudgetStat` per lane.
  - Return `(rendered, report)` so callers can consume both the transformed
    score and the analysis output.
  - Use `score_kind` values `"scene"`, `"song"`, `"pattern"`, and
    `"unsupported"` to mirror existing apply dispatch.
- Add `summarize_silence_budget_report(report)`:
  - Return a JSON-safe dictionary containing `score_kind`,
    `total_breath_extensions`, `total_tacet_steps`, `lane_count`,
    `applied_lane_count`, and per-lane dictionaries with the dataclass fields.
- Export the new public symbols (`LaneSilenceBudgetStat`,
  `SilenceBudgetReport`, `analyze_silence_budget`,
  `lane_silence_budget_stat`, `summarize_silence_budget_report`) from
  `senseweave.render.rules.__init__`.

Existing `DEFAULT_TARGET_DENSITY`, `DEFAULT_THRESHOLD`,
`SilenceBudgetRule.apply`, and `apply_silence_budget` behavior remain
unchanged.

## Edge Cases

- Non-melodic, ostinato, or percussion lanes report `applies=False`,
  zero breath-extension and tacet counts.
- A lane with fewer than two phrases produces no R10 output and reports
  `breath_extension_count=0`, `tacet_step_count=0`,
  `tacet_phrase_count=0` even when `applies=True`.
- A lane below threshold reports zero counts and `applies=True`.
- A lane whose threshold trigger lands on an existing breath row reports
  `breath_extension_count >= 1` and `tacet_step_count=0`.
- A lane whose threshold trigger has no breath row between phrases reports
  `tacet_step_count` equal to the rendered tacet phrase length and
  `tacet_phrase_count=1`.
- `TrackerSong` reports flattened lane stats across scenes in scene order.
- Direct `TrackerPattern` inputs reuse the existing apply dispatch.
- Unsupported score types return the original object and an empty report
  with `score_kind="unsupported"`.
- The auto-generated startup hardening checks target the daemon identity
  subsystem, not R10 silence budget. The current tree already calls
  `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon startup
  paths and has integration coverage for standalone and federated identity
  persistence; this task keeps those as mandatory regression anchors.

## Acceptance Criteria

1. Existing silence-budget rule behavior remains unchanged.
   VERIFY: `pytest tests/test_silence_budget_rule.py -q`

2. `lane_silence_budget_stat` returns a frozen `LaneSilenceBudgetStat` with
   correct phrase count, breath-extension count, tacet-step count, tacet
   phrase count, and applies flag for an eligible melody lane that triggers
   the threshold via tacet.
   VERIFY: `pytest tests/test_silence_budget_depth.py::test_lane_silence_budget_stat_reports_tacet_lane -q`

3. `lane_silence_budget_stat` reports a breath extension when the threshold
   trigger lands on an existing breath row.
   VERIFY: `pytest tests/test_silence_budget_depth.py::test_lane_silence_budget_stat_reports_breath_extension -q`

4. `lane_silence_budget_stat` reports non-application for non-melodic and
   percussion lanes.
   VERIFY: `pytest tests/test_silence_budget_depth.py::test_lane_silence_budget_stat_marks_non_melodic_lane_as_not_applying -q`

5. `analyze_silence_budget` returns the same rendered score as
   `apply_silence_budget` and aggregates scene lane stats with the correct
   `score_kind`.
   VERIFY: `pytest tests/test_silence_budget_depth.py::test_analyze_silence_budget_scene_returns_rendered_and_report -q`

6. `analyze_silence_budget` aggregates song scenes in order, supports direct
   `TrackerPattern` inputs, and handles unsupported score types without
   raising.
   VERIFY: `pytest tests/test_silence_budget_depth.py::test_analyze_silence_budget_song_aggregates_scenes tests/test_silence_budget_depth.py::test_analyze_silence_budget_pattern_reports_pattern_kind tests/test_silence_budget_depth.py::test_analyze_silence_budget_handles_unsupported_score -q`

7. `summarize_silence_budget_report` returns a stable JSON-safe dictionary.
   VERIFY: `pytest tests/test_silence_budget_depth.py::test_summarize_silence_budget_report_returns_json_safe_summary -q`

8. Fractal depth for
   `my-claw/tools/senseweave/render/rules/silence_budget.py` reaches at
   least depth 2.
   VERIFY: `pytest tests/test_silence_budget_depth.py::test_silence_budget_reaches_depth_two -q`

9. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

10. Full project validation remains clean.
    VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
