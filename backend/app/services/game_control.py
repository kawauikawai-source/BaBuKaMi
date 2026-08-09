from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.models import GameControlSettings, User


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_daily_counter(settings: GameControlSettings, now: datetime | None = None) -> None:
    today = (now or utc_now()).date()
    if settings.daily_bet_date != today:
        settings.daily_bet_date = today
        settings.daily_bet_spent_cents = 0


def get_or_create_settings(db: Session, user_id: int, *, lock: bool = False) -> GameControlSettings:
    statement = select(GameControlSettings).where(GameControlSettings.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    settings = db.scalar(statement)
    if settings is None:
        settings = GameControlSettings(user_id=user_id, daily_bet_date=utc_now().date())
        db.add(settings)
        db.flush()
    normalize_daily_counter(settings)
    return settings


def consume_game_budget(db: Session, *, user: User, amount_cents: int) -> GameControlSettings:
    settings = get_or_create_settings(db, user.id, lock=True)
    now = utc_now()
    paused_until = as_utc(settings.paused_until)
    if paused_until and paused_until > now:
        raise api_error(
            "err_game_control_paused",
            status_code=409,
            meta={"paused_until": paused_until.isoformat()},
        )

    limit = settings.daily_bet_limit_cents
    next_spent = int(settings.daily_bet_spent_cents or 0) + int(amount_cents)
    if limit is not None and next_spent > limit:
        raise api_error(
            "err_game_control_daily_limit",
            status_code=409,
            amount_cents=max(limit - int(settings.daily_bet_spent_cents or 0), 0),
            meta={"limit_cents": limit, "spent_cents": settings.daily_bet_spent_cents},
        )
    settings.daily_bet_spent_cents = next_spent
    db.add(settings)
    db.flush()
    return settings


def pause_until(minutes: int) -> datetime:
    return utc_now() + timedelta(minutes=minutes)
