"""add operator 08 manager tables

Revision ID: 202607160017
Revises: 202607160016
Create Date: 2026-08-09 19:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202607160017"
down_revision = "202607160016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manager_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manager_messages_user_created", "manager_messages", ["user_id", "created_at", "id"])
    op.create_index(op.f("ix_manager_messages_id"), "manager_messages", ["id"])
    op.create_index(op.f("ix_manager_messages_user_id"), "manager_messages", ["user_id"])

    op.create_table(
        "manager_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manager_actions_user_status", "manager_actions", ["user_id", "status", "created_at"])
    op.create_index(op.f("ix_manager_actions_id"), "manager_actions", ["id"])
    op.create_index(op.f("ix_manager_actions_kind"), "manager_actions", ["kind"])
    op.create_index(op.f("ix_manager_actions_status"), "manager_actions", ["status"])
    op.create_index(op.f("ix_manager_actions_user_id"), "manager_actions", ["user_id"])

    op.create_table(
        "manager_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("admin_response", sa.Text(), nullable=False),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manager_tickets_status_created", "manager_tickets", ["status", "created_at", "id"])
    op.create_index(op.f("ix_manager_tickets_category"), "manager_tickets", ["category"])
    op.create_index(op.f("ix_manager_tickets_id"), "manager_tickets", ["id"])
    op.create_index(op.f("ix_manager_tickets_status"), "manager_tickets", ["status"])
    op.create_index(op.f("ix_manager_tickets_user_id"), "manager_tickets", ["user_id"])

    op.create_table(
        "manager_bet_presets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.String(length=64), nullable=False),
        sa.Column("bet_cents", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("bet_cents > 10000", name="ck_manager_bet_preset_above_base"),
        sa.CheckConstraint("bet_cents % 500 = 0", name="ck_manager_bet_preset_step"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "game_id", name="uq_manager_bet_preset_user_game"),
    )
    op.create_index(op.f("ix_manager_bet_presets_game_id"), "manager_bet_presets", ["game_id"])
    op.create_index(op.f("ix_manager_bet_presets_id"), "manager_bet_presets", ["id"])
    op.create_index(op.f("ix_manager_bet_presets_user_id"), "manager_bet_presets", ["user_id"])


def downgrade() -> None:
    op.drop_table("manager_bet_presets")
    op.drop_table("manager_tickets")
    op.drop_table("manager_actions")
    op.drop_table("manager_messages")
