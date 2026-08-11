from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models import StudioTransaction, User
from app.schemas import StudioTransactionPublic, StudioWalletPublic, StudioWalletResponse
from app.services.studio import get_or_create_studio_wallet


router = APIRouter(prefix="/studio", tags=["studio"])


@router.get("/catalog")
def studio_catalog() -> dict[str, list[dict[str, str]]]:
    settings = get_settings()
    return {
        "projects": [
            {"id": "bambiku", "status": "live", "url": settings.public_base_url},
            {"id": "bukamiku", "status": "live", "url": settings.bukamiku_public_url},
            {"id": "bibukami-water", "status": "soon", "url": ""},
        ]
    }


@router.get("/wallet", response_model=StudioWalletResponse)
def studio_wallet(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StudioWalletResponse:
    user = db.merge(current_user)
    wallet = get_or_create_studio_wallet(db, user)
    recent = list(
        db.scalars(
            select(StudioTransaction)
            .where(StudioTransaction.user_id == user.id)
            .order_by(StudioTransaction.created_at.desc(), StudioTransaction.id.desc())
            .limit(5)
        ).all()
    )
    db.commit()
    return StudioWalletResponse(
        wallet=StudioWalletPublic.model_validate(wallet),
        recent_transactions=[StudioTransactionPublic.model_validate(item) for item in recent],
    )


@router.get("/transactions", response_model=list[StudioTransactionPublic])
def studio_transactions(
    transaction_type: str = Query(default="", alias="type", max_length=32),
    status_value: str = Query(default="", alias="status", max_length=24),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[StudioTransactionPublic]:
    query = select(StudioTransaction).where(StudioTransaction.user_id == current_user.id)
    if transaction_type:
        query = query.where(StudioTransaction.type == transaction_type)
    if status_value:
        query = query.where(StudioTransaction.status == status_value)
    rows = db.scalars(
        query.order_by(StudioTransaction.created_at.desc(), StudioTransaction.id.desc()).offset(offset).limit(limit)
    ).all()
    return [StudioTransactionPublic.model_validate(item) for item in rows]
