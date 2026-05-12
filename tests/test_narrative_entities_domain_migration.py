from __future__ import annotations

import dataclasses
import json
import importlib.util
import sqlite3
import sys
import types
from pathlib import Path
from types import ModuleType


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "narrative"
    / "migrations"
    / "20260502_001347za_add_entities_domain.py"
)


class SQLiteAlembicOp:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def execute(self, statement: str) -> None:
        self.connection.execute(statement)

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.connection.execute(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")


def load_migration(op: SQLiteAlembicOp) -> ModuleType:
    alembic = types.ModuleType("alembic")
    alembic.op = op
    previous = sys.modules.get("alembic")
    sys.modules["alembic"] = alembic
    try:
        spec = importlib.util.spec_from_file_location(
            "entities_domain_migration",
            MIGRATION_PATH,
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            del sys.modules["alembic"]
        else:
            sys.modules["alembic"] = previous


def test_domain_column_plans_describe_entities_and_events() -> None:
    migration = load_migration(SQLiteAlembicOp(sqlite3.connect(":memory:")))

    plans = migration.domain_column_plans()

    assert len(plans) == 2
    assert all(dataclasses.is_dataclass(plan) for plan in plans)
    assert all(getattr(plan, "__dataclass_params__").frozen for plan in plans)
    assert [dataclasses.asdict(plan) for plan in plans] == [
        {
            "table_name": "entities",
            "column_name": "domain",
            "column_type": "TEXT",
            "default_value": "shared",
            "nullable": True,
        },
        {
            "table_name": "events",
            "column_name": "domain",
            "column_type": "TEXT",
            "default_value": "shared",
            "nullable": True,
        },
    ]


def test_domain_migration_summary_is_json_safe() -> None:
    migration = load_migration(SQLiteAlembicOp(sqlite3.connect(":memory:")))

    summary = migration.domain_migration_summary()

    json.dumps(summary)
    assert summary == {
        "revision": "20260502_001347za_entities_domain",
        "target_tables": ["entities", "events"],
        "column_name": "domain",
        "default_domain": "shared",
        "upgrade_statements": [
            "ALTER TABLE entities ADD COLUMN domain TEXT DEFAULT 'shared'",
            "ALTER TABLE events ADD COLUMN domain TEXT DEFAULT 'shared'",
        ],
        "downgrade_targets": [
            {"table_name": "events", "column_name": "domain"},
            {"table_name": "entities", "column_name": "domain"},
        ],
    }


def test_entities_domain_migration_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth(MIGRATION_PATH)

    assert result.depth >= 2, result.reason


def _bootstrap_schema(connection: sqlite3.Connection) -> None:
    connection.execute("CREATE TABLE entities (id TEXT PRIMARY KEY, type TEXT)")
    connection.execute("INSERT INTO entities (id, type) VALUES ('entity-1', 'npc')")
    connection.execute("CREATE TABLE events (id TEXT PRIMARY KEY, kind TEXT)")
    connection.execute("INSERT INTO events (id, kind) VALUES ('event-1', 'spawn')")


def test_entities_domain_migration_defaults_existing_rows() -> None:
    connection = sqlite3.connect(":memory:")
    _bootstrap_schema(connection)

    migration = load_migration(SQLiteAlembicOp(connection))
    migration.upgrade()

    existing_domain = connection.execute(
        "SELECT domain FROM entities WHERE id = 'entity-1'"
    ).fetchone()[0]
    assert existing_domain == "shared"

    columns = {
        row[1]: {"type": row[2], "notnull": row[3], "default": row[4]}
        for row in connection.execute("PRAGMA table_info(entities)").fetchall()
    }
    assert columns["domain"] == {
        "type": "TEXT",
        "notnull": 0,
        "default": "'shared'",
    }

    connection.execute(
        "INSERT INTO entities (id, type, domain) VALUES "
        "('entity-2', 'npc', 'deniable')"
    )
    inserted_domain = connection.execute(
        "SELECT domain FROM entities WHERE id = 'entity-2'"
    ).fetchone()[0]
    assert inserted_domain == "deniable"


def test_events_domain_migration_defaults_existing_rows() -> None:
    connection = sqlite3.connect(":memory:")
    _bootstrap_schema(connection)

    migration = load_migration(SQLiteAlembicOp(connection))
    migration.upgrade()

    existing_domain = connection.execute(
        "SELECT domain FROM events WHERE id = 'event-1'"
    ).fetchone()[0]
    assert existing_domain == "shared"

    columns = {
        row[1]: {"type": row[2], "notnull": row[3], "default": row[4]}
        for row in connection.execute("PRAGMA table_info(events)").fetchall()
    }
    assert columns["domain"] == {
        "type": "TEXT",
        "notnull": 0,
        "default": "'shared'",
    }

    connection.execute(
        "INSERT INTO events (id, kind, domain) VALUES "
        "('event-2', 'spawn', 'deniable')"
    )
    inserted_domain = connection.execute(
        "SELECT domain FROM events WHERE id = 'event-2'"
    ).fetchone()[0]
    assert inserted_domain == "deniable"


def test_upgrade_downgrade_upgrade_round_trips_domain_columns() -> None:
    connection = sqlite3.connect(":memory:")
    _bootstrap_schema(connection)

    migration = load_migration(SQLiteAlembicOp(connection))
    migration.upgrade()
    migration.downgrade()

    entity_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(entities)").fetchall()
    }
    event_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(events)").fetchall()
    }
    assert "domain" not in entity_columns
    assert "domain" not in event_columns

    migration.upgrade()

    entity_domain = connection.execute(
        "SELECT domain FROM entities WHERE id = 'entity-1'"
    ).fetchone()[0]
    event_domain = connection.execute(
        "SELECT domain FROM events WHERE id = 'event-1'"
    ).fetchone()[0]
    assert entity_domain == "shared"
    assert event_domain == "shared"

    entity_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(entities)").fetchall()
    }
    event_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(events)").fetchall()
    }
    assert "domain" in entity_columns
    assert "domain" in event_columns


