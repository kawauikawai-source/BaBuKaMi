"""add composite indexes for user histories

Revision ID: 202607160013
Revises: 202607160012
Create Date: 2026-08-02 00:00:00.000000
"""

from alembic import op


revision = "202607160013"
down_revision = "202607160012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_user_created",
        "transactions",
        ["user_id", "created_at", "id"],
    )
    op.create_index(
        "ix_game_rounds_user_created",
        "game_rounds",
        ["user_id", "created_at", "id"],
    )
    op.create_index(
        "ix_game_rounds_user_game_status",
        "game_rounds",
        ["user_id", "game_id", "status"],
    )
    op.create_index(
        "ix_audit_logs_action_created",
        "audit_logs",
        ["action", "created_at", "id"],
    )
    op.create_index(
        "ix_audit_logs_target_created",
        "audit_logs",
        ["target_user_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_target_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action_created", table_name="audit_logs")
    op.drop_index("ix_game_rounds_user_game_status", table_name="game_rounds")
    op.drop_index("ix_game_rounds_user_created", table_name="game_rounds")
    op.drop_index("ix_transactions_user_created", table_name="transactions")
