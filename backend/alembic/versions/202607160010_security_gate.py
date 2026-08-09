"""security gate refresh sessions and abuse events

Revision ID: 202607160010
Revises: 202607160009
Create Date: 2026-07-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202607160010"
down_revision = "202607160009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    refresh_columns = {column["name"] for column in inspector.get_columns("refresh_sessions")}
    with op.batch_alter_table("refresh_sessions") as batch:
        if "last_used_at" not in refresh_columns:
            batch.add_column(sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
        if "rotated_at" not in refresh_columns:
            batch.add_column(sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))
        if "revoked_reason" not in refresh_columns:
            batch.add_column(sa.Column("revoked_reason", sa.String(length=64), nullable=False, server_default=""))
        if "replaced_by_session_id" not in refresh_columns:
            batch.add_column(sa.Column("replaced_by_session_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_refresh_sessions_replaced_by_session_id_refresh_sessions",
                "refresh_sessions",
                ["replaced_by_session_id"],
                ["id"],
            )

    if not inspector.has_table("abuse_events"):
        op.create_table(
            "abuse_events",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("ip_hash", sa.String(length=64), nullable=False, index=True, server_default=""),
            sa.Column("action", sa.String(length=64), nullable=False, index=True),
            sa.Column("key", sa.String(length=128), nullable=False, index=True, server_default=""),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("abuse_events"):
        op.drop_table("abuse_events")
    refresh_columns = {column["name"] for column in inspector.get_columns("refresh_sessions")}
    with op.batch_alter_table("refresh_sessions") as batch:
        if "replaced_by_session_id" in refresh_columns:
            batch.drop_constraint("fk_refresh_sessions_replaced_by_session_id_refresh_sessions", type_="foreignkey")
            batch.drop_column("replaced_by_session_id")
        if "revoked_reason" in refresh_columns:
            batch.drop_column("revoked_reason")
        if "rotated_at" in refresh_columns:
            batch.drop_column("rotated_at")
        if "last_used_at" in refresh_columns:
            batch.drop_column("last_used_at")
