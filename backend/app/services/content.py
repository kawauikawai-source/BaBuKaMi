import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
GAMES_PATH = DATA_DIR / "games.json"
I18N_PATH = DATA_DIR / "i18n.json"


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def require_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Missing or invalid list: {key}")
    return value


def require_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Missing or invalid object: {key}")
    return value


def validate_games_data(data: dict[str, Any]) -> dict[str, Any]:
    require_list(data, "slots")
    require_list(data, "table")
    require_list(data, "bonuses")
    require_list(data, "vip_tiers")
    require_dict(data, "stats")
    return data


def validate_i18n_data(data: dict[str, Any]) -> dict[str, Any]:
    ru = data.get("ru")
    en = data.get("en")
    if not isinstance(ru, dict) or not isinstance(en, dict):
        raise ValueError("i18n data must contain ru and en objects")
    return data


def get_games_content() -> dict[str, Any]:
    return validate_games_data(read_json(GAMES_PATH))


def get_i18n_content() -> dict[str, Any]:
    return validate_i18n_data(read_json(I18N_PATH))
