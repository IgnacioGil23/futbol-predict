"""Rutas de los datos y modelos de cada liga, sin dependencias (las importa la API, cuya imagen solo tiene fastapi,
numpy y pandas)."""

from pathlib import Path

from src.config import PROCESSED_DIR, PROJECT_ROOT

LEAGUES_DATA_DIR = PROCESSED_DIR / "leagues"
LEAGUE_MODELS_DIR = PROJECT_ROOT / "models" / "leagues"
LEAGUE_CONFIG_DIR = PROJECT_ROOT / "configs" / "leagues"
MODEL_FILES = {"odds_elo": "model.json", "elo": "elo_model.json"}


def model_path(code: str, kind: str = "odds_elo") -> Path:
    return LEAGUE_MODELS_DIR / code / MODEL_FILES[kind]


def serving_path(code: str) -> Path:
    return LEAGUES_DATA_DIR / f"{code}_serving_matches.csv.gz"


def league_matches_path(code: str) -> Path:
    return LEAGUES_DATA_DIR / f"{code}_matches.parquet"


def league_config_path(code: str) -> Path:
    return LEAGUE_CONFIG_DIR / f"{code}.json"
