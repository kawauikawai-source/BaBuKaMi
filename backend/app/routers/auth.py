import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from starlette.background import BackgroundTask
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import api_error
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.session import get_db
from app.deps import apply_admin_email_role, get_current_user
from app.models import AccountActionToken, IdentityAppSession, RefreshSession, User
from app.schemas import (
    AccountTokenRequest,
    ChangePasswordRequest,
    DeviceSessionPublic,
    ForgotPasswordRequest,
    GoogleStatusResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
)
from app.services.audit import add_audit_log
from app.services.email import send_new_login_email, send_password_reset_email, send_verification_email


router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
oauth = OAuth()
TELEGRAM_AUTH_URL = "https://oauth.telegram.org/auth"
TELEGRAM_TOKEN_URL = "https://oauth.telegram.org/token"
TELEGRAM_JWKS_URL = "https://oauth.telegram.org/.well-known/jwks.json"
TELEGRAM_ISSUER = "https://oauth.telegram.org"
telegram_jwks_client = jwt.PyJWKClient(TELEGRAM_JWKS_URL)

if settings.google_oauth_enabled:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def synthetic_telegram_email(telegram_sub: str) -> str:
    return f"telegram-{telegram_sub}@users.telegram.bambiku.dev"


def split_display_name(name: str) -> tuple[str, str]:
    parts = str(name or "").strip().split(maxsplit=1)
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def build_token_response(user: User) -> TokenResponse:
    apply_admin_email_role(user)
    return TokenResponse(access_token=create_access_token(user.id), user=UserPublic.model_validate(user))


def utc_now() -> datetime:
    return datetime.now(UTC)


def aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def request_user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:512]


def request_ip(request: Request) -> str:
    return (request.client.host if request.client else "")[:64]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def frontend_link(parameter: str, token: str) -> str:
    base = settings.public_base_url.strip().rstrip("/")
    return f"{base}/index.html?{urlencode({parameter: token})}"


def create_account_token(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    now = utc_now()
    db.execute(
        update(AccountActionToken)
        .where(
            AccountActionToken.user_id == user.id,
            AccountActionToken.purpose == purpose,
            AccountActionToken.used_at.is_(None),
        )
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    )
    raw_token = secrets.token_urlsafe(48)
    db.add(
        AccountActionToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=token_hash(raw_token),
            expires_at=now + ttl,
        )
    )
    return raw_token


def valid_account_token(db: Session, raw_token: str, purpose: str) -> AccountActionToken | None:
    item = db.scalar(
        select(AccountActionToken).where(
            AccountActionToken.token_hash == token_hash(raw_token),
            AccountActionToken.purpose == purpose,
            AccountActionToken.used_at.is_(None),
        )
    )
    if not item or aware_utc(item.expires_at) <= utc_now():
        return None
    return item


def device_details(user_agent: str) -> tuple[str, str]:
    source = (user_agent or "").lower()
    device = "Mobile" if any(value in source for value in ("mobile", "android", "iphone")) else "Computer"
    if "iphone" in source or "ipad" in source:
        device = "iPhone / iPad"
    elif "android" in source:
        device = "Android"
    elif "windows" in source:
        device = "Windows"
    elif "mac os" in source or "macintosh" in source:
        device = "macOS"
    browser = "Browser"
    for needle, label in (("edg/", "Edge"), ("opr/", "Opera"), ("chrome/", "Chrome"), ("firefox/", "Firefox"), ("safari/", "Safari")):
        if needle in source:
            browser = label
            break
    return device, browser


def ip_hint(ip_address: str) -> str:
    value = str(ip_address or "")
    if "." in value:
        parts = value.split(".")
        return ".".join(parts[:2] + ["*", "*"]) if len(parts) == 4 else "hidden"
    return (value[:4] + ":…") if value else "hidden"


