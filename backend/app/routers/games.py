import json
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.money import amount_to_cents, cents_to_amount
from app.core.crash import (
    ALLOWED_CRASH_BET_CENTS,
    CASHOUT_MIN_MULTIPLIER_CENTS,
    CRASH_GAME_ID,
    CRASH_METHOD_ID,
    CRASH_TITLE,
    CRASH_TITLE_KEY,
    current_multiplier_cents,
    generate_crash_multiplier_cents,
    multiplier_amount,
    seconds_until_multiplier,
    utc_now,
)
from app.core.blocks import (
    ALLOWED_BLOCKS_BET_CENTS,
    ALLOWED_BLOCKS_DIFFICULTIES,
    BLOCKS_GAME_ID,
    BLOCKS_METHOD_ID,
    BLOCKS_TITLE,
    BLOCKS_TITLE_KEY,
    BLOCKS_CASHOUT_MIN_MULTIPLIER_CENTS,
    NEXT_QUEUE_SIZE,
    DEFAULT_BLOCKS_DIFFICULTY,
    board_height_for,
    can_place_anywhere,
    can_place,
    difficulty_config,
    empty_board,
    ensure_queue,
    generate_piece_queue,
    has_valid_x,
    multiplier_after_clear,
    multiplier_amount as blocks_multiplier_amount,
    normalize_board,
    place_piece,
    place_piece_at_y,
    pressure_level_for,
    score_for_clear,
    starting_multiplier_cents_for,
    tick_ms_for,
    win_cents_for as blocks_win_cents_for,
)
from app.core.holdem import (
    ALLOWED_HOLDEM_ANTE_CENTS,
    HOLDEM_GAME_ID,
    HOLDEM_METHOD_ID,
    HOLDEM_TITLE,
    HOLDEM_TITLE_KEY,
    compare_hands,
    complete_community_cards,
    deal_holdem_round,
    dealer_qualifies,
    evaluate_best,
    public_hand,
)
from app.core.mines import (
    ALLOWED_MINE_COUNTS,
    ALLOWED_MINES_BET_CENTS,
    GRID_CELLS,
    MINES_GAME_ID,
    MINES_METHOD_ID,
    MINES_TITLE,
    MINES_TITLE_KEY,
    generate_mines,
    multiplier_cents,
    validate_cell,
    win_cents_for,
)
from app.core.plinko import (
    ALLOWED_PLINKO_BET_CENTS,
    PLINKO_GAME_ID,
    PLINKO_METHOD_ID,
    PLINKO_TITLE,
    PLINKO_TITLE_KEY,
    drop_midnight_vault,
)
from app.core.survival import (
    ALLOWED_SURVIVAL_BET_CENTS,
    SURVIVAL_GAME_ID,
    SURVIVAL_METHOD_ID,
    SURVIVAL_PAYOUT_MULTIPLIER_CENTS,
    SURVIVAL_RECENT_SCENARIO_LIMIT,
    SURVIVAL_TITLE,
    SURVIVAL_TITLE_KEY,
    SURVIVAL_TOTAL_STAGES,
    category_public,
    choice_explanation,
    correct_choice_id,
    create_round_plan,
    deadline_after,
    evaluate_choice,
    multiplier_amount as survival_multiplier_amount,
    normalize_lang,
    payout_cents as survival_payout_cents,
    public_question,
    resolution_parameter_values,
)
from app.core.rate_limit import limiter
from app.core.roulette import covered_numbers, describe_outcome, evaluate_bet, normalize_bet_type, spin_number
from app.core.slots import SLOT_GAME_ID, SLOT_METHOD_ID, SLOT_TITLE, SLOT_TITLE_KEY, ALLOWED_BET_CENTS, spin_lucky_bamboo
from app.core.vip import award_vip_bet_points
from app.db.session import get_db
from app.deps import get_current_user
from app.models import GameRound, Transaction, User
from app.routers.wallet import wallet_response
from app.schemas import (
    RouletteBetResult,
    RouletteSpinRequest,
    RouletteSpinResponse,
    RouletteResult,
    BlocksPlaceRequest,
    BlocksPiece,
    BlocksRoundResponse,
    BlocksStartRequest,
    CrashRoundResponse,
    CrashStartRequest,
    HoldemDecisionRequest,
    HoldemHandResponse,
    HoldemRoundResponse,
    HoldemStartRequest,
    MinesRevealRequest,
    MinesRoundResponse,
    MinesStartRequest,
    PlinkoBallResult,
    PlinkoDropRequest,
    PlinkoDropResponse,
    SurvivalActionRequest,
    SurvivalChoiceRequest,
    SurvivalRoundResponse,
    SurvivalStartRequest,
    SlotSpinRequest,
    SlotSpinResponse,
    SlotWinningLine,
    TransactionPublic,
)
from app.services.audit import add_audit_log
from app.services.idempotency import begin_idempotency, complete_idempotency
from app.services.game_control import consume_game_budget
from app.services.money import apply_game_result, apply_instant_game_result, reserve_bet
from app.services.manager import is_allowed_manager_bet


router = APIRouter(prefix="/games", tags=["games"])

ROULETTE_GAME_ID = "european-roulette"
MIN_BET_CENTS = 100
MAX_BET_CENTS = 99_999_999
MAX_TOTAL_BET_CENTS = 99_999_999
NUMBER_GROUP_BETS = {"straight", "split", "corner"}
NUMBERED_BETS = {"street", "six_line", "dozen", "column"}


def roulette_error(code: str, amount_cents: int | None = None) -> HTTPException:
    detail: dict[str, str] = {"code": code}
    if amount_cents is not None:
        detail["amount"] = str(cents_to_amount(amount_cents))
    return HTTPException(status_code=422, detail=detail)


def canonical_selection(bet_type: str, selection: str) -> str:
    normalized_type = normalize_bet_type(bet_type)
    covered = covered_numbers(normalized_type, selection)

    if normalized_type in NUMBER_GROUP_BETS:
        return "-".join(str(number) for number in sorted(covered))
    if normalized_type in NUMBERED_BETS:
        return str(int(selection.strip()))
    return selection.strip().lower()


def aggregate_roulette_bets(bets, outcome):
    aggregated: dict[tuple[str, str], int] = {}

    for bet in bets:
        amount_cents = amount_to_cents(bet.amount)
        try:
            normalized_type = normalize_bet_type(bet.type)
            selection = canonical_selection(normalized_type, bet.selection)
        except (TypeError, ValueError):
            raise roulette_error("err_roulette_bet_invalid") from None

        key = (normalized_type, selection)
        aggregated[key] = aggregated.get(key, 0) + amount_cents

    evaluated = []
    for (bet_type, selection), amount_cents in aggregated.items():
        if amount_cents < MIN_BET_CENTS:
            raise roulette_error("err_roulette_bet_min", MIN_BET_CENTS)
        if amount_cents > MAX_BET_CENTS:
            raise roulette_error("err_roulette_bet_max", MAX_BET_CENTS)
        try:
            evaluated.append(evaluate_bet(bet_type, selection, amount_cents, outcome))
        except (TypeError, ValueError):
            raise roulette_error("err_roulette_bet_invalid") from None

    return evaluated


