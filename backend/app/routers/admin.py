from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.money import ADMIN_BALANCE_MAX_CENTS, amount_to_cents
from app.core.errors import api_error
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.deps import get_admin_user
from app.models import AuditLog, GameRound, ManagerBetPreset, ManagerMessage, ManagerTicket, PromoCode, PromoRedemption, Transaction, User
from app.schemas import (
    AdminBalanceAdjustRequest,
    AdminBalanceAdjustResponse,
    AdminManagerTicketDetail,
    AdminManagerTicketUpdateRequest,
    AdminPromoCreateRequest,
    AdminPromoDetail,
    AdminPromoPublic,
    AdminPromoRedemptionPublic,
    AdminPromoRedemptionDetail,
    AdminPromoStats,
    AdminPromoUpdateRequest,
    AdminUserDetail,
    AdminUserSummary,
    AdminWithdrawalPublic,
    AuditLogPublic,
    GameRoundPublic,
    TransactionPublic,
    ManagerTicketPublic,
    UserPublic,
)
from app.services.money import apply_balance_delta, approve_withdrawal_transaction, reject_withdrawal_transaction
from app.services.idempotency import begin_idempotency, complete_idempotency
from app.services.promos import (
    PROMO_STATUSES,
    audit_promo_admin_action,
    normalize_promo_code,
    now_utc,
    percent_to_bps,
    promo_public,
    validate_reward_config,
)
from app.services.audit import add_audit_log
from app.services.manager import (
    MANAGER_TIERS,
    active_presets,
    add_message,
    message_public,
    parse_json,
    require_manager_access,
    ticket_public,
    utc_now,
)


router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()
WITHDRAWAL_STATUSES = {"pending", "completed", "rejected", "all"}


def withdrawal_response(transaction: Transaction) -> AdminWithdrawalPublic:
    return AdminWithdrawalPublic(
        transaction=TransactionPublic.model_validate(transaction),
        user=AdminUserSummary(
            id=transaction.user.id,
            email=transaction.user.email,
            name=transaction.user.name,
            currency=transaction.user.currency,
            balance_cents=transaction.user.balance_cents,
            vip_tier=transaction.user.vip_tier,
        ),
    )


def user_summary(user: User) -> AdminUserSummary:
    return AdminUserSummary(
        id=user.id,
        email=user.email,
        name=user.name,
        currency=user.currency,
        balance_cents=user.balance_cents,
        vip_tier=user.vip_tier,
    )


def user_detail(user: User) -> AdminUserDetail:
    return AdminUserDetail.model_validate(user)


