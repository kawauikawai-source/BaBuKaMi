from datetime import UTC, date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("google_sub", name="uq_users_google_sub"),
        UniqueConstraint("telegram_sub", name="uq_users_telegram_sub"),
        CheckConstraint("balance_cents >= 0", name="ck_users_balance_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    first_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    dob: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    country: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    kyc_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vip_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vip_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="bronze")
    games_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_won_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")
    refresh_sessions: Mapped[list["RefreshSession"]] = relationship(back_populates="user")
    game_rounds: Mapped[list["GameRound"]] = relationship(back_populates="user")
    vip_clicker_progress: Mapped[list["VipClickerProgress"]] = relationship(back_populates="user")
    promo_redemptions: Mapped[list["PromoRedemption"]] = relationship(back_populates="user", foreign_keys="PromoRedemption.user_id")
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        foreign_keys="AuditLog.target_user_id",
        back_populates="target_user",
    )
    game_control_settings: Mapped["GameControlSettings | None"] = relationship(
        back_populates="user",
        uselist=False,
    )
    manager_messages: Mapped[list["ManagerMessage"]] = relationship(back_populates="user")
    manager_actions: Mapped[list["ManagerAction"]] = relationship(back_populates="user")
    manager_tickets: Mapped[list["ManagerTicket"]] = relationship(
        back_populates="user",
        foreign_keys="ManagerTicket.user_id",
    )
    manager_bet_presets: Mapped[list["ManagerBetPreset"]] = relationship(back_populates="user")
    studio_wallet: Mapped["StudioWallet | None"] = relationship(back_populates="user", uselist=False)
    studio_transactions: Mapped[list["StudioTransaction"]] = relationship(back_populates="user")
    identity_sessions: Mapped[list["IdentityAppSession"]] = relationship(back_populates="user")
    soul_appraisals: Mapped[list["SoulAppraisal"]] = relationship(back_populates="user")


class GameControlSettings(Base):
    __tablename__ = "game_control_settings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_game_control_settings_user"),
        CheckConstraint("daily_bet_limit_cents IS NULL OR daily_bet_limit_cents >= 0", name="ck_game_control_daily_limit"),
        CheckConstraint("daily_bet_spent_cents >= 0", name="ck_game_control_daily_spent"),
        CheckConstraint("reminder_minutes >= 0", name="ck_game_control_reminder"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    daily_bet_limit_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_bet_spent_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_bet_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reminder_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="game_control_settings")


class ManagerMessage(Base):
    __tablename__ = "manager_messages"
    __table_args__ = (Index("ix_manager_messages_user_created", "user_id", "created_at", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="operator")
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="ru")
    intent: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="manager_messages")