def revoke_identity_sessions(db: Session, user_id: int, reason: str) -> None:
    revoke_all_refresh_sessions(db, user_id, reason)
    db.execute(
        update(IdentityAppSession)
        .where(IdentityAppSession.user_id == user_id, IdentityAppSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
        .execution_options(synchronize_session=False)
    )


def should_notify_login(user: User) -> bool:
    return bool(user.last_login_at and user.email_verified and "@users.telegram.bambiku.dev" not in user.email)


def schedule_login_notice(background_tasks: BackgroundTasks, user: User, request: Request) -> None:
    if should_notify_login(user):
        device, browser = device_details(request_user_agent(request))
        background_tasks.add_task(send_new_login_email, user.email, f"{device} · {browser}", utc_now().isoformat())


def create_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:128]


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/api/auth",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/api/auth",
    )


def redirect_oauth_error(target_url: str, reason: str) -> RedirectResponse:
    query = urlencode({"auth_error": "err_google_oauth_failed", "auth_reason": reason[:80]})
    separator = "&" if "?" in target_url else "?"
    return RedirectResponse(f"{target_url}{separator}{query}")


def create_refresh_session(db: Session, user: User, request: Request) -> tuple[str, RefreshSession]:
    token = create_refresh_token()
    session = RefreshSession(
        user_id=user.id,
        token_hash=hash_refresh_token(token),
        expires_at=utc_now() + timedelta(days=settings.refresh_token_expire_days),
        user_agent=request_user_agent(request),
        ip_address=request_ip(request),
    )
    db.add(session)
    db.flush()
    return token, session


def find_refresh_session(db: Session, token: str) -> RefreshSession | None:
    if not token:
        return None
    return db.scalar(select(RefreshSession).where(RefreshSession.token_hash == hash_refresh_token(token)))


def get_refresh_session(db: Session, token: str) -> RefreshSession | None:
    session = find_refresh_session(db, token)
    if not session or session.revoked_at is not None or aware_utc(session.expires_at) <= utc_now():
        return None
    return session


def revoke_all_refresh_sessions(db: Session, user_id: int, reason: str) -> None:
    now = utc_now()
    sessions = db.scalars(
        select(RefreshSession).where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
    ).all()
    for session in sessions:
        session.revoked_at = now
        session.revoked_reason = reason
        db.add(session)


def refresh_error(code: str, response: Response, status_code: int = status.HTTP_401_UNAUTHORIZED) -> None:
    clear_refresh_cookie(response)
    raise api_error(code, status_code)


def issue_token_response(user: User, request: Request, response: Response, db: Session) -> TokenResponse:
    refresh_token, _ = create_refresh_session(db, user, request)
    db.commit()
    db.refresh(user)
    set_refresh_cookie(response, refresh_token)
    return build_token_response(user)


def telegram_user_from_claims(db: Session, claims: dict) -> User:
    telegram_sub = str(claims.get("sub") or "").strip()
    if not telegram_sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram profile is missing subject")

    user = db.scalar(select(User).where(User.telegram_sub == telegram_sub))
    claim_name = str(claims.get("name") or claims.get("preferred_username") or f"Telegram {telegram_sub}").strip()
    claim_first = str(claims.get("given_name") or "").strip()
    claim_last = str(claims.get("family_name") or "").strip()
    if not claim_first:
        claim_first, inferred_last = split_display_name(claim_name)
        claim_last = claim_last or inferred_last

    if user:
        user.first_name = user.first_name or claim_first[:128]
        user.last_name = user.last_name or claim_last[:128]
        return user

    email = synthetic_telegram_email(telegram_sub)
    user = find_user_by_email(db, email)
    if user:
        user.telegram_sub = telegram_sub
        user.provider = "telegram"
        user.email_verified = True
        user.first_name = user.first_name or claim_first[:128]
        user.last_name = user.last_name or claim_last[:128]
        return user

    user = User(
        email=email,
        name=claim_name[:255],
        first_name=claim_first[:128],
        last_name=claim_last[:128],
        provider="telegram",
        telegram_sub=telegram_sub,
        email_verified=True,
    )
    db.add(user)
    return user


