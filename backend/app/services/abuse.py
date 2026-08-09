from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import api_error
from app.models import AbuseEvent, User


settings = get_settings()


def utc_now() -> datetime:
    return datetime.now(UTC)


def request_ip(request: Request | None) -> str:
    if not request or not request.client:
        return ""
    return request.client.host or ""


def ip_hash(request: Request | None) -> str:
    value = request_ip(request)
    if not value:
        return ""
    return hashlib.sha256(f"{settings.secret_key}:{value}".encode("utf-8")).hexdigest()


def add_abuse_event(
    db: Session,
    *,
    action: str,
    user: User | None = None,
    request: Request | None = None,
    key: str = "",
    metadata: dict[str, Any] | None = None,
) -> AbuseEvent:
    event = AbuseEvent(
        user_id=user.id if user else None,
        ip_hash=ip_hash(request),
        action=action,
        key=key[:128],
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        created_at=utc_now(),
    )
    db.add(event)
    db.flush()
    return event


def event_count(
    db: Session,
    *,
    action: str,
    user: User | None = None,
    request: Request | None = None,
    key: str = "",
    window: timedelta,
) -> int:
    since = utc_now() - window
    query = select(func.count(AbuseEvent.id)).where(AbuseEvent.action == action, AbuseEvent.created_at >= since)
    if key:
        query = query.where(AbuseEvent.key == key[:128])
    if user:
        query = query.where(AbuseEvent.user_id == user.id)
    else:
        query = query.where(AbuseEvent.ip_hash == ip_hash(request))
    return int(db.scalar(query) or 0)


def blocked_by_user_or_ip(
    db: Session,
    *,
    action: str,
    user: User | None,
    request: Request | None,
    window: timedelta,
    threshold: int,
) -> bool:
    return event_count(db, action=action, user=user, window=window, request=request) >= threshold or event_count(
        db,
        action=action,
        request=request,
        window=window,
    ) >= threshold


def enforce_promo_redeem_allowed(db: Session, *, user: User, request: Request) -> None:
    if blocked_by_user_or_ip(
        db,
        action="promo.redeem.failed",
        user=user,
        request=request,
        window=timedelta(hours=1),
        threshold=10,
    ):
        raise api_error("err_abuse_promo_blocked", status.HTTP_429_TOO_MANY_REQUESTS)


def enforce_withdraw_attempt_allowed(db: Session, *, user: User, request: Request) -> None:
    if event_count(db, action="cashier.withdraw.attempt", user=user, request=request, window=timedelta(hours=1)) >= 10:
        raise api_error("err_abuse_withdraw_blocked", status.HTTP_429_TOO_MANY_REQUESTS)


def enforce_vip_clicker_speed(db: Session, *, user: User, request: Request, tier: str) -> None:
    if event_count(
        db,
        action="vip.clicker.click",
        user=user,
        request=request,
        key=tier,
        window=timedelta(seconds=2),
    ) >= 6:
        raise api_error("err_abuse_too_fast", status.HTTP_429_TOO_MANY_REQUESTS)
