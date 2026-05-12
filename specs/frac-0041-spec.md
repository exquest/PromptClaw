# Task frac-0041 Specification: PromptClaw Paths Depth 2

## Problem Statement

`promptclaw/paths.py` owns the canonical filesystem contract for PromptClaw
projects and runs: artifact roots, memory, prompts, run input/routing/prompts,
outputs, handoffs, summaries, logs, and state files. Existing callers use
`ProjectPaths` throughout the orchestrator, artifact manager, memory store,
state store, and CLI status path.

The module currently classifies at fractal depth 1 because every public method
is a direct path projection. Callers can resolve one path at a time, but there
is no typed layout object, JSON-safe path summary, or path-owned way to prepare
the standard run directories. This task deepens the module to a simple depth-2
implementation while preserving the current attribute and method surface used
by existing callers.

## Technical Approach

- Keep `ProjectPaths(project_root, config)` as the construction surface.
- Materialize stable project-level paths as frozen dataclass fields during
  `__post_init__`, preserving existing attribute reads such as
  `paths.artifact_root`, `paths.runs_root`, and `paths.memory_file`.
- Add a frozen `RunPathLayout` dataclass that describes one run's root,
  standard directories, and named files.
- Add `ProjectPaths.run_layout(run_id)` to build the canonical layout for one
  run from the same path contract the existing `run_*` helpers expose.
- Add `ProjectPaths.ensure_run_layout(run_id)` to create the standard run
  directories plus the project memory directory and return the layout.
- Add `ProjectPaths.path_summary(run_id=None)` to return JSON-safe operator
  output for project-level paths and, when requested, run-level directories and
  files.
- Route `ArtifactManager.create_run_layout()` through `ProjectPaths.run_layout`
  so the end-to-end artifact path remains owned by the paths module while
  preserving the same on-disk layout.
- Do not add dependencies, migrations, database columns, provider secrets,
  runtime state files, or agent command strings.

## Edge Cases

- Existing project-level attributes and `run_*` helper return values must remain
  unchanged for normal run ids.
- Empty or whitespace-only run ids should fail fast with `ValueError` before
  preparing directories, avoiding writes under `.promptclaw/runs/` itself.
- `path_summary()` must be JSON-safe without custom encoders.
- `ensure_run_layout()` must be idempotent and return the same layout whether
  the directories already exist or not.
- The generated startup hardening checks target daemon/narrative startup
  identity, not this path module. The current tree already calls
  `bootstrap_identity()` before `FirstBootAnnouncer` in daemon startup paths and
  bootstraps identity for the ASGI narrative app; this task re-runs those tests
  as mandatory regression anchors.

## Acceptance Criteria

1. Existing config, orchestrator, and artifact behavior remains unchanged.
   VERIFY: `pytest tests/test_config.py tests/test_orchestrator.py tests/test_promptclaw_artifacts_depth.py -q`

2. `ProjectPaths` exposes a typed `RunPathLayout` that mirrors existing
   project-level and run-level path helpers.
   VERIFY: `pytest tests/test_promptclaw_paths_depth.py::test_run_layout_matches_existing_path_helpers -q`

3. Path summaries produce meaningful JSON-safe output for project and run
   layouts.
   VERIFY: `pytest tests/test_promptclaw_paths_depth.py::test_path_summary_is_json_safe_and_meaningful -q`

4. The path-owned layout preparation creates the standard end-to-end run
   directories and remains compatible with `ArtifactManager`.
   VERIFY: `pytest tests/test_promptclaw_paths_depth.py::test_ensure_run_layout_creates_directories_for_artifact_manager -q`

5. Empty run ids fail before directory preparation.
   VERIFY: `pytest tests/test_promptclaw_paths_depth.py::test_empty_run_id_is_rejected_before_layout_creation -q`

6. Fractal depth for `promptclaw/paths.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_promptclaw_paths_depth.py::test_paths_module_reaches_depth_two -q`

7. Startup identity hardening remains covered for first-boot persistence,
   standalone/federated startup wiring, and ASGI import persistence.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
