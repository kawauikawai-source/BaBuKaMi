import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def request_ip(request: Request | None) -> str:
    if not request or not request.client:
        return ""
    return request.client.host or ""


def request_user_agent(request: Request | None) -> str:
    if not request:
        return ""
    return request.headers.get("user-agent", "")[:512]


def add_audit_log(
    db: Session,
    *,
    action: str,
    actor_user: User | None = None,
    target_user: User | None = None,
    amount_cents: int | None = None,
    before_balance_cents: int | None = None,
    after_balance_cents: int | None = None,
    metadata: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        actor_user_id=actor_user.id if actor_user else None,
        target_user_id=target_user.id if target_user else None,
        action=action,
        amount_cents=amount_cents,
        before_balance_cents=before_balance_cents,
        after_balance_cents=after_balance_cents,
        metadata_json=json.dumps(metadata or {}, separators=(",", ":"), default=str),
        ip_address=request_ip(request),
        user_agent=request_user_agent(request),
    )
    db.add(audit_log)
    return audit_log
