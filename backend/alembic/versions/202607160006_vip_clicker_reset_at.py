"""add vip clicker reset marker

Revision ID: 202607160006
Revises: 202607160005
Create Date: 2026-07-18 00:00:06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607160006"
down_revision: str | Sequence[str] | None = "202607160005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = table_columns("vip_clicker_progress")
    if "reset_at" not in columns:
        op.add_column("vip_clicker_progress", sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    columns = table_columns("vip_clicker_progress")
    if "reset_at" in columns:
        op.drop_column("vip_clicker_progress", "reset_at")
