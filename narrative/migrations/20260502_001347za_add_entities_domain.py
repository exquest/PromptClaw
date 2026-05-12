"""Add domain tagging to narrative entities and events.

Revision ID: 20260502_001347za_entities_domain
Revises: None
Create Date: 2026-05-02 00:13:47
"""

from dataclasses import dataclass
from typing import Final

from alembic import op


revision = "20260502_001347za_entities_domain"
down_revision = None
branch_labels = None
depends_on = None

DOMAIN_COLUMN_NAME: Final = "domain"
DOMAIN_COLUMN_TYPE: Final = "TEXT"
DOMAIN_DEFAULT_VALUE: Final = "shared"
_TARGET_TABLES: Final = ("entities", "events")


@dataclass(frozen=True)
class DomainColumnPlan:
    """One table receiving the narrative domain column."""

    table_name: str
    column_name: str
    column_type: str
    default_value: str
    nullable: bool


def domain_column_plans() -> tuple[DomainColumnPlan, ...]:
    """Return the canonical entity/event domain migration plan."""

    plans: list[DomainColumnPlan] = []
    for table_name in _TARGET_TABLES:
        plans.append(
            DomainColumnPlan(
                table_name=table_name,
                column_name=DOMAIN_COLUMN_NAME,
                column_type=DOMAIN_COLUMN_TYPE,
                default_value=DOMAIN_DEFAULT_VALUE,
                nullable=True,
            )
        )
    return tuple(plans)


def domain_migration_summary() -> dict[str, object]:
    """Describe the migration in JSON-safe operator-facing form."""

    plans = domain_column_plans()
    target_tables: list[str] = []
    upgrade_statements: list[str] = []
    downgrade_targets: list[dict[str, str]] = []

    for plan in plans:
        target_tables.append(plan.table_name)
        upgrade_statements.append(
            f"ALTER TABLE {plan.table_name} ADD COLUMN "
            f"{plan.column_name} {plan.column_type} DEFAULT "
            f"'{plan.default_value}'"
        )

    for plan in reversed(plans):
        downgrade_targets.append(
            {"table_name": plan.table_name, "column_name": plan.column_name}
        )

    return {
        "revision": revision,
        "target_tables": target_tables,
        "column_name": DOMAIN_COLUMN_NAME,
        "default_domain": DOMAIN_DEFAULT_VALUE,
        "upgrade_statements": upgrade_statements,
        "downgrade_targets": downgrade_targets,
    }


def upgrade() -> None:
    for plan in domain_column_plans():
        statement = (
            f"ALTER TABLE {plan.table_name} ADD COLUMN "
            f"{plan.column_name} {plan.column_type} DEFAULT "
            f"'{plan.default_value}'"
        )
        op.execute(statement)


def downgrade() -> None:
    for plan in reversed(domain_column_plans()):
        op.drop_column(plan.table_name, plan.column_name)