class ManagerAction(Base):
    __tablename__ = "manager_actions"
    __table_args__ = (Index("ix_manager_actions_user_status", "user_id", "status", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="manager_actions")


class ManagerTicket(Base):
    __tablename__ = "manager_tickets"
    __table_args__ = (Index("ix_manager_tickets_status_created", "status", "created_at", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    admin_response: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="manager_tickets", foreign_keys=[user_id])
    resolved_by: Mapped[User | None] = relationship(foreign_keys=[resolved_by_user_id])


class ManagerBetPreset(Base):
    __tablename__ = "manager_bet_presets"
    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_manager_bet_preset_user_game"),
        CheckConstraint("bet_cents > 10000", name="ck_manager_bet_preset_above_base"),
        CheckConstraint("bet_cents % 500 = 0", name="ck_manager_bet_preset_step"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bet_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manager")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="manager_bet_presets")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    method_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    title_key: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    fee_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payout_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="transactions")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "key", "scope", name="uq_idempotency_user_key_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    response_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship()
    transaction: Mapped[Transaction | None] = relationship()


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    replaced_by_session_id: Mapped[int | None] = mapped_column(ForeignKey("refresh_sessions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    user: Mapped[User] = relationship(back_populates="refresh_sessions", foreign_keys=[user_id])
    replaced_by_session: Mapped["RefreshSession | None"] = relationship(remote_side=[id])


class AbuseEvent(Base):
    __tablename__ = "abuse_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user: Mapped[User | None] = relationship()


class StudioWallet(Base):
    __tablename__ = "studio_wallets"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_studio_wallets_user"),
        CheckConstraint("balance_cents >= 0", name="ck_studio_wallets_balance_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="studio_wallet")


class StudioTransaction(Base):
    __tablename__ = "studio_transactions"
    __table_args__ = (
        UniqueConstraint("casino_transaction_id", name="uq_studio_transactions_casino_transaction"),
        UniqueConstraint("external_ref", name="uq_studio_transactions_external_ref"),
        Index("ix_studio_transactions_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    casino_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    external_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="studio_transactions")
    casino_transaction: Mapped[Transaction | None] = relationship()


class IdentityAuthorizationCode(Base):
    __tablename__ = "identity_authorization_codes"
    __table_args__ = (Index("ix_identity_codes_client_expires", "client_id", "expires_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    scope: Mapped[str] = mapped_column(String(255), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class IdentityAppSession(Base):
    __tablename__ = "identity_app_sessions"
    __table_args__ = (Index("ix_identity_sessions_user_client", "user_id", "client_id", "revoked_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    scope: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="identity_sessions")


class IdentityConsent(Base):
    __tablename__ = "identity_consents"
    __table_args__ = (UniqueConstraint("user_id", "client_id", name="uq_identity_consents_user_client"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class SoulAppraisal(Base):
    __tablename__ = "soul_appraisals"
    __table_args__ = (
        UniqueConstraint("user_id", "sale_number", name="uq_soul_appraisals_user_sale"),
        UniqueConstraint("studio_transaction_id", name="uq_soul_appraisals_studio_transaction"),
        CheckConstraint("sale_number >= 1 AND sale_number <= 3", name="ck_soul_appraisals_sale_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    sale_number: Mapped[int] = mapped_column(Integer, nullable=False)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    daily_rate_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    base_value_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    decay_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    payout_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(32), nullable=False, default="soul-pact-v1")
    studio_transaction_id: Mapped[int] = mapped_column(ForeignKey("studio_transactions.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="soul_appraisals")
    studio_transaction: Mapped[StudioTransaction] = relationship()


class GameRound(Base):
    __tablename__ = "game_rounds"
    __table_args__ = (
        Index("ix_game_rounds_user_created", "user_id", "created_at", "id"),
        Index("ix_game_rounds_user_game_status", "user_id", "game_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    result_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    total_bet_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_win_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    bets_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="game_rounds")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_action_created", "action", "created_at", "id"),
        Index("ix_audit_logs_target_created", "target_user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    before_balance_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_balance_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    actor_user: Mapped[User | None] = relationship(foreign_keys=[actor_user_id])
    target_user: Mapped[User | None] = relationship(foreign_keys=[target_user_id], back_populates="audit_logs")


class VipClickerProgress(Base):
    __tablename__ = "vip_clicker_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "tier", name="uq_vip_clicker_progress_user_tier"),
        CheckConstraint("clicks >= 0", name="ck_vip_clicker_progress_clicks_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="vip_clicker_progress")


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_promo_codes_code"),
        CheckConstraint("amount_cents >= 0", name="ck_promo_codes_amount_nonnegative"),
        CheckConstraint("percent_bps >= 0", name="ck_promo_codes_percent_nonnegative"),
        CheckConstraint("max_bonus_cents >= 0", name="ck_promo_codes_max_bonus_nonnegative"),
        CheckConstraint("min_deposit_cents >= 0", name="ck_promo_codes_min_deposit_nonnegative"),
        CheckConstraint("usage_limit >= 0", name="ck_promo_codes_usage_limit_nonnegative"),
        CheckConstraint("per_user_limit >= 0", name="ck_promo_codes_per_user_limit_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    reward_type: Mapped[str] = mapped_column(String(16), nullable=False, default="fixed")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    percent_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_bonus_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_deposit_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    per_user_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])
    redemptions: Mapped[list["PromoRedemption"]] = relationship(back_populates="promo_code")


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    __table_args__ = (
        CheckConstraint("bonus_cents >= 0", name="ck_promo_redemptions_bonus_nonnegative"),
        CheckConstraint("deposit_cents >= 0", name="ck_promo_redemptions_deposit_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False, index=True)
    bonus_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deposit_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    promo_code: Mapped[PromoCode] = relationship(back_populates="redemptions")
    user: Mapped[User] = relationship(back_populates="promo_redemptions", foreign_keys=[user_id])
    transaction: Mapped[Transaction] = relationship()
