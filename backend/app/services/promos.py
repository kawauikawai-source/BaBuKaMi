from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
import re

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import amount_to_cents
from app.models import PromoCode, PromoRedemption, Transaction, User
from app.services.audit import add_audit_log
from app.services.money import apply_balance_delta


PROMO_REWARD_TYPES = {"fixed", "percent"}
PROMO_CODE_PATTERN = re.compile(r"^[A-Z0-9_-]{3,64}$")
PROMO_STATUSES = {"active", "scheduled", "inactive", "expired", "all"}


def now_utc() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_promo_code(code: str) -> str:
    value = re.sub(r"\s+", "", code or "").upper()
    if not PROMO_CODE_PATTERN.fullmatch(value):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "err_promo_invalid"})
    return value


def promo_error(code: str, amount_cents: int | None = None) -> HTTPException:
    detail: dict[str, str] = {"code": code}
    if amount_cents is not None:
        detail["amount"] = str(Decimal(amount_cents) / Decimal(100))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def promo_config_error(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": code})


def promo_status(promo: PromoCode, at: datetime | None = None) -> str:
    current = as_utc(at) or now_utc()
    starts_at = as_utc(promo.starts_at)
    expires_at = as_utc(promo.expires_at)
    if not promo.is_active:
        return "inactive"
    if expires_at and expires_at <= current:
        return "expired"
    if starts_at and starts_at > current:
        return "scheduled"
    return "active"


def redemption_count(db: Session, promo: PromoCode, user: User | None = None) -> int:
    query = select(func.count(PromoRedemption.id)).where(PromoRedemption.promo_code_id == promo.id)
    if user is not None:
        query = query.where(PromoRedemption.user_id == user.id)
    return int(db.scalar(query) or 0)


def percent_to_bps(percent: Decimal | None) -> int:
    if percent is None:
        return 0
    return int((percent * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def validate_reward_config(
    *,
    reward_type: str,
    amount_cents: int,
    percent_bps: int,
    max_bonus_cents: int,
    min_deposit_cents: int,
    starts_at: datetime | None,
    expires_at: datetime | None,
) -> None:
    if reward_type not in PROMO_REWARD_TYPES:
        raise promo_config_error("err_promo_reward_type")
    if reward_type == "fixed" and amount_cents <= 0:
        raise promo_config_error("err_promo_fixed_amount")
    if reward_type == "percent":
        if percent_bps <= 0:
            raise promo_config_error("err_promo_percent_value")
        if max_bonus_cents <= 0:
            raise promo_config_error("err_promo_max_bonus")
    start = as_utc(starts_at)
    end = as_utc(expires_at)
    if start and end and end <= start:
        raise promo_config_error("err_promo_date_range")


def promo_public(db: Session, promo: PromoCode):
    from app.schemas import AdminPromoPublic

    return AdminPromoPublic(
        id=promo.id,
        code=promo.code,
        title=promo.title,
        reward_type=promo.reward_type,
        amount_cents=promo.amount_cents,
        percent_bps=promo.percent_bps,
        max_bonus_cents=promo.max_bonus_cents,
        min_deposit_cents=promo.min_deposit_cents,
        usage_limit=promo.usage_limit,
        per_user_limit=promo.per_user_limit,
        starts_at=promo.starts_at,
        expires_at=promo.expires_at,
        is_active=promo.is_active,
        created_by_user_id=promo.created_by_user_id,
        created_at=promo.created_at,
        updated_at=promo.updated_at,
        used_count=redemption_count(db, promo),
        status=promo_status(promo),
    )


def calculate_bonus_cents(promo: PromoCode, deposit_cents: int) -> int:
    if promo.reward_type == "fixed":
        return promo.amount_cents
    raw_bonus = deposit_cents * promo.percent_bps // 10_000
    return min(raw_bonus, promo.max_bonus_cents)


def preview_promo_code(
    db: Session,
    *,
    code: str,
    deposit_amount=None,
) -> tuple[PromoCode, int, int]:
    promo_code = normalize_promo_code(code)
    promo = db.scalar(select(PromoCode).where(PromoCode.code == promo_code))
    if promo is None:
        raise promo_error("err_promo_invalid")

    current_status = promo_status(promo)
    if current_status == "inactive":
        raise promo_error("err_promo_inactive")
    if current_status == "scheduled":
        raise promo_error("err_promo_not_started")
    if current_status == "expired":
        raise promo_error("err_promo_expired")

    deposit_cents = amount_to_cents(deposit_amount) if deposit_amount is not None else 0
    if promo.reward_type == "percent":
        if deposit_cents <= 0:
            raise promo_error("err_amount_invalid")
        if deposit_cents < promo.min_deposit_cents:
            raise promo_error("err_promo_min_deposit", promo.min_deposit_cents)

    bonus_cents = calculate_bonus_cents(promo, deposit_cents)
    if bonus_cents <= 0:
        raise promo_error("err_promo_invalid")
    return promo, bonus_cents, deposit_cents


def redeem_promo_code(
    db: Session,
    *,
    user: User,
    code: str,
    deposit_amount,
    request: Request | None = None,
) -> Transaction:
    promo, bonus_cents, deposit_cents = preview_promo_code(db, code=code, deposit_amount=deposit_amount)

    if promo.usage_limit and redemption_count(db, promo) >= promo.usage_limit:
        raise promo_error("err_promo_usage_limit")
    if promo.per_user_limit and redemption_count(db, promo, user) >= promo.per_user_limit:
        raise promo_error("err_promo_already_used")

    transaction = apply_balance_delta(
        db,
        user=user,
        amount_cents=bonus_cents,
        transaction_type="deposit",
        method_id="promo",
        title_key="tx_promo_title",
        title=f"Promo code: {promo.code}",
        action="cashier.promo.redeem",
        metadata={
            "promo_id": promo.id,
            "promo_code": promo.code,
            "reward_type": promo.reward_type,
            "deposit_cents": deposit_cents,
            "bonus_cents": bonus_cents,
        },
        request=request,
    )
    db.add(
        PromoRedemption(
            promo_code_id=promo.id,
            user_id=user.id,
            transaction_id=transaction.id,
            bonus_cents=bonus_cents,
            deposit_cents=deposit_cents,
        )
    )
    return transaction


def audit_promo_admin_action(
    db: Session,
    *,
    action: str,
    promo: PromoCode,
    actor_user: User,
    request: Request | None = None,
) -> None:
    add_audit_log(
        db,
        action=action,
        actor_user=actor_user,
        target_user=None,
        metadata={
            "promo_id": promo.id,
            "promo_code": promo.code,
            "reward_type": promo.reward_type,
            "amount_cents": promo.amount_cents,
            "percent_bps": promo.percent_bps,
            "max_bonus_cents": promo.max_bonus_cents,
            "min_deposit_cents": promo.min_deposit_cents,
            "usage_limit": promo.usage_limit,
            "per_user_limit": promo.per_user_limit,
            "starts_at": promo.starts_at.isoformat() if promo.starts_at else None,
            "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
            "is_active": promo.is_active,
        },
        request=request,
    )
