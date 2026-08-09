"""replace Arctic Cash board storage with Arctic Protocol rounds

Revision ID: 202607160012
Revises: 202607160011
Create Date: 2026-07-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202607160012"
down_revision = "202607160011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("arctic_cash_boards"):
        op.drop_table("arctic_cash_boards")


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("arctic_cash_boards"):
        return
    op.create_table(
        "arctic_cash_boards",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("mode", sa.String(length=16), nullable=False, index=True),
        sa.Column("bet_cents", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "mode", "bet_cents", name="uq_arctic_cash_board_user_mode_bet"),
        sa.CheckConstraint("bet_cents > 0", name="ck_arctic_cash_board_bet_positive"),
        sa.CheckConstraint("version > 0", name="ck_arctic_cash_board_version_positive"),
    )
