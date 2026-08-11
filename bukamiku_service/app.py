from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware


CENTRAL_URL = os.getenv("BUKAMIKU_CENTRAL_URL", "http://127.0.0.1:8000").rstrip("/")
CLIENT_ID = os.getenv("BUKAMIKU_CLIENT_ID", "bukamiku-bank")
CLIENT_SECRET = os.getenv("BUKAMIKU_CLIENT_SECRET", "local-bukamiku-secret-change-me")
PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL", os.getenv("BUKAMIKU_PUBLIC_URL", "http://127.0.0.1:5600")).rstrip("/")
STUDIO_URL = os.getenv(
    "BUKAMIKU_STUDIO_URL",
    f"{CENTRAL_URL}/pages/partner.html" if CENTRAL_URL.startswith("https://") else "http://127.0.0.1:5500/pages/partner.html",
)
REDIRECT_URI = f"{PUBLIC_URL}/auth/callback"
COOKIE_NAME = "bk_bukamiku_session"
STATIC_DIR = Path(__file__).resolve().parent / "static"


app = FastAPI(title="BuKaMiKu Bank", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("BUKAMIKU_SESSION_SECRET", "local-bukamiku-session-secret"),
    https_only=PUBLIC_URL.startswith("https://"),
    same_site="lax",
)


def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def _session_token(request: Request) -> str:
    return request.cookies.get(COOKIE_NAME, "")


async def _central(request: Request, method: str, path: str, *, json: dict | None = None) -> httpx.Response:
    headers: dict[str, str] = {}
    token = _session_token(request)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if request.headers.get("Idempotency-Key"):
        headers["Idempotency-Key"] = request.headers["Idempotency-Key"]
    async with httpx.AsyncClient(timeout=20) as client:
        return await client.request(method, f"{CENTRAL_URL}{path}", json=json, headers=headers)


def _relay(response: httpx.Response) -> Response:
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": {"code": "err_api_unavailable"}}
    return JSONResponse(payload, status_code=response.status_code)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "bukamiku"}


@app.get("/studio")
async def studio() -> RedirectResponse:
    return RedirectResponse(STUDIO_URL)


@app.get("/auth/login")
async def login(request: Request, next_path: str = "/") -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    request.session["kawaui_id"] = {"state": state, "verifier": verifier, "next": next_path if next_path.startswith("/") else "/"}
    query = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "scope": "profile email birthdate country",
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"{CENTRAL_URL}/pages/identity.html?{query}")


@app.get("/auth/callback")
async def callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    pending = request.session.pop("kawaui_id", None) or {}
    if not code or not state or not secrets.compare_digest(state, str(pending.get("state", ""))):
        return RedirectResponse("/?auth_error=state")
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(
            f"{CENTRAL_URL}/api/id/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code_verifier": pending.get("verifier", ""),
            },
        )
    if token_response.status_code != 200:
        return RedirectResponse("/?auth_error=exchange")
    token = token_response.json()["access_token"]
    response = RedirectResponse(str(pending.get("next") or "/"))
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=PUBLIC_URL.startswith("https://"),
        samesite="lax",
        max_age=int(token_response.json().get("expires_in", 2_592_000)),
        path="/",
    )
    return response


@app.post("/auth/logout")
async def logout(request: Request) -> Response:
    token = _session_token(request)
    if token:
        await _central(request, "POST", "/api/id/session/revoke")
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@app.get("/api/session")
async def session(request: Request) -> Response:
    response = await _central(request, "GET", "/api/apps/bukamiku/session")
    return _relay(response)


@app.get("/api/soul-rate")
async def soul_rate(request: Request) -> Response:
    return _relay(await _central(request, "GET", "/api/apps/bukamiku/soul-rate"))


@app.post("/api/appraisals/preview")
async def preview(request: Request) -> Response:
    return _relay(await _central(request, "POST", "/api/apps/bukamiku/appraisals/preview", json=await request.json()))


@app.post("/api/appraisals")
async def appraisal(request: Request) -> Response:
    return _relay(await _central(request, "POST", "/api/apps/bukamiku/appraisals", json=await request.json()))


@app.get("/api/appraisals")
async def history(request: Request) -> Response:
    return _relay(await _central(request, "GET", "/api/apps/bukamiku/appraisals"))


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
