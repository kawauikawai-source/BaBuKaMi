"""add kawaui studio wallet, identity sessions, and soul sales

Revision ID: 202607160018
Revises: 202607160017
Create Date: 2026-08-11 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "202607160018"
down_revision = "202607160017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_wallets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("balance_cents", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("balance_cents >= 0", name="ck_studio_wallets_balance_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_studio_wallets_user"),
    )
    op.create_index(op.f("ix_studio_wallets_id"), "studio_wallets", ["id"])
    op.create_index(op.f("ix_studio_wallets_user_id"), "studio_wallets", ["user_id"])

    op.create_table(
        "studio_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("casino_transaction_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("fee_cents", sa.Integer(), nullable=False),
        sa.Column("net_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("external_ref", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["casino_transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("casino_transaction_id", name="uq_studio_transactions_casino_transaction"),
        sa.UniqueConstraint("external_ref", name="uq_studio_transactions_external_ref"),
    )
    op.create_index(op.f("ix_studio_transactions_id"), "studio_transactions", ["id"])
    op.create_index(op.f("ix_studio_transactions_user_id"), "studio_transactions", ["user_id"])
    op.create_index(op.f("ix_studio_transactions_casino_transaction_id"), "studio_transactions", ["casino_transaction_id"])
    op.create_index(op.f("ix_studio_transactions_source"), "studio_transactions", ["source"])
    op.create_index(op.f("ix_studio_transactions_type"), "studio_transactions", ["type"])
    op.create_index(op.f("ix_studio_transactions_status"), "studio_transactions", ["status"])
    op.create_index("ix_studio_transactions_user_created", "studio_transactions", ["user_id", "created_at", "id"])

    op.create_table(
        "identity_authorization_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("redirect_uri", sa.String(length=512), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index(op.f("ix_identity_authorization_codes_id"), "identity_authorization_codes", ["id"])
    op.create_index(op.f("ix_identity_authorization_codes_user_id"), "identity_authorization_codes", ["user_id"])
    op.create_index(op.f("ix_identity_authorization_codes_client_id"), "identity_authorization_codes", ["client_id"])
    op.create_index(op.f("ix_identity_authorization_codes_code_hash"), "identity_authorization_codes", ["code_hash"])
    op.create_index("ix_identity_codes_client_expires", "identity_authorization_codes", ["client_id", "expires_at"])

    op.create_table(
        "identity_app_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_identity_app_sessions_id"), "identity_app_sessions", ["id"])
    op.create_index(op.f("ix_identity_app_sessions_user_id"), "identity_app_sessions", ["user_id"])
    op.create_index(op.f("ix_identity_app_sessions_client_id"), "identity_app_sessions", ["client_id"])
    op.create_index(op.f("ix_identity_app_sessions_token_hash"), "identity_app_sessions", ["token_hash"])
    op.create_index("ix_identity_sessions_user_client", "identity_app_sessions", ["user_id", "client_id", "revoked_at"])

    op.create_table(
        "identity_consents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_id", name="uq_identity_consents_user_client"),
    )
    op.create_index(op.f("ix_identity_consents_id"), "identity_consents", ["id"])
    op.create_index(op.f("ix_identity_consents_user_id"), "identity_consents", ["user_id"])
    op.create_index(op.f("ix_identity_consents_client_id"), "identity_consents", ["client_id"])

    op.create_table(
        "soul_appraisals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sale_number", sa.Integer(), nullable=False),
        sa.Column("answers_json", sa.Text(), nullable=False),
        sa.Column("daily_rate_cents", sa.Integer(), nullable=False),
        sa.Column("base_value_cents", sa.Integer(), nullable=False),
        sa.Column("decay_bps", sa.Integer(), nullable=False),
        sa.Column("payout_cents", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(length=32), nullable=False),
        sa.Column("studio_transaction_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sale_number >= 1 AND sale_number <= 3", name="ck_soul_appraisals_sale_number"),
        sa.ForeignKeyConstraint(["studio_transaction_id"], ["studio_transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("studio_transaction_id", name="uq_soul_appraisals_studio_transaction"),
        sa.UniqueConstraint("user_id", "sale_number", name="uq_soul_appraisals_user_sale"),
    )
    op.create_index(op.f("ix_soul_appraisals_id"), "soul_appraisals", ["id"])
    op.create_index(op.f("ix_soul_appraisals_user_id"), "soul_appraisals", ["user_id"])


def downgrade() -> None:
    op.drop_table("soul_appraisals")
    op.drop_table("identity_consents")
    op.drop_table("identity_app_sessions")
    op.drop_table("identity_authorization_codes")
    op.drop_table("studio_transactions")
    op.drop_table("studio_wallets")
