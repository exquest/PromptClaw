# T-022b Specification — Composer Meter-Trajectory Planner

## Problem Statement

CC-032 requires the composer to plan multi-scene meter trajectories per arc.
T-022a added the typed `MeterTrajectory` carrier and compiler metadata
propagation, but `compose_score_tree(...)` still returns score trees with no
planned meter path unless tests or callers attach one manually. The composer
needs to generate an ordered sequence of meter values across the scenes in a
piece using the existing per-section arc phase analysis, then stamp each
section with JSON-safe `meter_trajectory_*` metadata.

## Technical Approach

- Add a deterministic meter-drift table in `recursive_composer.py`, keyed by
  CypherClaw arc phase names from `procedural_arc.py`.
- Add a small public helper, `plan_meter_trajectory(...)`, that accepts the
  planned sections plus their `ArcDirective` values and returns a
  `MeterTrajectory`.
- Keep the planner stdlib-only and deterministic. The section order, phase
  name, section function, transform strength, and cadence/groove context choose
  values from the drift table.
- Wire the helper into `compose_score_tree(...)` after
  `_production_arc_for_sections(...)` and before `SectionNode` creation.
- Attach the returned `MeterTrajectory` to `ScoreTree.meter_trajectory`.
- Stamp every composed `SectionNode.scene_metadata` with
  `trajectory.metadata_for_scene(section.scene_name)`.
- Add a compact composer-log payload to `arrangement_plan` so callers can
  inspect the planned path without rehydrating score-tree dataclasses.
- Do not change tracker row scheduling, active groove-meter selection, database
  schemas, migrations, startup identity wiring, or dependencies in this slice.

## Edge Cases

- Empty section lists return `None` from `plan_meter_trajectory(...)` and do
  not add metadata.
- Missing directives fall back to a stable default phase instead of failing.
- Unknown phase names fall back to a conservative `4/4`-centered path.
- Single-scene pieces still receive one scene value and a valid path.
- Metadata values remain strings through `MeterTrajectory.metadata_for_scene`.
- Existing `ScoreTree.from_dict(...)` legacy defaults from T-022a remain
  unchanged.
- Startup identity hardening remains covered by the existing regression anchor
  tests; this task does not broaden into identity startup rewiring.

## Acceptance Criteria

1. The composer exposes a deterministic helper that plans one
   `MeterSceneValue` per scene from arc phases and produces an ordered path
   that includes asymmetric meters for higher-complexity phases.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_plan_meter_trajectory_uses_arc_phase_drift_table -q`

2. `compose_score_tree(...)` automatically attaches `ScoreTree.meter_trajectory`
   and stamps every composed `SectionNode.scene_metadata` with matching
   `meter_trajectory_*` keys.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_recursive_composer_plans_meter_trajectory_for_full_arc -q`

3. A composed meter trajectory survives the score-tree-to-tracker handoff
   without manual test-time injection.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_composed_meter_trajectory_survives_tracker_compile -q`

4. Existing T-022a metadata carrier tests and T-021 metric-modulation timing
   anchors remain green.
   VERIFY: `pytest tests/test_score_tree.py::test_meter_trajectory_emits_scene_metadata tests/test_score_tree.py::test_score_tree_round_trips_meter_trajectory_and_scene_metadata tests/test_tracker_compiler.py::test_tracker_compiler_carries_meter_trajectory_scene_metadata tests/test_music_tracker.py::TestMetricModulationTiming::test_applies_three_to_two_modulation_from_target_row tests/test_music_tracker_runtime.py::TestScheduleScene::test_metric_modulation_changes_event_duration_and_row_sleeps_from_target_row -q`

5. Startup identity hardening remains covered without modifying unrelated
   startup flow.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Documentation and task metadata mention T-022b and accurately describe the
   behavior as composer planning plus metadata propagation, not active tracker
   meter scheduling.
   VERIFY: `rg -n "T-022b|meter trajectory planner|meter trajectories" specs/t-022b-spec.md CHANGELOG.md progress.md ESCALATIONS.md docs/architecture.md docs/handoff-protocol.md docs/startup-wizard.md docs/command-reference.md`

7. Full repository validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
