# Task T-021 Specification: Row-Based Metric Modulation Timing

## Problem Statement

`my-claw/tools/senseweave/music_tracker.py` already carries metric-modulation
intent as metadata. `GrooveProfile.metric_modulation`, `ModulationEvent`, scene
metadata, and step metadata can label a section as `3:2` or `7:8`. The timing
owner, however, still treats every row in a scene as the same duration:
`60 / tempo_bpm / rows_per_beat`.

That means a modulation label is visible for diagnostics, but a modulation at a
specific row cannot change the timing of subsequent rows. T-021 makes tracker
scenes apply row-positioned metric modulations deterministically so a `3:2`
modulation at row `N` changes timing from row `N` forward while rows before
`N` remain unchanged.

The generated startup identity hardening bullets target the existing identity
startup subsystem. Current MIDI intake, CLI, first-boot, governor, and
narrative ASGI tests already cover `bootstrap_identity()` before
`FirstBootAnnouncer` plus standalone/federated identity persistence. This task
keeps those as regression anchors rather than widening a tracker timing change
into startup rewiring.

## Technical Approach

- Add a small typed metric-modulation model in `music_tracker.py`:
  - `MetricModulation(at_row, ratio_num, ratio_den)`
  - ratio values must be positive; invalid entries are ignored by timing
    helpers rather than crashing playback.
- Add pure row-timing helpers in `music_tracker.py`:
  - row-duration table for a scene;
  - row-start table for a scene;
  - duration summing across a row span.
- Define ratio semantics as duration scaling:
  - `3:2` multiplies row duration by `3 / 2` from `at_row` onward;
  - stacked modulations multiply cumulatively in row order.
- Keep row numbers, step row placement, lane ordering, and pattern length
  unchanged. The modulation changes elapsed timing, not the tracker grid.
- Update `music_tracker_runtime.py` to consume the row-duration helpers for
  scheduled event durations and row sleeps so runtime behavior matches the
  tracker model.
- Keep existing groove metadata labels intact.

## Edge Cases

- A modulation at row `0` applies to the whole scene.
- A modulation with `at_row` beyond the scene length has no effect.
- Multiple modulations at the same row apply in input order and multiply
  cumulatively.
- Event durations that span a modulation boundary sum each covered row
  independently, preserving the boundary position.
- Empty scenes still produce no timing rows and schedule no events.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state directories, or startup hooks are required.

## Acceptance Criteria

1. `music_tracker.py` applies a `3:2` modulation from row `N` onward and
   preserves pre-`N` timing.
   VERIFY: `pytest tests/test_music_tracker.py::TestMetricModulationTiming::test_applies_three_to_two_modulation_from_target_row -q`

2. Runtime event durations and row sleep intervals use the same modulated row
   timing table.
   VERIFY: `pytest tests/test_music_tracker_runtime.py::TestScheduleScene::test_metric_modulation_changes_event_duration_and_row_sleeps_from_target_row -q`

3. Existing tracker and groove behavior remains green.
   VERIFY: `pytest tests/test_music_tracker.py tests/test_music_tracker_runtime.py tests/test_groove_engine.py -q`

4. Startup identity hardening remains covered as a regression anchor.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention T-021 metric modulation timing.
   VERIFY: `rg -n "T-021|metric modulation" specs/t-021-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

6. Full validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
