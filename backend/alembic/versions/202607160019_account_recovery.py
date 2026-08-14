"""add account recovery and device security

Revision ID: 202607160019
Revises: 202607160018
"""

from alembic import op
import sqlalchemy as sa


revision = "202607160019"
down_revision = "202607160018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "account_action_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purpose IN ('verify_email', 'reset_password')", name="ck_account_action_token_purpose"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_account_action_tokens_id"), "account_action_tokens", ["id"])
    op.create_index(op.f("ix_account_action_tokens_user_id"), "account_action_tokens", ["user_id"])
    op.create_index(op.f("ix_account_action_tokens_purpose"), "account_action_tokens", ["purpose"])
    op.create_index(op.f("ix_account_action_tokens_token_hash"), "account_action_tokens", ["token_hash"])
    op.create_index("ix_account_action_tokens_user_purpose", "account_action_tokens", ["user_id", "purpose", "created_at"])


def downgrade() -> None:
    op.drop_table("account_action_tokens")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("password_changed_at")
