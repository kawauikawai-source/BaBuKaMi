"""add vip tier

Revision ID: 202607160008
Revises: 202607160007
Create Date: 2026-07-23 00:00:08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607160008"
down_revision: str | Sequence[str] | None = "202607160007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def has_column(table_name: str, column_name: str) -> bool:
    if not has_table(table_name):
        return False
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if has_table("users") and not has_column("users", "vip_tier"):
        op.add_column("users", sa.Column("vip_tier", sa.String(length=16), nullable=False, server_default="bronze"))
        op.execute("UPDATE users SET vip_tier = 'bronze' WHERE vip_tier IS NULL OR vip_tier = ''")


def downgrade() -> None:
    if has_table("users") and has_column("users", "vip_tier"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("vip_tier")
