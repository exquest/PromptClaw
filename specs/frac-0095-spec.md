# Task frac-0095 Specification: test_narrative_entities_domain_migration Depth 2

## Problem Statement

`tests/test_narrative_entities_domain_migration.py` verifies the CN-001
narrative migration that adds a `domain TEXT DEFAULT 'shared'` column to the
`entities` and `events` tables. The production migration module already exposes
the typed `DomainColumnPlan`, `domain_column_plans()`, and
`domain_migration_summary()` helpers added by frac-0037, and the focused tests
already prove the individual plan, summary, upgrade, downgrade, and re-upgrade
behaviors.

The missing frac-0095 work is to deepen the test module itself with the same
explicit depth-2 pattern used by recent narrative test tasks: a deterministic
depth gate plus a named end-to-end test class. The end-to-end class should
drive one realistic migration lifecycle through the existing helper functions
and SQLite-backed Alembic shim so the test file proves meaningful output and
end-to-end behavior together, not only as separate assertions.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already invokes `bootstrap_identity()` from
CLI startup, daemon startup before `FirstBootAnnouncer`, and narrative ASGI
startup, with tests covering standalone/federated identity persistence. This
task keeps those tests as mandatory regression anchors rather than changing
unrelated startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_narrative_entities_domain_migration_depth.py` with an
  AST-based class check requiring
  `NarrativeEntitiesDomainMigrationEndToEndTests` and the repo-local
  `sdp.fractal.classify_depth` check for depth >= 2.
- Confirm the red phase by running the new depth gate before the end-to-end
  class exists.
- Append `NarrativeEntitiesDomainMigrationEndToEndTests` to
  `tests/test_narrative_entities_domain_migration.py` without modifying the
  existing locked assertions.
- Drive one migration lifecycle inside the class:
  - bootstrap an in-memory pre-migration `entities` / `events` schema;
  - load the Alembic migration through the existing SQLite shim;
  - inspect `domain_migration_summary()` before execution;
  - run `upgrade()` and verify existing rows default to `shared`;
  - insert explicit `deniable` entity and event rows and verify they persist;
  - inspect `PRAGMA table_info(...)` for both domain columns;
  - run `downgrade()` and verify both domain columns are removed;
  - run `upgrade()` again and verify the domain columns return with `shared`
    defaults for the retained rows;
  - round-trip a combined diagnostic payload through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Preserve production migration behavior. No new migration file, dependency,
  runtime state, provider secret, database table, HTTP route, or auth behavior
  is needed.

## Edge Cases

- The end-to-end path intentionally covers one simple SQLite lifecycle, not
  every database backend, Alembic version, or repeated-upgrade failure mode.
- Downgrade removes the domain column, so explicit deniable values are expected
  to be lost if the table is downgraded and upgraded again; the test only
  expects the reintroduced column to carry the documented default.
- The diagnostic payload must remain JSON-safe without custom encoders so
  verifier reports can persist it.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests.

## Acceptance Criteria

1. Existing narrative entities-domain migration assertions remain green.
   VERIFY: `pytest tests/test_narrative_entities_domain_migration.py -q`

2. The depth gate confirms
   `tests/test_narrative_entities_domain_migration.py` reaches depth >= 2 and
   contains `NarrativeEntitiesDomainMigrationEndToEndTests`.
   VERIFY: `pytest tests/test_test_narrative_entities_domain_migration_depth.py -q`

3. `NarrativeEntitiesDomainMigrationEndToEndTests` drives one meaningful
   migration lifecycle from summary through upgrade, explicit domain inserts,
   downgrade, re-upgrade, and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_narrative_entities_domain_migration.py::NarrativeEntitiesDomainMigrationEndToEndTests -q`

4. Related narrative entity API and migration behavior remains green.
   VERIFY: `pytest tests/test_narrative_api_entities.py tests/test_narrative_entities_domain_migration.py -q`

5. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

6. Product-facing task notes mention the frac-0095 migration test deepening.
   VERIFY: `grep -n "frac-0095" CHANGELOG.md progress.md`

7. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
