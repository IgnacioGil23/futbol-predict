"""Estado para servir de las otras ligas, sin scikit-learn (lo usan la etapa de datos de la imagen Docker y la
actualización de la web).

Por liga: los parámetros de sus dos ratings (configs/leagues/<liga>.json, elegidos con docs/preregistro_ligas.md), el
estado con los dos ratings (data/processed/leagues/<liga>_serving_matches.csv.gz) y las rutas de sus modelos
(models/leagues/<liga>/, que entrena src/serving/league_models.py una vez por temporada).

Uso (después de `python -m src.data.leagues`):
    python -m src.serving.league_state
"""

import argparse
import json
import logging

import pandas as pd

from src.features.build import load_elo_params
from src.features.elo import EloParams, compute_elo
from src.features.odds_elo import compute_odds_elo_with_history, load_odds_elo_params
from src.league_registry import LEAGUES
from src.serving.league_paths import (  # noqa: F401 - se re-exportan
    LEAGUE_CONFIG_DIR,
    LEAGUE_MODELS_DIR,
    LEAGUES_DATA_DIR,
    MODEL_FILES,
    league_config_path,
    league_matches_path,
    model_path,
    serving_path,
)
from src.serving.store import build_serving_matches, write_serving_matches

logger = logging.getLogger(__name__)

def load_league_params(code: str) -> tuple[EloParams, EloParams]:
    """(Elo de cuotas, Elo de resultados) de la liga; Inglaterra usa los de configs/."""
    if code == "ENG":
        return load_odds_elo_params(), load_elo_params()
    cfg = json.loads(league_config_path(code).read_text(encoding="utf-8"))
    return EloParams(**cfg["odds_elo"]["params"]), EloParams(**cfg["elo"]["params"])


def build_league_state(code: str, matches: pd.DataFrame | None = None) -> pd.DataFrame:
    """Partidos de las dos divisiones con los dos ratings, previo y posterior de cada equipo."""
    matches = pd.read_parquet(league_matches_path(code)) if matches is None else matches
    odds_params, elo_params = load_league_params(code)
    top = LEAGUES[code]["top"]
    elo, history = compute_elo(matches, elo_params, top_division=top)
    odds, odds_history = compute_odds_elo_with_history(matches, odds_params, top_division=top)
    serving = build_serving_matches(matches, elo, history, odds, odds_history)
    write_serving_matches(serving, serving_path(code))
    return serving


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leagues", nargs="*", default=list(LEAGUES))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for code in args.leagues:
        serving = build_league_state(code)
        logger.info("%s: %d partidos para servir -> %s", code, len(serving), serving_path(code))


if __name__ == "__main__":
    main()
