# Specification: T-039

## Problem Statement

CypherClaw's tuning primitives now exist, and faithful MIDI scenes can carry
`tuning_system_name`, `tuning_morph_target_name`, and `tuning_morph_curve`.
The score-tree composer still does not plan tuning by arc phase, so a composed
multi-scene arc has no composer-side evidence that Listen/Divination select
5-limit just intonation, Conversation/Procession select Slendro, or that
stillness-to-motion transitions request a morph.

## Technical Approach

Mirror the existing meter-trajectory pattern:

1. Add typed score-tree tuning trajectory models:
   - `TuningSceneValue`: one scene's arc phase, stillness/motion category,
     active tuning, optional morph target, morph curve, and transition kind.
   - `TuningTrajectory`: ordered scene values with metadata and log helpers.
2. Add `plan_tuning_trajectory(...)` in `senseweave.recursive_composer`.
   It will derive each section's arc phase from existing `ArcDirective`
   metadata, select a tuning system, detect category changes between adjacent
   sections, and mark those changes as tuning morph transitions.
3. Attach tuning metadata to every `SectionNode.scene_metadata`:
   `tuning_system_name`, `tuning_morph_target_name`, `tuning_morph_curve`,
   plus diagnostic `tuning_trajectory_*` keys.
4. Add a compact `arrangement_plan["tuning_trajectory"]` payload containing
   scene entries and composer log lines. The log line format is deterministic
   key/value text so tests and operators can grep for phase, tuning, and
   transition fields.
5. Preserve the tuning trajectory through `ScoreTree.to_json()` /
   `ScoreTree.from_dict()` and through tracker compilation.

## Phase Mapping

The PRD/design statement names `Listen`, `Divination`, `Conversation`, and
`Procession`. The current score-tree arc uses
`Divination -> Emergence -> Conversation -> Convergence -> Crystallization`.
T-039 therefore uses this conservative mapping:

- `Listen`, `Divination`, `Crystallization`: stillness,
  `just_intonation_5_limit`.
- `Conversation`, `Procession`, `Emergence`, `Convergence`: motion,
  `gamelan_slendro`.
- Unknown phases: legacy, `twelve_tet`, no morph transition.

The added `Crystallization`, `Emergence`, and `Convergence` mappings are the
engineering bridge from the existing five-phase composer arc to CypherClaw's
stillness/motion tuning rule.

## Edge Cases

- Empty section list returns `None` and emits no metadata.
- Missing directives default to legacy `twelve_tet` rather than guessing.
- Unknown phases are logged as `category=legacy` and never trigger morphs.
- The first scene in a trajectory cannot morph because there is no prior phase.
- Morphs are emitted only when adjacent categories cross between stillness and
  motion; repeated motion or repeated stillness scenes are steady.
- No database schema changes are required.
- No new dependencies are required.

## Startup Hardening

The generated startup hardening bullets target the existing identity subsystem,
not composer tuning. This checkout already invokes `bootstrap_identity()` before
`FirstBootAnnouncer` in MIDI intake and bootstraps identity on narrative API
startup. Existing integration tests cover standalone/federated persistence and
ASGI re-import persistence. T-039 will re-run those anchors and document that no
startup code changed.

## Acceptance Criteria

1. Composer tuning planning selects 5-limit JI for `Listen` and `Divination`,
   Slendro for `Conversation` and `Procession`, and marks stillness/motion
   morph transitions.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_plan_tuning_trajectory_applies_phase_rule_and_detects_morphs -q`

2. A 30-minute synthetic score-tree arc records a deterministic composer tuning
   log with one line per scene and detectable transition markers.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_recursive_composer_records_tuning_selection_log_for_30_minute_arc -q`

3. Composed scene metadata carries the required tuning fields and survives
   tracker compilation.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_composed_tuning_trajectory_survives_tracker_compile -q`

4. Tuning trajectory data round-trips through score-tree JSON without losing
   scene entries or transition metadata.
   VERIFY: `pytest tests/test_score_tree_composer.py::test_composed_tuning_trajectory_scene_metadata_round_trips_through_json -q`

5. Mandatory startup identity hardening anchors remain green for standalone and
   federated startup paths.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_midi_intake_daemon.py::test_main_invokes_bootstrap_identity tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Full repository validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
