from fastapi import HTTPException, Request, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.models import Transaction, User
from app.core.vip import award_vip_bet_points
from app.services.audit import add_audit_log
from app.services.game_control import consume_game_budget


def create_transaction(
    user: User,
    transaction_type: str,
    amount_cents: int,
    method_id: str,
    title_key: str = "",
    transaction_status: str = "completed",
    title: str = "",
) -> Transaction:
    return Transaction(
        user_id=user.id,
        type=transaction_type,
        status=transaction_status,
        amount_cents=amount_cents,
        currency=user.currency,
        method_id=method_id,
        title=title,
        title_key=title_key,
    )


def apply_balance_delta(
    db: Session,
    *,
    user: User,
    amount_cents: int,
    transaction_type: str,
    method_id: str,
    action: str,
    actor_user: User | None = None,
    title: str = "",
    title_key: str = "",
    transaction_status: str = "completed",
    metadata: dict | None = None,
    request: Request | None = None,
) -> Transaction:
    user = db.merge(user)
    before_balance = int(user.balance_cents or 0)
    if amount_cents < 0:
        balance_update = (
            update(User)
            .where(User.id == user.id, User.balance_cents >= abs(amount_cents))
            .values(balance_cents=User.balance_cents + amount_cents)
            .execution_options(synchronize_session=False)
        )
        update_result = db.execute(balance_update)
        if update_result.rowcount != 1:
            db.rollback()
            raise api_error("err_insufficient_balance")
    else:
        db.execute(
            update(User)
            .where(User.id == user.id)
            .values(balance_cents=User.balance_cents + amount_cents)
            .execution_options(synchronize_session=False)
        )

    db.flush()
    db.refresh(user)
    after_balance = int(user.balance_cents or 0)

    transaction = create_transaction(
        user,
        transaction_type,
        amount_cents,
        method_id,
        title_key=title_key,
        transaction_status=transaction_status,
        title=title,
    )
    db.add(user)
    db.add(transaction)
    db.flush()
    add_audit_log(
        db,
        action=action,
        actor_user=actor_user or user,
        target_user=user,
        amount_cents=amount_cents,
        before_balance_cents=before_balance,
        after_balance_cents=after_balance,
        metadata={"transaction_id": transaction.id, **(metadata or {})},
        request=request,
    )
    return transaction


def approve_withdrawal_transaction(
    db: Session,
    *,
    transaction: Transaction,
    actor_user: User,
    request: Request | None = None,
) -> Transaction:
    if transaction.status != "pending":
        raise api_error("err_withdraw_not_pending", status.HTTP_409_CONFLICT)
    transaction.status = "completed"
    db.add(transaction)
    db.flush()
    add_audit_log(
        db,
        action="withdraw.approve",
        actor_user=actor_user,
        target_user=transaction.user,
        amount_cents=transaction.amount_cents,
        before_balance_cents=transaction.user.balance_cents,
        after_balance_cents=transaction.user.balance_cents,
        metadata={
            "transaction_id": transaction.id,
            "method_id": transaction.method_id,
            "fee_cents": transaction.fee_cents,
            "payout_cents": transaction.payout_cents,
        },
        request=request,
    )
    return transaction


def reject_withdrawal_transaction(
    db: Session,
    *,
    transaction: Transaction,
    actor_user: User,
    request: Request | None = None,
) -> Transaction:
    if transaction.status != "pending":
        raise api_error("err_withdraw_not_pending", status.HTTP_409_CONFLICT)

    refund_cents = abs(transaction.amount_cents)
    before_balance = transaction.user.balance_cents
    transaction.status = "rejected"
    transaction.user.balance_cents += refund_cents
    db.add(transaction.user)
    db.add(transaction)
    db.flush()
    add_audit_log(
        db,
        action="withdraw.reject",
        actor_user=actor_user,
        target_user=transaction.user,
        amount_cents=refund_cents,
        before_balance_cents=before_balance,
        after_balance_cents=transaction.user.balance_cents,
        metadata={
            "transaction_id": transaction.id,
            "method_id": transaction.method_id,
            "fee_cents": transaction.fee_cents,
            "payout_cents": transaction.payout_cents,
        },
        request=request,
    )
    return transaction


