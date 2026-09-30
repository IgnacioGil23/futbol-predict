"""Ajuste de hiperparámetros del Elo propio.

Criterio (en la línea de Hvattum y Arntzen 2010, que ajustaron k0 y lam para
maximizar la calidad predictiva del rating como única covariable de una
regresión logística ordenada): log loss de una regresión logística multinomial
del resultado (H/D/A) sobre la diferencia de Elo previa al partido.

Solo se usan partidos de Premier League de las temporadas de ENTRENAMIENTO
(config.TRAIN_SEASONS). Validación y test no intervienen: el Elo se calcula
sobre toda la historia (es un proceso online sin fuga), pero el criterio de
selección solo mira entrenamiento.

Búsqueda: descenso por coordenadas sobre grillas (un parámetro por vez), con
varias pasadas hasta que ningún cambio mejora.

Ventaja de local: NO se elige por log loss. En entrenamiento el criterio es casi
plano en ese parámetro (entre h = 0 y h = 100 el log loss cambia ~0,0002, ruido),
así que se fija por calibración: el h tal que el puntaje esperado de un local
contra un rival de igual rating coincida con el puntaje medio observado del
local en entrenamiento, h = 400 * log10(s / (1 - s)). Así `elo_expected_home`
es una probabilidad interpretable (la usan el head-to-head y la web).

Uso:
    python -m src.features.tune_elo
"""

import json
import logging
from dataclasses import replace

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

from src.config import PREMIER_LEAGUE, TRAIN_SEASONS
from src.data.load import load_matches
from src.features.build import ELO_PARAMS_PATH
from src.features.elo import EloParams, compute_elo

logger = logging.getLogger(__name__)

GRID = {
    "k0": [5, 6, 7, 7.5, 8, 9, 10, 12.5, 15],
    "lam": [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5],
    "season_regression": [0.0, 0.05, 0.1, 0.15, 0.2, 0.3],
    "initial_gap": [100, 150, 200, 250, 300, 400],
    "newcomer_offset": [-150, -100, -75, -50, -25, 0],
}


def rating_logloss(diff: np.ndarray, results: np.ndarray) -> float:
    """Log loss (en muestra) de un logit multinomial resultado ~ diferencia de rating."""
    model = LogisticRegression(C=1e6, max_iter=1000)
    x = (diff / 100.0).reshape(-1, 1)
    model.fit(x, results)
    return float(log_loss(results, model.predict_proba(x), labels=model.classes_))


def evaluate(matches: pd.DataFrame, params: EloParams, mask: np.ndarray, results: np.ndarray) -> float:
    per_match, _ = compute_elo(matches, params)
    per_match = per_match.set_index("match_id").loc[matches["match_id"]]
    diff = (per_match["elo_home"] - per_match["elo_away"]).to_numpy()[mask]
    return rating_logloss(diff, results)


def calibrated_home_advantage(results: np.ndarray) -> float:
    """h tal que 1 / (1 + 10^(-h/400)) = puntaje medio del local (victoria 1, empate 0,5)."""
    score = float(np.mean(np.where(results == "H", 1.0, np.where(results == "D", 0.5, 0.0))))
    return float(round(400 * np.log10(score / (1 - score)), 1))


def tune(matches: pd.DataFrame, start: EloParams = EloParams(), max_passes: int = 4) -> tuple[EloParams, float, list]:
    matches = matches.sort_values(["date", "match_id"]).reset_index(drop=True)
    mask = ((matches["division"] == PREMIER_LEAGUE) & matches["season_start"].isin(TRAIN_SEASONS)
            & matches["home_goals"].notna()).to_numpy()
    results = matches.loc[mask, "result"].astype(str).to_numpy()
    start = replace(start, home_advantage=calibrated_home_advantage(results))

    cache: dict[EloParams, float] = {}

    def score(p: EloParams) -> float:
        if p not in cache:
            cache[p] = evaluate(matches, p, mask, results)
        return cache[p]

    best, best_score = start, score(start)
    trace = [{"pass": 0, **best.to_dict(), "log_loss": best_score}]
    for n_pass in range(1, max_passes + 1):
        improved = False
        for name, values in GRID.items():
            for value in values:
                candidate = replace(best, **{name: value})
                s = score(candidate)
                if s < best_score - 1e-7:
                    best, best_score, improved = candidate, s, True
            trace.append({"pass": n_pass, **best.to_dict(), "log_loss": best_score})
            logger.info("pasada %d, %s -> %s (log loss %.5f)", n_pass, name, getattr(best, name), best_score)
        if not improved:
            break
    return best, best_score, trace


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    matches = load_matches()
    paper = EloParams(k0=10, lam=1.0, home_advantage=100, season_regression=0.0, initial_gap=100, newcomer_offset=0)
    best, best_score, trace = tune(matches, start=paper)

    # Referencias en la misma muestra: parámetros del paper y Elo de ClubElo.
    ordered = matches.sort_values(["date", "match_id"]).reset_index(drop=True)
    mask = ((ordered["division"] == PREMIER_LEAGUE) & ordered["season_start"].isin(TRAIN_SEASONS)).to_numpy()
    results = ordered.loc[mask, "result"].astype(str).to_numpy()
    clubelo_diff = (ordered["clubelo_home"] - ordered["clubelo_away"]).to_numpy()[mask]
    reference = {
        "paper_params": evaluate(ordered, paper, mask, results),
        "clubelo": rating_logloss(clubelo_diff, results),
        "tuned": best_score,
        "n_matches": int(mask.sum()),
        "seasons": f"{min(TRAIN_SEASONS)}-{max(TRAIN_SEASONS) + 1}",
    }
    ELO_PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ELO_PARAMS_PATH.write_text(json.dumps({
        "params": best.to_dict(),
        "criterion": "log loss de logit multinomial resultado ~ diferencia de Elo, Premier League, temporadas de entrenamiento",
        "reference_log_loss": reference,
        "trace": trace,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Mejores parámetros: %s", best)
    logger.info("Log loss: ajustado %.5f | paper %.5f | ClubElo %.5f",
                reference["tuned"], reference["paper_params"], reference["clubelo"])


if __name__ == "__main__":
    main()