async def exchange_telegram_code(code: str, code_verifier: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            TELEGRAM_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.telegram_redirect_uri,
                "client_id": settings.telegram_client_id,
                "code_verifier": code_verifier,
            },
            auth=(settings.telegram_client_id, settings.telegram_client_secret),
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram token exchange failed")
    return response.json()


def validate_telegram_id_token(id_token: str, nonce: str | None = None) -> dict:
    try:
        signing_key = telegram_jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.telegram_client_id,
            issuer=TELEGRAM_ISSUER,
        )
    except jwt.PyJWTError as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram ID token") from err

    if nonce and claims.get("nonce") not in (None, nonce):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram nonce")
    return claims


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_auth_hour)
@limiter.limit(settings.rate_limit_auth)
def register(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = normalize_email(payload.email)
    if find_user_by_email(db, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    legacy_first, legacy_last = split_display_name(payload.name or "")
    first_name = str(payload.first_name or legacy_first).strip()
    last_name = str(payload.last_name or legacy_last).strip()
    display_name = " ".join(part for part in (first_name, last_name) if part).strip()
    user = User(
        email=email,
        name=display_name,
        first_name=first_name,
        last_name=last_name,
        phone=payload.phone.strip(),
        dob=payload.dob.strip(),
        country=payload.country.strip(),
        kyc_status="pending" if payload.kyc_opt_in else "not_started",
        password_hash=hash_password(payload.password),
        provider="local",
        email_verified=False,
    )
    apply_admin_email_role(user)
    db.add(user)
    db.flush()
    verification_token = create_account_token(
        db, user, "verify_email", timedelta(hours=settings.email_verification_expire_hours)
    )
    background_tasks.add_task(
        send_verification_email,
        user.email,
        user.name,
        frontend_link("verify_email", verification_token),
    )
    return issue_token_response(user, request, response, db)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_auth_hour)
@limiter.limit(settings.rate_limit_auth)
def login(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = find_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    schedule_login_notice(background_tasks, user, request)
    user.last_login_at = datetime.now(UTC)
    apply_admin_email_role(user)
    db.add(user)
    db.flush()
    return issue_token_response(user, request, response, db)


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_refresh)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    token = request.cookies.get(settings.refresh_cookie_name, "")
    refresh_session = find_refresh_session(db, token)
    if not refresh_session:
        refresh_error("err_refresh_invalid", response)

    if refresh_session.revoked_at is not None:
        if refresh_session.rotated_at is not None:
            revoke_all_refresh_sessions(db, refresh_session.user_id, "reuse_detected")
            db.commit()
            refresh_error("err_refresh_reuse_detected", response)
        refresh_error("err_refresh_invalid", response)

    if aware_utc(refresh_session.expires_at) <= utc_now():
        refresh_session.revoked_at = utc_now()
        refresh_session.revoked_reason = "expired"
        db.add(refresh_session)
        db.commit()
        refresh_error("err_refresh_expired", response)

    user = db.get(User, refresh_session.user_id)
    if not user or not user.is_active:
        refresh_session.revoked_at = utc_now()
        refresh_session.revoked_reason = "invalid_user"
        db.add(refresh_session)
        db.commit()
        refresh_error("err_refresh_invalid", response)

    if refresh_session.user_agent and refresh_session.user_agent != request_user_agent(request):
        refresh_session.revoked_at = utc_now()
        refresh_session.revoked_reason = "client_mismatch"
        db.add(refresh_session)
        db.commit()
        refresh_error("err_refresh_client_mismatch", response)

    now = utc_now()
    refresh_session.last_used_at = now
    refresh_session.rotated_at = now
    refresh_session.revoked_at = now
    refresh_session.revoked_reason = "rotated"
    new_token, new_session = create_refresh_session(db, user, request)
    refresh_session.replaced_by_session_id = new_session.id
    db.add(refresh_session)
    db.commit()
    db.refresh(user)
    set_refresh_cookie(response, new_token)

    return build_token_response(user)


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> MessageResponse:
    token = request.cookies.get(settings.refresh_cookie_name, "")
    refresh_session = get_refresh_session(db, token)
    if refresh_session:
        refresh_session.revoked_at = utc_now()
        refresh_session.revoked_reason = "logout"
        db.add(refresh_session)
        db.commit()
    clear_refresh_cookie(response)
    return MessageResponse(message="Logged out")


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    revoke_all_refresh_sessions(db, current_user.id, "logout_all")
    now = datetime.now(UTC)
    db.execute(
        update(IdentityAppSession)
        .where(IdentityAppSession.user_id == current_user.id, IdentityAppSession.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    clear_refresh_cookie(response)
    return MessageResponse(message="Logged out from all sessions")


@router.post("/email-verification/request", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_account_email)
def request_email_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    if current_user.email_verified:
        return MessageResponse(message="Email already verified")
    raw_token = create_account_token(
        db, current_user, "verify_email", timedelta(hours=settings.email_verification_expire_hours)
    )
    add_audit_log(db, action="auth.email_verification.request", actor_user=current_user, target_user=current_user, request=request)
    db.commit()
    background_tasks.add_task(
        send_verification_email,
        current_user.email,
        current_user.name,
        frontend_link("verify_email", raw_token),
    )
    return MessageResponse(message="Verification email sent")


@router.post("/email-verification/confirm", response_model=MessageResponse)
def confirm_email_verification(
    request: Request,
    payload: AccountTokenRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    item = valid_account_token(db, payload.token, "verify_email")
    if not item:
        raise api_error("err_email_verification_invalid", status.HTTP_422_UNPROCESSABLE_CONTENT)
    user = db.get(User, item.user_id)
    if not user:
        raise api_error("err_email_verification_invalid", status.HTTP_422_UNPROCESSABLE_CONTENT)
    item.used_at = utc_now()
    user.email_verified = True
    add_audit_log(db, action="auth.email_verification.confirm", actor_user=user, target_user=user, request=request)
    db.commit()
    return MessageResponse(message="Email verified")


@router.post("/password/forgot", response_model=MessageResponse)
@limiter.limit(settings.rate_limit_account_email)
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageResponse:
    user = find_user_by_email(db, payload.email)
    if user and user.is_active and "@users.telegram.bambiku.dev" not in user.email:
        raw_token = create_account_token(
            db, user, "reset_password", timedelta(minutes=settings.password_reset_expire_minutes)
        )
        add_audit_log(db, action="auth.password_reset.request", target_user=user, request=request)
        db.commit()
        background_tasks.add_task(
            send_password_reset_email,
            user.email,
            user.name,
            frontend_link("reset_password", raw_token),
        )
    return MessageResponse(message="If the account exists, a recovery email has been sent")


@router.post("/password/reset", response_model=MessageResponse)
def reset_password(
    request: Request,
    response: Response,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    item = valid_account_token(db, payload.token, "reset_password")
    if not item:
        raise api_error("err_password_reset_invalid", status.HTTP_422_UNPROCESSABLE_CONTENT)
    user = db.get(User, item.user_id)
    if not user:
        raise api_error("err_password_reset_invalid", status.HTTP_422_UNPROCESSABLE_CONTENT)
    item.used_at = utc_now()
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = utc_now()
    revoke_identity_sessions(db, user.id, "password_reset")
    add_audit_log(db, action="auth.password.reset", actor_user=user, target_user=user, request=request)
    db.commit()
    clear_refresh_cookie(response)
    return MessageResponse(message="Password changed")


@router.post("/password/change", response_model=MessageResponse)
def change_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise api_error("err_current_password", status.HTTP_422_UNPROCESSABLE_CONTENT)
    if verify_password(payload.new_password, current_user.password_hash):
        raise api_error("err_password_unchanged", status.HTTP_422_UNPROCESSABLE_CONTENT)
    current_user.password_hash = hash_password(payload.new_password)
    current_user.password_changed_at = utc_now()
    revoke_identity_sessions(db, current_user.id, "password_change")
    add_audit_log(db, action="auth.password.change", actor_user=current_user, target_user=current_user, request=request)
    db.commit()
    clear_refresh_cookie(response)
    return MessageResponse(message="Password changed")


@router.get("/sessions", response_model=list[DeviceSessionPublic])
def list_device_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DeviceSessionPublic]:
    now = utc_now()
    token = request.cookies.get(settings.refresh_cookie_name, "")
    current_hash = hash_refresh_token(token) if token else ""
    sessions = db.scalars(
        select(RefreshSession)
        .where(
            RefreshSession.user_id == current_user.id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
        .order_by(RefreshSession.created_at.desc())
    ).all()
    result = []
    for session in sessions:
        device, browser = device_details(session.user_agent)
        result.append(
            DeviceSessionPublic(
                id=session.id,
                device=device,
                browser=browser,
                ip_hint=ip_hint(session.ip_address),
                created_at=session.created_at,
                last_used_at=session.last_used_at,
                expires_at=session.expires_at,
                current=session.token_hash == current_hash,
            )
        )
    return result


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
def revoke_device_session(
    session_id: int,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    session = db.scalar(
        select(RefreshSession).where(RefreshSession.id == session_id, RefreshSession.user_id == current_user.id)
    )
    if not session or session.revoked_at is not None:
        raise api_error("err_session_not_found", status.HTTP_404_NOT_FOUND)
    current_token = request.cookies.get(settings.refresh_cookie_name, "")
    is_current = bool(current_token and session.token_hash == hash_refresh_token(current_token))
    session.revoked_at = utc_now()
    session.revoked_reason = "device_revoked"
    add_audit_log(
        db,
        action="auth.session.revoke",
        actor_user=current_user,
        target_user=current_user,
        metadata={"session_id": session.id, "current": is_current},
        request=request,
    )
    db.commit()
    if is_current:
        clear_refresh_cookie(response)
    return MessageResponse(message="Session revoked")


@router.get("/google/status", response_model=GoogleStatusResponse)
def google_status() -> GoogleStatusResponse:
    return GoogleStatusResponse(
        enabled=settings.google_oauth_enabled,
        login_url="/api/auth/google/login",
    )


@router.get("/telegram/status", response_model=GoogleStatusResponse)
def telegram_status() -> GoogleStatusResponse:
    return GoogleStatusResponse(
        enabled=settings.telegram_oauth_enabled,
        login_url="/api/auth/telegram/login",
    )


@router.get("/google/login")
@limiter.limit(settings.rate_limit_auth_hour)
@limiter.limit(settings.rate_limit_auth)
async def google_login(request: Request):
    if not settings.google_oauth_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured. Set BAMBIKU_GOOGLE_CLIENT_ID and BAMBIKU_GOOGLE_CLIENT_SECRET.",
        )
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/telegram/login")
@limiter.limit(settings.rate_limit_auth_hour)
@limiter.limit(settings.rate_limit_auth)
async def telegram_login(request: Request):
    if not settings.telegram_oauth_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Telegram OIDC is not configured. Set BAMBIKU_TELEGRAM_CLIENT_ID and BAMBIKU_TELEGRAM_CLIENT_SECRET.",
        )

    state = secrets.token_urlsafe(32)
    verifier = create_code_verifier()
    nonce = secrets.token_urlsafe(32)
    request.session["telegram_oidc"] = {
        "state": state,
        "code_verifier": verifier,
        "nonce": nonce,
    }
    query = urlencode(
        {
            "client_id": settings.telegram_client_id,
            "redirect_uri": settings.telegram_redirect_uri,
            "response_type": "code",
            "scope": settings.telegram_scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"{TELEGRAM_AUTH_URL}?{query}")


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    if not settings.google_oauth_enabled:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Google OAuth is not configured")

    if request.query_params.get("error"):
        return redirect_oauth_error(
            settings.google_success_redirect,
            request.query_params.get("error") or "google_error",
        )

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        return redirect_oauth_error(settings.google_success_redirect, "callback_failed")
    profile = token.get("userinfo")
    if profile is None:
        try:
            profile = await oauth.google.parse_id_token(request, token)
        except Exception:
            return redirect_oauth_error(settings.google_success_redirect, "profile_failed")

    google_sub = profile.get("sub")
    email = normalize_email(profile.get("email", ""))
    if not google_sub or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google profile is missing email or subject")

    profile_name = str(profile.get("name") or email.split("@")[0]).strip()
    profile_first = str(profile.get("given_name") or "").strip()
    profile_last = str(profile.get("family_name") or "").strip()
    if not profile_first:
        profile_first, inferred_last = split_display_name(profile_name)
        profile_last = profile_last or inferred_last

    user = db.scalar(select(User).where(User.google_sub == google_sub))
    if not user:
        user = find_user_by_email(db, email)
        if user:
            user.google_sub = google_sub
            user.provider = "google"
            user.email_verified = bool(profile.get("email_verified", user.email_verified))
            user.first_name = user.first_name or profile_first[:128]
            user.last_name = user.last_name or profile_last[:128]
        else:
            user = User(
                email=email,
                name=profile_name[:255],
                first_name=profile_first[:128],
                last_name=profile_last[:128],
                provider="google",
                google_sub=google_sub,
                email_verified=bool(profile.get("email_verified", False)),
            )
            db.add(user)
    else:
        user.first_name = user.first_name or profile_first[:128]
        user.last_name = user.last_name or profile_last[:128]

    notify_login = should_notify_login(user)
    user.last_login_at = datetime.now(UTC)
    apply_admin_email_role(user)
    db.flush()
    refresh_token, _ = create_refresh_session(db, user, request)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(user.id)
    query = urlencode({"access_token": access_token, "token_type": "bearer"})
    separator = "&" if "?" in settings.google_success_redirect else "?"
    response = RedirectResponse(f"{settings.google_success_redirect}{separator}{query}")
    set_refresh_cookie(response, refresh_token)
    if notify_login:
        device, browser = device_details(request_user_agent(request))
        response.background = BackgroundTask(
            send_new_login_email, user.email, f"{device} / {browser}", utc_now().isoformat()
        )
    return response


@router.get("/telegram/callback")
async def telegram_callback(request: Request, db: Session = Depends(get_db)):
    if not settings.telegram_oauth_enabled:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Telegram OIDC is not configured")

    if request.query_params.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=request.query_params.get("error_description") or "Telegram login failed")

    session_data = request.session.pop("telegram_oidc", None) or {}
    if not session_data or request.query_params.get("state") != session_data.get("state"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Telegram state")

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram authorization code is missing")

    token = await exchange_telegram_code(code, session_data["code_verifier"])
    id_token = token.get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram ID token is missing")

    claims = validate_telegram_id_token(id_token, session_data.get("nonce"))
    user = telegram_user_from_claims(db, claims)
    user.last_login_at = datetime.now(UTC)
    apply_admin_email_role(user)
    db.flush()
    refresh_token, _ = create_refresh_session(db, user, request)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(user.id)
    query = urlencode({"access_token": access_token, "token_type": "bearer"})
    separator = "&" if "?" in settings.telegram_success_redirect else "?"
    response = RedirectResponse(f"{settings.telegram_success_redirect}{separator}{query}")
    set_refresh_cookie(response, refresh_token)
    return response
