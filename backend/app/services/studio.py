from __future__ import annotations

import json
from typing import Any

from fastapi import Request, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.models import StudioTransaction, StudioWallet, Transaction, User
from app.services.audit import add_audit_log


def get_or_create_studio_wallet(db: Session, user: User) -> StudioWallet:
    wallet = db.scalar(select(StudioWallet).where(StudioWallet.user_id == user.id))
    if wallet is not None:
        return wallet
    wallet = StudioWallet(user_id=user.id, currency="EUR", balance_cents=0, version=0)
    db.add(wallet)
    db.flush()
    return wallet


def reconcile_studio_wallet(db: Session, user: User) -> StudioWallet:
    """Restore confirmed ledger credits missing from an older wallet snapshot."""
    wallet = get_or_create_studio_wallet(db, user)
    ledger_balance = int(
        db.scalar(
            select(func.coalesce(func.sum(StudioTransaction.net_cents), 0)).where(
                StudioTransaction.user_id == user.id,
                StudioTransaction.status == "completed",
            )
        )
        or 0
    )
    # Only restore money proven by the ledger. Never lower an existing wallet here.
    if ledger_balance > int(wallet.balance_cents or 0):
        db.execute(
            update(StudioWallet)
            .where(StudioWallet.id == wallet.id)
            .values(balance_cents=ledger_balance, version=StudioWallet.version + 1)
            .execution_options(synchronize_session=False)
        )
        db.flush()
        db.refresh(wallet)
    return wallet


def create_pending_casino_transfer(
    db: Session,
    *,
    user: User,
    casino_transaction: Transaction,
    metadata: dict[str, Any] | None = None,
) -> StudioTransaction:
    existing = db.scalar(
        select(StudioTransaction).where(StudioTransaction.casino_transaction_id == casino_transaction.id)
    )
    if existing is not None:
        return existing
    studio_transaction = StudioTransaction(
        user_id=user.id,
        casino_transaction_id=casino_transaction.id,
        source="casino",
        type="casino_transfer",
        status="pending",
        amount_cents=abs(casino_transaction.amount_cents),
        fee_cents=casino_transaction.fee_cents,
        net_cents=casino_transaction.payout_cents,
        currency="EUR",
        external_ref=f"casino-withdrawal:{casino_transaction.id}",
        metadata_json=json.dumps(metadata or {}, separators=(",", ":"), default=str),
    )
    db.add(studio_transaction)
    db.flush()
    return studio_transaction


