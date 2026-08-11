from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import api_error
from app.db.session import get_db
from app.deps import get_current_user
from app.models import IdentityAppSession, IdentityAuthorizationCode, IdentityConsent, User
from app.schemas import IdentityTokenRequest, IdentityTokenResponse, IdentityUserInfo


router = APIRouter(prefix="/id", tags=["kawaui-id"])
settings = get_settings()
ALLOWED_SCOPES = {"profile", "email", "birthdate", "country"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _validate_client(client_id: str, redirect_uri: str) -> None:
    if client_id != settings.bukamiku_client_id:
        raise api_error("err_identity_client", status.HTTP_400_BAD_REQUEST)
    if redirect_uri != settings.bukamiku_redirect_uri:
        raise api_error("err_identity_redirect", status.HTTP_400_BAD_REQUEST)


def _normalize_scope(scope: str) -> str:
    requested = {item for item in scope.split() if item}
    if not requested or not requested.issubset(ALLOWED_SCOPES):
        raise api_error("err_identity_scope", status.HTTP_400_BAD_REQUEST)
    return " ".join(sorted(requested))


@router.get("/authorize")
def authorize(
    client_id: str = Query(..., max_length=64),
    redirect_uri: str = Query(..., max_length=512),
    state: str = Query(..., min_length=16, max_length=256),
    code_challenge: str = Query(..., min_length=43, max_length=128),
    code_challenge_method: str = Query(default="S256"),
    scope: str = Query(default="profile email birthdate country", max_length=255),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    _validate_client(client_id, redirect_uri)
    if code_challenge_method != "S256":
        raise api_error("err_identity_pkce", status.HTTP_400_BAD_REQUEST)
    normalized_scope = _normalize_scope(scope)
    raw_code = secrets.token_urlsafe(48)
    row = IdentityAuthorizationCode(
        user_id=current_user.id,
        client_id=client_id,
        code_hash=_hash(raw_code),
        redirect_uri=redirect_uri,
        scope=normalized_scope,
        code_challenge=code_challenge,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.identity_code_ttl_seconds),
    )
    consent = db.scalar(
        select(IdentityConsent).where(
            IdentityConsent.user_id == current_user.id,
            IdentityConsent.client_id == client_id,
        )
    )
    if consent is None:
        consent = IdentityConsent(user_id=current_user.id, client_id=client_id, scope=normalized_scope)
    else:
        consent.scope = normalized_scope
    db.add(row)
    db.add(consent)
    db.commit()
    query = urlencode({"code": raw_code, "state": state})
    return {"authorization_url": f"{redirect_uri}?{query}"}


@router.post("/token", response_model=IdentityTokenResponse)
def exchange_token(payload: IdentityTokenRequest, db: Session = Depends(get_db)) -> IdentityTokenResponse:
    _validate_client(payload.client_id, payload.redirect_uri)
    if payload.grant_type != "authorization_code":
        raise api_error("err_identity_grant", status.HTTP_400_BAD_REQUEST)
    if not secrets.compare_digest(payload.client_secret, settings.bukamiku_client_secret):
        raise api_error("err_identity_client", status.HTTP_401_UNAUTHORIZED)
    code = db.scalar(
        select(IdentityAuthorizationCode).where(IdentityAuthorizationCode.code_hash == _hash(payload.code))
    )
    now = datetime.now(UTC)
    if (
        code is None
        or code.used_at is not None
        or _aware(code.expires_at) < now
        or code.client_id != payload.client_id
        or code.redirect_uri != payload.redirect_uri
    ):
        raise api_error("err_identity_code", status.HTTP_401_UNAUTHORIZED)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(payload.code_verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    if not secrets.compare_digest(challenge, code.code_challenge):
        raise api_error("err_identity_pkce", status.HTTP_401_UNAUTHORIZED)

    raw_token = secrets.token_urlsafe(48)
    expires_in = settings.identity_session_expire_days * 86_400
    app_session = IdentityAppSession(
        user_id=code.user_id,
        client_id=code.client_id,
        token_hash=_hash(raw_token),
        scope=code.scope,
        expires_at=now + timedelta(seconds=expires_in),
    )
    code.used_at = now
    db.add(code)
    db.add(app_session)
    db.commit()
    return IdentityTokenResponse(access_token=raw_token, expires_in=expires_in, scope=code.scope)


def get_identity_session(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> tuple[IdentityAppSession, User]:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise api_error("err_identity_session", status.HTTP_401_UNAUTHORIZED)
    session = db.scalar(select(IdentityAppSession).where(IdentityAppSession.token_hash == _hash(token)))
    now = datetime.now(UTC)
    if session is None or session.revoked_at is not None or _aware(session.expires_at) < now:
        raise api_error("err_identity_session", status.HTTP_401_UNAUTHORIZED)
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise api_error("err_identity_session", status.HTTP_401_UNAUTHORIZED)
    session.last_used_at = now
    db.add(session)
    return session, user


@router.get("/userinfo", response_model=IdentityUserInfo)
def userinfo(identity: tuple[IdentityAppSession, User] = Depends(get_identity_session)) -> IdentityUserInfo:
    _, user = identity
    return IdentityUserInfo(
        sub=str(user.id),
        name=user.name,
        given_name=user.first_name,
        family_name=user.last_name,
        email=user.email,
        birthdate=user.dob,
        country=user.country,
    )


@router.post("/session/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_identity_session(
    identity: tuple[IdentityAppSession, User] = Depends(get_identity_session),
    db: Session = Depends(get_db),
) -> None:
    session, _ = identity
    session.revoked_at = datetime.now(UTC)
    db.add(session)
    db.commit()
