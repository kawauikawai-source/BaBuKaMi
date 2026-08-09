"""initial production demo schema

Revision ID: 202607160001
Revises:
Create Date: 2026-07-16 00:00:01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "202607160001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()

    users = sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(length=255), nullable=False, index=True),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("dob", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("country", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("balance_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vip_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("games_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_won_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("google_sub", name="uq_users_google_sub"),
        sa.CheckConstraint("balance_cents >= 0", name="ck_users_balance_nonnegative"),
    )
    users.create(bind=bind, checkfirst=True)

    if _columns("users"):
        _add_column("users", sa.Column("phone", sa.String(length=64), nullable=False, server_default=""))
        _add_column("users", sa.Column("dob", sa.String(length=32), nullable=False, server_default=""))
        _add_column("users", sa.Column("country", sa.String(length=128), nullable=False, server_default=""))
        _add_column("users", sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"))
        _add_column("users", sa.Column("balance_cents", sa.Integer(), nullable=False, server_default="0"))
        _add_column("users", sa.Column("vip_points", sa.Integer(), nullable=False, server_default="0"))
        _add_column("users", sa.Column("games_played", sa.Integer(), nullable=False, server_default="0"))
        _add_column("users", sa.Column("total_won_cents", sa.Integer(), nullable=False, server_default="0"))
        _add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))

    transactions = sa.Table(
        "transactions",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("method_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("title_key", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    transactions.create(bind=bind, checkfirst=True)

    refresh_sessions = sa.Table(
        "refresh_sessions",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("ip_address", sa.String(length=64), nullable=False, server_default=""),
    )
    refresh_sessions.create(bind=bind, checkfirst=True)

    game_rounds = sa.Table(
        "game_rounds",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("game_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("result_number", sa.Integer(), nullable=True),
        sa.Column("result_color", sa.String(length=16), nullable=True),
        sa.Column("total_bet_cents", sa.Integer(), nullable=False),
        sa.Column("total_win_cents", sa.Integer(), nullable=False),
        sa.Column("net_cents", sa.Integer(), nullable=False),
        sa.Column("bets_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    game_rounds.create(bind=bind, checkfirst=True)

    audit_logs = sa.Table(
        "audit_logs",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("action", sa.String(length=64), nullable=False, index=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("before_balance_cents", sa.Integer(), nullable=True),
        sa.Column("after_balance_cents", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    audit_logs.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("game_rounds")
    op.drop_table("refresh_sessions")
    op.drop_table("transactions")
    op.drop_table("users")
