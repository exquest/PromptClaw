# frac-0035 Spec: Tamagotchi Depth 2

## Problem Statement

`my-claw/tools/tamagotchi.py` owns the JSON-backed CypherClaw pet runtime for
Claude, Codex, Gemini, and CypherClaw. It already persists pets, records task
start/end transitions, decays idle stats, renders portraits through GlyphWeave,
and feeds daemon `/pets`, `/feed`, `/play`, startup, and heartbeat displays.

The module currently classifies at fractal depth 1 (`24/36 trivial, 12 real`)
because most of the public surface is simple state mutation or display shims.
This task deepens it to a simple depth-2 implementation by adding one typed
diagnostic path that turns existing pet state into meaningful health, activity,
and fleet summaries while preserving the current persistence and display
contracts.

## Technical Approach

- Keep `Pet`, `PetManager`, JSON persistence, stage thresholds, task XP, idle
  decay, and GlyphWeave sprite contracts unchanged.
- Add frozen dataclasses:
  - `PetVitalSnapshot` for one pet's resolved state, stats, task history,
    stage progress, health band, activity band, attention flag, and compact
    summary line.
  - `PetFleetReport` for aggregate fleet health, total XP/tasks, average stats,
    active/sleeping/attention agents, and the XP leader.
- Add stdlib-only typed helpers:
  - `pet_health_band(pet)` classifies one pet from mood, hunger, and energy.
  - `pet_activity_band(pet)` classifies one pet from task count and success
    rate.
  - `xp_to_next_stage(pet)` reports remaining XP before the next stage, or
    `None` at max stage.
  - `build_pet_vital_snapshot(pet)` builds one operator-readable snapshot.
  - `build_pet_fleet_report(pets)` builds one aggregate report in canonical pet
    order.
  - `summarize_pet_fleet_report(report)` returns a JSON-safe dictionary for
    status surfaces and logs.
- Add `PetManager.fleet_report()` so the persisted manager can produce the same
  report end-to-end after task transitions.
- Add type hints to touched function signatures. No new dependencies,
  migrations, provider secrets, database columns, or agent commands are
  introduced.

## Edge Cases

- Pets with no recorded tasks report `success_rate=None` and
  `activity_band="new"`.
- Max-stage pets report `xp_to_next_stage=None`.
- Unknown or missing pet class names display as `"Unclassed"` in diagnostic
  summaries while the existing portrait behavior remains unchanged.
- Empty fleet mappings produce zero totals, empty agent tuples, and no XP
  leader.
- Startup identity hardening is not changed by this task; existing tests verify
  first-boot persistence and bootstrap-before-announcer ordering for standalone
  and federated startup paths.

## Acceptance Criteria

1. Existing tamagotchi runtime behavior remains unchanged.
   VERIFY: `pytest tests/test_tamagotchi_runtime.py -q`

2. Pet health and activity helpers produce meaningful bands from existing pet
   stats and task history.
   VERIFY: `pytest tests/test_tamagotchi_depth.py::test_pet_health_and_activity_bands_are_meaningful -q`

3. `build_pet_vital_snapshot` returns a frozen typed snapshot with stage
   progress, success rate, class label, attention state, and a compact summary.
   VERIFY: `pytest tests/test_tamagotchi_depth.py::test_pet_vital_snapshot_reports_stage_progress_and_summary -q`

4. `build_pet_fleet_report` and `summarize_pet_fleet_report` return stable
   aggregate fleet diagnostics in canonical pet order.
   VERIFY: `pytest tests/test_tamagotchi_depth.py::test_pet_fleet_report_summarizes_health_and_attention -q`

5. The persisted `PetManager` path works end-to-end after task transitions and
   can produce the same fleet report after reload.
   VERIFY: `pytest tests/test_tamagotchi_depth.py::test_pet_manager_fleet_report_round_trips_through_persistence -q`

6. Fractal depth for `my-claw/tools/tamagotchi.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_tamagotchi_depth.py::test_tamagotchi_reaches_depth_two -q`

7. Startup identity hardening remains explicitly covered for first-boot
   identity persistence, standalone/federated modes, and
   bootstrap-before-announcer wiring.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

8. Required validation passes with no new dependency or migration.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
