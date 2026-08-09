"""add crash round lifecycle fields

Revision ID: 202607160003
Revises: 202607160002
Create Date: 2026-07-16 00:00:03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607160003"
down_revision: str | Sequence[str] | None = "202607160002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("game_rounds")
    if "status" not in columns:
        op.add_column(
            "game_rounds",
            sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        )
    if "settled_at" not in columns:
        op.add_column("game_rounds", sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    columns = _columns("game_rounds")
    with op.batch_alter_table("game_rounds") as batch_op:
        if "settled_at" in columns:
            batch_op.drop_column("settled_at")
        if "status" in columns:
            batch_op.drop_column("status")