def get_withdrawal(db: Session, transaction_id: int) -> Transaction:
    transaction = db.scalar(
        select(Transaction)
        .options(joinedload(Transaction.user))
        .where(Transaction.id == transaction_id, Transaction.type == "withdraw")
    )
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Withdrawal not found")
    return transaction


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def parse_date_filter(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid date filter") from None


def get_promo(db: Session, promo_id: int) -> PromoCode:
    promo = db.get(PromoCode, promo_id)
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo code not found")
    return promo


def promo_amount_cents(payload: AdminPromoCreateRequest | AdminPromoUpdateRequest, current: PromoCode | None = None) -> int:
    if "amount" in payload.model_fields_set or current is None:
        return amount_to_cents(payload.amount) if payload.amount is not None else 0
    return current.amount_cents


def promo_max_bonus_cents(payload: AdminPromoCreateRequest | AdminPromoUpdateRequest, current: PromoCode | None = None) -> int:
    if "max_bonus" in payload.model_fields_set or current is None:
        return amount_to_cents(payload.max_bonus) if payload.max_bonus is not None else 0
    return current.max_bonus_cents


def promo_min_deposit_cents(payload: AdminPromoCreateRequest | AdminPromoUpdateRequest, current: PromoCode | None = None) -> int:
    if "min_deposit" in payload.model_fields_set or current is None:
        return amount_to_cents(payload.min_deposit) if payload.min_deposit is not None else 0
    return current.min_deposit_cents


def promo_redemption_public(redemption: PromoRedemption) -> AdminPromoRedemptionDetail:
    user = redemption.user
    return AdminPromoRedemptionDetail(
        id=redemption.id,
        promo_code_id=redemption.promo_code_id,
        promo_code=redemption.promo_code.code if redemption.promo_code else "",
        promo_title=redemption.promo_code.title if redemption.promo_code else "",
        transaction_id=redemption.transaction_id,
        bonus_cents=redemption.bonus_cents,
        deposit_cents=redemption.deposit_cents,
        created_at=redemption.created_at,
        user_id=redemption.user_id,
        user_email=user.email if user else "",
        user_name=user.name if user else "",
    )


def promo_audit_query(promo_id: int):
    needle = f'"promo_id":{promo_id}'
    return (
        select(AuditLog)
        .where(AuditLog.metadata_json.contains(needle))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )


@router.get("/users", response_model=list[AdminUserSummary])
def list_users(
    q: str = Query(default="", max_length=128),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[AdminUserSummary]:
    search = q.strip().lower()
    query = select(User).order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
    if search:
        pattern = f"%{search}%"
        query = query.where((User.email.ilike(pattern)) | (User.name.ilike(pattern)))
    return [user_summary(user) for user in db.scalars(query).all()]


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user_detail(
    user_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserDetail:
    return user_detail(get_user(db, user_id))


@router.get("/users/{user_id}/transactions", response_model=list[TransactionPublic])
def get_user_transactions(
    user_id: int,
    type_filter: str = Query(default="", alias="type", max_length=32),
    status_filter: str = Query(default="", alias="status", max_length=32),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[TransactionPublic]:
    get_user(db, user_id)
    query = select(Transaction).where(Transaction.user_id == user_id)
    if type_filter.strip():
        query = query.where(Transaction.type == type_filter.strip().lower())
    if status_filter.strip():
        query = query.where(Transaction.status == status_filter.strip().lower())
    start = parse_date_filter(date_from)
    end = parse_date_filter(date_to)
    if start:
        query = query.where(Transaction.created_at >= start)
    if end:
        query = query.where(Transaction.created_at <= end)
    transactions = db.scalars(query.order_by(Transaction.created_at.desc(), Transaction.id.desc()).offset(offset).limit(limit)).all()
    return [TransactionPublic.model_validate(transaction) for transaction in transactions]


@router.get("/users/{user_id}/game-rounds", response_model=list[GameRoundPublic])
def get_user_game_rounds(
    user_id: int,
    game_id: str = Query(default="", max_length=64),
    status_filter: str = Query(default="", alias="status", max_length=32),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[GameRoundPublic]:
    get_user(db, user_id)
    query = select(GameRound).where(GameRound.user_id == user_id)
    if game_id.strip():
        query = query.where(GameRound.game_id == game_id.strip())
    if status_filter.strip():
        query = query.where(GameRound.status == status_filter.strip().lower())
    start = parse_date_filter(date_from)
    end = parse_date_filter(date_to)
    if start:
        query = query.where(GameRound.created_at >= start)
    if end:
        query = query.where(GameRound.created_at <= end)
    rounds = db.scalars(query.order_by(GameRound.created_at.desc(), GameRound.id.desc()).offset(offset).limit(limit)).all()
    return [GameRoundPublic.model_validate(round_item) for round_item in rounds]


@router.get("/users/{user_id}/promo-redemptions", response_model=list[AdminPromoRedemptionPublic])
def get_user_promo_redemptions(
    user_id: int,
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[AdminPromoRedemptionPublic]:
    get_user(db, user_id)
    redemptions = db.scalars(
        select(PromoRedemption)
        .options(joinedload(PromoRedemption.promo_code))
        .where(PromoRedemption.user_id == user_id)
        .order_by(PromoRedemption.created_at.desc(), PromoRedemption.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        AdminPromoRedemptionPublic(
            id=redemption.id,
            promo_code_id=redemption.promo_code_id,
            promo_code=redemption.promo_code.code if redemption.promo_code else "",
            promo_title=redemption.promo_code.title if redemption.promo_code else "",
            transaction_id=redemption.transaction_id,
            bonus_cents=redemption.bonus_cents,
            deposit_cents=redemption.deposit_cents,
            created_at=redemption.created_at,
        )
        for redemption in redemptions
    ]


@router.post("/users/{user_id}/balance", response_model=AdminBalanceAdjustResponse)
@limiter.limit(settings.rate_limit_admin_money)
def adjust_user_balance(
    user_id: int,
    payload: AdminBalanceAdjustRequest,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminBalanceAdjustResponse:
    amount_cents = amount_to_cents(payload.amount)
    if amount_cents == 0:
        raise api_error("err_amount_invalid")
    if abs(amount_cents) > ADMIN_BALANCE_MAX_CENTS:
        raise api_error("err_admin_balance_max", amount_cents=ADMIN_BALANCE_MAX_CENTS)

    idem = begin_idempotency(
        db,
        user=admin_user,
        request=request,
        payload={"user_id": user_id, **payload.model_dump(mode="json")},
    )
    if idem.replay_response is not None:
        return AdminBalanceAdjustResponse.model_validate(idem.replay_response)

    user = get_user(db, user_id)
    note = payload.note.strip() or "Admin balance adjustment"
    transaction = apply_balance_delta(
        db,
        user=user,
        amount_cents=amount_cents,
        transaction_type="deposit" if amount_cents > 0 else "withdraw",
        method_id="admin",
        title=note,
        action="admin.balance.credit" if amount_cents > 0 else "admin.balance.debit",
        actor_user=admin_user,
        metadata={"note": note},
        request=request,
    )
    response = AdminBalanceAdjustResponse(user=user_summary(user), transaction=TransactionPublic.model_validate(transaction))
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(user)
    db.refresh(transaction)
    return AdminBalanceAdjustResponse(user=user_summary(user), transaction=TransactionPublic.model_validate(transaction))


@router.get("/promos", response_model=list[AdminPromoPublic])
def list_promos(
    status_filter: str = Query(default="active", alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[AdminPromoPublic]:
    status_value = status_filter.strip().lower()
    if status_value not in PROMO_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid promo status")

    current = now_utc()
    query = select(PromoCode).order_by(PromoCode.created_at.desc(), PromoCode.id.desc())
    if status_value == "inactive":
        query = query.where(PromoCode.is_active.is_(False))
    elif status_value == "expired":
        query = query.where(PromoCode.is_active.is_(True), PromoCode.expires_at.is_not(None), PromoCode.expires_at <= current)
    elif status_value == "scheduled":
        query = query.where(PromoCode.is_active.is_(True), PromoCode.starts_at.is_not(None), PromoCode.starts_at > current)
    elif status_value == "active":
        query = query.where(
            PromoCode.is_active.is_(True),
            (PromoCode.starts_at.is_(None)) | (PromoCode.starts_at <= current),
            (PromoCode.expires_at.is_(None)) | (PromoCode.expires_at > current),
        )
    promos = db.scalars(query.offset(offset).limit(limit)).all()
    return [promo_public(db, promo) for promo in promos]


@router.get("/promos/stats", response_model=AdminPromoStats)
def promo_stats(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminPromoStats:
    promos = db.scalars(select(PromoCode)).all()
    statuses = [promo_public(db, promo).status for promo in promos]
    return AdminPromoStats(
        total=len(promos),
        active=statuses.count("active"),
        scheduled=statuses.count("scheduled"),
        expired=statuses.count("expired"),
        inactive=statuses.count("inactive"),
        total_redemptions=int(db.scalar(select(func.count(PromoRedemption.id))) or 0),
    )


@router.get("/promos/{promo_id}", response_model=AdminPromoDetail)
def promo_detail(
    promo_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminPromoDetail:
    promo = get_promo(db, promo_id)
    redemptions = db.scalars(
        select(PromoRedemption)
        .options(joinedload(PromoRedemption.promo_code), joinedload(PromoRedemption.user))
        .where(PromoRedemption.promo_code_id == promo.id)
        .order_by(PromoRedemption.created_at.desc(), PromoRedemption.id.desc())
        .limit(5)
    ).all()
    audit = db.scalars(promo_audit_query(promo.id).limit(10)).all()
    return AdminPromoDetail(
        promo=promo_public(db, promo),
        redemptions=[promo_redemption_public(redemption) for redemption in redemptions],
        audit=[AuditLogPublic.model_validate(item) for item in audit],
    )


@router.get("/promos/{promo_id}/redemptions", response_model=list[AdminPromoRedemptionDetail])
def promo_redemptions(
    promo_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[AdminPromoRedemptionDetail]:
    promo = get_promo(db, promo_id)
    redemptions = db.scalars(
        select(PromoRedemption)
        .options(joinedload(PromoRedemption.promo_code), joinedload(PromoRedemption.user))
        .where(PromoRedemption.promo_code_id == promo.id)
        .order_by(PromoRedemption.created_at.desc(), PromoRedemption.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [promo_redemption_public(redemption) for redemption in redemptions]


@router.post("/promos", response_model=AdminPromoPublic, status_code=status.HTTP_201_CREATED)
def create_promo(
    payload: AdminPromoCreateRequest,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminPromoPublic:
    code = normalize_promo_code(payload.code)
    if db.scalar(select(PromoCode.id).where(PromoCode.code == code)):
        raise api_error("err_promo_duplicate", status.HTTP_409_CONFLICT)
    reward_type = payload.reward_type.strip().lower()
    amount_cents = promo_amount_cents(payload)
    percent_bps = percent_to_bps(payload.percent)
    max_bonus_cents = promo_max_bonus_cents(payload)
    min_deposit_cents = promo_min_deposit_cents(payload)
    if reward_type == "fixed":
        percent_bps = 0
        max_bonus_cents = 0
    elif reward_type == "percent":
        amount_cents = 0
    validate_reward_config(
        reward_type=reward_type,
        amount_cents=amount_cents,
        percent_bps=percent_bps,
        max_bonus_cents=max_bonus_cents,
        min_deposit_cents=min_deposit_cents,
        starts_at=payload.starts_at,
        expires_at=payload.expires_at,
    )
    promo = PromoCode(
        code=code,
        title=payload.title.strip() or code,
        reward_type=reward_type,
        amount_cents=amount_cents,
        percent_bps=percent_bps,
        max_bonus_cents=max_bonus_cents,
        min_deposit_cents=min_deposit_cents,
        usage_limit=payload.usage_limit,
        per_user_limit=payload.per_user_limit,
        starts_at=payload.starts_at,
        expires_at=payload.expires_at,
        is_active=payload.is_active,
        created_by_user_id=admin_user.id,
    )
    db.add(promo)
    db.flush()
    audit_promo_admin_action(db, action="admin.promo.create", promo=promo, actor_user=admin_user, request=request)
    db.commit()
    db.refresh(promo)
    return promo_public(db, promo)


@router.patch("/promos/{promo_id}", response_model=AdminPromoPublic)
def update_promo(
    promo_id: int,
    payload: AdminPromoUpdateRequest,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminPromoPublic:
    promo = get_promo(db, promo_id)
    if payload.title is not None:
        promo.title = payload.title.strip() or promo.code
    if payload.is_active is not None:
        promo.is_active = payload.is_active
    if payload.usage_limit is not None:
        promo.usage_limit = payload.usage_limit
    if payload.per_user_limit is not None:
        promo.per_user_limit = payload.per_user_limit
    if "starts_at" in payload.model_fields_set:
        promo.starts_at = payload.starts_at
    if "expires_at" in payload.model_fields_set:
        promo.expires_at = payload.expires_at

    reward_type = payload.reward_type.strip().lower() if payload.reward_type is not None else promo.reward_type
    amount_cents = promo_amount_cents(payload, promo)
    percent_bps = percent_to_bps(payload.percent) if payload.percent is not None else promo.percent_bps
    max_bonus_cents = promo_max_bonus_cents(payload, promo)
    min_deposit_cents = promo_min_deposit_cents(payload, promo)
    if reward_type == "fixed":
        percent_bps = 0
        max_bonus_cents = 0
    elif reward_type == "percent":
        amount_cents = 0
    validate_reward_config(
        reward_type=reward_type,
        amount_cents=amount_cents,
        percent_bps=percent_bps,
        max_bonus_cents=max_bonus_cents,
        min_deposit_cents=min_deposit_cents,
        starts_at=promo.starts_at,
        expires_at=promo.expires_at,
    )
    promo.reward_type = reward_type
    promo.amount_cents = amount_cents
    promo.percent_bps = percent_bps
    promo.max_bonus_cents = max_bonus_cents
    promo.min_deposit_cents = min_deposit_cents
    db.add(promo)
    db.flush()
    audit_promo_admin_action(db, action="admin.promo.update", promo=promo, actor_user=admin_user, request=request)
    db.commit()
    db.refresh(promo)
    return promo_public(db, promo)


@router.post("/promos/{promo_id}/disable", response_model=AdminPromoPublic)
def disable_promo(
    promo_id: int,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminPromoPublic:
    promo = get_promo(db, promo_id)
    promo.is_active = False
    db.add(promo)
    db.flush()
    audit_promo_admin_action(db, action="admin.promo.disable", promo=promo, actor_user=admin_user, request=request)
    db.commit()
    db.refresh(promo)
    return promo_public(db, promo)


@router.get("/withdrawals", response_model=list[AdminWithdrawalPublic])
def list_withdrawals(
    status_filter: str = Query(default="pending", alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[AdminWithdrawalPublic]:
    status_value = status_filter.strip().lower()
    if status_value not in WITHDRAWAL_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid withdrawal status")

    query = (
        select(Transaction)
        .options(joinedload(Transaction.user))
        .where(Transaction.type == "withdraw")
        .order_by(Transaction.updated_at.desc(), Transaction.created_at.desc(), Transaction.id.desc())
    )
    if status_value != "all":
        query = query.where(Transaction.status == status_value)

    transactions = db.scalars(query.offset(offset).limit(limit)).all()
    return [withdrawal_response(transaction) for transaction in transactions]


@router.post("/withdrawals/{transaction_id}/approve", response_model=AdminWithdrawalPublic)
@limiter.limit(settings.rate_limit_admin_money)
def approve_withdrawal(
    transaction_id: int,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminWithdrawalPublic:
    idem = begin_idempotency(
        db,
        user=admin_user,
        request=request,
        payload={"transaction_id": transaction_id, "action": "approve"},
    )
    if idem.replay_response is not None:
        return AdminWithdrawalPublic.model_validate(idem.replay_response)
    transaction = get_withdrawal(db, transaction_id)
    approve_withdrawal_transaction(db, transaction=transaction, actor_user=admin_user, request=request)
    response = withdrawal_response(transaction)
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(transaction)
    db.refresh(transaction.user)
    return withdrawal_response(transaction)


@router.post("/withdrawals/{transaction_id}/reject", response_model=AdminWithdrawalPublic)
@limiter.limit(settings.rate_limit_admin_money)
def reject_withdrawal(
    transaction_id: int,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminWithdrawalPublic:
    idem = begin_idempotency(
        db,
        user=admin_user,
        request=request,
        payload={"transaction_id": transaction_id, "action": "reject"},
    )
    if idem.replay_response is not None:
        return AdminWithdrawalPublic.model_validate(idem.replay_response)
    transaction = get_withdrawal(db, transaction_id)
    reject_withdrawal_transaction(db, transaction=transaction, actor_user=admin_user, request=request)
    response = withdrawal_response(transaction)
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(transaction.user)
    db.refresh(transaction)
    return withdrawal_response(transaction)


@router.get("/audit", response_model=list[AuditLogPublic])
def list_audit_logs(
    action: str = Query(default="", max_length=64),
    target_user_id: int | None = Query(default=None),
    actor_user_id: int | None = Query(default=None),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[AuditLogPublic]:
    query = select(AuditLog)
    if action.strip():
        query = query.where(AuditLog.action == action.strip())
    if target_user_id is not None:
        query = query.where(AuditLog.target_user_id == target_user_id)
    if actor_user_id is not None:
        query = query.where(AuditLog.actor_user_id == actor_user_id)
    start = parse_date_filter(date_from)
    end = parse_date_filter(date_to)
    if start:
        query = query.where(AuditLog.created_at >= start)
    if end:
        query = query.where(AuditLog.created_at <= end)
    logs = db.scalars(query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(limit)).all()
    return [AuditLogPublic.model_validate(log) for log in logs]


@router.get("/manager/tickets", response_model=list[ManagerTicketPublic])
def list_manager_tickets(
    ticket_status: str = Query(default="open", alias="status", max_length=24),
    category: str = Query(default="", max_length=32),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[ManagerTicketPublic]:
    query = select(ManagerTicket).options(joinedload(ManagerTicket.user))
    if ticket_status != "all":
        query = query.where(ManagerTicket.status == ticket_status)
    if category.strip():
        query = query.where(ManagerTicket.category == category.strip())
    tickets = db.scalars(
        query.order_by(ManagerTicket.created_at.desc(), ManagerTicket.id.desc()).offset(offset).limit(limit)
    ).all()
    return [ticket_public(ticket, ticket.user) for ticket in tickets]


@router.get("/manager/tickets/{ticket_id}", response_model=AdminManagerTicketDetail)
def get_manager_ticket_detail(
    ticket_id: int,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminManagerTicketDetail:
    ticket = db.scalar(
        select(ManagerTicket)
        .options(joinedload(ManagerTicket.user))
        .where(ManagerTicket.id == ticket_id)
    )
    if not ticket:
        raise api_error("err_manager_ticket_not_found", status_code=404)
    messages = list(
        db.scalars(
            select(ManagerMessage)
            .where(ManagerMessage.user_id == ticket.user_id)
            .order_by(ManagerMessage.id.desc())
            .limit(100)
        ).all()
    )
    return AdminManagerTicketDetail(
        ticket=ticket_public(ticket, ticket.user),
        messages=[message_public(item) for item in reversed(messages)],
        user=UserPublic.model_validate(ticket.user),
    )


@router.patch("/manager/tickets/{ticket_id}", response_model=ManagerTicketPublic)
@limiter.limit(settings.rate_limit_admin_money)
def update_manager_ticket(
    ticket_id: int,
    payload: AdminManagerTicketUpdateRequest,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> ManagerTicketPublic:
    ticket = db.scalar(select(ManagerTicket).where(ManagerTicket.id == ticket_id).with_for_update())
    if not ticket:
        raise api_error("err_manager_ticket_not_found", status_code=404)
    if ticket.status in {"resolved", "rejected", "closed"}:
        raise api_error("err_manager_ticket_settled", status_code=409)

    owner = db.get(User, ticket.user_id)
    if owner is None:
        raise api_error("err_user_not_found", status_code=404)
    metadata = parse_json(ticket.payload_json)
    approved_bet = payload.approved_bet_cents
    approved_game = (payload.game_id or metadata.get("game_id") or "").strip()
    if approved_bet is not None:
        rules = require_manager_access(owner)
        requested = int(metadata.get("bet_cents") or 0)
        if (
            ticket.category != "bet_exception"
            or approved_game not in {"dragons-fortune", "lucky-bamboo", "solar-wilds", "neon-pyramids", "midnight-vault", "texas-holdem", "arctic-protocol", "roulette"}
            or approved_bet > rules["exception_cap_cents"]
            or approved_bet <= rules["max_bet_cents"]
            or approved_bet > requested
            or approved_bet % 500
        ):
            raise api_error("err_manager_bet_exception_invalid")
        preset = db.scalar(
            select(ManagerBetPreset).where(
                ManagerBetPreset.user_id == owner.id,
                ManagerBetPreset.game_id == approved_game,
            )
        )
        if preset is None and len(active_presets(db, owner.id)) >= rules["max_games"]:
            raise api_error("err_manager_game_limit", status_code=409, meta={"max_games": rules["max_games"]})
        if preset is None:
            preset = ManagerBetPreset(user_id=owner.id, game_id=approved_game, bet_cents=approved_bet)
        preset.bet_cents = approved_bet
        preset.source = "admin_exception"
        preset.expires_at = utc_now() + timedelta(hours=24)
        db.add(preset)

    ticket.status = payload.status
    ticket.admin_response = payload.response.strip()
    ticket.resolved_by_user_id = admin_user.id if payload.status in {"resolved", "rejected", "closed"} else None
    ticket.resolved_at = utc_now() if ticket.resolved_by_user_id else None
    db.add(ticket)
    if payload.response.strip():
        latest = db.scalar(
            select(ManagerMessage)
            .where(ManagerMessage.user_id == owner.id)
            .order_by(ManagerMessage.id.desc())
            .limit(1)
        )
        add_message(
            db,
            owner,
            role="admin",
            language=latest.language if latest else "ru",
            intent="ticket_reply",
            text=payload.response.strip(),
            metadata={"ticket_id": ticket.id, "status": ticket.status},
        )
    add_audit_log(
        db,
        action="manager.ticket.resolve",
        actor_user=admin_user,
        target_user=owner,
        metadata={
            "ticket_id": ticket.id,
            "status": ticket.status,
            "approved_bet_cents": approved_bet,
            "game_id": approved_game or None,
        },
        request=request,
    )
    db.commit()
    db.refresh(ticket)
    return ticket_public(ticket, owner)
