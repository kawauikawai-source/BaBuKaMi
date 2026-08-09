from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.vip import VIP_RULES, next_vip_rule, normalize_vip_tier, vip_rule, vip_tier_index
from app.db.session import get_db
from app.deps import get_current_user
from app.models import User, VipClickerProgress
from app.routers.wallet import wallet_response
from app.schemas import (
    TransactionPublic,
    VipClickerClickRequest,
    VipClickerProgressResponse,
    VipClickerTierProgress,
    VipTierPurchaseRequest,
    VipTierPurchaseResponse,
)
from app.services.idempotency import begin_idempotency, complete_idempotency
from app.services.money import apply_balance_delta
from app.services.abuse import add_abuse_event, enforce_vip_clicker_speed


router = APIRouter(prefix="/vip", tags=["vip"])
settings = get_settings()

VALID_CLICKER_TIERS = ("bronze", "silver", "gold", "platinum")


def normalize_tier(tier: str) -> str:
    value = tier.strip().lower()
    if value not in VALID_CLICKER_TIERS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid VIP tier")
    return value


def to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def progress_response(rows: list[VipClickerProgress]) -> VipClickerProgressResponse:
    totals = {tier: 0 for tier in VALID_CLICKER_TIERS}
    for row in rows:
        if row.tier in totals:
            totals[row.tier] = row.clicks
    return VipClickerProgressResponse(
        tiers=[VipClickerTierProgress(tier=tier, clicks=totals[tier]) for tier in VALID_CLICKER_TIERS],
        totals=totals,
        total_clicks=sum(totals.values()),
    )


def user_progress(db: Session, user_id: int) -> list[VipClickerProgress]:
    return list(
        db.scalars(
            select(VipClickerProgress)
            .where(VipClickerProgress.user_id == user_id)
            .order_by(VipClickerProgress.id.asc())
        ).all()
    )


@router.get("/clicker", response_model=VipClickerProgressResponse)
def get_clicker_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VipClickerProgressResponse:
    return progress_response(user_progress(db, current_user.id))


@router.post("/clicker/{tier}/click", response_model=VipClickerProgressResponse)
@limiter.limit(settings.rate_limit_vip_clicker)
def click_vip_tier(
    request: Request,
    tier: str,
    payload: VipClickerClickRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VipClickerProgressResponse:
    tier = normalize_tier(tier)
    enforce_vip_clicker_speed(db, user=current_user, request=request, tier=tier)
    click_count = payload.count if payload else 1
    add_abuse_event(
        db,
        action="vip.clicker.click",
        user=current_user,
        request=request,
        key=tier,
        metadata={"count": click_count},
    )
    client_action_at = to_utc(payload.client_action_at if payload else None)
    row = db.scalar(
        select(VipClickerProgress).where(
            VipClickerProgress.user_id == current_user.id,
            VipClickerProgress.tier == tier,
        )
    )
    if row is None:
        row = VipClickerProgress(user_id=current_user.id, tier=tier, clicks=0)
        db.add(row)
    elif client_action_at is not None and row.reset_at is not None and client_action_at <= to_utc(row.reset_at):
        return progress_response(user_progress(db, current_user.id))
    row.clicks += click_count
    db.commit()
    return progress_response(user_progress(db, current_user.id))


@router.post("/clicker/{tier}/reset", response_model=VipClickerProgressResponse)
@limiter.limit(settings.rate_limit_vip_clicker)
def reset_vip_tier(
    request: Request,
    tier: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VipClickerProgressResponse:
    tier = normalize_tier(tier)
    row = db.scalar(
        select(VipClickerProgress).where(
            VipClickerProgress.user_id == current_user.id,
            VipClickerProgress.tier == tier,
        )
    )
    if row is not None:
        row.clicks = 0
        row.reset_at = datetime.now(UTC)
    else:
        row = VipClickerProgress(user_id=current_user.id, tier=tier, clicks=0, reset_at=datetime.now(UTC))
        db.add(row)
    db.commit()
    return progress_response(user_progress(db, current_user.id))


def vip_error(code: str, status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


@router.post("/tiers/purchase", response_model=VipTierPurchaseResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_vip_purchase)
def purchase_vip_tier(
    request: Request,
    payload: VipTierPurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VipTierPurchaseResponse:
    requested_tier = str(payload.tier or "").strip().lower()
    if requested_tier not in VIP_RULES:
        raise vip_error("err_vip_invalid")
    target_tier = normalize_vip_tier(requested_tier)
    if target_tier == "bronze":
        raise vip_error("err_vip_already_unlocked", status.HTTP_409_CONFLICT)
    if target_tier not in VIP_RULES:
        raise vip_error("err_vip_invalid")

    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return VipTierPurchaseResponse.model_validate(idem.replay_response)

    user = db.merge(current_user)
    current_tier = normalize_vip_tier(user.vip_tier)
    if vip_tier_index(target_tier) <= vip_tier_index(current_tier):
        raise vip_error("err_vip_already_unlocked", status.HTTP_409_CONFLICT)

    expected_next = next_vip_rule(current_tier)
    if not expected_next or expected_next.tier != target_tier:
        raise vip_error("err_vip_not_next", status.HTTP_409_CONFLICT)

    current_rule = vip_rule(current_tier)
    if current_rule.purchase_threshold is None or int(user.vip_points or 0) < current_rule.purchase_threshold:
        raise vip_error("err_vip_not_enough_points")

    price_cents = current_rule.next_price_cents
    before_balance = user.balance_cents
    if before_balance < price_cents:
        raise vip_error("err_vip_balance")

    user.vip_tier = target_tier
    user.vip_points = max(int(user.vip_points or 0), expected_next.min_points)
    db.add(user)
    db.flush()
    transaction = apply_balance_delta(
        db,
        user=user,
        amount_cents=-price_cents,
        transaction_type="vip",
        method_id="vip-tier",
        title=target_tier.title() + " VIP",
        title_key="tx_vip_tier_purchase",
        action="vip.tier.purchase",
        actor_user=user,
        metadata={
            "tier": target_tier,
            "previous_tier": current_tier,
            "vip_points": user.vip_points,
        },
        request=request,
    )
    response = VipTierPurchaseResponse(
        wallet=wallet_response(user),
        transaction=TransactionPublic.model_validate(transaction),
    )
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(user)
    db.refresh(transaction)
    return VipTierPurchaseResponse(
        wallet=wallet_response(user),
        transaction=TransactionPublic.model_validate(transaction),
    )