class NarrativeEntitiesDomainMigrationEndToEndTests:
    __test__ = True

    def test_sqlite_migration_lifecycle_is_json_safe(self) -> None:
        connection = sqlite3.connect(":memory:")
        _bootstrap_schema(connection)

        migration = load_migration(SQLiteAlembicOp(connection))
        summary = migration.domain_migration_summary()

        assert summary["target_tables"] == ["entities", "events"]
        assert summary["default_domain"] == "shared"

        migration.upgrade()

        connection.execute(
            "INSERT INTO entities (id, type, domain) VALUES "
            "('entity-2', 'npc', 'deniable')"
        )
        connection.execute(
            "INSERT INTO events (id, kind, domain) VALUES "
            "('event-2', 'raid.completed', 'deniable')"
        )

        entity_rows = [
            {"id": row[0], "type": row[1], "domain": row[2]}
            for row in connection.execute(
                "SELECT id, type, domain FROM entities ORDER BY id"
            ).fetchall()
        ]
        event_rows = [
            {"id": row[0], "kind": row[1], "domain": row[2]}
            for row in connection.execute(
                "SELECT id, kind, domain FROM events ORDER BY id"
            ).fetchall()
        ]
        assert entity_rows == [
            {"id": "entity-1", "type": "npc", "domain": "shared"},
            {"id": "entity-2", "type": "npc", "domain": "deniable"},
        ]
        assert event_rows == [
            {"id": "event-1", "kind": "spawn", "domain": "shared"},
            {"id": "event-2", "kind": "raid.completed", "domain": "deniable"},
        ]

        domain_columns = {
            table_name: {
                row[1]: {"type": row[2], "notnull": row[3], "default": row[4]}
                for row in connection.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            }["domain"]
            for table_name in ("entities", "events")
        }
        assert domain_columns == {
            "entities": {"type": "TEXT", "notnull": 0, "default": "'shared'"},
            "events": {"type": "TEXT", "notnull": 0, "default": "'shared'"},
        }

        migration.downgrade()

        columns_after_downgrade = {
            table_name: [
                row[1]
                for row in connection.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            ]
            for table_name in ("entities", "events")
        }
        assert columns_after_downgrade == {
            "entities": ["id", "type"],
            "events": ["id", "kind"],
        }

        migration.upgrade()

        rows_after_reupgrade = {
            "entities": [
                {"id": row[0], "domain": row[1]}
                for row in connection.execute(
                    "SELECT id, domain FROM entities ORDER BY id"
                ).fetchall()
            ],
            "events": [
                {"id": row[0], "domain": row[1]}
                for row in connection.execute(
                    "SELECT id, domain FROM events ORDER BY id"
                ).fetchall()
            ],
        }
        assert rows_after_reupgrade == {
            "entities": [
                {"id": "entity-1", "domain": "shared"},
                {"id": "entity-2", "domain": "shared"},
            ],
            "events": [
                {"id": "event-1", "domain": "shared"},
                {"id": "event-2", "domain": "shared"},
            ],
        }

        diagnostic = {
            "summary": summary,
            "domain_columns": domain_columns,
            "entity_rows": entity_rows,
            "event_rows": event_rows,
            "columns_after_downgrade": columns_after_downgrade,
            "rows_after_reupgrade": rows_after_reupgrade,
        }
        decoded = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert decoded["summary"]["revision"] == migration.revision
        assert decoded["entity_rows"][1]["domain"] == "deniable"
        assert decoded["event_rows"][1]["kind"] == "raid.completed"
        assert decoded["rows_after_reupgrade"]["events"][1]["domain"] == "shared"