def transfer_studio_to_casino(
    db: Session,
    *,
    user: User,
    amount_cents: int,
    request: Request | None = None,
) -> Transaction:
    if amount_cents <= 0:
        raise api_error("err_studio_amount_invalid")

    wallet = reconcile_studio_wallet(db, user)
    studio_before = int(wallet.balance_cents or 0)
    update_result = db.execute(
        update(StudioWallet)
        .where(StudioWallet.id == wallet.id, StudioWallet.balance_cents >= amount_cents)
        .values(
            balance_cents=StudioWallet.balance_cents - amount_cents,
            version=StudioWallet.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if update_result.rowcount != 1:
        db.rollback()
        raise api_error("err_studio_insufficient_balance")

    casino_before = int(user.balance_cents or 0)
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(balance_cents=User.balance_cents + amount_cents)
        .execution_options(synchronize_session=False)
    )
    db.flush()
    db.refresh(wallet)
    db.refresh(user)

    casino_transaction = Transaction(
        user_id=user.id,
        type="deposit",
        status="completed",
        amount_cents=amount_cents,
        currency=user.currency,
        method_id="kawaui-studio",
        title_key="tx_deposit_title",
    )
    db.add(casino_transaction)
    db.flush()

    studio_transaction = StudioTransaction(
        user_id=user.id,
        casino_transaction_id=casino_transaction.id,
        source="studio",
        type="casino_deposit",
        status="completed",
        amount_cents=amount_cents,
        fee_cents=0,
        net_cents=-amount_cents,
        currency="EUR",
        external_ref=f"studio-deposit:{casino_transaction.id}",
        metadata_json=json.dumps(
            {"casino_transaction_id": casino_transaction.id},
            separators=(",", ":"),
        ),
    )
    db.add(studio_transaction)
    db.flush()
    add_audit_log(
        db,
        action="studio.transfer.to_casino",
        actor_user=user,
        target_user=user,
        amount_cents=amount_cents,
        before_balance_cents=casino_before,
        after_balance_cents=int(user.balance_cents or 0),
        metadata={
            "transaction_id": casino_transaction.id,
            "studio_transaction_id": studio_transaction.id,
            "studio_before_cents": studio_before,
            "studio_after_cents": int(wallet.balance_cents or 0),
            "method_id": "kawaui-studio",
        },
        request=request,
    )
    return casino_transaction


def credit_studio_wallet(
    db: Session,
    *,
    user: User,
    amount_cents: int,
    source: str,
    transaction_type: str,
    external_ref: str,
    actor_user: User | None = None,
    metadata: dict[str, Any] | None = None,
    request: Request | None = None,
) -> tuple[StudioWallet, StudioTransaction]:
    if amount_cents <= 0:
        raise api_error("err_studio_amount_invalid")
    existing = db.scalar(select(StudioTransaction).where(StudioTransaction.external_ref == external_ref))
    if existing is not None:
        wallet = get_or_create_studio_wallet(db, user)
        return wallet, existing

    wallet = get_or_create_studio_wallet(db, user)
    before_balance = wallet.balance_cents
    db.execute(
        update(StudioWallet)
        .where(StudioWallet.id == wallet.id)
        .values(
            balance_cents=StudioWallet.balance_cents + amount_cents,
            version=StudioWallet.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    db.flush()
    db.refresh(wallet)
    transaction = StudioTransaction(
        user_id=user.id,
        source=source,
        type=transaction_type,
        status="completed",
        amount_cents=amount_cents,
        fee_cents=0,
        net_cents=amount_cents,
        currency="EUR",
        external_ref=external_ref,
        metadata_json=json.dumps(metadata or {}, separators=(",", ":"), default=str),
    )
    db.add(transaction)
    db.flush()
    add_audit_log(
        db,
        action="studio.wallet.credit",
        actor_user=actor_user or user,
        target_user=user,
        amount_cents=amount_cents,
        before_balance_cents=before_balance,
        after_balance_cents=wallet.balance_cents,
        metadata={"studio_transaction_id": transaction.id, "source": source, **(metadata or {})},
        request=request,
    )
    return wallet, transaction


def approve_casino_transfer(
    db: Session,
    *,
    casino_transaction: Transaction,
    actor_user: User,
    request: Request | None = None,
) -> StudioTransaction:
    studio_transaction = db.scalar(
        select(StudioTransaction).where(StudioTransaction.casino_transaction_id == casino_transaction.id)
    )
    if studio_transaction is None:
        raise api_error("err_studio_transfer_missing", status.HTTP_409_CONFLICT)
    if studio_transaction.status != "pending":
        raise api_error("err_studio_transfer_settled", status.HTTP_409_CONFLICT)

    wallet = get_or_create_studio_wallet(db, casino_transaction.user)
    before_balance = wallet.balance_cents
    db.execute(
        update(StudioWallet)
        .where(StudioWallet.id == wallet.id)
        .values(
            balance_cents=StudioWallet.balance_cents + studio_transaction.net_cents,
            version=StudioWallet.version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    studio_transaction.status = "completed"
    db.add(studio_transaction)
    db.flush()
    db.refresh(wallet)
    add_audit_log(
        db,
        action="studio.transfer.approve",
        actor_user=actor_user,
        target_user=casino_transaction.user,
        amount_cents=studio_transaction.net_cents,
        before_balance_cents=before_balance,
        after_balance_cents=wallet.balance_cents,
        metadata={
            "transaction_id": casino_transaction.id,
            "studio_transaction_id": studio_transaction.id,
            "gross_cents": studio_transaction.amount_cents,
            "fee_cents": studio_transaction.fee_cents,
            "payout_cents": studio_transaction.net_cents,
        },
        request=request,
    )
    return studio_transaction


def reject_casino_transfer(db: Session, *, casino_transaction: Transaction) -> StudioTransaction:
    studio_transaction = db.scalar(
        select(StudioTransaction).where(StudioTransaction.casino_transaction_id == casino_transaction.id)
    )
    if studio_transaction is None:
        raise api_error("err_studio_transfer_missing", status.HTTP_409_CONFLICT)
    if studio_transaction.status != "pending":
        raise api_error("err_studio_transfer_settled", status.HTTP_409_CONFLICT)
    studio_transaction.status = "rejected"
    db.add(studio_transaction)
    db.flush()
    return studio_transaction
