# Task frac-0070 Specification: test_dashboard_generator Depth 2

## Problem Statement

`tests/test_dashboard_generator.py` covers the CypherClaw dashboard generator
compatibility surface, but the depth-2 task requires a one-path end-to-end test
that proves the module produces meaningful dashboard output. Exploration found
the production dashboard path is mostly implemented: it reads SDP task counts,
Observatory events, pet JSON state, server-health checks, and renders static
HTML without JavaScript. The remaining shallow path is
`collect_pet_classes()`, which always returns `{}`. As a result, generated
dashboards can render class/level rows only when a caller manually injects
class overrides; the normal `generate_dashboard()` path cannot surface agent
class data from runtime state.

This task deepens the dashboard test surface and implements the simplest
working class-collection path so the dashboard works end-to-end with real
SQLite + JSON fixtures.

## Technical Approach

- Preserve existing assertions in `tests/test_dashboard_generator.py` and
  `tests/test_dashboard_generator_runtime.py`.
- Add a dedicated red-phase gate at
  `tests/test_test_dashboard_generator_depth.py` requiring
  `tests/test_dashboard_generator.py` to classify at depth >= 2 and contain
  `DashboardGeneratorEndToEndTests`.
- Append `DashboardGeneratorEndToEndTests` to
  `tests/test_dashboard_generator.py`. The class drives the public
  `generate_dashboard()`, `collect_pipeline()`, `collect_events()`,
  `collect_pets()`, and `collect_pet_classes()` path through local SQLite
  databases and a pets JSON file, then verifies meaningful HTML output and
  JSON-safe source payloads.
- Implement `collect_pet_classes(path: Path = OBSERVATORY_DB) ->
  dict[str, tuple[str, int]]` by reading Observatory `agent_skills` rows from
  SQLite. Categories map to the existing dashboard class names, per-agent class
  strength is `score * sample_count` accumulated by class, and class level is
  the rounded accumulated strength with a minimum of 1.
- Update `generate_dashboard()` to pass the `obs_db` argument into
  `collect_pet_classes(obs_db)` so custom/test Observatory paths drive the
  class rows in the generated HTML.
- Treat the generated startup identity hardening bullets as regression anchors.
  Existing code already calls `bootstrap_identity()` from CLI startup, both
  daemon poll loops before `FirstBootAnnouncer`, and narrative ASGI app import;
  this task re-runs those tests instead of changing unrelated startup code.

## Edge Cases

- Missing Observatory DB, missing `agent_skills` table, or invalid SQLite data
  returns an empty class override mapping without breaking dashboard generation.
- Unknown skill categories are ignored.
- Multiple skill categories that map to the same class are accumulated before
  choosing the dominant class.
- Ties are resolved deterministically by class name through sorted iteration.
- Existing manually supplied `collect_pets(..., class_overrides=...)` behavior
  remains unchanged.
- No new dependencies, migrations, provider secrets, database columns, runtime
  state files, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing dashboard generator tests remain green.
   VERIFY: `pytest tests/test_dashboard_generator.py tests/test_dashboard_generator_runtime.py -q`

2. The new depth gate confirms `tests/test_dashboard_generator.py` reaches
   depth >= 2 and contains `DashboardGeneratorEndToEndTests`.
   VERIFY: `pytest tests/test_test_dashboard_generator_depth.py -q`

3. `collect_pet_classes()` returns meaningful dominant class/level overrides
   from Observatory `agent_skills` rows and tolerates a missing DB.
   VERIFY: `pytest tests/test_dashboard_generator.py::DashboardGeneratorEndToEndTests::test_collect_pet_classes_derives_dominant_classes_from_observatory -q`

4. `generate_dashboard()` works end-to-end from local health, SDP, Observatory,
   and pets fixtures and writes an HTML dashboard containing pipeline, service,
   event, pet, class, and level output.
   VERIFY: `pytest tests/test_dashboard_generator.py::DashboardGeneratorEndToEndTests::test_generate_dashboard_renders_end_to_end_runtime_snapshot -q`

5. Startup identity hardening remains covered for CLI startup, standalone and
   federated identity persistence, daemon bootstrap-before-announcer ordering,
   and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing notes mention the frac-0070 dashboard generator depth-2 work.
   VERIFY: `grep -n "frac-0070" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
