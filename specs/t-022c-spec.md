# T-022c Specification - Meter Trajectory Scene Metadata Emission

## Problem Statement

T-022a added the typed `MeterTrajectory` / `MeterSceneValue` score-tree carrier
and T-022b taught the recursive composer to plan meter trajectories. The
remaining gap is scene metadata emission: tracker scene construction should be
able to derive the matching per-scene trajectory entry from the compact planned
trajectory payload, so every emitted scene carries its own planned meter entry
without relying on manual test-time metadata injection.

## Technical Approach

- Keep the feature metadata-only. Do not change active tracker scheduling,
  `groove_meter` selection, row timing, metric-modulation application, database
  schemas, dependencies, or startup identity flow.
- Add a JSON-safe `meter_trajectory_entry` string to
  `MeterTrajectory.metadata_for_scene(...)`. The entry is the planned
  `MeterSceneValue` for that scene plus its index and scene count.
- Include ordered scene entries in the compact
  `arrangement_plan["meter_trajectory"]` composer payload, preserving existing
  summary fields such as `meter_path`.
- Teach `build_korsakov_tracker_song(...)` to read a compact
  `score.metadata["meter_trajectory"]` JSON payload and add the matching
  per-scene `meter_trajectory_*` metadata when a scene-specific score has not
  already supplied those keys.
- Preserve existing precedence: explicit scene-score `meter_trajectory_*`
  metadata wins over derived compact-payload metadata.

## Edge Cases

- Missing, malformed, non-JSON, or non-mapping `meter_trajectory` metadata is
  ignored.
- Scene entries with names not present in the emitted form are ignored.
- Scenes without a matching trajectory entry receive no derived
  `meter_trajectory_*` metadata.
- Existing flattened metadata from score-tree compilation is preserved and not
  overwritten by compact-payload derivation.
- `polymeter` remains a JSON string in emitted metadata and a list in the
  nested `meter_trajectory_entry` payload.
- Startup identity hardening remains covered by the existing regression anchor
  tests; this task does not broaden into unrelated startup rewiring.

## Acceptance Criteria

1. `MeterTrajectory.metadata_for_scene(...)` emits a JSON-safe
   `meter_trajectory_entry` string describing the matching scene value.
   VERIFY: `pytest tests/test_score_tree.py::test_meter_trajectory_emits_scene_metadata_entry_payload -q`

2. `compose_score_tree(...)` records ordered trajectory scene entries in
   `arrangement_plan["meter_trajectory"]`.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_recursive_composer_records_meter_trajectory_scene_entries -q`

3. Generic tracker scene emission derives per-scene meter trajectory metadata
   from a compact score metadata payload and attaches the matching entry to
   each scene.
   VERIFY: `pytest tests/test_music_tracker.py::TestBuildKorsakovTrackerSong::test_emits_meter_trajectory_entries_from_compact_score_metadata -q`

4. Existing score-tree compiler metadata remains explicit and complete,
   including the per-scene entry payload.
   VERIFY: `pytest tests/test_tracker_compiler.py::test_tracker_compiler_carries_meter_trajectory_scene_metadata -q`

5. Startup identity hardening anchors remain green without modifying unrelated
   startup flow.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Documentation and task metadata mention T-022c and accurately describe the
   behavior as metadata emission, not active meter scheduling.
   VERIFY: `rg -n "T-022c|meter trajectory scene metadata|meter_trajectory_entry" specs/t-022c-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

7. Full repository validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
