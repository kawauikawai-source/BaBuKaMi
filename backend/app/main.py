from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from alembic.script import ScriptDirectory
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.db.migrations import alembic_config, run_alembic_upgrade
from app.db.session import engine
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.cashier import router as cashier_router
from app.routers.content import router as content_router
from app.routers.games import router as games_router
from app.routers.game_control import router as game_control_router
from app.routers.manager import router as manager_router
from app.routers.transactions import router as transactions_router
from app.routers.users import router as users_router
from app.routers.vip import router as vip_router
from app.routers.wallet import router as wallet_router


settings = get_settings()
configure_logging(settings)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.run_migrations_on_startup:
        logger.info("Running Alembic migrations")
        try:
            run_alembic_upgrade()
        except Exception:
            logger.exception("Alembic migration failed")
            raise
        logger.info("Alembic migrations complete")
    yield


def get_migration_head() -> str | None:
    try:
        return ScriptDirectory.from_config(alembic_config()).get_current_head()
    except Exception:
        logger.exception("Could not read Alembic head")
        return None


def get_database_health() -> tuple[bool, str | None]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            try:
                return True, connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            except Exception:
                return True, None
    except Exception:
        logger.exception("Database healthcheck failed")
        return False, None


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request, exc):
        retry_after = ""
        headers = getattr(exc, "headers", None) or {}
        if isinstance(headers, dict):
            retry_after = headers.get("Retry-After", "")
        return JSONResponse(
            status_code=429,
            content={"detail": {"code": "err_rate_limited", "retry_after": retry_after}},
            headers=headers if isinstance(headers, dict) else None,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        https_only=settings.refresh_cookie_secure,
        same_site=settings.refresh_cookie_samesite,
    )

    @app.middleware("http")
    async def security_and_cache_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.environment.lower() == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        path = request.url.path
        if not path.startswith("/api/") and path not in {"/docs", "/openapi.json", "/redoc"}:
            if path == "/" or path.endswith(".html") or path == "/js/config/runtime.js":
                response.headers["Cache-Control"] = "no-store"
            elif Path(path).suffix.lower() in {".css", ".js", ".json", ".woff2", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico"}:
                response.headers.setdefault("Cache-Control", "public, max-age=604800")
        return response

    @app.get("/api/health")
    def health(response: Response) -> dict[str, str | None]:
        database_ok, migration_current = get_database_health()
        migration_head = get_migration_head()
        database_status = "ok" if database_ok else "error"
        migration_status = "ok" if migration_current and migration_current == migration_head else "error"
        if database_status != "ok" or migration_status != "ok":
            response.status_code = 503
        return {
            "status": "ok" if database_status == "ok" and migration_status == "ok" else "error",
            "env": settings.environment,
            "database": database_status,
            "migration": migration_status,
            "migration_current": migration_current,
            "migration_head": migration_head,
        }

    app.include_router(auth_router, prefix="/api")
    app.include_router(users_router, prefix="/api")
    app.include_router(wallet_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(cashier_router, prefix="/api")
    app.include_router(transactions_router, prefix="/api")
    app.include_router(content_router, prefix="/api")
    app.include_router(vip_router, prefix="/api")
    app.include_router(games_router, prefix="/api")
    app.include_router(game_control_router, prefix="/api")
    app.include_router(manager_router, prefix="/api")

    if settings.serve_frontend:
        frontend_dir = Path(settings.frontend_dist_dir).expanduser().resolve()
        if not (frontend_dir / "index.html").is_file():
            raise RuntimeError(f"Frontend build is missing at {frontend_dir}")
        logger.info("Serving frontend build from %s", frontend_dir)
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app


app = create_app()
