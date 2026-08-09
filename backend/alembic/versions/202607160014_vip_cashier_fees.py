"""add VIP cashier fee and payout fields

Revision ID: 202607160014
Revises: 202607160013
Create Date: 2026-08-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202607160014"
down_revision = "202607160013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("transactions")}
    with op.batch_alter_table("transactions") as batch:
        if "fee_cents" not in columns:
            batch.add_column(sa.Column("fee_cents", sa.Integer(), nullable=False, server_default="0"))
        if "payout_cents" not in columns:
            batch.add_column(sa.Column("payout_cents", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("transactions")}
    with op.batch_alter_table("transactions") as batch:
        if "payout_cents" in columns:
            batch.drop_column("payout_cents")
        if "fee_cents" in columns:
            batch.drop_column("fee_cents")