@router.post("/roulette/spin", response_model=RouletteSpinResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def roulette_spin(
    request: Request,
    payload: RouletteSpinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RouletteSpinResponse:
    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return RouletteSpinResponse.model_validate(idem.replay_response)

    outcome = describe_outcome(spin_number())
    evaluated = aggregate_roulette_bets(payload.bets, outcome)

    total_bet_cents = sum(bet.amount_cents for bet in evaluated)
    if total_bet_cents > MAX_TOTAL_BET_CENTS:
        raise roulette_error("err_roulette_total_max", MAX_TOTAL_BET_CENTS)

    total_win_cents = sum(bet.win_cents for bet in evaluated)
    net_cents = total_win_cents - total_bet_cents
    try:
        current_user, transaction = apply_instant_game_result(
            db,
            user=current_user,
            game_id=ROULETTE_GAME_ID,
            method_id="roulette",
            title="European Roulette",
            title_key="tx_roulette_title",
            total_bet_cents=total_bet_cents,
            total_win_cents=total_win_cents,
            net_cents=net_cents,
            action="game.roulette.spin",
            balance_error_code="err_roulette_balance",
            metadata={"idempotency_key": idem.key_hash},
            request=request,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "err_roulette_balance"}
        if detail.get("code") == "err_roulette_balance":
            raise roulette_error("err_roulette_balance") from None
        raise

    round_payload = [
        {
            "type": bet.type,
            "selection": bet.selection,
            "amount_cents": bet.amount_cents,
            "win_cents": bet.win_cents,
            "payout": bet.payout,
            "won": bet.won,
        }
        for bet in evaluated
    ]
    game_round = GameRound(
        user_id=current_user.id,
        game_id=ROULETTE_GAME_ID,
        result_number=outcome.number,
        result_color=outcome.color,
        total_bet_cents=total_bet_cents,
        total_win_cents=total_win_cents,
        net_cents=net_cents,
        bets_json=json.dumps(round_payload, separators=(",", ":")),
        result_json=json.dumps(
            {
                "number": outcome.number,
                "color": outcome.color,
                "parity": outcome.parity,
                "range": outcome.range,
                "dozen": outcome.dozen,
                "column": outcome.column,
            },
            separators=(",", ":"),
        ),
    )
    db.add(current_user)
    db.add(game_round)
    db.flush()
    response = RouletteSpinResponse(
        round_id=game_round.id,
        result=RouletteResult(
            number=outcome.number,
            color=outcome.color,
            parity=outcome.parity,
            range=outcome.range,
            dozen=outcome.dozen,
            column=outcome.column,
        ),
        bets=[RouletteBetResult(**bet.__dict__) for bet in evaluated],
        total_bet_cents=total_bet_cents,
        total_win_cents=total_win_cents,
        net_cents=net_cents,
        wallet=wallet_response(current_user),
        transaction=TransactionPublic.model_validate(transaction),
    )
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(current_user)
    db.refresh(game_round)
    db.refresh(transaction)
    return response


def slot_error(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": code})


def crash_error(code: str, status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def mines_error(code: str, status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def blocks_error(code: str, status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def holdem_error(code: str, status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def plinko_error(code: str, status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def survival_error(code: str, status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def round_result(round_item: GameRound) -> dict:
    try:
        value = json.loads(round_item.result_json or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def write_round_result(round_item: GameRound, result: dict) -> None:
    round_item.result_json = json.dumps(result, separators=(",", ":"))


def claim_active_round(db: Session, round_item: GameRound, error: HTTPException) -> None:
    claim = (
        update(GameRound)
        .where(GameRound.id == round_item.id, GameRound.status == "active")
        .values(status="settling")
        .execution_options(synchronize_session=False)
    )
    if db.execute(claim).rowcount != 1:
        raise error
    db.flush()
    db.refresh(round_item)


def transaction_for_round(db: Session, result: dict) -> Transaction | None:
    transaction_id = result.get("transaction_id")
    if not transaction_id:
        return None
    return db.get(Transaction, int(transaction_id))


def started_at_for_round(round_item: GameRound, result: dict):
    raw = result.get("started_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return round_item.created_at
    return round_item.created_at


def crash_round_response(
    round_item: GameRound,
    user: User,
    transaction: Transaction | None,
    *,
    reveal_crash: bool = False,
) -> CrashRoundResponse:
    result = round_result(round_item)
    started_at = started_at_for_round(round_item, result)
    cashout_multiplier_cents = result.get("cashout_multiplier_cents")
    crash_multiplier_cents = int(result.get("crash_multiplier_cents") or 100)
    if round_item.status == "active":
        current_cents = min(current_multiplier_cents(started_at), crash_multiplier_cents)
    else:
        current_cents = int(cashout_multiplier_cents or result.get("final_multiplier_cents") or crash_multiplier_cents)

    return CrashRoundResponse(
        round_id=round_item.id,
        status=round_item.status,
        current_multiplier=multiplier_amount(current_cents),
        crash_multiplier=multiplier_amount(crash_multiplier_cents) if reveal_crash or round_item.status != "active" else None,
        cashout_multiplier=multiplier_amount(int(cashout_multiplier_cents)) if cashout_multiplier_cents else None,
        total_bet_cents=round_item.total_bet_cents,
        total_win_cents=round_item.total_win_cents,
        net_cents=round_item.net_cents,
        started_at=started_at,
        settled_at=round_item.settled_at,
        wallet=wallet_response(user),
        transaction=TransactionPublic.model_validate(transaction) if transaction else None,
    )


def settle_crash_loss(db: Session, *, round_item: GameRound, user: User, request: Request | None = None) -> Transaction | None:
    if round_item.status != "active":
        raise crash_error("err_crash_round_settled", status.HTTP_409_CONFLICT)
    claim_active_round(db, round_item, crash_error("err_crash_round_settled", status.HTTP_409_CONFLICT))

    result = round_result(round_item)
    transaction = transaction_for_round(db, result)
    now = utc_now()
    before_balance = user.balance_cents

    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(games_played=User.games_played + 1)
        .execution_options(synchronize_session=False)
    )
    round_item.status = "lost"
    round_item.total_win_cents = 0
    round_item.net_cents = -round_item.total_bet_cents
    round_item.settled_at = now
    result.update(
        {
            "final_multiplier_cents": result.get("crash_multiplier_cents", 100),
            "crashed_at": now.isoformat(),
            "summary": {
                "status": "lost",
                "crash_multiplier": multiplier_amount(int(result.get("crash_multiplier_cents") or 100)),
            },
        }
    )
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = -round_item.total_bet_cents

    db.add(round_item)
    if transaction:
        db.add(transaction)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action="game.crash.lost",
        actor_user=user,
        target_user=user,
        amount_cents=-round_item.total_bet_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": CRASH_GAME_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "crash_multiplier_cents": result.get("crash_multiplier_cents"),
        },
        request=request,
    )
    return transaction


def settle_crash_cashout(
    db: Session,
    *,
    round_item: GameRound,
    user: User,
    cashout_multiplier_cents: int,
    request: Request | None = None,
) -> Transaction | None:
    if round_item.status != "active":
        raise crash_error("err_crash_round_settled", status.HTTP_409_CONFLICT)
    claim_active_round(db, round_item, crash_error("err_crash_round_settled", status.HTTP_409_CONFLICT))

    result = round_result(round_item)
    transaction = transaction_for_round(db, result)
    win_cents = round_item.total_bet_cents * cashout_multiplier_cents // 100
    net_cents = win_cents - round_item.total_bet_cents
    before_balance = user.balance_cents
    now = utc_now()

    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            balance_cents=User.balance_cents + win_cents,
            games_played=User.games_played + 1,
            total_won_cents=User.total_won_cents + max(net_cents, 0),
        )
        .execution_options(synchronize_session=False)
    )
    round_item.status = "completed"
    round_item.total_win_cents = win_cents
    round_item.net_cents = net_cents
    round_item.settled_at = now
    result.update(
        {
            "cashout_multiplier_cents": cashout_multiplier_cents,
            "final_multiplier_cents": cashout_multiplier_cents,
            "cashed_out_at": now.isoformat(),
            "summary": {
                "status": "cashed_out",
                "cashout_multiplier": multiplier_amount(cashout_multiplier_cents),
                "crash_multiplier": multiplier_amount(int(result.get("crash_multiplier_cents") or 100)),
            },
        }
    )
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = net_cents

    db.add(round_item)
    if transaction:
        db.add(transaction)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action="game.crash.cashout",
        actor_user=user,
        target_user=user,
        amount_cents=win_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": CRASH_GAME_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "cashout_multiplier_cents": cashout_multiplier_cents,
            "net_cents": net_cents,
        },
        request=request,
    )
    return transaction


def active_crash_round(db: Session, user_id: int) -> GameRound | None:
    return db.scalar(
        select(GameRound)
        .where(GameRound.user_id == user_id, GameRound.game_id == CRASH_GAME_ID, GameRound.status == "active")
        .order_by(GameRound.id.desc())
    )


def crash_multiplier_reached(round_item: GameRound) -> bool:
    result = round_result(round_item)
    started_at = started_at_for_round(round_item, result)
    crash_multiplier_cents = int(result.get("crash_multiplier_cents") or 100)
    return current_multiplier_cents(started_at) >= crash_multiplier_cents


def active_mines_round(db: Session, user_id: int) -> GameRound | None:
    return db.scalar(
        select(GameRound)
        .where(GameRound.user_id == user_id, GameRound.game_id == MINES_GAME_ID, GameRound.status == "active")
        .order_by(GameRound.id.desc())
    )


def mines_round_response(
    round_item: GameRound,
    user: User,
    transaction: Transaction | None,
    *,
    reveal_mines: bool = False,
) -> MinesRoundResponse:
    result = round_result(round_item)
    mine_count = int(result.get("mine_count") or 0)
    revealed_cells = sorted(int(cell) for cell in result.get("revealed_cells", []))
    current_multiplier_cents = int(result.get("multiplier_cents") or multiplier_cents(mine_count, len(revealed_cells)))
    potential_win_cents = win_cents_for(round_item.total_bet_cents, mine_count, len(revealed_cells))
    mines = sorted(int(cell) for cell in result.get("mines", [])) if reveal_mines or round_item.status != "active" else None

    return MinesRoundResponse(
        round_id=round_item.id,
        status=round_item.status,
        mine_count=mine_count,
        revealed_cells=revealed_cells,
        mines=mines,
        current_multiplier=cents_to_amount(current_multiplier_cents),
        total_bet_cents=round_item.total_bet_cents,
        total_win_cents=round_item.total_win_cents,
        net_cents=round_item.net_cents,
        potential_win_cents=potential_win_cents,
        started_at=round_item.created_at,
        settled_at=round_item.settled_at,
        wallet=wallet_response(user),
        transaction=TransactionPublic.model_validate(transaction) if transaction else None,
    )


def settle_mines_loss(db: Session, *, round_item: GameRound, user: User, hit_cell: int, request: Request | None = None) -> Transaction | None:
    if round_item.status != "active":
        raise mines_error("err_mines_round_settled", status.HTTP_409_CONFLICT)
    claim_active_round(db, round_item, mines_error("err_mines_round_settled", status.HTTP_409_CONFLICT))

    result = round_result(round_item)
    transaction = transaction_for_round(db, result)
    now = utc_now()
    before_balance = user.balance_cents
    revealed_cells = sorted(set(int(cell) for cell in result.get("revealed_cells", [])))

    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(games_played=User.games_played + 1)
        .execution_options(synchronize_session=False)
    )
    round_item.status = "lost"
    round_item.total_win_cents = 0
    round_item.net_cents = -round_item.total_bet_cents
    round_item.settled_at = now
    result.update(
        {
            "hit_cell": hit_cell,
            "revealed_cells": revealed_cells,
            "settled_at": now.isoformat(),
            "summary": {
                "status": "lost",
                "opened": len(revealed_cells),
                "mine_count": result.get("mine_count"),
                "hit_cell": hit_cell,
            },
        }
    )
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = -round_item.total_bet_cents

    db.add(round_item)
    if transaction:
        db.add(transaction)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action="game.mines.lost",
        actor_user=user,
        target_user=user,
        amount_cents=-round_item.total_bet_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": MINES_GAME_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "hit_cell": hit_cell,
            "opened": len(revealed_cells),
        },
        request=request,
    )
    return transaction


def settle_mines_cashout(db: Session, *, round_item: GameRound, user: User, request: Request | None = None) -> Transaction | None:
    if round_item.status != "active":
        raise mines_error("err_mines_round_settled", status.HTTP_409_CONFLICT)
    claim_active_round(db, round_item, mines_error("err_mines_round_settled", status.HTTP_409_CONFLICT))

    result = round_result(round_item)
    transaction = transaction_for_round(db, result)
    revealed_cells = sorted(int(cell) for cell in result.get("revealed_cells", []))
    mine_count = int(result.get("mine_count") or 0)
    cashout_multiplier_cents = multiplier_cents(mine_count, len(revealed_cells))
    win_cents = round_item.total_bet_cents * cashout_multiplier_cents // 100
    net_cents = win_cents - round_item.total_bet_cents
    before_balance = user.balance_cents
    now = utc_now()

    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            balance_cents=User.balance_cents + win_cents,
            games_played=User.games_played + 1,
            total_won_cents=User.total_won_cents + max(net_cents, 0),
        )
        .execution_options(synchronize_session=False)
    )
    round_item.status = "completed"
    round_item.total_win_cents = win_cents
    round_item.net_cents = net_cents
    round_item.settled_at = now
    result.update(
        {
            "multiplier_cents": cashout_multiplier_cents,
            "settled_at": now.isoformat(),
            "summary": {
                "status": "cashed_out",
                "opened": len(revealed_cells),
                "mine_count": mine_count,
                "multiplier": str(cents_to_amount(cashout_multiplier_cents)),
            },
        }
    )
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = net_cents

    db.add(round_item)
    if transaction:
        db.add(transaction)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action="game.mines.cashout",
        actor_user=user,
        target_user=user,
        amount_cents=win_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": MINES_GAME_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "opened": len(revealed_cells),
            "multiplier_cents": cashout_multiplier_cents,
            "net_cents": net_cents,
        },
        request=request,
    )
    return transaction


def active_blocks_round(db: Session, user_id: int) -> GameRound | None:
    return db.scalar(
        select(GameRound)
        .where(GameRound.user_id == user_id, GameRound.game_id == BLOCKS_GAME_ID, GameRound.status == "active")
        .order_by(GameRound.id.desc())
    )


def blocks_next_pieces(result: dict) -> list[BlocksPiece]:
    current = result.get("current_piece") if isinstance(result.get("current_piece"), dict) else None
    next_id = int(current.get("id") or 0) + 1 if current else int(result.get("piece_counter") or 1)
    queue = ensure_queue(result.get("queue", []), NEXT_QUEUE_SIZE)
    return [BlocksPiece(id=next_id + index, type=piece_type) for index, piece_type in enumerate(queue[:NEXT_QUEUE_SIZE])]


