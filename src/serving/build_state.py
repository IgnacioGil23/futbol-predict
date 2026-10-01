"""Genera data/processed/serving_matches.csv.gz (partidos E0+E1 con los dos ratings) para la API y la web.

Solo depende de pandas/numpy (sin scikit-learn, XGBoost ni MLflow), para que el
build de la imagen Docker sea liviano. Requiere haber corrido antes:
    python -m src.data.download && python -m src.data.load

Uso:
    python -m src.serving.build_state
"""

import logging

from src.data.load import load_matches
from src.features.build import load_elo_params
from src.features.elo import compute_elo
from src.features.odds_elo import compute_odds_elo_with_history, load_odds_elo_params
from src.serving.store import SERVING_MATCHES_PATH, build_serving_matches, write_serving_matches

logger = logging.getLogger(__name__)


def build_state():
    matches = load_matches()
    elo, history = compute_elo(matches, load_elo_params())
    odds_elo, odds_history = compute_odds_elo_with_history(matches, load_odds_elo_params())
    serving = build_serving_matches(matches, elo, history, odds_elo, odds_history)
    write_serving_matches(serving)
    return serving


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    serving = build_state()
    logger.info("Partidos para servir -> %s (%d)", SERVING_MATCHES_PATH, len(serving))


if __name__ == "__main__":
    main()
