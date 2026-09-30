"""Umbrales del monitoreo, calibrados con un backtest (no elegidos a ojo).

Se reproducen las predicciones del modelo de producción fuera de muestra
(reentrenamiento anual con ventana expansiva) en la era reciente, se calculan los
indicadores en ventanas móviles de WINDOW partidos y se toman percentiles: una
ventana "normal" cae entre p2,5 y p97,5 (fuera = atención) y casi nunca fuera de
p0,5 / p99,5 (fuera = alerta).

Por qué la brecha con el mercado y no el log loss absoluto: hay temporadas
intrínsecamente impredecibles para todos (en 2025-26 hasta Bet365 superó 1,0 de
log loss); comparar contra el mercado en los mismos partidos aísla el deterioro
propio del modelo.

Uso:
    python -m src.monitoring.thresholds      # -> configs/monitoring_thresholds.json
"""

import json
import logging
from datetime import date

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.features.build import FEATURES_PATH
from src.models.experiments import predict_feature_model, prepare
from src.models.feature_models import PoissonGLMModel
from src.odds import shin_probabilities
from src.serving.production import ALPHA, FEATURES

logger = logging.getLogger(__name__)

THRESHOLDS_PATH = PROJECT_ROOT / "configs" / "monitoring_thresholds.json"
WINDOW = 190                     # media temporada
BACKTEST_SEASONS = range(2016, 2026)   # era reciente: la brecha con el mercado cambió desde ~2016
INDICATORS = {
    "gap_vs_market": "Brecha de log loss contra Bet365 pre-cierre (modelo − mercado)",
    "goals_ratio": "Goles reales / goles esperados",
    "draws_diff_pp": "Empates reales − esperados (puntos porcentuales)",
    "home_residual": "Diferencia de gol real − esperada del local (goles por partido)",
}
# Solo la brecha es unilateral: que el modelo mejore frente al mercado no es un problema.
ONE_SIDED = {"gap_vs_market"}


def per_match_frame(pred: pd.DataFrame, info: pd.DataFrame) -> pd.DataFrame:
    """Una fila por partido con lo necesario para los indicadores.

    `pred`: match_id, p_home/p_draw/p_away, lam, mu. `info`: match_id, date, result, home_goals,
    away_goals y probabilidades de mercado market_home/draw/away (NaN si no hay).
    """
    d = pred.merge(info, on="match_id").sort_values(["date", "match_id"]).reset_index(drop=True)
    # Las probabilidades guardadas en disco están redondeadas (6 decimales el modelo, 4 el mercado
    # reconstruido): se renormalizan para que cada fila sume exactamente 1.
    for cols in (["p_home", "p_draw", "p_away"], ["market_home", "market_draw", "market_away"]):
        d[cols] = d[cols].astype(float).div(d[cols].astype(float).sum(axis=1), axis=0)
    k = d["result"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
    rows = np.arange(len(d))
    d["ll_model"] = -np.log(d[["p_home", "p_draw", "p_away"]].to_numpy()[rows, k])
    d["ll_market"] = -np.log(d[["market_home", "market_draw", "market_away"]].to_numpy()[rows, k])
    d["goals"] = d["home_goals"] + d["away_goals"]
    d["xg"] = d["lam"] + d["mu"]
    d["draw"] = (d["result"] == "D").astype(float)
    d["gd_residual"] = (d["home_goals"] - d["away_goals"]) - (d["lam"] - d["mu"])
    return d


def window_indicators(d: pd.DataFrame) -> dict:
    """Indicadores sobre un conjunto de partidos (típicamente, la ventana más reciente)."""
    with_market = d.dropna(subset=["ll_market"])
    return {
        "gap_vs_market": float((with_market.ll_model - with_market.ll_market).mean()) if len(with_market) else None,
        "goals_ratio": float(d.goals.sum() / d.xg.sum()) if len(d) else None,
        "draws_diff_pp": float((d.draw - d.p_draw).mean() * 100) if len(d) else None,
        "home_residual": float(d.gd_residual.mean()) if len(d) else None,
    }


def rolling_indicators(d: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    gap = (d.ll_model - d.ll_market)
    return pd.DataFrame({
        "gap_vs_market": gap.rolling(window).mean(),
        "goals_ratio": d.goals.rolling(window).sum() / d.xg.rolling(window).sum(),
        "draws_diff_pp": (d.draw - d.p_draw).rolling(window).mean() * 100,
        "home_residual": d.gd_residual.rolling(window).mean(),
    }).dropna()


def compute_thresholds() -> dict:
    features = prepare(pd.read_parquet(FEATURES_PATH))
    pred = predict_feature_model(lambda: PoissonGLMModel(FEATURES, alpha=ALPHA), features, list(BACKTEST_SEASONS))
    info = features[["match_id", "date", "result", "home_goals", "away_goals"]].copy()
    info[["home_goals", "away_goals"]] = info[["home_goals", "away_goals"]].astype(float)
    odds = features[["b365_home", "b365_draw", "b365_away"]].to_numpy(float)
    info[["market_home", "market_draw", "market_away"]] = shin_probabilities(odds)
    d = per_match_frame(pred, info.dropna(subset=["market_home"]))
    roll = rolling_indicators(d)
    q = roll.quantile([0.005, 0.025, 0.5, 0.975, 0.995])
    out = {}
    for name in INDICATORS:
        out[name] = {
            "description": INDICATORS[name],
            "one_sided": name in ONE_SIDED,
            "p0.5": float(q.loc[0.005, name]), "p2.5": float(q.loc[0.025, name]),
            "median": float(q.loc[0.5, name]),
            "p97.5": float(q.loc[0.975, name]), "p99.5": float(q.loc[0.995, name]),
        }
    return {
        "computed_on": date.today().isoformat(),
        "window": WINDOW,
        "backtest": {"seasons": f"{min(BACKTEST_SEASONS)}-{(min(BACKTEST_SEASONS) + 1) % 100:02d} a "
                                f"{max(BACKTEST_SEASONS)}-{(max(BACKTEST_SEASONS) + 1) % 100:02d}",
                     "matches": int(len(d)), "rolling_windows": int(len(roll)),
                     "method": "predicciones fuera de muestra del modelo de producción (reentrenamiento anual); "
                               "mercado = Bet365 pre-cierre sin margen (Shin)"},
        "levels": {"atencion": "fuera de [p2.5, p97.5]", "alerta": "fuera de [p0.5, p99.5]"},
        "indicators": out,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    th = compute_thresholds()
    THRESHOLDS_PATH.write_text(json.dumps(th, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, v in th["indicators"].items():
        logger.info("%-15s p0.5 %+.4f  p2.5 %+.4f  mediana %+.4f  p97.5 %+.4f  p99.5 %+.4f",
                    name, v["p0.5"], v["p2.5"], v["median"], v["p97.5"], v["p99.5"])


if __name__ == "__main__":
    main()
