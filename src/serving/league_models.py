"""Modelos y estado para servir de las otras ligas (LaLiga, Serie A, Bundesliga, Ligue 1).

Mismo modelo que la Premier (src/serving/production.py), entrenado en cada liga con sus partidos:
* model.json: Poisson sobre la diferencia del Elo de cuotas (el modelo publicado);
* elo_model.json: Poisson sobre la diferencia del Elo de resultados (la simulación de la temporada, que necesita un
  rating que se actualice con resultados simulados).
Los parámetros de cada rating son los de configs/leagues/<liga>.json, elegidos con la regla de
docs/preregistro_ligas.md. Cada modelo se entrena con las temporadas completas desde la primera de la evaluación de
esa liga (FIRST_TRAIN de src/models/odds_elo_eval.py) y se reentrena una vez por temporada, como el de la Premier.

Uso:
    python -m src.serving.league_models --train     # reentrena los modelos (una vez por temporada) y el estado
    python -m src.serving.league_models             # solo el estado para servir (cada actualización de datos)
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT, TEST_SEASONS, season_label, season_start_year
from src.data.leagues import LEAGUES, LEAGUES_DIR, matches_path
from src.features.build import build_features
from src.features.elo import compute_elo
from src.features.odds_elo import compute_odds_elo_with_history
from src.metrics import summarize
from src.models.experiments import predict_feature_model, prepare
from src.models.feature_models import PoissonGLMModel
from src.models.league_params import load_league_params
from src.models.odds_elo_eval import FIRST_TRAIN
from src.odds import shin_probabilities
from src.serving.production import ALPHA, export_params
from src.serving.store import build_serving_matches, write_serving_matches

logger = logging.getLogger(__name__)

LEAGUE_MODELS_DIR = PROJECT_ROOT / "models" / "leagues"
MODELS = {
    "odds_elo": {"file": "model.json", "features": ["odds_elo_diff"],
                 "model": "Poisson (goles del local y del visitante) sobre la diferencia del rating basado en cuotas "
                          "(ELO-Odds)"},
    "elo": {"file": "elo_model.json", "features": ["elo_diff"],
            "model": "Poisson (goles del local y del visitante) sobre la diferencia del Elo de resultados "
                     "(simulación de la temporada)"},
}
METRIC_KEYS = ("log_loss", "rps", "brier", "accuracy", "ece")


def model_path(code: str, kind: str = "odds_elo") -> Path:
    return LEAGUE_MODELS_DIR / code / MODELS[kind]["file"]


def serving_path(code: str) -> Path:
    return LEAGUES_DIR / f"{code}_serving_matches.csv.gz"


def features_path(code: str) -> Path:
    return LEAGUES_DIR / f"{code}_live_features.parquet"


def league_features(code: str, matches: pd.DataFrame | None = None) -> pd.DataFrame:
    """Variables de la primera división con los parámetros de rating de la liga."""
    matches = pd.read_parquet(matches_path(code)) if matches is None else matches
    odds_params, elo_params = load_league_params(code)
    feats, _ = build_features(matches, elo_params, division=LEAGUES[code]["top"], odds_elo_params=odds_params)
    return prepare(feats)


def _market_metrics(features: pd.DataFrame, cols: list[str]) -> dict | None:
    test = features[features.season_start.isin(TEST_SEASONS) & features.played]
    odds = test[cols].to_numpy(dtype=float, na_value=np.nan)
    ok = ~np.isnan(odds).any(axis=1) & (odds > 1).all(axis=1)
    if not ok.any():
        return None
    s = summarize(shin_probabilities(odds[ok]), test.loc[ok, "result"].astype(str).to_numpy())
    return {k: float(s[k]) for k in METRIC_KEYS} | {"n": int(s["n"])}


def test_metrics(features: pd.DataFrame, kind: str, first_train: int) -> dict:
    """Métricas en 2023-24 a 2025-26 (cada temporada con un modelo entrenado con las anteriores) y las del mercado en
    los mismos partidos."""
    cols = MODELS[kind]["features"]
    pred = predict_feature_model(lambda: PoissonGLMModel(cols, alpha=ALPHA), features, list(TEST_SEASONS),
                                 first_train=first_train)
    results = pred.merge(features[["match_id", "result"]], on="match_id")["result"].astype(str).to_numpy()
    model = summarize(pred[["p_home", "p_draw", "p_away"]].to_numpy(), results)
    return {
        "seasons": f"{season_label(min(TEST_SEASONS))} a {season_label(max(TEST_SEASONS))}",
        "model": {k: float(model[k]) for k in METRIC_KEYS} | {"n": int(model["n"])},
        "bet365_pre_closing": _market_metrics(features, ["b365_home", "b365_draw", "b365_away"]),
        "pinnacle_closing": _market_metrics(features, ["psc_home", "psc_draw", "psc_away"]),
    }


def train_league(code: str, features: pd.DataFrame, kind: str, today: date | None = None) -> dict:
    """Artefacto (parámetros + metadatos) del modelo `kind` de la liga."""
    current = season_start_year(today or date.today())
    first = FIRST_TRAIN[code]
    cols = MODELS[kind]["features"]
    train = features[(features.season_start >= first) & (features.season_start < current) & features.played]
    model = PoissonGLMModel(cols, alpha=ALPHA).fit(train)
    odds_params, elo_params = load_league_params(code)
    rating_params = odds_params if kind == "odds_elo" else elo_params
    meta = {
        "league": code, "competition": LEAGUES[code]["competition"],
        "model": MODELS[kind]["model"], "features": cols, "rating": kind, "alpha": ALPHA,
        "trained_on": {"seasons": f"{train.season.min()} a {train.season.max()}", "matches": int(len(train))},
        "trained_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "elo_params": rating_params.to_dict(),              # entran en el hash de versión
        "results_elo_params": elo_params.to_dict(),
        "preregistration": "docs/preregistro_ligas.md",
        "test_metrics": test_metrics(features, kind, first),
    }
    return {"params": export_params(model), "meta": meta}


def build_league_state(code: str, matches: pd.DataFrame | None = None) -> pd.DataFrame:
    """Partidos de las dos divisiones con los dos ratings (data/processed/leagues/<liga>_serving_matches.csv.gz)."""
    matches = pd.read_parquet(matches_path(code)) if matches is None else matches
    odds_params, elo_params = load_league_params(code)
    top = LEAGUES[code]["top"]
    elo, history = compute_elo(matches, elo_params, top_division=top)
    odds, odds_history = compute_odds_elo_with_history(matches, odds_params, top_division=top)
    serving = build_serving_matches(matches, elo, history, odds, odds_history)
    write_serving_matches(serving, serving_path(code))
    return serving


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true", help="reentrenar los modelos de cada liga")
    parser.add_argument("--leagues", nargs="*", default=list(LEAGUES))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for code in args.leagues:
        matches = pd.read_parquet(matches_path(code))
        if args.train:
            features = league_features(code, matches)
            features.to_parquet(features_path(code), index=False)
            for kind in MODELS:
                artifact = train_league(code, features, kind)
                path = model_path(code, kind)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
                m = artifact["meta"]["test_metrics"]
                logger.info("%s %s -> %s (%s) · test log loss %.4f vs Bet365 %.4f", code, kind, path,
                            artifact["meta"]["trained_on"]["seasons"], m["model"]["log_loss"],
                            (m["bet365_pre_closing"] or {}).get("log_loss", float("nan")))
        serving = build_league_state(code, matches)
        logger.info("%s: %d partidos para servir -> %s", code, len(serving), serving_path(code))


if __name__ == "__main__":
    main()
