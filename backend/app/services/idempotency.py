from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.models import IdempotencyKey, User


IDEMPOTENCY_TTL_HOURS = 24


@dataclass
class IdempotencyContext:
    row: IdempotencyKey | None = None
    replay_response: dict[str, Any] | None = None
    key_hash: str = ""

    @property
    def enabled(self) -> bool:
        return self.row is not None


def canonical_json(value: Any) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"), default=str)


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_payload_hash(payload: Any) -> str:
    return hash_value(canonical_json(payload))


def idempotency_scope(request: Request, fallback: str = "") -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", "") if route else ""
    return f"{request.method.upper()} {route_path or fallback or request.url.path}"


def begin_idempotency(
    db: Session,
    *,
    user: User,
    request: Request,
    payload: Any,
    scope: str | None = None,
) -> IdempotencyContext:
    raw_key = (request.headers.get("Idempotency-Key") or "").strip()
    if not raw_key:
        return IdempotencyContext()
    if len(raw_key) > 256:
        raise api_error("err_idempotency_key_invalid")

    key_hash = hash_value(raw_key)
    request_hash = request_payload_hash(payload)
    scope_value = scope or idempotency_scope(request)
    now = datetime.now(UTC)

    row = db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user.id,
            IdempotencyKey.key == key_hash,
            IdempotencyKey.scope == scope_value,
        )
    )
    if row is not None:
        if row.request_hash != request_hash:
            raise api_error("err_idempotency_conflict", status.HTTP_409_CONFLICT)
        if row.status == "completed" and row.response_json:
            try:
                replay = json.loads(row.response_json)
            except json.JSONDecodeError:
                replay = {}
            return IdempotencyContext(row=row, replay_response=replay, key_hash=key_hash)
        raise api_error("err_request_processing", status.HTTP_409_CONFLICT)

    row = IdempotencyKey(
        user_id=user.id,
        key=key_hash,
        scope=scope_value,
        request_hash=request_hash,
        status="processing",
        expires_at=now + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return begin_idempotency(db, user=user, request=request, payload=payload, scope=scope_value)
    return IdempotencyContext(row=row, key_hash=key_hash)


def response_to_jsonable(response: Any) -> dict[str, Any]:
    if isinstance(response, BaseModel):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return json.loads(canonical_json(response))
    return json.loads(canonical_json(response))


def complete_idempotency(
    db: Session,
    context: IdempotencyContext,
    response: Any,
    *,
    transaction_id: int | None = None,
) -> None:
    if not context.enabled or context.row is None:
        return
    context.row.status = "completed"
    context.row.response_json = canonical_json(response_to_jsonable(response))
    context.row.transaction_id = transaction_id
    db.add(context.row)
    db.flush()
