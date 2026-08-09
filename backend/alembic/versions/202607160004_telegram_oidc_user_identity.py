"""add telegram oidc user identity

Revision ID: 202607160004
Revises: 202607160003
Create Date: 2026-07-18 00:00:04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607160004"
down_revision: str | Sequence[str] | None = "202607160003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _unique_constraints(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {item["name"] for item in inspector.get_unique_constraints(table_name) if item.get("name")}


def upgrade() -> None:
    columns = _columns("users")
    constraints = _unique_constraints("users")
    with op.batch_alter_table("users") as batch_op:
        if "telegram_sub" not in columns:
            batch_op.add_column(sa.Column("telegram_sub", sa.String(length=255), nullable=True))
        if "uq_users_telegram_sub" not in constraints:
            batch_op.create_unique_constraint("uq_users_telegram_sub", ["telegram_sub"])


def downgrade() -> None:
    columns = _columns("users")
    constraints = _unique_constraints("users")
    with op.batch_alter_table("users") as batch_op:
        if "uq_users_telegram_sub" in constraints:
            batch_op.drop_constraint("uq_users_telegram_sub", type_="unique")
        if "telegram_sub" in columns:
            batch_op.drop_column("telegram_sub")
