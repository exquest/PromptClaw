# Task frac-0037 Specification: Entities Domain Migration Depth 2

## Problem Statement

`narrative/migrations/20260502_001347za_add_entities_domain.py` owns the
CN-001 migration that adds a `domain TEXT DEFAULT 'shared'` column to both
`entities` and `events`. Existing tests prove the migration defaults existing
rows, accepts explicit domain values for new rows, and can downgrade then
upgrade again.

The module still classifies at fractal depth 1 because `upgrade()` and
`downgrade()` are only direct Alembic operation calls. This task deepens the
migration to a simple depth-2 implementation by adding one typed planning and
summary path that produces meaningful inspectable output while preserving the
same schema change.

## Technical Approach

Extend the migration module in place with stdlib-only helpers.

- Add a frozen `DomainColumnPlan` dataclass describing one target table,
  column name, SQL type, default value, and nullable status.
- Add `domain_column_plans()` to return the canonical two-table plan for
  `entities` and `events`.
- Add `domain_migration_summary()` to emit a JSON-safe operator summary with
  the revision id, table order, default domain, upgrade SQL statements, and
  downgrade drop targets.
- Route `upgrade()` through `domain_column_plans()` and execute one generated
  `ALTER TABLE ... ADD COLUMN ... DEFAULT 'shared'` statement per target.
- Route `downgrade()` through the same plan in reverse order and call
  `op.drop_column(table_name, "domain")`.
- Do not add dependencies, runtime files, provider secrets, database tables,
  or extra agent command strings.

## Edge Cases

- Existing rows must still receive `shared` through SQLite/Alembic default
  behavior when the new column is added.
- New rows must still be able to set a non-default domain such as `deniable`.
- Downgrade should remove the events column before entities, matching the
  existing reverse order.
- The summary is diagnostic only; schema authority remains the Alembic
  `upgrade()` / `downgrade()` functions.
- The generated startup hardening checks target daemon/narrative startup
  identity, not this migration. The current tree already calls
  `bootstrap_identity()` before `FirstBootAnnouncer` in daemon startup paths
  and the narrative API entry point; this task will re-run the existing
  startup identity integration tests as mandatory regression anchors.

## Acceptance Criteria

1. Existing domain migration behavior remains unchanged for entities,
   events, downgrade, and re-upgrade.
   VERIFY: `pytest tests/test_narrative_entities_domain_migration.py::test_entities_domain_migration_defaults_existing_rows tests/test_narrative_entities_domain_migration.py::test_events_domain_migration_defaults_existing_rows tests/test_narrative_entities_domain_migration.py::test_upgrade_downgrade_upgrade_round_trips_domain_columns -q`

2. The migration exposes a typed canonical plan for both target tables.
   VERIFY: `pytest tests/test_narrative_entities_domain_migration.py::test_domain_column_plans_describe_entities_and_events -q`

3. The migration summary is JSON-safe and mirrors the canonical plan.
   VERIFY: `pytest tests/test_narrative_entities_domain_migration.py::test_domain_migration_summary_is_json_safe -q`

4. Fractal depth for
   `narrative/migrations/20260502_001347za_add_entities_domain.py` reaches
   at least depth 2.
   VERIFY: `pytest tests/test_narrative_entities_domain_migration.py::test_entities_domain_migration_reaches_depth_two -q`

5. Startup identity hardening remains covered for first-boot persistence and
   standalone/federated startup wiring.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_main_calls_bootstrap_identity -q`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
