from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

from fastapi import Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import api_error
from app.models import SoulAppraisal, User
from app.schemas import SoulAppraisalRequest
from app.services.audit import add_audit_log
from app.services.studio import credit_studio_wallet


settings = get_settings()
DECAY_BPS = (10_000, 2_500, 500)
FATIGUE_BPS = {"fresh": 13_500, "tired": 11_000, "burned": 9_000, "zombie": 7_500}
DEBT_BPS = {"none": 10_000, "small": 10_800, "mortgage": 12_200}
COMPROMISE_BPS = {"saint": 11_500, "minor": 10_000, "career": 8_500}
CONTRACT_VERSION = "soul-pact-v1"


def daily_soul_rate_cents(now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    digest = hmac.new(
        settings.secret_key.encode("utf-8"),
        current.date().isoformat().encode("ascii"),
        hashlib.sha256,
    ).digest()
    # EUR 1,425.00 .. 1,575.00, stable for the whole UTC day.
    return 142_500 + int.from_bytes(digest[:4], "big") % 15_001


def _validated_answers(payload: SoulAppraisalRequest) -> dict[str, str]:
    answers = {
        "fatigue": payload.fatigue.strip().lower(),
        "debt": payload.debt.strip().lower(),
        "compromise": payload.compromise.strip().lower(),
    }
    if answers["fatigue"] not in FATIGUE_BPS:
        raise api_error("err_soul_fatigue")
    if answers["debt"] not in DEBT_BPS:
        raise api_error("err_soul_debt")
    if answers["compromise"] not in COMPROMISE_BPS:
        raise api_error("err_soul_compromise")
    return answers


def calculate_appraisal(payload: SoulAppraisalRequest, sale_number: int) -> dict[str, int | dict[str, str]]:
    if sale_number < 1 or sale_number > 3:
        raise api_error("err_soul_sale_limit", status.HTTP_409_CONFLICT)
    answers = _validated_answers(payload)
    rate = daily_soul_rate_cents()
    weighted = rate
    weighted = weighted * FATIGUE_BPS[answers["fatigue"]] // 10_000
    weighted = weighted * DEBT_BPS[answers["debt"]] // 10_000
    weighted = weighted * COMPROMISE_BPS[answers["compromise"]] // 10_000
    base_value = ((weighted + 2_500) // 5_000) * 5_000
    decay_bps = DECAY_BPS[sale_number - 1]
    payout = ((base_value * decay_bps // 10_000) // 500) * 500
    return {
        "answers": answers,
        "daily_rate_cents": rate,
        "base_value_cents": base_value,
        "decay_bps": decay_bps,
        "payout_cents": payout,
    }


def next_sale_number(db: Session, user_id: int) -> int:
    return int(db.scalar(select(func.count(SoulAppraisal.id)).where(SoulAppraisal.user_id == user_id)) or 0) + 1


def create_soul_sale(
    db: Session,
    *,
    user: User,
    payload: SoulAppraisalRequest,
    request: Request | None = None,
) -> tuple[SoulAppraisal, object, object]:
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None:
        raise api_error("err_user_not_found", status.HTTP_404_NOT_FOUND)
    sale_number = next_sale_number(db, locked_user.id)
    values = calculate_appraisal(payload, sale_number)
    wallet, studio_transaction = credit_studio_wallet(
        db,
        user=locked_user,
        amount_cents=int(values["payout_cents"]),
        source="bukamiku",
        transaction_type="soul_sale",
        external_ref=f"bukamiku-soul:{locked_user.id}:{sale_number}",
        metadata={"sale_number": sale_number, "contract_version": CONTRACT_VERSION},
        request=request,
    )
    appraisal = SoulAppraisal(
        user_id=locked_user.id,
        sale_number=sale_number,
        answers_json=json.dumps(values["answers"], separators=(",", ":")),
        daily_rate_cents=int(values["daily_rate_cents"]),
        base_value_cents=int(values["base_value_cents"]),
        decay_bps=int(values["decay_bps"]),
        payout_cents=int(values["payout_cents"]),
        contract_version=CONTRACT_VERSION,
        studio_transaction_id=studio_transaction.id,
    )
    db.add(appraisal)
    db.flush()
    add_audit_log(
        db,
        action="bukamiku.soul.sale",
        actor_user=locked_user,
        target_user=locked_user,
        amount_cents=appraisal.payout_cents,
        metadata={
            "appraisal_id": appraisal.id,
            "sale_number": sale_number,
            "studio_transaction_id": studio_transaction.id,
            "base_value_cents": appraisal.base_value_cents,
            "decay_bps": appraisal.decay_bps,
        },
        request=request,
    )
    return appraisal, wallet, studio_transaction
