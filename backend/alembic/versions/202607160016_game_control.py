"""add game control settings

Revision ID: 202607160016
Revises: 202607160015
Create Date: 2026-08-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202607160016"
down_revision = "202607160015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_control_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("daily_bet_limit_cents", sa.Integer(), nullable=True),
        sa.Column("daily_bet_spent_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("daily_bet_date", sa.Date(), nullable=True),
        sa.Column("reminder_minutes", sa.Integer(), server_default="30", nullable=False),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("daily_bet_limit_cents IS NULL OR daily_bet_limit_cents >= 0", name="ck_game_control_daily_limit"),
        sa.CheckConstraint("daily_bet_spent_cents >= 0", name="ck_game_control_daily_spent"),
        sa.CheckConstraint("reminder_minutes >= 0", name="ck_game_control_reminder"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_game_control_settings_user"),
    )
    op.create_index(op.f("ix_game_control_settings_id"), "game_control_settings", ["id"], unique=False)
    op.create_index(op.f("ix_game_control_settings_user_id"), "game_control_settings", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_game_control_settings_user_id"), table_name="game_control_settings")
    op.drop_index(op.f("ix_game_control_settings_id"), table_name="game_control_settings")
    op.drop_table("game_control_settings")
