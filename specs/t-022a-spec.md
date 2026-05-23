# T-022a Specification — MeterTrajectory Model and Scene Metadata Carrier

## Problem Statement

CC-032 requires the composer to plan multi-scene meter trajectories where a
piece can move across meters such as `4/4 -> 15/16 -> 7/8`. T-020/T-021 already
added metric-modulation timing support, and current score-tree composition
already carries production arc metadata per scene. The missing first step is a
typed score-tree model for an arc-level meter plan plus a scene metadata carrier
that can preserve per-scene meter values through JSON round-trip and into
`TrackerScene.metadata`.

## Technical Approach

- Add score-tree dataclasses for:
  - `MeterSceneValue`: one scene's planned meter, subdivision, timing/breath
    policy, optional metric-modulation label, and optional polymeter overlay.
  - `MeterTrajectory`: the arc-level plan id/name plus ordered
    `MeterSceneValue` entries and JSON-safe metadata generation per scene.
- Add `SectionNode.scene_metadata: dict[str, str]` as the scene-level carrier.
- Add `ScoreTree.meter_trajectory: MeterTrajectory | None` for the canonical
  arc-level plan.
- Preserve both new fields through `ScoreTree.to_json()` /
  `ScoreTree.from_dict(...)`.
- Propagate `SectionNode.scene_metadata` through `compile_score_tree_to_tracker`
  so compiled `TrackerScene.metadata` exposes the trajectory. This slice only
  carries metadata; later T-022 slices can use it to choose active groove meters.

## Edge Cases

- Legacy score-tree JSON without `scene_metadata` or `meter_trajectory` must
  still load with empty per-section metadata and `meter_trajectory is None`.
- `MeterTrajectory.metadata_for_scene(...)` returns an empty dict when asked for
  a scene outside the trajectory.
- All emitted metadata values must be strings so existing tracker metadata
  handling remains stable.
- Polymeter overlays must serialize and restore as tuples in Python while
  remaining JSON-safe on disk.
- The generated startup-hardening bullets are treated as existing regression
  anchors, not as a request to modify startup identity flow for this meter task.

## Acceptance Criteria

1. The score-tree model exposes `MeterSceneValue` and `MeterTrajectory`, and a
   trajectory can emit JSON-safe scene metadata containing the arc-level plan and
   per-scene meter value.
   VERIFY: `pytest tests/test_score_tree.py::test_meter_trajectory_emits_scene_metadata -q`

2. `ScoreTree` JSON round-trips preserve `meter_trajectory` and each
   `SectionNode.scene_metadata` without breaking legacy score-tree loading.
   VERIFY: `pytest tests/test_score_tree.py::test_score_tree_round_trips_meter_trajectory_and_scene_metadata tests/test_score_tree.py::test_score_tree_from_legacy_payload_defaults_meter_fields -q`

3. Compiling a score tree to tracker scenes carries section `scene_metadata`
   into the matching `TrackerScene.metadata`, including meter-trajectory keys.
   VERIFY: `pytest tests/test_tracker_compiler.py::test_tracker_compiler_carries_meter_trajectory_scene_metadata -q`

4. Existing metric-modulation timing and startup identity anchors remain clean.
   VERIFY: `pytest tests/test_music_tracker.py::TestMetricModulationTiming::test_applies_three_to_two_modulation_from_target_row tests/test_music_tracker_runtime.py::TestScheduleScene::test_metric_modulation_changes_event_duration_and_row_sleeps_from_target_row tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

5. Full repository validation passes after implementation.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
