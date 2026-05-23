# T-022d Specification - Meter Trajectory Arc-Cycle and Metadata Round-Trip Tests

## Problem Statement

CC-032 requires the composer to plan multi-scene meter trajectories per arc and
to carry that trajectory in scene metadata. T-022a/T-022b/T-022c added the data
model, composer planner, compact payload, and tracker metadata emission. The
remaining hardening gap is coverage:

- the planner currently needs a regression test for pieces that cross from one
  procedural arc cycle into the next;
- composed scene metadata needs an integration-style round-trip test that
  serializes a `ScoreTree`, restores it, compiles it, and verifies the same
  per-scene trajectory entry survives into tracker scenes.

## Technical Approach

- Add focused tests in `tests/test_score_tree_composer.py`.
- Drive the planner through public seams: `PlannedSection`,
  `directive_for_elapsed(...)`, `plan_meter_trajectory(...)`,
  `ScoreTree.to_json()`, `ScoreTree.from_dict(...)`, and
  `compile_score_tree_to_tracker(...)`.
- For arc-cycle coverage, build a synthetic section list spanning the end of one
  30-minute procedural arc and the start of the next. The first `Divination` and
  `Emergence` scenes in the second cycle must restart their phase drift table
  instead of inheriting occurrence counts from the previous cycle.
- For scene metadata round-trip coverage, compose a normal score tree, serialize
  and restore it, then compile the restored tree and assert that
  `meter_trajectory_entry`, flattened `meter_trajectory_*` keys, and the meter
  path are preserved for every section.
- Implement only the minimum production fix needed by the arc-cycle test.

## Edge Cases

- Repeated phases inside the same continuous arc segment may continue to advance
  through that phase's drift cells.
- A canonical wrap from `Crystallization` to `Divination` starts a new arc cycle
  and resets per-phase drift counts.
- Unknown phase names still fall back to the conservative default drift table.
- Empty section lists still return `None`.
- Metadata remains JSON-safe strings at the section and tracker scene boundary.
- This task does not change active tracker row timing, `groove_meter`
  selection, database schemas, migrations, dependencies, provider secrets, or
  startup identity wiring.
- The generated startup-hardening bullets are handled as mandatory regression
  anchors. Existing tests already cover `bootstrap_identity()` before
  `FirstBootAnnouncer`, first-boot persistence, and standalone/federated mode
  persistence.

## Acceptance Criteria

1. Meter trajectory planning restarts phase drift when a piece crosses into a
   new procedural arc cycle.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_plan_meter_trajectory_restarts_phase_drift_per_arc_cycle -q`

2. Composed meter trajectory scene metadata survives score-tree JSON
   round-trip and tracker compilation for every restored section.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_composed_meter_trajectory_scene_metadata_round_trips_through_json_and_tracker -q`

3. Existing T-022 trajectory, metadata emission, and tracker compiler anchors
   remain green.
   VERIFY: `pytest tests/test_score_tree.py::test_meter_trajectory_emits_scene_metadata_entry_payload tests/test_score_tree.py::test_score_tree_round_trips_meter_trajectory_and_scene_metadata tests/test_score_tree_composer.py::test_plan_meter_trajectory_uses_arc_phase_drift_table tests/test_score_tree_composer.py::test_recursive_composer_records_meter_trajectory_scene_entries tests/test_music_tracker.py::TestBuildKorsakovTrackerSong::test_emits_meter_trajectory_entries_from_compact_score_metadata tests/test_tracker_compiler.py::test_tracker_compiler_carries_meter_trajectory_scene_metadata -q`

4. Startup identity hardening anchors remain green without broadening this
   meter-trajectory task into startup rewiring.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Documentation and task metadata mention T-022d and accurately describe the
   behavior as trajectory-test hardening plus arc-cycle reset, not active meter
   scheduling.
   VERIFY: `rg -n "T-022d|arc-cycle meter trajectory|metadata round-trip" specs/t-022d-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

6. Full repository validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
