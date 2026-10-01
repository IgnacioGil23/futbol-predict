"""Rating basado en cuotas (ELO-Odds; Wunderlich y Memmert 2018, PLoS ONE 13(6): e0198668).

Protocolo en docs/preregistro_cuotas.md (commit c5dcf30, anterior a este código).

Mismo Elo que el del proyecto (src/features/elo.py), con una sola diferencia: en la actualización, el resultado se
reemplaza por el puntaje que el mercado esperaba ANTES de ese partido,

    a = p_local + 0,5 · p_empate        (Bet365 de Football-Data, margen quitado por el método de Shin),

con k = k0 constante. Los partidos sin cuotas no actualizan. El rating previo a un partido del día D solo usa cuotas
de partidos jugados antes de D: las cuotas del propio partido nunca entran.

Ajuste (mismo criterio y misma búsqueda que src/features/tune_elo.py): log loss de un logit multinomial del resultado
sobre la diferencia de rating, en partidos de Premier de TUNE_SEASONS. La ventaja de local se fija por calibración con
el puntaje medio del mercado para el local en esas temporadas.
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from src.config import PREMIER_LEAGUE
from src.features.elo import EloParams, compute_elo
from src.features.tune_elo import GRID as ELO_GRID
from src.features.tune_elo import rating_logloss
from src.odds import shin_probabilities

ODDS_COLUMNS = ["b365_home", "b365_draw", "b365_away"]
SCORE_COLUMN = "market_score_home"
TUNE_SEASONS = list(range(2004, 2015))          # 2004-05 .. 2014-15 (2002-03 y 2003-04: arranque del rating)
GRID = {
    "k0": [10, 15, 20, 30, 40, 50, 60, 80, 100, 125, 150],
    **{name: values for name, values in ELO_GRID.items() if name not in ("k0", "lam")},
}


def market_score(matches: pd.DataFrame) -> np.ndarray:
    """Puntaje esperado del local según el mercado (p_local + 0,5 · p_empate); NaN sin cuotas válidas."""
    odds = matches[ODDS_COLUMNS].to_numpy(dtype=float, na_value=np.nan)
    ok = ~np.isnan(odds).any(axis=1) & (odds > 1).all(axis=1)
    out = np.full(len(matches), np.nan)
    if ok.any():
        p = shin_probabilities(odds[ok])
        out[ok] = p[:, 0] + 0.5 * p[:, 1]
    return out


def compute_odds_elo(matches: pd.DataFrame, params: EloParams, top_division: str = PREMIER_LEAGUE) -> pd.DataFrame:
    """ELO-Odds previo a cada partido: match_id, odds_elo_home, odds_elo_away."""
    df = matches.assign(**{SCORE_COLUMN: market_score(matches)})
    per_match, _ = compute_elo(df, replace(params, lam=0.0), top_division=top_division, score_column=SCORE_COLUMN)
    return per_match.rename(columns={"elo_home": "odds_elo_home", "elo_away": "odds_elo_away"})[
        ["match_id", "odds_elo_home", "odds_elo_away"]]


def calibrated_home_advantage(scores: np.ndarray) -> float:
    """h tal que 1 / (1 + 10^(-h/400)) = puntaje medio del local según el mercado."""
    s = float(np.nanmean(scores))
    return float(round(400 * np.log10(s / (1 - s)), 1))


def tune(matches: pd.DataFrame, start: EloParams, max_passes: int = 4) -> tuple[EloParams, float, list]:
    """Descenso por coordenadas sobre GRID, como src/features/tune_elo.tune, en partidos de Premier de TUNE_SEASONS."""
    matches = matches.sort_values(["date", "match_id"]).reset_index(drop=True)
    mask = ((matches["division"] == PREMIER_LEAGUE) & matches["season_start"].isin(TUNE_SEASONS)
            & matches["home_goals"].notna()).to_numpy()
    results = matches.loc[mask, "result"].astype(str).to_numpy()
    scores = market_score(matches)[mask]
    start = replace(start, lam=0.0, home_advantage=calibrated_home_advantage(scores))
    cache: dict[EloParams, float] = {}

    def score(p: EloParams) -> float:
        if p not in cache:
            ratings = compute_odds_elo(matches, p).set_index("match_id").loc[matches["match_id"]]
            diff = (ratings["odds_elo_home"] - ratings["odds_elo_away"]).to_numpy()[mask]
            cache[p] = rating_logloss(diff, results)
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
        if not improved:
            break
    return best, best_score, trace
