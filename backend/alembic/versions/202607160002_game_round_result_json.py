"""generalize game round result storage

Revision ID: 202607160002
Revises: 202607160001
Create Date: 2026-07-16 00:00:02
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607160002"
down_revision: str | Sequence[str] | None = "202607160001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("game_rounds")
    if "result_json" not in columns:
        op.add_column("game_rounds", sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"))

    with op.batch_alter_table("game_rounds") as batch_op:
        if "result_number" in columns:
            batch_op.alter_column("result_number", existing_type=sa.Integer(), nullable=True)
        if "result_color" in columns:
            batch_op.alter_column("result_color", existing_type=sa.String(length=16), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("game_rounds") as batch_op:
        batch_op.alter_column("result_number", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("result_color", existing_type=sa.String(length=16), nullable=False)
        batch_op.drop_column("result_json")
