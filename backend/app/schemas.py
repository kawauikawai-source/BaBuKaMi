from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator, model_validator


def cents_to_amount(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(100)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    dob: str = ""
    country: str = ""
    kyc_status: str = "not_started"
    currency: str = "EUR"
    balance_cents: int = 0
    vip_points: int = 0
    vip_tier: str = "bronze"
    games_played: int = 0
    total_won_cents: int = 0
    provider: str
    email_verified: bool
    is_admin: bool = False
    created_at: datetime
    last_login_at: datetime | None = None

    @computed_field
    @property
    def balance(self) -> Decimal:
        return cents_to_amount(self.balance_cents)

    @computed_field
    @property
    def total_won(self) -> Decimal:
        return cents_to_amount(self.total_won_cents)

    @computed_field
    @property
    def profile_missing_fields(self) -> list[str]:
        fields = {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "date_of_birth": self.dob,
            "phone": self.phone,
            "country": self.country,
        }
        return [key for key, value in fields.items() if not str(value or "").strip()]

    @computed_field
    @property
    def profile_completion(self) -> int:
        return round((5 - len(self.profile_missing_fields)) / 5 * 100)

    @computed_field
    @property
    def onboarding_required(self) -> bool:
        required = {"first_name", "last_name", "date_of_birth"}
        return bool(required.intersection(self.profile_missing_fields))


class UserUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    first_name: str | None = Field(default=None, min_length=1, max_length=128)
    last_name: str | None = Field(default=None, min_length=1, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    dob: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=128)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("dob")
    @classmethod
    def validate_date_of_birth(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value
        try:
            born = date.fromisoformat(value.strip())
        except ValueError as err:
            raise ValueError("Invalid date of birth") from err
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if age < 18 or age > 120:
            raise ValueError("Invalid date of birth")
        return value.strip()


class RegisterRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    first_name: str | None = Field(default=None, min_length=1, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    dob: str = Field(default="", max_length=32)
    phone: str = Field(default="", max_length=64)
    country: str = Field(default="", max_length=128)
    kyc_opt_in: bool = False

    @model_validator(mode="after")
    def validate_identity(self) -> "RegisterRequest":
        if not str(self.first_name or self.name or "").strip():
            raise ValueError("First name is required")
        return self

    @field_validator("dob")
    @classmethod
    def validate_date_of_birth(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        try:
            born = date.fromisoformat(normalized)
        except ValueError as err:
            raise ValueError("Invalid date of birth") from err
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if age < 18:
            raise ValueError("User must be at least 18 years old")
        if age > 120:
            raise ValueError("Invalid date of birth")
        return normalized


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class MessageResponse(BaseModel):
    message: str


class GameControlSettingsUpdateRequest(BaseModel):
    daily_bet_limit_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    reminder_minutes: int = Field(default=30)

    @field_validator("reminder_minutes")
    @classmethod
    def validate_reminder_minutes(cls, value: int) -> int:
        if value not in {0, 15, 30, 60}:
            raise ValueError("Invalid reminder interval")
        return value


class GameControlPauseRequest(BaseModel):
    duration_minutes: int

    @field_validator("duration_minutes")
    @classmethod
    def validate_pause_duration(cls, value: int) -> int:
        if value not in {15, 60, 1440}:
            raise ValueError("Invalid pause duration")
        return value


class GameControlResponse(BaseModel):
    daily_bet_limit_cents: int | None
    daily_bet_spent_cents: int
    daily_bet_remaining_cents: int | None
    reminder_minutes: int
    paused_until: datetime | None
    is_paused: bool
    server_time: datetime


class ManagerMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    language: str = Field(default="ru", pattern="^(ru|en)$")
    intent: str | None = Field(default=None, max_length=64)
    payload: dict = Field(default_factory=dict)


class ManagerMessagePublic(BaseModel):
    id: int
    role: str
    language: str
    intent: str
    text: str
    metadata: dict = Field(default_factory=dict)
    is_unread: bool = False
    created_at: datetime


class ManagerActionPublic(BaseModel):
    id: int
    kind: str
    status: str
    payload: dict = Field(default_factory=dict)
    expires_at: datetime
    created_at: datetime


class ManagerTicketPublic(BaseModel):
    id: int
    category: str
    status: str
    subject: str
    payload: dict = Field(default_factory=dict)
    admin_response: str = ""
    user_id: int | None = None
    user_name: str = ""
    user_email: str = ""
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class ManagerBetPresetPublic(BaseModel):
    game_id: str
    bet_cents: int
    source: str
    expires_at: datetime | None = None


class ManagerStateResponse(BaseModel):
    operator_name: str = "Operator 08"
    line_status: str
    vip_tier: str
    max_bet_cents: int
    max_games: int
    unread_count: int
    balance_cents: int
    vip_points: int
    pending_withdrawals: int
    active_rounds: int
    cashier_rules: dict
    game_control: GameControlResponse
    bet_presets: list[ManagerBetPresetPublic]
    open_tickets: int


class ManagerMessageResult(BaseModel):
    user_message: ManagerMessagePublic
    operator_message: ManagerMessagePublic
    action: ManagerActionPublic | None = None
    ticket: ManagerTicketPublic | None = None


class ManagerActionConfirmResponse(BaseModel):
    action: ManagerActionPublic
    operator_message: ManagerMessagePublic
    state: ManagerStateResponse


class AdminManagerTicketUpdateRequest(BaseModel):
    status: str = Field(pattern="^(open|in_progress|resolved|rejected|closed)$")
    response: str = Field(default="", max_length=2000)
    approved_bet_cents: int | None = Field(default=None, gt=10_000, le=50_000)
    game_id: str | None = Field(default=None, max_length=64)


class AdminManagerTicketDetail(BaseModel):
    ticket: ManagerTicketPublic
    messages: list[ManagerMessagePublic]
    user: UserPublic


class GoogleStatusResponse(BaseModel):
    enabled: bool
    login_url: str


class WalletResponse(BaseModel):
    currency: str
    balance_cents: int
    vip_points: int
    vip_tier: str = "bronze"
    games_played: int
    total_won_cents: int

    @computed_field
    @property
    def balance(self) -> Decimal:
        return cents_to_amount(self.balance_cents)

    @computed_field
    @property
    def total_won(self) -> Decimal:
        return cents_to_amount(self.total_won_cents)


class VipClickerTierProgress(BaseModel):
    tier: str
    clicks: int


class VipClickerProgressResponse(BaseModel):
    tiers: list[VipClickerTierProgress]
    totals: dict[str, int]
    total_clicks: int


class VipClickerClickRequest(BaseModel):
    client_action_at: datetime | None = None
    count: int = Field(default=1, ge=1, le=25)


class VipTierPurchaseRequest(BaseModel):
    tier: str = Field(min_length=1, max_length=16)


class VipTierPurchaseResponse(BaseModel):
    wallet: WalletResponse
    transaction: TransactionPublic


class CashierRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    method_id: str = Field(min_length=1, max_length=64)
    promo_code: str | None = Field(default=None, max_length=64)


class TransactionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    amount_cents: int
    currency: str
    method_id: str = ""
    title: str = ""
    title_key: str = ""
    fee_cents: int = 0
    payout_cents: int = 0
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def amount(self) -> Decimal:
        return cents_to_amount(self.amount_cents)

    @computed_field
    @property
    def fee(self) -> Decimal:
        return cents_to_amount(self.fee_cents)

    @computed_field
    @property
    def payout(self) -> Decimal:
        return cents_to_amount(self.payout_cents)


class StudioWalletPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str = "EUR"
    balance_cents: int = 0
    version: int = 0

    @computed_field
    @property
    def balance(self) -> Decimal:
        return cents_to_amount(self.balance_cents)


class StudioTransactionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    type: str
    status: str
    amount_cents: int
    fee_cents: int = 0
    net_cents: int
    currency: str = "EUR"
    external_ref: str | None = None
    created_at: datetime
    updated_at: datetime


class StudioWalletResponse(BaseModel):
    wallet: StudioWalletPublic
    recent_transactions: list[StudioTransactionPublic] = Field(default_factory=list)


class SoulAppraisalRequest(BaseModel):
    fatigue: str = Field(default="fresh", max_length=24)
    debt: str = Field(default="none", max_length=24)
    compromise: str = Field(default="minor", max_length=24)


class SoulAppraisalPreviewPublic(BaseModel):
    daily_rate_cents: int
    base_value_cents: int
    next_sale_number: int
    decay_bps: int
    payout_cents: int
    sales_remaining: int


class SoulAppraisalPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_number: int
    daily_rate_cents: int
    base_value_cents: int
    decay_bps: int
    payout_cents: int
    contract_version: str
    studio_transaction_id: int
    created_at: datetime


class SoulAppraisalResponse(BaseModel):
    appraisal: SoulAppraisalPublic
    wallet: StudioWalletPublic
    transaction: StudioTransactionPublic


class IdentityTokenRequest(BaseModel):
    grant_type: str = "authorization_code"
    code: str
    redirect_uri: str
    client_id: str
    client_secret: str
    code_verifier: str


class IdentityTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: str


class IdentityUserInfo(BaseModel):
    sub: str
    name: str
    given_name: str = ""
    family_name: str = ""
    email: EmailStr
    birthdate: str = ""
    country: str = ""


class AdminUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    currency: str = "EUR"
    balance_cents: int = 0
    vip_tier: str = "bronze"

    @computed_field
    @property
    def balance(self) -> Decimal:
        return cents_to_amount(self.balance_cents)


class AdminWithdrawalPublic(BaseModel):
    transaction: TransactionPublic
    user: AdminUserSummary


class AdminUserDetail(AdminUserSummary):
    phone: str = ""
    dob: str = ""
    country: str = ""
    vip_points: int = 0
    vip_tier: str = "bronze"
    games_played: int = 0
    total_won_cents: int = 0
    provider: str
    email_verified: bool
    is_admin: bool = False
    created_at: datetime
    last_login_at: datetime | None = None
    studio_balance_cents: int = 0

    @computed_field
    @property
    def total_won(self) -> Decimal:
        return cents_to_amount(self.total_won_cents)

    @computed_field
    @property
    def studio_balance(self) -> Decimal:
        return cents_to_amount(self.studio_balance_cents)


class AdminBalanceAdjustRequest(BaseModel):
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    note: str = Field(default="Admin balance adjustment", max_length=255)


class AdminBalanceAdjustResponse(BaseModel):
    user: AdminUserSummary
    transaction: TransactionPublic


class AdminPromoCreateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    title: str = Field(default="", max_length=255)
    reward_type: str = Field(default="fixed", max_length=16)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    percent: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    max_bonus: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    min_deposit: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    usage_limit: int = Field(default=100, ge=0, le=1_000_000)
    per_user_limit: int = Field(default=1, ge=0, le=10_000)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool = True


class AdminPromoUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    reward_type: str | None = Field(default=None, max_length=16)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    percent: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2)
    max_bonus: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    min_deposit: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    usage_limit: int | None = Field(default=None, ge=0, le=1_000_000)
    per_user_limit: int | None = Field(default=None, ge=0, le=10_000)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool | None = None


class AdminPromoPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    title: str = ""
    reward_type: str
    amount_cents: int
    percent_bps: int
    max_bonus_cents: int
    min_deposit_cents: int
    usage_limit: int
    per_user_limit: int
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime
    used_count: int = 0
    status: str = "active"

    @computed_field
    @property
    def amount(self) -> Decimal:
        return cents_to_amount(self.amount_cents)

    @computed_field
    @property
    def percent(self) -> Decimal:
        return Decimal(self.percent_bps) / Decimal(100)

    @computed_field
    @property
    def max_bonus(self) -> Decimal:
        return cents_to_amount(self.max_bonus_cents)

    @computed_field
    @property
    def min_deposit(self) -> Decimal:
        return cents_to_amount(self.min_deposit_cents)


class AdminPromoRedemptionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    promo_code_id: int
    promo_code: str = ""
    promo_title: str = ""
    transaction_id: int
    bonus_cents: int
    deposit_cents: int
    created_at: datetime

    @computed_field
    @property
    def bonus(self) -> Decimal:
        return cents_to_amount(self.bonus_cents)

    @computed_field
    @property
    def deposit(self) -> Decimal:
        return cents_to_amount(self.deposit_cents)


class AdminPromoRedemptionDetail(AdminPromoRedemptionPublic):
    user_id: int
    user_email: str = ""
    user_name: str = ""


class AdminPromoStats(BaseModel):
    total: int = 0
    active: int = 0
    scheduled: int = 0
    expired: int = 0
    inactive: int = 0
    total_redemptions: int = 0


class PromoPreviewPublic(BaseModel):
    promo: AdminPromoPublic
    bonus_cents: int
    deposit_cents: int
    status: str = "active"

    @computed_field
    @property
    def bonus(self) -> Decimal:
        return cents_to_amount(self.bonus_cents)

    @computed_field
    @property
    def deposit(self) -> Decimal:
        return cents_to_amount(self.deposit_cents)


class GameRoundPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    game_id: str
    result_number: int | None = None
    result_color: str | None = None
    total_bet_cents: int
    total_win_cents: int
    net_cents: int
    status: str = "completed"
    bets_json: str = "[]"
    result_json: str = "{}"
    created_at: datetime
    settled_at: datetime | None = None

    @computed_field
    @property
    def total_bet(self) -> Decimal:
        return cents_to_amount(self.total_bet_cents)

    @computed_field
    @property
    def total_win(self) -> Decimal:
        return cents_to_amount(self.total_win_cents)

    @computed_field
    @property
    def net(self) -> Decimal:
        return cents_to_amount(self.net_cents)

    @computed_field
    @property
    def bets(self) -> list[dict]:
        try:
            value = json.loads(self.bets_json or "[]")
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    @computed_field
    @property
    def result(self) -> dict:
        try:
            value = json.loads(self.result_json or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


class AuditLogPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None = None
    target_user_id: int | None = None
    action: str
    amount_cents: int | None = None
    before_balance_cents: int | None = None
    after_balance_cents: int | None = None
    metadata_json: str = "{}"
    ip_address: str = ""
    user_agent: str = ""
    created_at: datetime

    @computed_field
    @property
    def amount(self) -> Decimal | None:
        return cents_to_amount(self.amount_cents) if self.amount_cents is not None else None

    @computed_field
    @property
    def metadata(self) -> dict:
        try:
            value = json.loads(self.metadata_json or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


class AdminPromoDetail(BaseModel):
    promo: AdminPromoPublic
    redemptions: list[AdminPromoRedemptionDetail] = []
    audit: list[AuditLogPublic] = []


class CashierResponse(BaseModel):
    wallet: WalletResponse
    transaction: TransactionPublic


class RouletteBetRequest(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    selection: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=8, decimal_places=2)


class RouletteSpinRequest(BaseModel):
    bets: list[RouletteBetRequest] = Field(min_length=1, max_length=64)


class RouletteBetResult(BaseModel):
    type: str
    selection: str
    amount_cents: int
    win_cents: int
    payout: int
    won: bool

    @computed_field
    @property
    def amount(self) -> Decimal:
        return cents_to_amount(self.amount_cents)

    @computed_field
    @property
    def win(self) -> Decimal:
        return cents_to_amount(self.win_cents)


class RouletteResult(BaseModel):
    number: int
    color: str
    parity: str
    range: str
    dozen: str
    column: str


class RouletteSpinResponse(BaseModel):
    round_id: int
    result: RouletteResult
    bets: list[RouletteBetResult]
    total_bet_cents: int
    total_win_cents: int
    net_cents: int
    wallet: WalletResponse
    transaction: TransactionPublic

    @computed_field
    @property
    def total_bet(self) -> Decimal:
        return cents_to_amount(self.total_bet_cents)

    @computed_field
    @property
    def total_win(self) -> Decimal:
        return cents_to_amount(self.total_win_cents)

    @computed_field
    @property
    def net(self) -> Decimal:
        return cents_to_amount(self.net_cents)


class SlotSpinRequest(BaseModel):
    bet: Decimal = Field(gt=0, max_digits=8, decimal_places=2)


class SlotWinningLine(BaseModel):
    line: int
    symbol: str
    count: int
    multiplier: int
    win_cents: int
    positions: list[dict]

    @computed_field
    @property
    def win(self) -> Decimal:
        return cents_to_amount(self.win_cents)


class SlotSpinResponse(BaseModel):
    round_id: int
    grid: list[list[str]]
    winning_lines: list[SlotWinningLine]
    total_bet_cents: int
    total_win_cents: int
    net_cents: int
    wallet: WalletResponse
    transaction: TransactionPublic

    @computed_field
    @property
    def total_bet(self) -> Decimal:
        return cents_to_amount(self.total_bet_cents)

    @computed_field
    @property
    def total_win(self) -> Decimal:
        return cents_to_amount(self.total_win_cents)

    @computed_field
    @property
    def net(self) -> Decimal:
        return cents_to_amount(self.net_cents)


class PlinkoDropRequest(BaseModel):
    bet: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    mode: str = Field(default="classic", min_length=1, max_length=16)
    risk: str = Field(default="medium", min_length=1, max_length=16)
    rows: int = Field(default=12, ge=8, le=16)
    balls: int = Field(default=1, ge=1, le=10)


class PlinkoBallResult(BaseModel):
    index: int
    bet_cents: int
    path: list[str]
    slot: int
    multiplier_cents: int
    win_cents: int

    @computed_field
    @property
    def multiplier(self) -> Decimal:
        return cents_to_amount(self.multiplier_cents)

    @computed_field
    @property
    def win(self) -> Decimal:
        return cents_to_amount(self.win_cents)


class PlinkoDropResponse(BaseModel):
    round_id: int
    mode: str
    risk: str
    rows: int
    ball_count: int
    pockets: list[int]
    balls: list[PlinkoBallResult]
    total_bet_cents: int
    total_win_cents: int
    net_cents: int
    wallet: WalletResponse
    transaction: TransactionPublic

    @computed_field
    @property
    def total_bet(self) -> Decimal:
        return cents_to_amount(self.total_bet_cents)

    @computed_field
    @property
    def total_win(self) -> Decimal:
        return cents_to_amount(self.total_win_cents)

    @computed_field
    @property
    def net(self) -> Decimal:
        return cents_to_amount(self.net_cents)


class SurvivalStartRequest(BaseModel):
    bet: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    lang: str = Field(default="ru", min_length=2, max_length=2)


class SurvivalChoiceRequest(BaseModel):
    choice_id: str = Field(min_length=1, max_length=1)
    lang: str = Field(default="ru", min_length=2, max_length=2)


class SurvivalActionRequest(BaseModel):
    lang: str = Field(default="ru", min_length=2, max_length=2)


class SurvivalChoicePublic(BaseModel):
    id: str
    text: str


class SurvivalParameterPublic(BaseModel):
    key: str
    label: str
    value: str
    resolved_value: str | None = None


class SurvivalQuestionPublic(BaseModel):
    scenario_id: str
    stage_key: str
    stage_label: str
    title: str
    prompt: str
    parameters: list[SurvivalParameterPublic]
    choices: list[SurvivalChoicePublic]


class SurvivalRoundResponse(BaseModel):
    round_id: int
    status: str
    phase: str
    category_key: str
    category_label: str
    cause: str
    stage: int
    total_stages: int
    deadline_at: datetime | None = None
    question: SurvivalQuestionPublic | None = None
    selected_choice_id: str | None = None
    correct_choice_id: str | None = None
    explanation: str | None = None
    outcome: str | None = None
    final_multiplier: Decimal
    potential_win_cents: int
    total_bet_cents: int
    total_win_cents: int
    net_cents: int
    started_at: datetime
    settled_at: datetime | None = None
    wallet: WalletResponse
    transaction: TransactionPublic | None = None

    @computed_field
    @property
    def potential_win(self) -> Decimal:
        return cents_to_amount(self.potential_win_cents)

    @computed_field
    @property
    def total_bet(self) -> Decimal:
        return cents_to_amount(self.total_bet_cents)

    @computed_field
    @property
    def total_win(self) -> Decimal:
        return cents_to_amount(self.total_win_cents)

    @computed_field
    @property
    def net(self) -> Decimal:
        return cents_to_amount(self.net_cents)


class MinesStartRequest(BaseModel):
    bet: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    mine_count: int = Field(ge=1, le=19)


class MinesRevealRequest(BaseModel):
    cell: int = Field(ge=0, le=19)


class MinesRoundResponse(BaseModel):
    round_id: int
    status: str
    mine_count: int
    revealed_cells: list[int]
    mines: list[int] | None = None
    current_multiplier: Decimal
    total_bet_cents: int
    total_win_cents: int
    net_cents: int
    potential_win_cents: int
    started_at: datetime
    settled_at: datetime | None = None
    wallet: WalletResponse
    transaction: TransactionPublic | None = None

    @computed_field
    @property
    def total_bet(self) -> Decimal:
        return cents_to_amount(self.total_bet_cents)

    @computed_field
    @property
    def total_win(self) -> Decimal:
        return cents_to_amount(self.total_win_cents)

    @computed_field
    @property
    def net(self) -> Decimal:
        return cents_to_amount(self.net_cents)

    @computed_field
    @property
    def potential_win(self) -> Decimal:
        return cents_to_amount(self.potential_win_cents)


class BlocksStartRequest(BaseModel):
    bet: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    difficulty: str = "level1"


class BlocksPlaceRequest(BaseModel):
    piece_id: int = Field(ge=1)
    rotation: int = Field(ge=0, le=3)
    x: int = Field(ge=-4, le=10)
    y: int | None = Field(default=None, ge=0, le=20)


class BlocksPiece(BaseModel):
    id: int
    type: str


class BlocksRoundResponse(BaseModel):
    round_id: int
    status: str
    difficulty: str
    board_height: int
    tick_ms: int
    pressure_level: int
    cashout_available: bool
    board: list[list[str]]
    current_piece: BlocksPiece | None = None
    next_pieces: list[BlocksPiece]
    score: int
    lines_cleared: int
    combo: int
    pieces_placed: int
    current_multiplier: Decimal
    total_bet_cents: int
    total_win_cents: int
    net_cents: int
    potential_win_cents: int
    last_clear: int = 0
    last_drop_y: int | None = None
    loss_reason: str | None = None
    started_at: datetime
    settled_at: datetime | None = None
    wallet: WalletResponse
    transaction: TransactionPublic | None = None

    @computed_field
    @property
    def total_bet(self) -> Decimal:
        return cents_to_amount(self.total_bet_cents)

    @computed_field
    @property
    def total_win(self) -> Decimal:
        return cents_to_amount(self.total_win_cents)

    @computed_field
    @property
    def net(self) -> Decimal:
        return cents_to_amount(self.net_cents)

    @computed_field
    @property
    def potential_win(self) -> Decimal:
        return cents_to_amount(self.potential_win_cents)


class HoldemStartRequest(BaseModel):
    ante: Decimal = Field(gt=0, max_digits=8, decimal_places=2)


class HoldemDecisionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=16)


class HoldemHandResponse(BaseModel):
    name: str
    name_key: str
    rank: int
    cards: list[str]


class HoldemRoundResponse(BaseModel):
    round_id: int
    status: str
    stage: str
    player_cards: list[str]
    dealer_cards: list[str]
    dealer_hidden_count: int
    community_cards: list[str]
    available_actions: list[str]
    dealer_qualified: bool | None = None
    outcome: str | None = None
    player_hand: HoldemHandResponse | None = None
    dealer_hand: HoldemHandResponse | None = None
    total_bet_cents: int
    total_win_cents: int
    net_cents: int
    call_amount_cents: int
    started_at: datetime
    settled_at: datetime | None = None
    wallet: WalletResponse
    transaction: TransactionPublic | None = None

    @computed_field
    @property
    def total_bet(self) -> Decimal:
        return cents_to_amount(self.total_bet_cents)

    @computed_field
    @property
    def total_win(self) -> Decimal:
        return cents_to_amount(self.total_win_cents)

    @computed_field
    @property
    def net(self) -> Decimal:
        return cents_to_amount(self.net_cents)

    @computed_field
    @property
    def call_amount(self) -> Decimal:
        return cents_to_amount(self.call_amount_cents)


class CrashStartRequest(BaseModel):
    bet: Decimal = Field(gt=0, max_digits=8, decimal_places=2)


class CrashRoundResponse(BaseModel):
    round_id: int
    status: str
    current_multiplier: Decimal
    crash_multiplier: Decimal | None = None
    cashout_multiplier: Decimal | None = None
    total_bet_cents: int
    total_win_cents: int
    net_cents: int
    started_at: datetime
    settled_at: datetime | None = None
    wallet: WalletResponse
    transaction: TransactionPublic | None = None

    @computed_field
    @property
    def total_bet(self) -> Decimal:
        return cents_to_amount(self.total_bet_cents)

    @computed_field
    @property
    def total_win(self) -> Decimal:
        return cents_to_amount(self.total_win_cents)

    @computed_field
    @property
    def net(self) -> Decimal:
        return cents_to_amount(self.net_cents)
