from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings


def alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_database_url)
    return config


def run_alembic_upgrade(revision: str = "head") -> None:
    command.upgrade(alembic_config(), revision)


def ensure_user_columns(engine) -> None:
    # Backward-compatible shim for older imports. Schema changes now live in Alembic.
    run_alembic_upgrade()


def ensure_user_profile_columns(engine) -> None:
    ensure_user_columns(engine)