def apply_game_result(
    db: Session,
    *,
    user: User,
    game_id: str,
    total_bet_cents: int,
    total_win_cents: int,
    net_cents: int,
    action: str = "game.roulette.spin",
    balance_error_code: str = "err_game_balance",
    metadata: dict | None = None,
    request: Request | None = None,
) -> User:
    user = db.merge(user)
    consume_game_budget(db, user=user, amount_cents=total_bet_cents)
    before_balance = user.balance_cents
    after_balance = before_balance + net_cents
    if after_balance < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": balance_error_code})

    profile_win_cents = max(net_cents, 0)
    balance_update = (
        update(User)
        .where(User.id == user.id, User.balance_cents >= total_bet_cents)
        .values(
            balance_cents=User.balance_cents + net_cents,
            games_played=User.games_played + 1,
            total_won_cents=User.total_won_cents + profile_win_cents,
        )
        .execution_options(synchronize_session=False)
    )
    update_result = db.execute(balance_update)
    if update_result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": balance_error_code})

    db.flush()
    db.refresh(user)
    earned_vip_points = award_vip_bet_points(user, total_bet_cents)
    if earned_vip_points:
        db.add(user)
        db.flush()
        db.refresh(user)
    add_audit_log(
        db,
        action=action,
        actor_user=user,
        target_user=user,
        amount_cents=net_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": game_id,
            "total_bet_cents": total_bet_cents,
            "total_win_cents": total_win_cents,
            "vip_points_earned": earned_vip_points,
            **(metadata or {}),
        },
        request=request,
    )
    return user


def apply_instant_game_result(
    db: Session,
    *,
    user: User,
    game_id: str,
    method_id: str,
    title: str,
    title_key: str,
    total_bet_cents: int,
    total_win_cents: int,
    net_cents: int,
    action: str,
    balance_error_code: str,
    metadata: dict | None = None,
    request: Request | None = None,
) -> tuple[User, Transaction]:
    user = apply_game_result(
        db,
        user=user,
        game_id=game_id,
        total_bet_cents=total_bet_cents,
        total_win_cents=total_win_cents,
        net_cents=net_cents,
        action=action,
        balance_error_code=balance_error_code,
        metadata=metadata,
        request=request,
    )
    transaction = create_transaction(
        user,
        "game",
        net_cents,
        method_id,
        title_key=title_key,
        title=title,
    )
    db.add(transaction)
    db.flush()
    return user, transaction


def reserve_bet(
    db: Session,
    *,
    user: User,
    amount_cents: int,
    game_id: str,
    method_id: str,
    title: str,
    title_key: str,
    action: str,
    balance_error_code: str,
    metadata: dict | None = None,
    request: Request | None = None,
) -> tuple[User, Transaction, int, int]:
    user = db.merge(user)
    consume_game_budget(db, user=user, amount_cents=amount_cents)
    before_balance = int(user.balance_cents or 0)
    balance_update = (
        update(User)
        .where(User.id == user.id, User.balance_cents >= amount_cents)
        .values(balance_cents=User.balance_cents - amount_cents)
        .execution_options(synchronize_session=False)
    )
    update_result = db.execute(balance_update)
    if update_result.rowcount != 1:
        db.rollback()
        raise api_error(balance_error_code)
    db.flush()
    db.refresh(user)
    earned_vip_points = award_vip_bet_points(user, amount_cents)
    if earned_vip_points:
        db.add(user)
        db.flush()
        db.refresh(user)

    transaction = create_transaction(
        user,
        "game",
        -amount_cents,
        method_id,
        title_key=title_key,
        transaction_status="pending",
        title=title,
    )
    db.add(transaction)
    db.flush()
    add_audit_log(
        db,
        action=action,
        actor_user=user,
        target_user=user,
        amount_cents=-amount_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": game_id,
            "transaction_id": transaction.id,
            "total_bet_cents": amount_cents,
            "vip_points_earned": earned_vip_points,
            **(metadata or {}),
        },
        request=request,
    )
    return user, transaction, before_balance, earned_vip_points
