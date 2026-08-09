"""add promo codes

Revision ID: 202607160007
Revises: 202607160006
Create Date: 2026-07-19 00:00:07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607160007"
down_revision: str | Sequence[str] | None = "202607160006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not has_table("promo_codes"):
        op.create_table(
            "promo_codes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("reward_type", sa.String(length=16), nullable=False, server_default="fixed"),
            sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("percent_bps", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_bonus_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("min_deposit_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("usage_limit", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("per_user_limit", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_promo_codes_code"),
            sa.CheckConstraint("amount_cents >= 0", name="ck_promo_codes_amount_nonnegative"),
            sa.CheckConstraint("percent_bps >= 0", name="ck_promo_codes_percent_nonnegative"),
            sa.CheckConstraint("max_bonus_cents >= 0", name="ck_promo_codes_max_bonus_nonnegative"),
            sa.CheckConstraint("min_deposit_cents >= 0", name="ck_promo_codes_min_deposit_nonnegative"),
            sa.CheckConstraint("usage_limit >= 0", name="ck_promo_codes_usage_limit_nonnegative"),
            sa.CheckConstraint("per_user_limit >= 0", name="ck_promo_codes_per_user_limit_nonnegative"),
        )
        op.create_index(op.f("ix_promo_codes_id"), "promo_codes", ["id"], unique=False)
        op.create_index(op.f("ix_promo_codes_code"), "promo_codes", ["code"], unique=False)
        op.create_index(op.f("ix_promo_codes_created_by_user_id"), "promo_codes", ["created_by_user_id"], unique=False)

    if not has_table("promo_redemptions"):
        op.create_table(
            "promo_redemptions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("promo_code_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("transaction_id", sa.Integer(), nullable=False),
            sa.Column("bonus_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("deposit_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"]),
            sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("bonus_cents >= 0", name="ck_promo_redemptions_bonus_nonnegative"),
            sa.CheckConstraint("deposit_cents >= 0", name="ck_promo_redemptions_deposit_nonnegative"),
        )
        op.create_index(op.f("ix_promo_redemptions_id"), "promo_redemptions", ["id"], unique=False)
        op.create_index(op.f("ix_promo_redemptions_promo_code_id"), "promo_redemptions", ["promo_code_id"], unique=False)
        op.create_index(op.f("ix_promo_redemptions_transaction_id"), "promo_redemptions", ["transaction_id"], unique=False)
        op.create_index(op.f("ix_promo_redemptions_user_id"), "promo_redemptions", ["user_id"], unique=False)


def downgrade() -> None:
    if has_table("promo_redemptions"):
        op.drop_index(op.f("ix_promo_redemptions_user_id"), table_name="promo_redemptions")
        op.drop_index(op.f("ix_promo_redemptions_transaction_id"), table_name="promo_redemptions")
        op.drop_index(op.f("ix_promo_redemptions_promo_code_id"), table_name="promo_redemptions")
        op.drop_index(op.f("ix_promo_redemptions_id"), table_name="promo_redemptions")
        op.drop_table("promo_redemptions")
    if has_table("promo_codes"):
        op.drop_index(op.f("ix_promo_codes_created_by_user_id"), table_name="promo_codes")
        op.drop_index(op.f("ix_promo_codes_code"), table_name="promo_codes")
        op.drop_index(op.f("ix_promo_codes_id"), table_name="promo_codes")
        op.drop_table("promo_codes")
