from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.money import (
    DEPOSIT_METHODS,
    SUSPENDED_DEPOSIT_METHODS,
    SUSPENDED_WITHDRAW_METHODS,
    WITHDRAW_METHODS,
    amount_to_cents,
    cashier_rules_for_tier,
    cents_to_amount,
    deposit_min_cents,
    withdrawal_fee_cents,
)
from app.db.session import get_db
from app.deps import get_current_user
from app.models import Transaction, User
from app.routers.wallet import wallet_response
from app.schemas import CashierRequest, CashierResponse, PromoPreviewPublic, TransactionPublic
from app.core.errors import api_error
from app.services.idempotency import begin_idempotency, complete_idempotency
from app.services.money import apply_balance_delta
from app.services.audit import add_audit_log
from app.services.studio import create_pending_casino_transfer, transfer_studio_to_casino
from app.services.promos import preview_promo_code, promo_public, redeem_promo_code
from app.services.abuse import (
    add_abuse_event,
    enforce_promo_redeem_allowed,
    enforce_withdraw_attempt_allowed,
)


router = APIRouter(prefix="/cashier", tags=["cashier"])
settings = get_settings()


def limit_error(code: str, cents: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": code, "amount": str(cents_to_amount(cents))},
    )


@router.get("/promos/preview", response_model=PromoPreviewPublic)
def preview_promo(
    code: str = Query(default="", max_length=64),
    amount: Decimal | None = Query(default=None, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PromoPreviewPublic:
    promo, bonus_cents, deposit_cents = preview_promo_code(db, code=code, deposit_amount=amount)
    return PromoPreviewPublic(
        promo=promo_public(db, promo),
        bonus_cents=bonus_cents,
        deposit_cents=deposit_cents,
        status="active",
    )


@router.post("/deposit", response_model=CashierResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_cashier)
def deposit(
    request: Request,
    payload: CashierRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CashierResponse:
    user = db.merge(current_user)
    method_id = payload.method_id.strip().lower()
    if method_id not in DEPOSIT_METHODS:
        raise api_error("err_payment_method_invalid")
    if method_id in SUSPENDED_DEPOSIT_METHODS:
        raise api_error("err_deposit_method_maintenance", status.HTTP_409_CONFLICT)

    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return CashierResponse.model_validate(idem.replay_response)

    promo_code = (payload.promo_code or "").strip().upper()
    if method_id == "promo":
        enforce_promo_redeem_allowed(db, user=user, request=request)
        if not promo_code:
            raise api_error("err_promo_required")
        try:
            transaction = redeem_promo_code(
                db,
                user=user,
                code=promo_code,
                deposit_amount=payload.amount,
                request=request,
            )
        except HTTPException as err:
            add_abuse_event(
                db,
                action="promo.redeem.failed",
                user=user,
                request=request,
                key=promo_code,
                metadata={"status_code": err.status_code},
            )
            db.commit()
            raise
        response = CashierResponse(wallet=wallet_response(user), transaction=TransactionPublic.model_validate(transaction))
        complete_idempotency(db, idem, response, transaction_id=transaction.id)
        db.commit()
        db.refresh(user)
        db.refresh(transaction)
        return CashierResponse(wallet=wallet_response(user), transaction=TransactionPublic.model_validate(transaction))
    else:
        if payload.amount is None:
            raise api_error("err_amount_invalid")
        amount_cents = amount_to_cents(payload.amount)
        rules = cashier_rules_for_tier(user.vip_tier)
        min_cents = deposit_min_cents(method_id, user.vip_tier)
        if amount_cents < min_cents:
            raise limit_error("err_deposit_min", min_cents)
        if amount_cents > rules["deposit_max_cents"]:
            raise limit_error("err_deposit_max", rules["deposit_max_cents"])

    if method_id == "kawaui-studio":
        transaction = transfer_studio_to_casino(
            db,
            user=user,
            amount_cents=amount_cents,
            request=request,
        )
    else:
        transaction = apply_balance_delta(
            db,
            user=user,
            amount_cents=amount_cents,
            transaction_type="deposit",
            method_id=method_id,
            title_key="tx_deposit_title",
            title=f"Promo code: {promo_code}" if method_id == "promo" else "",
            action="cashier.deposit",
            metadata={"method_id": method_id, "promo_code": promo_code if method_id == "promo" else ""},
            request=request,
        )
    response = CashierResponse(wallet=wallet_response(user), transaction=TransactionPublic.model_validate(transaction))
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(user)
    db.refresh(transaction)
    return CashierResponse(wallet=wallet_response(user), transaction=TransactionPublic.model_validate(transaction))


@router.post("/withdraw", response_model=CashierResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_cashier)
def withdraw(
    request: Request,
    payload: CashierRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CashierResponse:
    user = db.merge(current_user)
    enforce_withdraw_attempt_allowed(db, user=user, request=request)
    add_abuse_event(db, action="cashier.withdraw.attempt", user=user, request=request)
    db.commit()
    user = db.merge(current_user)
    method_id = payload.method_id.strip().lower()
    if method_id not in WITHDRAW_METHODS:
        raise api_error("err_payment_method_invalid")
    if method_id in SUSPENDED_WITHDRAW_METHODS:
        raise api_error("err_withdraw_method_maintenance", status.HTTP_409_CONFLICT)

    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return CashierResponse.model_validate(idem.replay_response)

    if payload.amount is None:
        raise api_error("err_amount_invalid")

    amount_cents = amount_to_cents(payload.amount)
    rules = cashier_rules_for_tier(user.vip_tier)
    if amount_cents < rules["withdraw_min_cents"]:
        raise limit_error("err_withdraw_min", rules["withdraw_min_cents"])
    if amount_cents > rules["withdraw_max_cents"]:
        raise limit_error("err_withdraw_max", rules["withdraw_max_cents"])
    if amount_cents > user.balance_cents:
        raise api_error("err_withdraw_balance")
    pending_count = int(
        db.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.user_id == user.id,
                Transaction.type == "withdraw",
                Transaction.status == "pending",
            )
        )
        or 0
    )
    if pending_count >= 3:
        raise api_error("err_withdraw_pending_limit", status.HTTP_409_CONFLICT)

    fee_cents = withdrawal_fee_cents(amount_cents, user.vip_tier)
    payout_cents = amount_cents - fee_cents
    transaction = apply_balance_delta(
        db,
        user=user,
        amount_cents=-amount_cents,
        transaction_type="withdraw",
        method_id=method_id,
        title_key="tx_withdraw_title",
        transaction_status="pending",
        action="cashier.withdraw.request",
        metadata={
            "method_id": method_id,
            "vip_tier": user.vip_tier,
            "commission_bps": rules["withdraw_fee_bps"],
            "withdraw_processing_hours": rules["withdraw_processing_hours"],
            "gross_amount_cents": amount_cents,
            "fee_cents": fee_cents,
            "payout_cents": payout_cents,
        },
        request=request,
    )
    transaction.fee_cents = fee_cents
    transaction.payout_cents = payout_cents
    db.add(transaction)
    db.flush()
    if method_id == "kawaui-studio":
        studio_transaction = create_pending_casino_transfer(
            db,
            user=user,
            casino_transaction=transaction,
            metadata={"vip_tier": user.vip_tier, "processing_hours": rules["withdraw_processing_hours"]},
        )
        add_audit_log(
            db,
            action="studio.transfer.request",
            actor_user=user,
            target_user=user,
            amount_cents=payout_cents,
            before_balance_cents=user.balance_cents,
            after_balance_cents=user.balance_cents,
            metadata={
                "transaction_id": transaction.id,
                "studio_transaction_id": studio_transaction.id,
                "gross_cents": amount_cents,
                "fee_cents": fee_cents,
                "payout_cents": payout_cents,
            },
            request=request,
        )
    response = CashierResponse(wallet=wallet_response(user), transaction=TransactionPublic.model_validate(transaction))
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(user)
    db.refresh(transaction)
    return CashierResponse(wallet=wallet_response(user), transaction=TransactionPublic.model_validate(transaction))
