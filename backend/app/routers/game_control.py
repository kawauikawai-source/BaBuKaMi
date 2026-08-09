from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models import GameControlSettings, User
from app.schemas import GameControlPauseRequest, GameControlResponse, GameControlSettingsUpdateRequest
from app.services.audit import add_audit_log
from app.services.game_control import as_utc, get_or_create_settings, pause_until, utc_now


router = APIRouter(prefix="/game-control", tags=["game-control"])


def response_for(settings: GameControlSettings) -> GameControlResponse:
    now = utc_now()
    paused = as_utc(settings.paused_until)
    limit = settings.daily_bet_limit_cents
    spent = int(settings.daily_bet_spent_cents or 0)
    return GameControlResponse(
        daily_bet_limit_cents=limit,
        daily_bet_spent_cents=spent,
        daily_bet_remaining_cents=None if limit is None else max(limit - spent, 0),
        reminder_minutes=settings.reminder_minutes,
        paused_until=paused,
        is_paused=bool(paused and paused > now),
        server_time=now,
    )


@router.get("", response_model=GameControlResponse)
def get_game_control(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> GameControlResponse:
    settings = get_or_create_settings(db, current_user.id)
    db.commit()
    db.refresh(settings)
    return response_for(settings)


@router.put("/settings", response_model=GameControlResponse)
def update_game_control(
    payload: GameControlSettingsUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GameControlResponse:
    settings = get_or_create_settings(db, current_user.id, lock=True)
    settings.daily_bet_limit_cents = payload.daily_bet_limit_cents
    settings.reminder_minutes = payload.reminder_minutes
    db.add(settings)
    db.flush()
    add_audit_log(db, action="game.control.update", actor_user=current_user, target_user=current_user,
                  metadata={"daily_bet_limit_cents": settings.daily_bet_limit_cents, "reminder_minutes": settings.reminder_minutes}, request=request)
    db.commit()
    db.refresh(settings)
    return response_for(settings)


@router.post("/pause", response_model=GameControlResponse)
def pause_game_control(
    payload: GameControlPauseRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GameControlResponse:
    settings = get_or_create_settings(db, current_user.id, lock=True)
    settings.paused_until = pause_until(payload.duration_minutes)
    db.add(settings)
    db.flush()
    add_audit_log(db, action="game.control.pause", actor_user=current_user, target_user=current_user,
                  metadata={"duration_minutes": payload.duration_minutes, "paused_until": settings.paused_until.isoformat()}, request=request)
    db.commit()
    db.refresh(settings)
    return response_for(settings)


@router.post("/resume", response_model=GameControlResponse)
def resume_game_control(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GameControlResponse:
    settings = get_or_create_settings(db, current_user.id, lock=True)
    settings.paused_until = None
    db.add(settings)
    db.flush()
    add_audit_log(db, action="game.control.resume", actor_user=current_user, target_user=current_user, request=request)
    db.commit()
    db.refresh(settings)
    return response_for(settings)
