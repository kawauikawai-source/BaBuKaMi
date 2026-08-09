from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status

from app.core.money import cents_to_amount


def api_error(
    code: str,
    status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT,
    *,
    amount_cents: int | None = None,
    meta: dict[str, Any] | None = None,
) -> HTTPException:
    detail: dict[str, Any] = {"code": code}
    if amount_cents is not None:
        detail["amount"] = str(cents_to_amount(amount_cents))
    if meta:
        detail["meta"] = meta
    return HTTPException(status_code=status_code, detail=detail)


def api_amount(value: int | Decimal | None) -> str:
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return str(value)
    return str(cents_to_amount(value))