def blocks_round_response(
    round_item: GameRound,
    user: User,
    transaction: Transaction | None,
) -> BlocksRoundResponse:
    result = round_result(round_item)
    difficulty = str(result.get("difficulty") or DEFAULT_BLOCKS_DIFFICULTY)
    if difficulty not in ALLOWED_BLOCKS_DIFFICULTIES:
        difficulty = DEFAULT_BLOCKS_DIFFICULTY
    board = normalize_board(result.get("board"), difficulty)
    multiplier_cents = int(result.get("multiplier_cents") or starting_multiplier_cents_for(difficulty))
    pieces_placed = int(result.get("pieces_placed") or 0)
    current_piece = result.get("current_piece") if round_item.status == "active" else None
    return BlocksRoundResponse(
        round_id=round_item.id,
        status=round_item.status,
        difficulty=difficulty,
        board_height=board_height_for(difficulty),
        tick_ms=tick_ms_for(difficulty, pieces_placed),
        pressure_level=pressure_level_for(difficulty, pieces_placed),
        cashout_available=round_item.status == "active" and multiplier_cents >= BLOCKS_CASHOUT_MIN_MULTIPLIER_CENTS,
        board=board,
        current_piece=BlocksPiece(**current_piece) if isinstance(current_piece, dict) else None,
        next_pieces=blocks_next_pieces(result) if round_item.status == "active" else [],
        score=int(result.get("score") or 0),
        lines_cleared=int(result.get("lines_cleared") or 0),
        combo=int(result.get("combo") or 0),
        pieces_placed=pieces_placed,
        current_multiplier=blocks_multiplier_amount(multiplier_cents),
        total_bet_cents=round_item.total_bet_cents,
        total_win_cents=round_item.total_win_cents,
        net_cents=round_item.net_cents,
        potential_win_cents=blocks_win_cents_for(round_item.total_bet_cents, multiplier_cents),
        last_clear=int(result.get("last_clear") or 0),
        last_drop_y=result.get("last_drop_y"),
        loss_reason=result.get("loss_reason"),
        started_at=round_item.created_at,
        settled_at=round_item.settled_at,
        wallet=wallet_response(user),
        transaction=TransactionPublic.model_validate(transaction) if transaction else None,
    )


def blocks_stack_overloaded(board: list[list[str]]) -> bool:
    top_rows = board[: min(2, len(board))]
    return any(any(cell for cell in row) for row in top_rows)


def settle_blocks_loss(
    db: Session,
    *,
    round_item: GameRound,
    user: User,
    action: str = "game.blocks.lost",
    reason: str = "top_out",
    request: Request | None = None,
) -> Transaction | None:
    if round_item.status != "active":
        raise blocks_error("err_blocks_round_settled", status.HTTP_409_CONFLICT)
    claim_active_round(db, round_item, blocks_error("err_blocks_round_settled", status.HTTP_409_CONFLICT))

    result = round_result(round_item)
    transaction = transaction_for_round(db, result)
    now = utc_now()
    before_balance = user.balance_cents

    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(games_played=User.games_played + 1)
        .execution_options(synchronize_session=False)
    )
    round_item.status = "lost"
    round_item.total_win_cents = 0
    round_item.net_cents = -round_item.total_bet_cents
    round_item.settled_at = now
    result["current_piece"] = None
    result.update(
        {
            "settled_at": now.isoformat(),
            "loss_reason": reason,
            "summary": {
                "status": "forfeit" if action.endswith(".forfeit") else "lost",
                "reason": reason,
                "score": int(result.get("score") or 0),
                "lines": int(result.get("lines_cleared") or 0),
                "difficulty": result.get("difficulty") or DEFAULT_BLOCKS_DIFFICULTY,
                "multiplier": str(blocks_multiplier_amount(int(result.get("multiplier_cents") or starting_multiplier_cents_for(result.get("difficulty"))))),
            },
        }
    )
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = -round_item.total_bet_cents

    db.add(round_item)
    if transaction:
        db.add(transaction)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action=action,
        actor_user=user,
        target_user=user,
        amount_cents=-round_item.total_bet_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": BLOCKS_GAME_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "reason": reason,
            "score": int(result.get("score") or 0),
            "lines_cleared": int(result.get("lines_cleared") or 0),
        },
        request=request,
    )
    return transaction


def settle_blocks_cashout(db: Session, *, round_item: GameRound, user: User, request: Request | None = None) -> Transaction | None:
    if round_item.status != "active":
        raise blocks_error("err_blocks_round_settled", status.HTTP_409_CONFLICT)
    claim_active_round(db, round_item, blocks_error("err_blocks_round_settled", status.HTTP_409_CONFLICT))

    result = round_result(round_item)
    transaction = transaction_for_round(db, result)
    difficulty = str(result.get("difficulty") or DEFAULT_BLOCKS_DIFFICULTY)
    multiplier_cents = int(result.get("multiplier_cents") or starting_multiplier_cents_for(difficulty))
    win_cents = blocks_win_cents_for(round_item.total_bet_cents, multiplier_cents)
    net_cents = win_cents - round_item.total_bet_cents
    before_balance = user.balance_cents
    now = utc_now()

    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            balance_cents=User.balance_cents + win_cents,
            games_played=User.games_played + 1,
            total_won_cents=User.total_won_cents + max(net_cents, 0),
        )
        .execution_options(synchronize_session=False)
    )
    round_item.status = "completed"
    round_item.total_win_cents = win_cents
    round_item.net_cents = net_cents
    round_item.settled_at = now
    result["current_piece"] = None
    result.update(
        {
            "settled_at": now.isoformat(),
            "summary": {
                "status": "cashed_out",
                "difficulty": difficulty,
                "score": int(result.get("score") or 0),
                "lines": int(result.get("lines_cleared") or 0),
                "multiplier": str(blocks_multiplier_amount(multiplier_cents)),
            },
        }
    )
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = net_cents

    db.add(round_item)
    if transaction:
        db.add(transaction)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action="game.blocks.cashout",
        actor_user=user,
        target_user=user,
        amount_cents=win_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": BLOCKS_GAME_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "score": int(result.get("score") or 0),
            "lines_cleared": int(result.get("lines_cleared") or 0),
            "multiplier_cents": multiplier_cents,
            "net_cents": net_cents,
        },
        request=request,
    )
    return transaction


