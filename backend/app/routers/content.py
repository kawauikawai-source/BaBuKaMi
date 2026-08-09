from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.services.content import get_games_content, get_i18n_content


router = APIRouter(tags=["content"])


def content_error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Content source is unavailable or invalid: {error}",
    )


def games_data() -> dict[str, Any]:
    try:
        return get_games_content()
    except (OSError, ValueError) as error:
        raise content_error(error) from error


@router.get("/games")
def list_games() -> dict[str, Any]:
    data = games_data()
    return {
        "slots": data["slots"],
        "table": data["table"],
        "stats": data["stats"],
    }


@router.get("/bonuses")
def list_bonuses() -> list[Any]:
    return games_data()["bonuses"]


@router.get("/vip/tiers")
def list_vip_tiers() -> list[Any]:
    return games_data()["vip_tiers"]


@router.get("/content/i18n")
def get_i18n() -> dict[str, Any]:
    try:
        return get_i18n_content()
    except (OSError, ValueError) as error:
        raise content_error(error) from error
