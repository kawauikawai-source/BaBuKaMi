from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BAMBIKU_",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "BamBiku API"
    environment: str = Field(default="development", validation_alias=AliasChoices("BAMBIKU_ENV", "ENV"))
    log_level: str = "INFO"
    log_format: str = "plain"
    public_base_url: str = "http://127.0.0.1:5500"
    api_base_url: str = "http://127.0.0.1:8000/api"
    secret_key: str = Field(default="change-me-to-a-long-random-secret", min_length=16)
    database_url: str = "sqlite:///./bambiku.db"
    run_migrations_on_startup: bool = True
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    refresh_cookie_name: str = "bk_refresh_token"
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: str = "lax"
    frontend_origins: str = (
        "http://localhost:5500,http://127.0.0.1:5500,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )
    rate_limit_auth: str = "5/minute"
    rate_limit_auth_hour: str = "25/hour"
    rate_limit_refresh: str = "20/minute"
    rate_limit_cashier: str = "8/minute"
    rate_limit_admin_money: str = "20/minute"
    rate_limit_vip_clicker: str = "120/minute"
    rate_limit_vip_purchase: str = "10/minute"
    admin_emails: str = Field(default="", validation_alias=AliasChoices("BAMBIKU_ADMIN_EMAILS", "ADMIN_EMAILS"))

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    google_success_redirect: str = "http://localhost:5500/index.html"
    telegram_client_id: str = ""
    telegram_client_secret: str = ""
    telegram_redirect_uri: str = "http://localhost:8000/api/auth/telegram/callback"
    telegram_success_redirect: str = "http://localhost:5500/index.html"
    telegram_scopes: str = "openid profile"
    render_external_url: str = Field(
        default="",
        validation_alias=AliasChoices("RENDER_EXTERNAL_URL", "BAMBIKU_RENDER_EXTERNAL_URL"),
    )
    serve_frontend: bool = False
    frontend_dist_dir: str = "../dist"

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        render_url = self.render_external_url.strip().rstrip("/")
        if render_url:
            parsed = urlsplit(render_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("RENDER_EXTERNAL_URL must be a valid HTTPS origin")
            self.public_base_url = render_url
            self.api_base_url = f"{render_url}/api"
            self.frontend_origins = render_url
            local_markers = ("localhost", "127.0.0.1", "0.0.0.0")
            oauth_urls = {
                "google_redirect_uri": f"{render_url}/api/auth/google/callback",
                "google_success_redirect": f"{render_url}/index.html",
                "telegram_redirect_uri": f"{render_url}/api/auth/telegram/callback",
                "telegram_success_redirect": f"{render_url}/index.html",
            }
            for field_name, hosted_url in oauth_urls.items():
                configured_url = str(getattr(self, field_name, "")).lower()
                if any(marker in configured_url for marker in local_markers):
                    setattr(self, field_name, hosted_url)

        env = self.environment.lower()
        origins = self.cors_origins
        if env in {"staging", "production"}:
            if "*" in origins:
                raise ValueError("Wildcard CORS origins are not allowed in staging/production")
            if self.secret_key.startswith("change-me"):
                raise ValueError("BAMBIKU_SECRET_KEY must be changed in staging/production")
        if env == "production":
            local_markers = ("localhost", "127.0.0.1", "0.0.0.0")
            if any(marker in origin.lower() for origin in origins for marker in local_markers):
                raise ValueError("Localhost CORS origins are not allowed in production")
            if not self.refresh_cookie_secure:
                raise ValueError("BAMBIKU_REFRESH_COOKIE_SECURE=true is required in production")
        return self

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @computed_field
    @property
    def admin_email_set(self) -> set[str]:
        return {email.strip().lower() for email in self.admin_emails.split(",") if email.strip()}

    @computed_field
    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @computed_field
    @property
    def telegram_oauth_enabled(self) -> bool:
        return bool(self.telegram_client_id and self.telegram_client_secret)

    @computed_field
    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
