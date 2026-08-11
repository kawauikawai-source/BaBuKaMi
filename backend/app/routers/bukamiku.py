from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import IdentityAppSession, SoulAppraisal, User
from app.routers.identity import get_identity_session
from app.schemas import (
    SoulAppraisalPreviewPublic,
    SoulAppraisalPublic,
    SoulAppraisalRequest,
    SoulAppraisalResponse,
    StudioTransactionPublic,
    StudioWalletPublic,
)
from app.services.audit import add_audit_log
from app.services.bukamiku import calculate_appraisal, create_soul_sale, daily_soul_rate_cents, next_sale_number
from app.services.idempotency import begin_idempotency, complete_idempotency
from app.services.studio import get_or_create_studio_wallet


router = APIRouter(prefix="/apps/bukamiku", tags=["bukamiku"])


@router.get("/session")
def bukamiku_session(
    identity: tuple[IdentityAppSession, User] = Depends(get_identity_session),
    db: Session = Depends(get_db),
) -> dict:
    _, user = identity
    wallet = get_or_create_studio_wallet(db, user)
    db.commit()
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "dob": user.dob,
            "country": user.country,
        },
        "wallet": StudioWalletPublic.model_validate(wallet).model_dump(mode="json"),
    }


@router.get("/soul-rate")
def soul_rate() -> dict[str, int | str]:
    return {"date": datetime.now(UTC).date().isoformat(), "rate_cents": daily_soul_rate_cents(), "currency": "EUR"}


@router.post("/appraisals/preview", response_model=SoulAppraisalPreviewPublic)
def preview_appraisal(
    request: Request,
    payload: SoulAppraisalRequest,
    identity: tuple[IdentityAppSession, User] = Depends(get_identity_session),
    db: Session = Depends(get_db),
) -> SoulAppraisalPreviewPublic:
    _, user = identity
    sale_number = next_sale_number(db, user.id)
    values = calculate_appraisal(payload, min(sale_number, 3))
    if sale_number > 3:
        values["decay_bps"] = 0
        values["payout_cents"] = 0
    add_audit_log(
        db,
        action="bukamiku.appraisal.preview",
        actor_user=user,
        target_user=user,
        amount_cents=int(values["payout_cents"]),
        metadata={"sale_number": sale_number, "base_value_cents": values["base_value_cents"]},
        request=request,
    )
    db.commit()
    return SoulAppraisalPreviewPublic(
        daily_rate_cents=int(values["daily_rate_cents"]),
        base_value_cents=int(values["base_value_cents"]),
        next_sale_number=sale_number,
        decay_bps=int(values["decay_bps"]),
        payout_cents=int(values["payout_cents"]),
        sales_remaining=max(0, 4 - sale_number),
    )


@router.post("/appraisals", response_model=SoulAppraisalResponse, status_code=status.HTTP_201_CREATED)
def sell_soul(
    request: Request,
    payload: SoulAppraisalRequest,
    identity: tuple[IdentityAppSession, User] = Depends(get_identity_session),
    db: Session = Depends(get_db),
) -> SoulAppraisalResponse:
    _, user = identity
    idem = begin_idempotency(db, user=user, request=request, payload=payload.model_dump(mode="json"))
    if idem.replay_response is not None:
        return SoulAppraisalResponse.model_validate(idem.replay_response)
    appraisal, wallet, transaction = create_soul_sale(db, user=user, payload=payload, request=request)
    response = SoulAppraisalResponse(
        appraisal=SoulAppraisalPublic.model_validate(appraisal),
        wallet=StudioWalletPublic.model_validate(wallet),
        transaction=StudioTransactionPublic.model_validate(transaction),
    )
    complete_idempotency(db, idem, response)
    db.commit()
    return response


@router.get("/appraisals", response_model=list[SoulAppraisalPublic])
def appraisal_history(
    identity: tuple[IdentityAppSession, User] = Depends(get_identity_session),
    db: Session = Depends(get_db),
) -> list[SoulAppraisalPublic]:
    _, user = identity
    rows = db.scalars(
        select(SoulAppraisal)
        .where(SoulAppraisal.user_id == user.id)
        .order_by(SoulAppraisal.sale_number.desc())
    ).all()
    return [SoulAppraisalPublic.model_validate(item) for item in rows]
