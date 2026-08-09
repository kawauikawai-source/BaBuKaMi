from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.errors import api_error
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.deps import get_current_user
from app.models import ManagerAction, ManagerMessage, ManagerTicket, User
from app.schemas import (
    ManagerActionConfirmResponse,
    ManagerMessagePublic,
    ManagerMessageRequest,
    ManagerMessageResult,
    ManagerStateResponse,
    ManagerTicketPublic,
)
from app.services.audit import add_audit_log
from app.services.idempotency import begin_idempotency, complete_idempotency
from app.services.manager import (
    action_public,
    add_message,
    build_reply,
    execute_action,
    manager_state,
    message_public,
    require_manager_access,
    ticket_public,
    utc_now,
)


router = APIRouter(prefix="/manager", tags=["manager"])
settings = get_settings()


@router.get("", response_model=ManagerStateResponse)
def get_manager_state(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ManagerStateResponse:
    require_manager_access(current_user)
    state = manager_state(db, current_user)
    db.commit()
    return state


@router.get("/messages", response_model=list[ManagerMessagePublic])
def get_manager_messages(
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ManagerMessagePublic]:
    require_manager_access(current_user)
    query = select(ManagerMessage).where(ManagerMessage.user_id == current_user.id)
    if before_id:
        query = query.where(ManagerMessage.id < before_id)
    messages = list(db.scalars(query.order_by(ManagerMessage.id.desc()).limit(limit)).all())
    for item in messages:
        if item.role == "admin" and item.read_at is None:
            item.read_at = utc_now()
            db.add(item)
    db.commit()
    return [message_public(item) for item in reversed(messages)]


@router.post("/messages", response_model=ManagerMessageResult)
@limiter.limit(settings.rate_limit_manager_messages)
def post_manager_message(
    payload: ManagerMessageRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ManagerMessageResult:
    require_manager_access(current_user)
    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload=payload.model_dump(mode="json"),
    )
    if idem.replay_response is not None:
        return ManagerMessageResult.model_validate(idem.replay_response)
    text = payload.text.strip()
    user_message = add_message(
        db,
        current_user,
        role="user",
        language=payload.language,
        intent=payload.intent or "general",
        text=text,
    )
    intent, reply, action, ticket = build_reply(
        db,
        current_user,
        text=text,
        language=payload.language,
        explicit_intent=payload.intent,
        payload=payload.payload,
    )
    operator_message = add_message(
        db,
        current_user,
        role="operator",
        language=payload.language,
        intent=intent,
        text=reply,
        metadata={
            "action_id": action.id if action else None,
            "action": action_public(action).model_dump(mode="json") if action else None,
            "ticket_id": ticket.id if ticket else None,
        },
    )
    add_audit_log(
        db,
        action="manager.message",
        actor_user=current_user,
        target_user=current_user,
        metadata={"intent": intent, "action_id": action.id if action else None, "ticket_id": ticket.id if ticket else None},
        request=request,
    )
    if ticket:
        add_audit_log(
            db,
            action="manager.ticket.create",
            actor_user=current_user,
            target_user=current_user,
            metadata={"ticket_id": ticket.id, "category": ticket.category},
            request=request,
        )
    response = ManagerMessageResult(
        user_message=message_public(user_message),
        operator_message=message_public(operator_message),
        action=action_public(action) if action else None,
        ticket=ticket_public(ticket, current_user) if ticket else None,
    )
    complete_idempotency(db, idem, response)
    db.commit()
    return response


@router.post("/actions/{action_id}/confirm", response_model=ManagerActionConfirmResponse)
@limiter.limit(settings.rate_limit_manager_actions)
def confirm_manager_action(
    action_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ManagerActionConfirmResponse:
    require_manager_access(current_user)
    idem = begin_idempotency(
        db,
        user=current_user,
        request=request,
        payload={"action_id": action_id, "action": "confirm"},
    )
    if idem.replay_response is not None:
        return ManagerActionConfirmResponse.model_validate(idem.replay_response)
    action = db.scalar(
        select(ManagerAction)
        .where(ManagerAction.id == action_id, ManagerAction.user_id == current_user.id)
        .with_for_update()
    )
    if not action:
        raise api_error("err_manager_action_not_found", status_code=404)
    details = execute_action(db, current_user, action)
    language = "ru"
    latest = db.scalar(
        select(ManagerMessage)
        .where(ManagerMessage.user_id == current_user.id)
        .order_by(ManagerMessage.id.desc())
        .limit(1)
    )
    if latest:
        language = latest.language
    text = "Действие выполнено. Кавай не вмешался, что заметно ускорило процедуру." if language == "ru" else "Action completed. Kawaui did not interfere, which noticeably accelerated the process."
    operator_message = add_message(db, current_user, role="operator", language=language, intent="action_completed", text=text, metadata={"action_id": action.id})
    audit_action = "manager.bet_preset.update" if action.kind.startswith("bet_") else "manager.action"
    add_audit_log(
        db,
        action=audit_action,
        actor_user=current_user,
        target_user=current_user,
        metadata={"manager_action_id": action.id, "kind": action.kind, **details},
        request=request,
    )
    response = ManagerActionConfirmResponse(
        action=action_public(action),
        operator_message=message_public(operator_message),
        state=manager_state(db, current_user),
    )
    complete_idempotency(db, idem, response)
    db.commit()
    return response


@router.get("/tickets", response_model=list[ManagerTicketPublic])
def get_manager_tickets(
    limit: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ManagerTicketPublic]:
    require_manager_access(current_user)
    tickets = list(
        db.scalars(
            select(ManagerTicket)
            .where(ManagerTicket.user_id == current_user.id)
            .order_by(ManagerTicket.created_at.desc(), ManagerTicket.id.desc())
            .limit(limit)
        ).all()
    )
    return [ticket_public(item, current_user) for item in tickets]
