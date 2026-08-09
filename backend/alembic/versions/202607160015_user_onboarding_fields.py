"""add user onboarding fields

Revision ID: 202607160015
Revises: 202607160014
Create Date: 2026-08-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202607160015"
down_revision = "202607160014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    with op.batch_alter_table("users") as batch:
        if "first_name" not in columns:
            batch.add_column(sa.Column("first_name", sa.String(length=128), nullable=False, server_default=""))
        if "last_name" not in columns:
            batch.add_column(sa.Column("last_name", sa.String(length=128), nullable=False, server_default=""))
        if "kyc_status" not in columns:
            batch.add_column(
                sa.Column("kyc_status", sa.String(length=32), nullable=False, server_default="not_started")
            )

    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("first_name", sa.String()),
        sa.column("last_name", sa.String()),
    )
    rows = bind.execute(sa.select(users.c.id, users.c.name, users.c.first_name, users.c.last_name)).mappings()
    for row in rows:
        if (row["first_name"] or "").strip() or (row["last_name"] or "").strip():
            continue
        parts = (row["name"] or "").strip().split(maxsplit=1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""
        bind.execute(
            users.update().where(users.c.id == row["id"]).values(first_name=first_name, last_name=last_name)
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    with op.batch_alter_table("users") as batch:
        if "kyc_status" in columns:
            batch.drop_column("kyc_status")
        if "last_name" in columns:
            batch.drop_column("last_name")
        if "first_name" in columns:
            batch.drop_column("first_name")