@router.post("/mines/solar-wilds/start", response_model=MinesRoundResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("45/minute")
def solar_mines_start(
    request: Request,
    payload: MinesStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MinesRoundResponse:
    bet_cents = amount_to_cents(payload.bet)
    mine_count = int(payload.mine_count)
    if not is_allowed_manager_bet(db, current_user, MINES_GAME_ID, bet_cents, ALLOWED_MINES_BET_CENTS):
        raise mines_error("err_mines_bet_invalid")
    if mine_count not in ALLOWED_MINE_COUNTS:
        raise mines_error("err_mines_count_invalid")

    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return MinesRoundResponse.model_validate(idem.replay_response)

    user = db.merge(current_user)
    if active_mines_round(db, user.id):
        raise mines_error("err_mines_active_round", status.HTTP_409_CONFLICT)

    started_at = utc_now()
    user, transaction, before_balance, earned_vip_points = reserve_bet(
        db,
        user=user,
        amount_cents=bet_cents,
        game_id=MINES_GAME_ID,
        method_id=MINES_METHOD_ID,
        title=MINES_TITLE,
        title_key=MINES_TITLE_KEY,
        action="game.mines.start",
        balance_error_code="err_mines_balance",
        metadata={"mine_count": mine_count, "idempotency_key": idem.key_hash},
        request=request,
    )

    result = {
        "started_at": started_at.isoformat(),
        "mine_count": mine_count,
        "mines": generate_mines(mine_count),
        "revealed_cells": [],
        "multiplier_cents": multiplier_cents(mine_count, 0),
        "transaction_id": transaction.id,
        "summary": {"status": "active", "opened": 0, "mine_count": mine_count},
    }
    game_round = GameRound(
        user_id=user.id,
        game_id=MINES_GAME_ID,
        result_number=None,
        result_color=None,
        total_bet_cents=bet_cents,
        total_win_cents=0,
        net_cents=-bet_cents,
        status="active",
        bets_json=json.dumps([{"type": "mines", "amount_cents": bet_cents, "mine_count": mine_count}], separators=(",", ":")),
        result_json=json.dumps(result, separators=(",", ":")),
        created_at=started_at,
    )
    db.add(game_round)
    db.flush()

    response = mines_round_response(game_round, user, transaction)
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(user)
    db.refresh(game_round)
    db.refresh(transaction)
    return response


@router.get("/mines/solar-wilds/active", response_model=MinesRoundResponse | None)
@limiter.limit("120/minute")
def solar_mines_active_round(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MinesRoundResponse | None:
    user = db.merge(current_user)
    round_item = active_mines_round(db, user.id)
    if not round_item:
        return None
    return mines_round_response(round_item, user, transaction_for_round(db, round_result(round_item)))


@router.get("/mines/solar-wilds/rounds/{round_id}", response_model=MinesRoundResponse)
@limiter.limit("120/minute")
def solar_mines_round_status(
    request: Request,
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MinesRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != MINES_GAME_ID:
        raise mines_error("err_mines_round_not_found", status.HTTP_404_NOT_FOUND)
    return mines_round_response(round_item, user, transaction_for_round(db, round_result(round_item)))


@router.post("/mines/solar-wilds/rounds/{round_id}/reveal", response_model=MinesRoundResponse)
@limiter.limit("120/minute")
def solar_mines_reveal(
    request: Request,
    round_id: int,
    payload: MinesRevealRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MinesRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != MINES_GAME_ID:
        raise mines_error("err_mines_round_not_found", status.HTTP_404_NOT_FOUND)
    if round_item.status != "active":
        raise mines_error("err_mines_round_settled", status.HTTP_409_CONFLICT)

    try:
        cell = validate_cell(payload.cell)
    except (TypeError, ValueError):
        raise mines_error("err_mines_cell_invalid") from None

    result = round_result(round_item)
    revealed_cells = sorted(set(int(value) for value in result.get("revealed_cells", [])))
    if cell in revealed_cells:
        raise mines_error("err_mines_cell_revealed", status.HTTP_409_CONFLICT)

    mines = set(int(value) for value in result.get("mines", []))
    transaction = transaction_for_round(db, result)
    if cell in mines:
        transaction = settle_mines_loss(db, round_item=round_item, user=user, hit_cell=cell, request=request)
        db.commit()
        db.refresh(user)
        db.refresh(round_item)
        if transaction:
            db.refresh(transaction)
        return mines_round_response(round_item, user, transaction, reveal_mines=True)

    revealed_cells.append(cell)
    revealed_cells = sorted(revealed_cells)
    mine_count = int(result.get("mine_count") or 0)
    next_multiplier_cents = multiplier_cents(mine_count, len(revealed_cells))
    result.update(
        {
            "revealed_cells": revealed_cells,
            "multiplier_cents": next_multiplier_cents,
            "summary": {
                "status": "active",
                "opened": len(revealed_cells),
                "mine_count": mine_count,
                "multiplier": str(cents_to_amount(next_multiplier_cents)),
            },
        }
    )
    write_round_result(round_item, result)
    db.add(round_item)

    if len(revealed_cells) >= GRID_CELLS - mine_count:
        db.flush()
        transaction = settle_mines_cashout(db, round_item=round_item, user=user, request=request)
        db.commit()
        db.refresh(user)
        db.refresh(round_item)
        if transaction:
            db.refresh(transaction)
        return mines_round_response(round_item, user, transaction, reveal_mines=True)

    db.commit()
    db.refresh(user)
    db.refresh(round_item)
    if transaction:
        db.refresh(transaction)
    return mines_round_response(round_item, user, transaction)


@router.post("/mines/solar-wilds/rounds/{round_id}/cashout", response_model=MinesRoundResponse)
@limiter.limit("60/minute")
def solar_mines_cashout(
    request: Request,
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MinesRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != MINES_GAME_ID:
        raise mines_error("err_mines_round_not_found", status.HTTP_404_NOT_FOUND)
    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload={"round_id": round_id},
    )
    if idem.replay_response is not None:
        return MinesRoundResponse.model_validate(idem.replay_response)
    if round_item.status != "active":
        raise mines_error("err_mines_round_settled", status.HTTP_409_CONFLICT)

    result = round_result(round_item)
    if not result.get("revealed_cells"):
        raise mines_error("err_mines_no_reveals", status.HTTP_409_CONFLICT)

    transaction = settle_mines_cashout(db, round_item=round_item, user=user, request=request)
    response = mines_round_response(round_item, user, transaction, reveal_mines=True)
    complete_idempotency(db, idem, response, transaction_id=transaction.id if transaction else None)
    db.commit()
    db.refresh(user)
    db.refresh(round_item)
    if transaction:
        db.refresh(transaction)
    return response


@router.post("/blocks/neon-pyramids/start", response_model=BlocksRoundResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("45/minute")
def neon_pyramids_start(
    request: Request,
    payload: BlocksStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BlocksRoundResponse:
    bet_cents = amount_to_cents(payload.bet)
    difficulty = str(payload.difficulty or DEFAULT_BLOCKS_DIFFICULTY)
    if not is_allowed_manager_bet(db, current_user, BLOCKS_GAME_ID, bet_cents, ALLOWED_BLOCKS_BET_CENTS):
        raise blocks_error("err_blocks_bet_invalid")
    if difficulty not in ALLOWED_BLOCKS_DIFFICULTIES:
        raise blocks_error("err_blocks_difficulty_invalid")

    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return BlocksRoundResponse.model_validate(idem.replay_response)

    user = db.merge(current_user)
    if active_blocks_round(db, user.id):
        raise blocks_error("err_blocks_active_round", status.HTTP_409_CONFLICT)

    started_at = utc_now()
    queue = ensure_queue(generate_piece_queue(), NEXT_QUEUE_SIZE + 2)
    current_piece = {"id": 1, "type": queue.pop(0)}
    user, transaction, before_balance, earned_vip_points = reserve_bet(
        db,
        user=user,
        amount_cents=bet_cents,
        game_id=BLOCKS_GAME_ID,
        method_id=BLOCKS_METHOD_ID,
        title=BLOCKS_TITLE,
        title_key=BLOCKS_TITLE_KEY,
        action="game.blocks.start",
        balance_error_code="err_blocks_balance",
        metadata={"difficulty": difficulty, "idempotency_key": idem.key_hash},
        request=request,
    )

    result = {
        "started_at": started_at.isoformat(),
        "difficulty": difficulty,
        "board": empty_board(difficulty),
        "queue": ensure_queue(queue, NEXT_QUEUE_SIZE + 2),
        "current_piece": current_piece,
        "piece_counter": 1,
        "score": 0,
        "lines_cleared": 0,
        "combo": 0,
        "pieces_placed": 0,
        "pressure_level": 0,
        "multiplier_cents": starting_multiplier_cents_for(difficulty),
        "last_clear": 0,
        "last_drop_y": None,
        "transaction_id": transaction.id,
        "summary": {
            "status": "active",
            "difficulty": difficulty,
            "score": 0,
            "lines": 0,
            "pressure_level": 0,
            "multiplier": str(blocks_multiplier_amount(starting_multiplier_cents_for(difficulty))),
        },
    }
    game_round = GameRound(
        user_id=user.id,
        game_id=BLOCKS_GAME_ID,
        result_number=None,
        result_color=None,
        total_bet_cents=bet_cents,
        total_win_cents=0,
        net_cents=-bet_cents,
        status="active",
        bets_json=json.dumps([{"type": "blocks", "amount_cents": bet_cents}], separators=(",", ":")),
        result_json=json.dumps(result, separators=(",", ":")),
        created_at=started_at,
    )
    db.add(game_round)
    db.flush()

    response = blocks_round_response(game_round, user, transaction)
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(user)
    db.refresh(game_round)
    db.refresh(transaction)
    return response


@router.get("/blocks/neon-pyramids/active", response_model=BlocksRoundResponse | None)
@limiter.limit("120/minute")
def neon_pyramids_active_round(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BlocksRoundResponse | None:
    user = db.merge(current_user)
    round_item = active_blocks_round(db, user.id)
    if not round_item:
        return None
    result = round_result(round_item)
    difficulty = str(result.get("difficulty") or DEFAULT_BLOCKS_DIFFICULTY)
    current_piece = result.get("current_piece") if isinstance(result.get("current_piece"), dict) else None
    board = normalize_board(result.get("board"), difficulty)
    transaction = transaction_for_round(db, result)
    if current_piece and not can_place_anywhere(board, str(current_piece.get("type") or "")):
        transaction = settle_blocks_loss(db, round_item=round_item, user=user, reason="top_out", request=request)
        db.commit()
        db.refresh(user)
        db.refresh(round_item)
        if transaction:
            db.refresh(transaction)
    return blocks_round_response(round_item, user, transaction)


@router.get("/blocks/neon-pyramids/rounds/{round_id}", response_model=BlocksRoundResponse)
@limiter.limit("120/minute")
def neon_pyramids_round_status(
    request: Request,
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BlocksRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != BLOCKS_GAME_ID:
        raise blocks_error("err_blocks_round_not_found", status.HTTP_404_NOT_FOUND)
    result = round_result(round_item)
    transaction = transaction_for_round(db, result)
    if round_item.status == "active":
        difficulty = str(result.get("difficulty") or DEFAULT_BLOCKS_DIFFICULTY)
        current_piece = result.get("current_piece") if isinstance(result.get("current_piece"), dict) else None
        board = normalize_board(result.get("board"), difficulty)
        if current_piece and not can_place_anywhere(board, str(current_piece.get("type") or "")):
            transaction = settle_blocks_loss(db, round_item=round_item, user=user, reason="top_out", request=request)
            db.commit()
            db.refresh(user)
            db.refresh(round_item)
            if transaction:
                db.refresh(transaction)
    return blocks_round_response(round_item, user, transaction)


@router.post("/blocks/neon-pyramids/rounds/{round_id}/place", response_model=BlocksRoundResponse)
@limiter.limit("180/minute")
def neon_pyramids_place(
    request: Request,
    round_id: int,
    payload: BlocksPlaceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BlocksRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != BLOCKS_GAME_ID:
        raise blocks_error("err_blocks_round_not_found", status.HTTP_404_NOT_FOUND)
    if round_item.status != "active":
        raise blocks_error("err_blocks_round_settled", status.HTTP_409_CONFLICT)

    result = round_result(round_item)
    difficulty = str(result.get("difficulty") or DEFAULT_BLOCKS_DIFFICULTY)
    if difficulty not in ALLOWED_BLOCKS_DIFFICULTIES:
        difficulty = DEFAULT_BLOCKS_DIFFICULTY
    current_piece = result.get("current_piece") if isinstance(result.get("current_piece"), dict) else None
    if not current_piece or int(current_piece.get("id") or 0) != payload.piece_id:
        raise blocks_error("err_blocks_piece_invalid", status.HTTP_409_CONFLICT)

    board = normalize_board(result.get("board"), difficulty)
    piece_type = str(current_piece.get("type") or "")
    if not can_place_anywhere(board, piece_type):
        transaction = settle_blocks_loss(db, round_item=round_item, user=user, reason="top_out", request=request)
        db.commit()
        db.refresh(user)
        db.refresh(round_item)
        if transaction:
            db.refresh(transaction)
        return blocks_round_response(round_item, user, transaction)

    if not has_valid_x(piece_type, payload.rotation, payload.x):
        raise blocks_error("err_blocks_placement_invalid")

    try:
        if payload.y is None:
            next_board, cleared, drop_y = place_piece(board, piece_type, payload.rotation, payload.x, difficulty)
        else:
            next_board, cleared, drop_y = place_piece_at_y(
                board,
                piece_type,
                payload.rotation,
                payload.x,
                payload.y,
                difficulty,
            )
    except (TypeError, ValueError):
        if blocks_stack_overloaded(board):
            transaction = settle_blocks_loss(db, round_item=round_item, user=user, reason="top_out", request=request)
            db.commit()
            db.refresh(user)
            db.refresh(round_item)
            if transaction:
                db.refresh(transaction)
            return blocks_round_response(round_item, user, transaction)
        raise blocks_error("err_blocks_placement_invalid") from None

    previous_combo = int(result.get("combo") or 0)
    combo = previous_combo + 1 if cleared > 0 else 0
    pieces_placed = int(result.get("pieces_placed") or 0) + 1
    multiplier_cents = multiplier_after_clear(
        int(result.get("multiplier_cents") or starting_multiplier_cents_for(difficulty)),
        cleared,
        combo,
        pieces_placed,
        difficulty,
    )
    score = int(result.get("score") or 0) + score_for_clear(cleared, combo, pieces_placed)
    lines_cleared = int(result.get("lines_cleared") or 0) + cleared

    queue = ensure_queue(result.get("queue", []), NEXT_QUEUE_SIZE + 2)
    next_type = queue.pop(0)
    next_piece = {"id": int(current_piece.get("id") or 0) + 1, "type": next_type}
    result.update(
        {
            "board": next_board,
            "queue": ensure_queue(queue, NEXT_QUEUE_SIZE + 2),
            "current_piece": next_piece,
            "piece_counter": next_piece["id"],
            "score": score,
            "lines_cleared": lines_cleared,
            "combo": combo,
            "pieces_placed": pieces_placed,
            "pressure_level": pressure_level_for(difficulty, pieces_placed),
            "multiplier_cents": multiplier_cents,
            "last_clear": cleared,
            "last_drop_y": drop_y,
            "summary": {
                "status": "active",
                "difficulty": difficulty,
                "score": score,
                "lines": lines_cleared,
                "pressure_level": pressure_level_for(difficulty, pieces_placed),
                "multiplier": str(blocks_multiplier_amount(multiplier_cents)),
                "last_clear": cleared,
            },
        }
    )
    write_round_result(round_item, result)
    db.add(round_item)
    db.flush()

    add_audit_log(
        db,
        action="game.blocks.place",
        actor_user=user,
        target_user=user,
        amount_cents=None,
        before_balance_cents=user.balance_cents,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": BLOCKS_GAME_ID,
            "round_id": round_item.id,
            "piece": piece_type,
            "piece_id": payload.piece_id,
            "rotation": payload.rotation,
            "x": payload.x,
            "drop_y": drop_y,
            "cleared": cleared,
            "score": score,
            "lines_cleared": lines_cleared,
            "multiplier_cents": multiplier_cents,
            "difficulty": difficulty,
        },
        request=request,
    )

    transaction = transaction_for_round(db, result)
    if not can_place_anywhere(next_board, next_type):
        transaction = settle_blocks_loss(db, round_item=round_item, user=user, reason="top_out", request=request)

    db.commit()
    db.refresh(user)
    db.refresh(round_item)
    if transaction:
        db.refresh(transaction)
    return blocks_round_response(round_item, user, transaction)


@router.post("/blocks/neon-pyramids/rounds/{round_id}/cashout", response_model=BlocksRoundResponse)
@limiter.limit("60/minute")
def neon_pyramids_cashout(
    request: Request,
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BlocksRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != BLOCKS_GAME_ID:
        raise blocks_error("err_blocks_round_not_found", status.HTTP_404_NOT_FOUND)
    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload={"round_id": round_id},
    )
    if idem.replay_response is not None:
        return BlocksRoundResponse.model_validate(idem.replay_response)
    if round_item.status != "active":
        raise blocks_error("err_blocks_round_settled", status.HTTP_409_CONFLICT)

    result = round_result(round_item)
    multiplier_cents = int(result.get("multiplier_cents") or starting_multiplier_cents_for(result.get("difficulty")))
    if int(result.get("lines_cleared") or 0) <= 0 or multiplier_cents < BLOCKS_CASHOUT_MIN_MULTIPLIER_CENTS:
        raise blocks_error("err_blocks_no_lines", status.HTTP_409_CONFLICT)

    transaction = settle_blocks_cashout(db, round_item=round_item, user=user, request=request)
    response = blocks_round_response(round_item, user, transaction)
    complete_idempotency(db, idem, response, transaction_id=transaction.id if transaction else None)
    db.commit()
    db.refresh(user)
    db.refresh(round_item)
    if transaction:
        db.refresh(transaction)
    return response


@router.post("/blocks/neon-pyramids/rounds/{round_id}/forfeit", response_model=BlocksRoundResponse)
@limiter.limit("60/minute")
def neon_pyramids_forfeit(
    request: Request,
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BlocksRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != BLOCKS_GAME_ID:
        raise blocks_error("err_blocks_round_not_found", status.HTTP_404_NOT_FOUND)
    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload={"round_id": round_id, "action": "forfeit"},
    )
    if idem.replay_response is not None:
        return BlocksRoundResponse.model_validate(idem.replay_response)
    if round_item.status != "active":
        raise blocks_error("err_blocks_round_settled", status.HTTP_409_CONFLICT)

    transaction = settle_blocks_loss(
        db,
        round_item=round_item,
        user=user,
        action="game.blocks.forfeit",
        reason="forfeit",
        request=request,
    )
    response = blocks_round_response(round_item, user, transaction)
    complete_idempotency(db, idem, response, transaction_id=transaction.id if transaction else None)
    db.commit()
    db.refresh(user)
    db.refresh(round_item)
    if transaction:
        db.refresh(transaction)
    return response


def active_holdem_round(db: Session, user_id: int) -> GameRound | None:
    return db.scalar(
        select(GameRound)
        .where(GameRound.user_id == user_id, GameRound.game_id == HOLDEM_GAME_ID, GameRound.status == "active")
        .order_by(GameRound.id.desc())
    )


def holdem_round_response(round_item: GameRound, user: User, transaction: Transaction | None) -> HoldemRoundResponse:
    result = round_result(round_item)
    stage = str(result.get("stage") or ("settled" if round_item.status != "active" else "decision"))
    is_active = round_item.status == "active"
    community_cards = list(result.get("community_cards") or [])
    dealer_cards = [] if is_active else list(result.get("dealer_cards") or [])
    player_hand = result.get("player_hand") if isinstance(result.get("player_hand"), dict) else None
    dealer_hand = result.get("dealer_hand") if isinstance(result.get("dealer_hand"), dict) else None
    return HoldemRoundResponse(
        round_id=round_item.id,
        status=round_item.status,
        stage=stage,
        player_cards=list(result.get("player_cards") or []),
        dealer_cards=dealer_cards,
        dealer_hidden_count=2 if is_active else 0,
        community_cards=community_cards,
        available_actions=["call", "fold"] if is_active else [],
        dealer_qualified=result.get("dealer_qualified") if not is_active else None,
        outcome=result.get("outcome") if not is_active else None,
        player_hand=player_hand,
        dealer_hand=dealer_hand,
        total_bet_cents=round_item.total_bet_cents,
        total_win_cents=round_item.total_win_cents,
        net_cents=round_item.net_cents,
        call_amount_cents=int(result.get("call_amount_cents") or round_item.total_bet_cents * 2),
        started_at=round_item.created_at,
        settled_at=round_item.settled_at,
        wallet=wallet_response(user),
        transaction=TransactionPublic.model_validate(transaction) if transaction else None,
    )


def settle_holdem_fold(db: Session, *, round_item: GameRound, user: User, request: Request | None = None) -> Transaction | None:
    if round_item.status != "active":
        raise holdem_error("err_holdem_round_settled", status.HTTP_409_CONFLICT)
    claim_active_round(db, round_item, holdem_error("err_holdem_round_settled", status.HTTP_409_CONFLICT))

    result = round_result(round_item)
    transaction = transaction_for_round(db, result)
    now = utc_now()
    before_balance = user.balance_cents

    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(games_played=User.games_played + 1)
        .execution_options(synchronize_session=False)
    )
    round_item.status = "lost"
    round_item.total_win_cents = 0
    round_item.net_cents = -round_item.total_bet_cents
    round_item.settled_at = now
    result.update(
        {
            "stage": "folded",
            "settled_at": now.isoformat(),
            "outcome": "fold",
            "summary": {
                "status": "fold",
                "player_cards": result.get("player_cards", []),
                "community_cards": result.get("community_cards", []),
            },
        }
    )
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = -round_item.total_bet_cents

    db.add(round_item)
    if transaction:
        db.add(transaction)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action="game.holdem.fold",
        actor_user=user,
        target_user=user,
        amount_cents=-round_item.total_bet_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={"game_id": HOLDEM_GAME_ID, "round_id": round_item.id, "transaction_id": transaction.id if transaction else None},
        request=request,
    )
    return transaction


def settle_holdem_call(db: Session, *, round_item: GameRound, user: User, request: Request | None = None) -> Transaction | None:
    if round_item.status != "active":
        raise holdem_error("err_holdem_round_settled", status.HTTP_409_CONFLICT)
    claim_active_round(db, round_item, holdem_error("err_holdem_round_settled", status.HTTP_409_CONFLICT))

    result = round_result(round_item)
    transaction = transaction_for_round(db, result)
    ante_cents = int(result.get("ante_cents") or round_item.total_bet_cents)
    call_cents = int(result.get("call_amount_cents") or ante_cents * 2)
    consume_game_budget(db, user=user, amount_cents=call_cents)
    before_reserve_balance = user.balance_cents
    balance_update = (
        update(User)
        .where(User.id == user.id, User.balance_cents >= call_cents)
        .values(balance_cents=User.balance_cents - call_cents)
        .execution_options(synchronize_session=False)
    )
    update_result = db.execute(balance_update)
    if update_result.rowcount != 1:
        db.rollback()
        raise holdem_error("err_holdem_balance")
    round_item.total_bet_cents = ante_cents + call_cents
    round_item.net_cents = -round_item.total_bet_cents
    if transaction:
        transaction.amount_cents = -round_item.total_bet_cents
        db.add(transaction)
    db.flush()
    db.refresh(user)
    earned_vip_points = award_vip_bet_points(user, call_cents)
    if earned_vip_points:
        db.add(user)
        db.flush()
        db.refresh(user)

    add_audit_log(
        db,
        action="game.holdem.call",
        actor_user=user,
        target_user=user,
        amount_cents=-call_cents,
        before_balance_cents=before_reserve_balance,
        after_balance_cents=user.balance_cents,
        metadata={"game_id": HOLDEM_GAME_ID, "round_id": round_item.id, "transaction_id": transaction.id if transaction else None},
        request=request,
    )

    community_cards = complete_community_cards(result)
    player_cards = list(result.get("player_cards") or [])
    dealer_cards = list(result.get("dealer_cards") or [])
    player_full = player_cards + community_cards
    dealer_full = dealer_cards + community_cards
    player_hand = evaluate_best(player_full)
    dealer_hand = evaluate_best(dealer_full)
    qualified = dealer_qualifies(dealer_full)
    compare = compare_hands(player_full, dealer_full) if qualified else 1

    if not qualified:
        outcome = "dealer_not_qualified"
        status_value = "completed"
        total_win_cents = (ante_cents * 2) + call_cents
    elif compare > 0:
        outcome = "win"
        status_value = "completed"
        total_win_cents = round_item.total_bet_cents * 2
    elif compare == 0:
        outcome = "push"
        status_value = "completed"
        total_win_cents = round_item.total_bet_cents
    else:
        outcome = "loss"
        status_value = "lost"
        total_win_cents = 0

    net_cents = total_win_cents - round_item.total_bet_cents
    before_settle_balance = user.balance_cents
    now = utc_now()
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            balance_cents=User.balance_cents + total_win_cents,
            games_played=User.games_played + 1,
            total_won_cents=User.total_won_cents + max(net_cents, 0),
        )
        .execution_options(synchronize_session=False)
    )
    round_item.status = status_value
    round_item.total_win_cents = total_win_cents
    round_item.net_cents = net_cents
    round_item.settled_at = now
    result.update(
        {
            "stage": "settled",
            "settled_at": now.isoformat(),
            "dealer_qualified": qualified,
            "outcome": outcome,
            "player_hand": public_hand(player_hand),
            "dealer_hand": public_hand(dealer_hand),
            "summary": {
                "status": outcome,
                "player_hand": player_hand.name,
                "dealer_hand": dealer_hand.name,
                "dealer_qualified": qualified,
                "net_cents": net_cents,
            },
        }
    )
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = net_cents

    db.add(round_item)
    if transaction:
        db.add(transaction)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action="game.holdem.settle",
        actor_user=user,
        target_user=user,
        amount_cents=total_win_cents,
        before_balance_cents=before_settle_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": HOLDEM_GAME_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "outcome": outcome,
            "net_cents": net_cents,
        },
        request=request,
    )
    return transaction


@router.post("/holdem/texas-holdem/start", response_model=HoldemRoundResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("45/minute")
def texas_holdem_start(
    request: Request,
    payload: HoldemStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HoldemRoundResponse:
    ante_cents = amount_to_cents(payload.ante)
    if not is_allowed_manager_bet(db, current_user, HOLDEM_GAME_ID, ante_cents, ALLOWED_HOLDEM_ANTE_CENTS):
        raise holdem_error("err_holdem_ante_invalid")

    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return HoldemRoundResponse.model_validate(idem.replay_response)

    user = db.merge(current_user)
    if active_holdem_round(db, user.id):
        raise holdem_error("err_holdem_active_round", status.HTTP_409_CONFLICT)

    user, transaction, before_balance, earned_vip_points = reserve_bet(
        db,
        user=user,
        amount_cents=ante_cents,
        game_id=HOLDEM_GAME_ID,
        method_id=HOLDEM_METHOD_ID,
        title=HOLDEM_TITLE,
        title_key=HOLDEM_TITLE_KEY,
        action="game.holdem.start",
        balance_error_code="err_holdem_balance",
        metadata={"idempotency_key": idem.key_hash},
        request=request,
    )

    dealt = deal_holdem_round()
    result = {
        "stage": "decision",
        "ante_cents": ante_cents,
        "call_amount_cents": ante_cents * 2,
        "player_cards": dealt["player_cards"],
        "dealer_cards": dealt["dealer_cards"],
        "community_cards": dealt["community_cards"],
        "deck": dealt["deck"],
        "transaction_id": transaction.id,
        "summary": {"status": "active", "player_cards": dealt["player_cards"], "community_cards": dealt["community_cards"]},
    }
    game_round = GameRound(
        user_id=user.id,
        game_id=HOLDEM_GAME_ID,
        result_number=None,
        result_color=None,
        total_bet_cents=ante_cents,
        total_win_cents=0,
        net_cents=-ante_cents,
        status="active",
        bets_json=json.dumps([{"type": "ante", "amount_cents": ante_cents}], separators=(",", ":")),
        result_json=json.dumps(result, separators=(",", ":")),
    )
    db.add(game_round)
    db.flush()
    response = holdem_round_response(game_round, user, transaction)
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(user)
    db.refresh(game_round)
    db.refresh(transaction)
    return response


@router.get("/holdem/texas-holdem/active", response_model=HoldemRoundResponse | None)
@limiter.limit("60/minute")
def texas_holdem_active(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HoldemRoundResponse | None:
    user = db.merge(current_user)
    round_item = active_holdem_round(db, user.id)
    if not round_item:
        return None
    return holdem_round_response(round_item, user, transaction_for_round(db, round_result(round_item)))


@router.get("/holdem/texas-holdem/rounds/{round_id}", response_model=HoldemRoundResponse)
@limiter.limit("60/minute")
def texas_holdem_round(
    request: Request,
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HoldemRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != HOLDEM_GAME_ID:
        raise holdem_error("err_holdem_round_not_found", status.HTTP_404_NOT_FOUND)
    return holdem_round_response(round_item, user, transaction_for_round(db, round_result(round_item)))


@router.post("/holdem/texas-holdem/rounds/{round_id}/decision", response_model=HoldemRoundResponse)
@limiter.limit("45/minute")
def texas_holdem_decision(
    request: Request,
    round_id: int,
    payload: HoldemDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HoldemRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != HOLDEM_GAME_ID:
        raise holdem_error("err_holdem_round_not_found", status.HTTP_404_NOT_FOUND)
    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload={"round_id": round_id, **payload.model_dump(mode="json")},
    )
    if idem.replay_response is not None:
        return HoldemRoundResponse.model_validate(idem.replay_response)
    if round_item.status != "active":
        raise holdem_error("err_holdem_round_settled", status.HTTP_409_CONFLICT)

    action = payload.action.strip().lower()
    if action == "fold":
        transaction = settle_holdem_fold(db, round_item=round_item, user=user, request=request)
    elif action == "call":
        transaction = settle_holdem_call(db, round_item=round_item, user=user, request=request)
    else:
        raise holdem_error("err_holdem_action_invalid")

    response = holdem_round_response(round_item, user, transaction)
    complete_idempotency(db, idem, response, transaction_id=transaction.id if transaction else None)
    db.commit()
    db.refresh(user)
    db.refresh(round_item)
    if transaction:
        db.refresh(transaction)
    return response


def active_survival_round(db: Session, user_id: int) -> GameRound | None:
    return db.scalar(
        select(GameRound)
        .where(
            GameRound.user_id == user_id,
            GameRound.game_id == SURVIVAL_GAME_ID,
            GameRound.status == "active",
        )
        .order_by(GameRound.id.desc())
        .limit(1)
    )


def survival_deadline(result: dict) -> datetime | None:
    raw = result.get("deadline_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def recent_survival_scenario_ids(db: Session, user_id: int) -> list[str]:
    rounds = db.scalars(
        select(GameRound)
        .where(GameRound.user_id == user_id, GameRound.game_id == SURVIVAL_GAME_ID)
        .order_by(GameRound.id.desc())
        .limit(12)
    ).all()
    recent_tokens: list[str] = []
    for round_item in rounds:
        result = round_result(round_item)
        for selection in result.get("selections") or []:
            scenario_id = str(selection.get("scenario_id") or "")
            profile_id = str(selection.get("profile_id") or "")
            for token in (
                scenario_id,
                f"{scenario_id}::{profile_id}" if scenario_id and profile_id else "",
            ):
                if token and token not in recent_tokens:
                    recent_tokens.append(token)
                if len(recent_tokens) >= SURVIVAL_RECENT_SCENARIO_LIMIT:
                    return recent_tokens
    return recent_tokens


def survival_round_response(
    round_item: GameRound,
    user: User,
    transaction: Transaction | None,
    lang: str,
) -> SurvivalRoundResponse:
    result = round_result(round_item)
    lang = normalize_lang(lang)
    stage_index = max(0, min(int(result.get("stage_index") or 0), SURVIVAL_TOTAL_STAGES - 1))
    selections = result.get("selections") or []
    selection = selections[stage_index] if stage_index < len(selections) else None
    phase = str(result.get("phase") or ("completed" if round_item.status == "completed" else round_item.status))
    selected_choice_id = result.get("selected_choice_id")
    explanation = None
    revealed_choice_id = None
    if selection and phase not in {"briefing", "awaiting_choice"}:
        revealed_choice_id = correct_choice_id(selection)
        if selected_choice_id:
            explanation = choice_explanation(
                selection,
                str(selected_choice_id),
                lang,
                correct=bool(result.get("last_choice_correct")),
            )
        elif result.get("outcome") == "timeout":
            explanation = (
                "Время истекло. Протокол не считает молчание стратегией выживания."
                if lang == "ru"
                else "Time expired. The protocol does not classify silence as a survival strategy."
            )
    category = category_public(str(result.get("category_key") or ""), lang)
    question = public_question(selection, lang) if selection else None
    if question is not None and phase == "briefing":
        question["choices"] = []
    if (
        question is not None
        and bool(result.get("last_choice_correct"))
        and phase in {"resolved", "completed"}
    ):
        resolved_values = resolution_parameter_values(selection, lang)
        for parameter in question["parameters"]:
            parameter["resolved_value"] = resolved_values.get(str(parameter["key"]))
    return SurvivalRoundResponse(
        round_id=round_item.id,
        status=round_item.status,
        phase=phase,
        category_key=category["key"],
        category_label=category["label"],
        cause=category["cause"],
        stage=stage_index + 1,
        total_stages=SURVIVAL_TOTAL_STAGES,
        deadline_at=survival_deadline(result) if phase == "awaiting_choice" else None,
        question=question,
        selected_choice_id=str(selected_choice_id) if selected_choice_id else None,
        correct_choice_id=revealed_choice_id,
        explanation=explanation,
        outcome=result.get("outcome"),
        final_multiplier=survival_multiplier_amount(),
        potential_win_cents=survival_payout_cents(round_item.total_bet_cents),
        total_bet_cents=round_item.total_bet_cents,
        total_win_cents=round_item.total_win_cents,
        net_cents=round_item.net_cents,
        started_at=round_item.created_at,
        settled_at=round_item.settled_at,
        wallet=wallet_response(user),
        transaction=TransactionPublic.model_validate(transaction) if transaction else None,
    )


def settle_survival_loss(
    db: Session,
    *,
    round_item: GameRound,
    user: User,
    result: dict,
    outcome: str,
    action: str,
    request: Request | None,
) -> Transaction | None:
    transaction = transaction_for_round(db, result)
    now = datetime.now(UTC)
    before_balance = user.balance_cents
    stage_index = int(result.get("stage_index") or 0)
    result.update(
        {
            "phase": "lost",
            "deadline_at": None,
            "outcome": outcome,
            "settled_at": now.isoformat(),
            "summary": {
                "status": outcome,
                "category": result.get("category_key"),
                "survived": stage_index,
                "total_stages": SURVIVAL_TOTAL_STAGES,
            },
        }
    )
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(games_played=User.games_played + 1)
        .execution_options(synchronize_session=False)
    )
    round_item.status = "lost"
    round_item.total_win_cents = 0
    round_item.net_cents = -round_item.total_bet_cents
    round_item.settled_at = now
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = -round_item.total_bet_cents
        db.add(transaction)
    db.add(round_item)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action=action,
        actor_user=user,
        target_user=user,
        amount_cents=-round_item.total_bet_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": SURVIVAL_GAME_ID,
            "method_id": SURVIVAL_METHOD_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "stage": stage_index + 1,
            "scenario_id": (result.get("selections") or [{}])[stage_index].get("scenario_id"),
            "outcome": outcome,
        },
        request=request,
    )
    return transaction


def settle_survival_win(
    db: Session,
    *,
    round_item: GameRound,
    user: User,
    result: dict,
    request: Request | None,
) -> Transaction | None:
    transaction = transaction_for_round(db, result)
    now = datetime.now(UTC)
    total_win_cents = survival_payout_cents(round_item.total_bet_cents)
    net_cents = total_win_cents - round_item.total_bet_cents
    before_balance = user.balance_cents
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            balance_cents=User.balance_cents + total_win_cents,
            games_played=User.games_played + 1,
            total_won_cents=User.total_won_cents + net_cents,
        )
        .execution_options(synchronize_session=False)
    )
    result.update(
        {
            "phase": "completed",
            "deadline_at": None,
            "outcome": "survived",
            "settled_at": now.isoformat(),
            "summary": {
                "status": "survived",
                "category": result.get("category_key"),
                "survived": SURVIVAL_TOTAL_STAGES,
                "total_stages": SURVIVAL_TOTAL_STAGES,
                "multiplier_cents": SURVIVAL_PAYOUT_MULTIPLIER_CENTS,
                "net_cents": net_cents,
            },
        }
    )
    round_item.status = "completed"
    round_item.total_win_cents = total_win_cents
    round_item.net_cents = net_cents
    round_item.settled_at = now
    write_round_result(round_item, result)
    if transaction:
        transaction.status = "completed"
        transaction.amount_cents = net_cents
        db.add(transaction)
    db.add(round_item)
    db.flush()
    db.refresh(user)
    add_audit_log(
        db,
        action="game.survival.completed",
        actor_user=user,
        target_user=user,
        amount_cents=total_win_cents,
        before_balance_cents=before_balance,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": SURVIVAL_GAME_ID,
            "method_id": SURVIVAL_METHOD_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "total_bet_cents": round_item.total_bet_cents,
            "total_win_cents": total_win_cents,
            "net_cents": net_cents,
            "multiplier_cents": SURVIVAL_PAYOUT_MULTIPLIER_CENTS,
        },
        request=request,
    )
    return transaction


def settle_survival_timeout_if_due(
    db: Session,
    *,
    round_item: GameRound,
    user: User,
    request: Request | None,
    require_due: bool = False,
) -> Transaction | None:
    result = round_result(round_item)
    deadline = survival_deadline(result)
    due = (
        round_item.status == "active"
        and result.get("phase") == "awaiting_choice"
        and deadline is not None
        and datetime.now(UTC) >= deadline
    )
    if not due:
        if require_due:
            raise survival_error("err_survival_timeout_not_due", status.HTTP_409_CONFLICT)
        return None
    claim_active_round(db, round_item, survival_error("err_survival_round_settled", status.HTTP_409_CONFLICT))
    return settle_survival_loss(
        db,
        round_item=round_item,
        user=user,
        result=result,
        outcome="timeout",
        action="game.survival.timeout",
        request=request,
    )


@router.post(
    "/survival/arctic-protocol/start",
    response_model=SurvivalRoundResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
def arctic_protocol_start(
    request: Request,
    payload: SurvivalStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SurvivalRoundResponse:
    bet_cents = amount_to_cents(payload.bet)
    if not is_allowed_manager_bet(db, current_user, SURVIVAL_GAME_ID, bet_cents, ALLOWED_SURVIVAL_BET_CENTS):
        raise survival_error("err_survival_bet_invalid")
    lang = normalize_lang(payload.lang)
    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return SurvivalRoundResponse.model_validate(idem.replay_response)

    user = db.merge(current_user)
    active_round = active_survival_round(db, user.id)
    if active_round:
        settle_survival_timeout_if_due(db, round_item=active_round, user=user, request=request)
        if active_round.status == "active":
            raise survival_error("err_survival_active_round", status.HTTP_409_CONFLICT)

    plan = create_round_plan(recent_ids=recent_survival_scenario_ids(db, user.id))
    user, transaction, _, _ = reserve_bet(
        db,
        user=user,
        amount_cents=bet_cents,
        game_id=SURVIVAL_GAME_ID,
        method_id=SURVIVAL_METHOD_ID,
        title=SURVIVAL_TITLE,
        title_key=SURVIVAL_TITLE_KEY,
        action="game.survival.start",
        balance_error_code="err_survival_balance",
        metadata={"method_id": SURVIVAL_METHOD_ID, "idempotency_key": idem.key_hash},
        request=request,
    )
    result = {
        **plan,
        "phase": "briefing",
        "stage_index": 0,
        "deadline_at": None,
        "decisions": [],
        "selected_choice_id": None,
        "last_choice_correct": None,
        "outcome": None,
        "transaction_id": transaction.id,
        "summary": {
            "status": "active",
            "category": plan["category_key"],
            "survived": 0,
            "total_stages": SURVIVAL_TOTAL_STAGES,
        },
    }
    game_round = GameRound(
        user_id=user.id,
        game_id=SURVIVAL_GAME_ID,
        result_number=None,
        result_color=None,
        total_bet_cents=bet_cents,
        total_win_cents=0,
        net_cents=-bet_cents,
        status="active",
        bets_json=json.dumps([{"type": "protocol", "amount_cents": bet_cents}], separators=(",", ":")),
        result_json=json.dumps(result, separators=(",", ":")),
    )
    db.add(game_round)
    db.flush()
    response = survival_round_response(game_round, user, transaction, lang)
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(user)
    db.refresh(game_round)
    db.refresh(transaction)
    return response


@router.get("/survival/arctic-protocol/active", response_model=SurvivalRoundResponse | None)
@limiter.limit("60/minute")
def arctic_protocol_active(
    request: Request,
    lang: str = "ru",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SurvivalRoundResponse | None:
    user = db.merge(current_user)
    round_item = active_survival_round(db, user.id)
    if not round_item:
        return None
    transaction = settle_survival_timeout_if_due(db, round_item=round_item, user=user, request=request)
    result = round_result(round_item)
    transaction = transaction or transaction_for_round(db, result)
    response = survival_round_response(round_item, user, transaction, lang)
    db.commit()
    return response


@router.get("/survival/arctic-protocol/rounds/{round_id}", response_model=SurvivalRoundResponse)
@limiter.limit("60/minute")
def arctic_protocol_round(
    request: Request,
    round_id: int,
    lang: str = "ru",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SurvivalRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != SURVIVAL_GAME_ID:
        raise survival_error("err_survival_round_not_found", status.HTTP_404_NOT_FOUND)
    transaction = settle_survival_timeout_if_due(db, round_item=round_item, user=user, request=request)
    result = round_result(round_item)
    transaction = transaction or transaction_for_round(db, result)
    response = survival_round_response(round_item, user, transaction, lang)
    db.commit()
    return response


@router.post("/survival/arctic-protocol/rounds/{round_id}/ready", response_model=SurvivalRoundResponse)
@limiter.limit("45/minute")
def arctic_protocol_ready(
    request: Request,
    round_id: int,
    payload: SurvivalActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SurvivalRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != SURVIVAL_GAME_ID:
        raise survival_error("err_survival_round_not_found", status.HTTP_404_NOT_FOUND)
    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload={"round_id": round_id, "action": "ready", **payload.model_dump(mode="json")},
    )
    if idem.replay_response is not None:
        return SurvivalRoundResponse.model_validate(idem.replay_response)
    if round_item.status != "active":
        raise survival_error("err_survival_round_settled", status.HTTP_409_CONFLICT)
    result = round_result(round_item)
    if result.get("phase") != "briefing":
        raise survival_error("err_survival_ready_phase", status.HTTP_409_CONFLICT)

    claim_active_round(db, round_item, survival_error("err_survival_ready_phase", status.HTTP_409_CONFLICT))
    result.update(
        {
            "phase": "awaiting_choice",
            "deadline_at": deadline_after().isoformat(),
            "selected_choice_id": None,
            "last_choice_correct": None,
            "outcome": None,
        }
    )
    round_item.status = "active"
    write_round_result(round_item, result)
    db.add(round_item)
    transaction = transaction_for_round(db, result)
    add_audit_log(
        db,
        action="game.survival.ready",
        actor_user=user,
        target_user=user,
        amount_cents=0,
        before_balance_cents=user.balance_cents,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": SURVIVAL_GAME_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "stage": int(result.get("stage_index") or 0) + 1,
            "idempotency_key": idem.key_hash,
        },
        request=request,
    )
    db.flush()
    response = survival_round_response(round_item, user, transaction, payload.lang)
    complete_idempotency(db, idem, response, transaction_id=transaction.id if transaction else None)
    db.commit()
    return response


@router.post("/survival/arctic-protocol/rounds/{round_id}/choice", response_model=SurvivalRoundResponse)
@limiter.limit("45/minute")
def arctic_protocol_choice(
    request: Request,
    round_id: int,
    payload: SurvivalChoiceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SurvivalRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != SURVIVAL_GAME_ID:
        raise survival_error("err_survival_round_not_found", status.HTTP_404_NOT_FOUND)
    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload={"round_id": round_id, **payload.model_dump(mode="json")},
    )
    if idem.replay_response is not None:
        return SurvivalRoundResponse.model_validate(idem.replay_response)
    if round_item.status != "active":
        raise survival_error("err_survival_round_settled", status.HTTP_409_CONFLICT)

    result = round_result(round_item)
    if result.get("phase") != "awaiting_choice":
        raise survival_error("err_survival_choice_phase", status.HTTP_409_CONFLICT)
    deadline = survival_deadline(result)
    if deadline and datetime.now(UTC) >= deadline:
        claim_active_round(db, round_item, survival_error("err_survival_round_settled", status.HTTP_409_CONFLICT))
        transaction = settle_survival_loss(
            db,
            round_item=round_item,
            user=user,
            result=result,
            outcome="timeout",
            action="game.survival.timeout",
            request=request,
        )
    else:
        choice_id = payload.choice_id.strip().lower()
        stage_index = int(result.get("stage_index") or 0)
        selections = result.get("selections") or []
        if choice_id not in {"a", "b", "c"} or stage_index >= len(selections):
            raise survival_error("err_survival_choice_invalid")
        selection = selections[stage_index]
        is_correct = evaluate_choice(selection, choice_id)
        claim_active_round(db, round_item, survival_error("err_survival_choice_phase", status.HTTP_409_CONFLICT))
        result["selected_choice_id"] = choice_id
        result["last_choice_correct"] = is_correct
        result["deadline_at"] = None
        result.setdefault("decisions", []).append(
            {
                "stage": stage_index + 1,
                "scenario_id": selection["scenario_id"],
                "profile_id": selection["profile_id"],
                "choice_id": choice_id,
                "correct": is_correct,
                "answered_at": datetime.now(UTC).isoformat(),
            }
        )
        add_audit_log(
            db,
            action="game.survival.choice",
            actor_user=user,
            target_user=user,
            amount_cents=0,
            before_balance_cents=user.balance_cents,
            after_balance_cents=user.balance_cents,
            metadata={
                "game_id": SURVIVAL_GAME_ID,
                "round_id": round_item.id,
                "transaction_id": result.get("transaction_id"),
                "stage": stage_index + 1,
                "scenario_id": selection["scenario_id"],
                "correct": is_correct,
                "idempotency_key": idem.key_hash,
            },
            request=request,
        )
        if not is_correct:
            transaction = settle_survival_loss(
                db,
                round_item=round_item,
                user=user,
                result=result,
                outcome="wrong_choice",
                action="game.survival.lost",
                request=request,
            )
        elif stage_index + 1 >= SURVIVAL_TOTAL_STAGES:
            transaction = settle_survival_win(
                db,
                round_item=round_item,
                user=user,
                result=result,
                request=request,
            )
        else:
            result["phase"] = "resolved"
            result["outcome"] = "correct"
            result["summary"] = {
                "status": "active",
                "category": result.get("category_key"),
                "survived": stage_index + 1,
                "total_stages": SURVIVAL_TOTAL_STAGES,
            }
            round_item.status = "active"
            write_round_result(round_item, result)
            db.add(round_item)
            transaction = transaction_for_round(db, result)

    db.flush()
    response = survival_round_response(round_item, user, transaction, payload.lang)
    complete_idempotency(db, idem, response, transaction_id=transaction.id if transaction else None)
    db.commit()
    return response


@router.post("/survival/arctic-protocol/rounds/{round_id}/continue", response_model=SurvivalRoundResponse)
@limiter.limit("45/minute")
def arctic_protocol_continue(
    request: Request,
    round_id: int,
    payload: SurvivalActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SurvivalRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != SURVIVAL_GAME_ID:
        raise survival_error("err_survival_round_not_found", status.HTTP_404_NOT_FOUND)
    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload={"round_id": round_id, "action": "continue", **payload.model_dump(mode="json")},
    )
    if idem.replay_response is not None:
        return SurvivalRoundResponse.model_validate(idem.replay_response)
    if round_item.status != "active":
        raise survival_error("err_survival_round_settled", status.HTTP_409_CONFLICT)
    result = round_result(round_item)
    if result.get("phase") != "resolved":
        raise survival_error("err_survival_continue_phase", status.HTTP_409_CONFLICT)
    claim_active_round(db, round_item, survival_error("err_survival_continue_phase", status.HTTP_409_CONFLICT))
    next_stage = int(result.get("stage_index") or 0) + 1
    if next_stage >= SURVIVAL_TOTAL_STAGES:
        raise survival_error("err_survival_round_settled", status.HTTP_409_CONFLICT)
    result.update(
        {
            "phase": "briefing",
            "stage_index": next_stage,
            "deadline_at": None,
            "selected_choice_id": None,
            "last_choice_correct": None,
            "outcome": None,
        }
    )
    round_item.status = "active"
    write_round_result(round_item, result)
    db.add(round_item)
    transaction = transaction_for_round(db, result)
    add_audit_log(
        db,
        action="game.survival.continue",
        actor_user=user,
        target_user=user,
        amount_cents=0,
        before_balance_cents=user.balance_cents,
        after_balance_cents=user.balance_cents,
        metadata={
            "game_id": SURVIVAL_GAME_ID,
            "round_id": round_item.id,
            "transaction_id": transaction.id if transaction else None,
            "stage": next_stage + 1,
            "idempotency_key": idem.key_hash,
        },
        request=request,
    )
    db.flush()
    response = survival_round_response(round_item, user, transaction, payload.lang)
    complete_idempotency(db, idem, response, transaction_id=transaction.id if transaction else None)
    db.commit()
    return response


@router.post("/survival/arctic-protocol/rounds/{round_id}/timeout", response_model=SurvivalRoundResponse)
@limiter.limit("30/minute")
def arctic_protocol_timeout(
    request: Request,
    round_id: int,
    payload: SurvivalActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SurvivalRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != SURVIVAL_GAME_ID:
        raise survival_error("err_survival_round_not_found", status.HTTP_404_NOT_FOUND)
    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload={"round_id": round_id, "action": "timeout", **payload.model_dump(mode="json")},
    )
    if idem.replay_response is not None:
        return SurvivalRoundResponse.model_validate(idem.replay_response)
    if round_item.status != "active":
        raise survival_error("err_survival_round_settled", status.HTTP_409_CONFLICT)
    transaction = settle_survival_timeout_if_due(
        db,
        round_item=round_item,
        user=user,
        request=request,
        require_due=True,
    )
    response = survival_round_response(round_item, user, transaction, payload.lang)
    complete_idempotency(db, idem, response, transaction_id=transaction.id if transaction else None)
    db.commit()
    return response


@router.post("/plinko/midnight-vault/drop", response_model=PlinkoDropResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("45/minute")
def midnight_vault_drop(
    request: Request,
    payload: PlinkoDropRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlinkoDropResponse:
    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return PlinkoDropResponse.model_validate(idem.replay_response)

    bet_cents = amount_to_cents(payload.bet)
    mode = payload.mode.strip().lower()
    risk = payload.risk.strip().lower()
    rows = int(payload.rows)
    balls = int(payload.balls)

    if not is_allowed_manager_bet(db, current_user, PLINKO_GAME_ID, bet_cents, ALLOWED_PLINKO_BET_CENTS):
        raise plinko_error("err_plinko_bet_invalid")

    try:
        result = drop_midnight_vault(bet_cents, mode, risk, rows, balls, validate_bet=False)
    except ValueError as exc:
        error_map = {
            "invalid_bet": "err_plinko_bet_invalid",
            "invalid_mode": "err_plinko_mode_invalid",
            "invalid_risk": "err_plinko_risk_invalid",
            "invalid_rows": "err_plinko_rows_invalid",
            "invalid_balls": "err_plinko_balls_invalid",
        }
        raise plinko_error(error_map.get(str(exc), "err_plinko_invalid")) from None

    try:
        current_user, transaction = apply_instant_game_result(
            db,
            user=current_user,
            game_id=PLINKO_GAME_ID,
            method_id=PLINKO_METHOD_ID,
            title=PLINKO_TITLE,
            title_key=PLINKO_TITLE_KEY,
            total_bet_cents=result["total_bet_cents"],
            total_win_cents=result["total_win_cents"],
            net_cents=result["net_cents"],
            action="game.plinko.drop",
            balance_error_code="err_plinko_balance",
            metadata={
                "method_id": PLINKO_METHOD_ID,
                "mode": result["mode"],
                "risk": result["risk"],
                "rows": result["rows"],
                "ball_count": result["ball_count"],
                "idempotency_key": idem.key_hash,
            },
            request=request,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "err_plinko_balance"}
        if detail.get("code") == "err_plinko_balance":
            raise plinko_error("err_plinko_balance") from None
        raise

    game_round = GameRound(
        user_id=current_user.id,
        game_id=PLINKO_GAME_ID,
        result_number=None,
        result_color=None,
        total_bet_cents=result["total_bet_cents"],
        total_win_cents=result["total_win_cents"],
        net_cents=result["net_cents"],
        bets_json=json.dumps(
            [
                {
                    "type": "drop",
                    "amount_cents": bet_cents,
                    "mode": result["mode"],
                    "risk": result["risk"],
                    "rows": result["rows"],
                    "balls": result["ball_count"],
                }
            ],
            separators=(",", ":"),
        ),
        result_json=json.dumps(
            {
                "mode": result["mode"],
                "risk": result["risk"],
                "rows": result["rows"],
                "ball_count": result["ball_count"],
                "pockets": result["pockets"],
                "balls": result["balls"],
                "summary": result["summary"],
            },
            separators=(",", ":"),
        ),
    )
    db.add(current_user)
    db.add(game_round)
    db.flush()
    response = PlinkoDropResponse(
        round_id=game_round.id,
        mode=result["mode"],
        risk=result["risk"],
        rows=result["rows"],
        ball_count=result["ball_count"],
        pockets=result["pockets"],
        balls=[PlinkoBallResult(**ball) for ball in result["balls"]],
        total_bet_cents=result["total_bet_cents"],
        total_win_cents=result["total_win_cents"],
        net_cents=result["net_cents"],
        wallet=wallet_response(current_user),
        transaction=TransactionPublic.model_validate(transaction),
    )
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(current_user)
    db.refresh(game_round)
    db.refresh(transaction)

    return response


@router.post("/slots/lucky-bamboo/spin", response_model=SlotSpinResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("45/minute")
def lucky_bamboo_spin(
    request: Request,
    payload: SlotSpinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlotSpinResponse:
    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return SlotSpinResponse.model_validate(idem.replay_response)

    bet_cents = amount_to_cents(payload.bet)
    if not is_allowed_manager_bet(db, current_user, SLOT_GAME_ID, bet_cents, ALLOWED_BET_CENTS):
        raise slot_error("err_slot_bet_invalid")

    result = spin_lucky_bamboo(bet_cents, validate_bet=False)
    try:
        current_user, transaction = apply_instant_game_result(
            db,
            user=current_user,
            game_id=SLOT_GAME_ID,
            method_id=SLOT_METHOD_ID,
            title=SLOT_TITLE,
            title_key=SLOT_TITLE_KEY,
            total_bet_cents=result["total_bet_cents"],
            total_win_cents=result["total_win_cents"],
            net_cents=result["net_cents"],
            action="game.slots.spin",
            balance_error_code="err_slot_balance",
            metadata={
                "winning_lines": len(result["winning_lines"]),
                "method_id": SLOT_METHOD_ID,
                "idempotency_key": idem.key_hash,
            },
            request=request,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "err_slot_balance"}
        if detail.get("code") == "err_slot_balance":
            raise slot_error("err_slot_balance") from None
        raise

    game_round = GameRound(
        user_id=current_user.id,
        game_id=SLOT_GAME_ID,
        result_number=None,
        result_color=None,
        total_bet_cents=result["total_bet_cents"],
        total_win_cents=result["total_win_cents"],
        net_cents=result["net_cents"],
        bets_json=json.dumps([{"type": "spin", "amount_cents": bet_cents}], separators=(",", ":")),
        result_json=json.dumps(
            {
                "grid": result["grid"],
                "winning_lines": result["winning_lines"],
                "summary": result["summary"],
            },
            separators=(",", ":"),
        ),
    )
    db.add(current_user)
    db.add(game_round)
    db.flush()
    response = SlotSpinResponse(
        round_id=game_round.id,
        grid=result["grid"],
        winning_lines=[SlotWinningLine(**line) for line in result["winning_lines"]],
        total_bet_cents=result["total_bet_cents"],
        total_win_cents=result["total_win_cents"],
        net_cents=result["net_cents"],
        wallet=wallet_response(current_user),
        transaction=TransactionPublic.model_validate(transaction),
    )
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(current_user)
    db.refresh(game_round)
    db.refresh(transaction)

    return response


@router.post("/crash/dragons-fortune/start", response_model=CrashRoundResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("40/minute")
def dragons_fortune_start(
    request: Request,
    payload: CrashStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CrashRoundResponse:
    bet_cents = amount_to_cents(payload.bet)
    if not is_allowed_manager_bet(db, current_user, CRASH_GAME_ID, bet_cents, ALLOWED_CRASH_BET_CENTS):
        raise crash_error("err_crash_bet_invalid")

    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return CrashRoundResponse.model_validate(idem.replay_response)

    user = db.merge(current_user)
    active = active_crash_round(db, user.id)
    if active:
        if crash_multiplier_reached(active):
            settle_crash_loss(db, round_item=active, user=user, request=request)
            db.flush()
        else:
            raise crash_error("err_crash_active_round", status.HTTP_409_CONFLICT)

    started_at = utc_now()
    crash_multiplier_cents = generate_crash_multiplier_cents()
    user, transaction, before_balance, earned_vip_points = reserve_bet(
        db,
        user=user,
        amount_cents=bet_cents,
        game_id=CRASH_GAME_ID,
        method_id=CRASH_METHOD_ID,
        title=CRASH_TITLE,
        title_key=CRASH_TITLE_KEY,
        action="game.crash.start",
        balance_error_code="err_crash_balance",
        metadata={"idempotency_key": idem.key_hash},
        request=request,
    )

    result = {
        "started_at": started_at.isoformat(),
        "crash_multiplier_cents": crash_multiplier_cents,
        "crash_after_seconds": round(seconds_until_multiplier(crash_multiplier_cents), 3),
        "transaction_id": transaction.id,
        "summary": {"status": "active"},
    }
    game_round = GameRound(
        user_id=user.id,
        game_id=CRASH_GAME_ID,
        result_number=None,
        result_color=None,
        total_bet_cents=bet_cents,
        total_win_cents=0,
        net_cents=-bet_cents,
        status="active",
        bets_json=json.dumps([{"type": "crash", "amount_cents": bet_cents}], separators=(",", ":")),
        result_json=json.dumps(result, separators=(",", ":")),
        created_at=started_at,
    )
    db.add(game_round)
    db.flush()

    response = crash_round_response(game_round, user, transaction)
    complete_idempotency(db, idem, response, transaction_id=transaction.id)
    db.commit()
    db.refresh(user)
    db.refresh(game_round)
    db.refresh(transaction)
    return response


@router.get("/crash/dragons-fortune/rounds/{round_id}", response_model=CrashRoundResponse)
@limiter.limit("120/minute")
def dragons_fortune_round_status(
    request: Request,
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CrashRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != CRASH_GAME_ID:
        raise crash_error("err_crash_round_not_found", status.HTTP_404_NOT_FOUND)

    transaction = transaction_for_round(db, round_result(round_item))
    if round_item.status == "active" and crash_multiplier_reached(round_item):
        transaction = settle_crash_loss(db, round_item=round_item, user=user, request=request)
        db.commit()
        db.refresh(user)
        db.refresh(round_item)
        if transaction:
            db.refresh(transaction)

    return crash_round_response(round_item, user, transaction)


@router.post("/crash/dragons-fortune/rounds/{round_id}/cashout", response_model=CrashRoundResponse)
@limiter.limit("60/minute")
def dragons_fortune_cashout(
    request: Request,
    round_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CrashRoundResponse:
    user = db.merge(current_user)
    round_item = db.get(GameRound, round_id)
    if not round_item or round_item.user_id != user.id or round_item.game_id != CRASH_GAME_ID:
        raise crash_error("err_crash_round_not_found", status.HTTP_404_NOT_FOUND)
    idem = begin_idempotency(
        db,
        user=user,
        request=request,
        payload={"round_id": round_id},
    )
    if idem.replay_response is not None:
        return CrashRoundResponse.model_validate(idem.replay_response)
    if round_item.status != "active":
        raise crash_error("err_crash_round_settled", status.HTTP_409_CONFLICT)

    result = round_result(round_item)
    started_at = started_at_for_round(round_item, result)
    crash_multiplier_cents = int(result.get("crash_multiplier_cents") or 100)
    cashout_multiplier_cents = current_multiplier_cents(started_at)

    if cashout_multiplier_cents < CASHOUT_MIN_MULTIPLIER_CENTS:
        raise crash_error("err_crash_cashout_locked", status.HTTP_409_CONFLICT)

    if cashout_multiplier_cents >= crash_multiplier_cents:
        transaction = settle_crash_loss(db, round_item=round_item, user=user, request=request)
    else:
        transaction = settle_crash_cashout(
            db,
            round_item=round_item,
            user=user,
            cashout_multiplier_cents=cashout_multiplier_cents,
            request=request,
        )
    response = crash_round_response(round_item, user, transaction, reveal_crash=True)
    complete_idempotency(db, idem, response, transaction_id=transaction.id if transaction else None)
    db.commit()
    db.refresh(user)
    db.refresh(round_item)
    if transaction:
        db.refresh(transaction)
    return response
