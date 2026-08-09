"""add idempotency keys

Revision ID: 202607160009
Revises: 202607160008
Create Date: 2026-07-23 00:00:09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607160009"
down_revision: str | Sequence[str] | None = "202607160008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if has_table("idempotency_keys"):
        return

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="processing"),
        sa.Column("response_json", sa.Text(), nullable=False, server_default=""),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", "scope", name="uq_idempotency_user_key_scope"),
    )
    op.create_index(op.f("ix_idempotency_keys_id"), "idempotency_keys", ["id"], unique=False)
    op.create_index(op.f("ix_idempotency_keys_key"), "idempotency_keys", ["key"], unique=False)
    op.create_index(op.f("ix_idempotency_keys_scope"), "idempotency_keys", ["scope"], unique=False)
    op.create_index(op.f("ix_idempotency_keys_transaction_id"), "idempotency_keys", ["transaction_id"], unique=False)
    op.create_index(op.f("ix_idempotency_keys_user_id"), "idempotency_keys", ["user_id"], unique=False)


def downgrade() -> None:
    if has_table("idempotency_keys"):
        op.drop_table("idempotency_keys")
