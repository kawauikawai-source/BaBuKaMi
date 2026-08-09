"""add vip clicker progress

Revision ID: 202607160005
Revises: 202607160004
Create Date: 2026-07-18 00:00:05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607160005"
down_revision: str | Sequence[str] | None = "202607160004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("vip_clicker_progress"):
        return
    op.create_table(
        "vip_clicker_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tier", name="uq_vip_clicker_progress_user_tier"),
        sa.CheckConstraint("clicks >= 0", name="ck_vip_clicker_progress_clicks_nonnegative"),
    )
    op.create_index(op.f("ix_vip_clicker_progress_id"), "vip_clicker_progress", ["id"], unique=False)
    op.create_index(op.f("ix_vip_clicker_progress_tier"), "vip_clicker_progress", ["tier"], unique=False)
    op.create_index(op.f("ix_vip_clicker_progress_user_id"), "vip_clicker_progress", ["user_id"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("vip_clicker_progress"):
        return
    op.drop_index(op.f("ix_vip_clicker_progress_user_id"), table_name="vip_clicker_progress")
    op.drop_index(op.f("ix_vip_clicker_progress_tier"), table_name="vip_clicker_progress")
    op.drop_index(op.f("ix_vip_clicker_progress_id"), table_name="vip_clicker_progress")
    op.drop_table("vip_clicker_progress")
