from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models import User
from app.schemas import WalletResponse


router = APIRouter(prefix="/wallet", tags=["wallet"])


def wallet_response(user: User) -> WalletResponse:
    return WalletResponse(
        currency=user.currency,
        balance_cents=user.balance_cents,
        vip_points=user.vip_points,
        vip_tier=user.vip_tier,
        games_played=user.games_played,
        total_won_cents=user.total_won_cents,
    )


@router.get("", response_model=WalletResponse)
def get_wallet(current_user: User = Depends(get_current_user)) -> WalletResponse:
    return wallet_response(current_user)
