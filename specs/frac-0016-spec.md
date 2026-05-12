# Task frac-0016 Specification: Lung Capacity Depth 2

## Problem Statement

`my-claw/tools/senseweave/render/rules/lung_capacity.py` provides the R11
wind/voice lung-capacity rule: it walks tracker scenes/songs and inserts or
tags breath steps wherever continuous wind or voice playback would exceed the
configured capacity window. The transformation works and is wired into the
render pipeline, but the module classifies at fractal depth 1 because most of
its surface is small private helpers (clamp, capacity-text, breath-detection,
metadata builders) and there is no public seam that produces a meaningful
end-to-end report from one apply pass.

This task deepens the module to a simple depth-2 implementation while
preserving the existing `LungCapacityRule.apply` / `apply_lung_capacity` /
`lung_capacity_seconds_for_voice` contracts. The new surface should compare a
score before and after the rule, produce stable per-lane breath statistics,
and emit JSON-safe operator summaries that tests and future diagnostics can
consume without re-walking tracker internals.

## Technical Approach

Extend `senseweave.render.rules.lung_capacity` in place with typed,
stdlib-only helpers. No new dependencies, migrations, runtime state files,
provider secrets, or agent commands are introduced.

- Add frozen dataclasses:
  - `LaneBreathStat(lane_name, voice, role, capacity_seconds,
    inserted_breath_count, tagged_breath_count, applies)` for one lane's
    breath outcome from a single apply pass.
  - `LungCapacityReport(score_kind, total_inserted, total_tagged, lane_stats)`
    for the full apply pass aggregate.
- Add `lane_breath_stat(original, rendered, *, rule)`:
  - Resolve `applies` via the same role / metadata gate `LungCapacityRule`
    uses.
  - Resolve `capacity_seconds` for the voice through the existing
    `lung_capacity_seconds_for_voice` helper so overrides and disabled values
    are honored consistently.
  - Count breath steps that exist in `rendered` but not at the same row in
    `original` as `inserted_breath_count`.
  - Count breath steps at rows that existed in `original` but were not breath
    in `original` and became breath-tagged in `rendered` as
    `tagged_breath_count`.
- Add `analyze_lung_capacity(score, *, k=1.0, seeds=None, roles=None,
  rule=None)`:
  - Run `apply_lung_capacity` once with the same arguments to produce the
    rendered score.
  - Walk lanes in pattern order (scene or song-of-scenes) and build a
    `LaneBreathStat` per lane.
  - Aggregate inserted and tagged breath counts into a `LungCapacityReport`.
  - Return a `(rendered, report)` tuple so callers can both consume the
    transformed score and inspect the report.
  - `score_kind` is `"scene"`, `"song"`, `"pattern"`, or `"unsupported"` based
    on input type, mirroring the existing dispatch in `apply_lung_capacity`.
- Add `summarize_lung_capacity_report(report)`:
  - Return a JSON-safe dictionary with `score_kind`, `total_inserted`,
    `total_tagged`, `lane_count`, `applied_lane_count`, and a `lanes` list
    where each entry contains `lane_name`, `voice`, `role`,
    `capacity_seconds` (float or `None`), `inserted_breath_count`,
    `tagged_breath_count`, and `applies`.
- Export the new public symbols from
  `senseweave.render.rules.__init__` (`LaneBreathStat`,
  `LungCapacityReport`, `analyze_lung_capacity`,
  `summarize_lung_capacity_report`).

Existing `LungCapacityRule`, `apply_lung_capacity`,
`lung_capacity_seconds_for_voice`, and the rule's `apply()` signature and
behavior remain unchanged.

## Edge Cases

- A score whose lanes never trigger breath insertion (non-wind/voice lanes,
  short phrases, disabled capacity) produces `inserted_breath_count = 0` and
  `tagged_breath_count = 0` for every lane and `total_inserted = total_tagged
  = 0` in the report.
- A `TrackerSong` with multiple scenes flattens lane stats across scenes in
  scene order; `score_kind` is `"song"`.
- A `TrackerPattern` directly (no scene wrapper) is supported via
  `apply_lung_capacity`'s existing default-tempo fallback; `score_kind` is
  `"pattern"`.
- An unsupported score type returns `(score, report)` where the report has
  empty `lane_stats`, zero counts, and `score_kind == "unsupported"`.
- Lane equality between original and rendered is by row position so that
  inserted breaths (new rows after the terminal) and tagged breaths (existing
  steps mutated to breath) are counted distinctly.

## Acceptance Criteria

1. Existing `LungCapacityRule` apply / `apply_lung_capacity` /
   `lung_capacity_seconds_for_voice` behavior remains unchanged.
   VERIFY: `pytest tests/test_lung_capacity_rule.py -q`

2. `lane_breath_stat` returns a frozen `LaneBreathStat` with correct
   inserted/tagged counts for a wind lane, and `applies=False` /
   `capacity_seconds=None` for a non-wind lane.
   VERIFY: `pytest tests/test_lung_capacity_depth.py::test_lane_breath_stat_counts_inserted_and_tagged_breaths tests/test_lung_capacity_depth.py::test_lane_breath_stat_marks_non_wind_lane_as_not_applying -q`

3. `analyze_lung_capacity` returns a `(rendered, report)` tuple where the
   rendered score is the same shape `apply_lung_capacity` would produce, and
   the report aggregates per-lane stats with the correct `score_kind` for
   scenes and songs.
   VERIFY: `pytest tests/test_lung_capacity_depth.py::test_analyze_lung_capacity_scene_returns_rendered_and_report tests/test_lung_capacity_depth.py::test_analyze_lung_capacity_song_aggregates_scenes -q`

4. `analyze_lung_capacity` handles unsupported score types without raising
   and reports zero totals.
   VERIFY: `pytest tests/test_lung_capacity_depth.py::test_analyze_lung_capacity_handles_unsupported_score -q`

5. `summarize_lung_capacity_report` returns a stable JSON-safe dictionary
   matching the spec's shape.
   VERIFY: `pytest tests/test_lung_capacity_depth.py::test_summarize_lung_capacity_report_returns_json_safe_summary -q`

6. Fractal depth for `my-claw/tools/senseweave/render/rules/lung_capacity.py`
   reaches at least depth 2.
   VERIFY: `pytest tests/test_lung_capacity_depth.py::test_lung_capacity_reaches_depth_two -q`

7. Startup identity hardening remains covered for standalone and federated
   startup paths.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
