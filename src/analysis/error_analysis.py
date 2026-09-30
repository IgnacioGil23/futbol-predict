"""Análisis de errores: ¿dónde pierde el modelo contra el mercado?

Descriptivo: no elige ni ajusta ningún modelo, así que no consume datos de evaluación. Sirve para decidir qué
información falta.

* Partidos: Premier League 2015-16 a 2025-26, cada temporada predicha por el modelo de producción entrenado con
  las temporadas anteriores (ventana expansiva desde 2002-03), con cuotas de Bet365 pre-cierre (margen quitado
  por el método de Shin).
* Brecha por partido = log loss del modelo − log loss del mercado (positivo = el mercado predijo mejor).
* Cortes fijados antes de mirar:
    1. momento de la temporada (partidos jugados por el local antes de este: 0-4, 5-9, 10-18, 19-37);
    2. equipos recién ascendidos (alguno de los dos no jugó la Premier la temporada anterior), y cruzado con 1;
    3. qué tan claro es el favorito según el mercado (probabilidad máxima: < 0,45, 0,45-0,60, 0,60-0,75, ≥ 0,75);
    4. resultado real (local, empate, visitante);
    5. desacuerdo entre modelo y mercado (diferencia absoluta en la probabilidad del local: < 5, 5-10, ≥ 10 puntos);
    6. temporada;
    7. equipo (cada partido cuenta para los dos equipos).
* Para cada grupo: partidos, brecha media con IC 95% (bootstrap de partidos) y qué parte de la brecha total explica.
* Además: probabilidad media del modelo y del mercado para cada resultado contra la frecuencia real (sesgos).

Uso:
    python -m src.analysis.error_analysis --out reports/analysis
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PREMIER_LEAGUE, season_label
from src.data.load import load_matches
from src.features.build import FEATURES_PATH
from src.metrics import OUTCOMES
from src.models.experiments import predict_feature_model, prepare
from src.models.feature_models import PoissonGLMModel
from src.odds import shin_probabilities
from src.serving.production import ALPHA, FEATURES

logger = logging.getLogger(__name__)

SEASONS = list(range(2015, 2026))
N_BOOT = 5_000
MIN_TEAM_MATCHES = 76          # equipos con al menos 2 temporadas en el período


def per_match_frame(features: pd.DataFrame, promoted: set[tuple[int, str]]) -> pd.DataFrame:
    pred = predict_feature_model(lambda: PoissonGLMModel(FEATURES, alpha=ALPHA), features, SEASONS)
    d = pred.merge(features, on="match_id")
    odds = d[["b365_home", "b365_draw", "b365_away"]].to_numpy(float)
    d = d[~np.isnan(odds).any(axis=1)].reset_index(drop=True)
    market = shin_probabilities(d[["b365_home", "b365_draw", "b365_away"]].to_numpy(float))
    d[["m_home", "m_draw", "m_away"]] = market
    k = d["result"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy()
    rows = np.arange(len(d))
    d["ll_model"] = -np.log(d[["p_home", "p_draw", "p_away"]].to_numpy()[rows, k])
    d["ll_market"] = -np.log(market[rows, k])
    d["gap"] = d["ll_model"] - d["ll_market"]
    d["promoted_home"] = [(s, t) in promoted for s, t in zip(d["season_start"], d["home_team"])]
    d["promoted_away"] = [(s, t) in promoted for s, t in zip(d["season_start"], d["away_team"])]
    return d


def promoted_teams(matches: pd.DataFrame) -> set[tuple[int, str]]:
    """(temporada, equipo) para los que jugaron la Premier esa temporada pero no la anterior."""
    pl = matches[matches.division == PREMIER_LEAGUE]
    members = {s: set(g.home_team) | set(g.away_team) for s, g in pl.groupby("season_start")}
    return {(s, t) for s, teams in members.items() for t in teams if s - 1 in members and t not in members[s - 1]}


def summarize_groups(d: pd.DataFrame, key: pd.Series, total_gap: float, rng: np.random.Generator) -> list[dict]:
    out = []
    for name, g in d.groupby(key, sort=True):
        gap = g["gap"].to_numpy()
        boots = gap[rng.integers(0, len(gap), size=(N_BOOT, len(gap)))].mean(axis=1)
        out.append({"group": str(name), "n": int(len(g)), "gap": float(gap.mean()),
                    "ci": [float(v) for v in np.percentile(boots, [2.5, 97.5])],
                    "share_of_total_gap": float(gap.sum() / total_gap),
                    "model_log_loss": float(g["ll_model"].mean()), "market_log_loss": float(g["ll_market"].mean())})
    return out


def team_view(d: pd.DataFrame, rng: np.random.Generator) -> list[dict]:
    long = pd.concat([d[["home_team", "gap", "season"]].rename(columns={"home_team": "team"}),
                      d[["away_team", "gap", "season"]].rename(columns={"away_team": "team"})])
    out = []
    for team, g in long.groupby("team"):
        if len(g) < MIN_TEAM_MATCHES:
            continue
        gap = g["gap"].to_numpy()
        boots = gap[rng.integers(0, len(gap), size=(N_BOOT, len(gap)))].mean(axis=1)
        out.append({"team": team, "n": int(len(g)), "gap": float(gap.mean()),
                    "ci": [float(v) for v in np.percentile(boots, [2.5, 97.5])]})
    return sorted(out, key=lambda r: -r["gap"])


def bias_table(d: pd.DataFrame) -> dict:
    actual = {o: float((d["result"] == o).mean()) for o in OUTCOMES}
    return {o: {"actual": actual[o], "model": float(d[f"p_{n}"].mean()), "market": float(d[f"m_{n}"].mean())}
            for o, n in zip(OUTCOMES, ("home", "draw", "away"))}


def analyze(features: pd.DataFrame, matches: pd.DataFrame, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    d = per_match_frame(features, promoted_teams(matches))
    total = float(d["gap"].sum())
    phase = pd.cut(d["games_played_home"], [-1, 4, 9, 18, 37], labels=["0-4", "5-9", "10-18", "19-37"])
    promoted = np.where(d["promoted_home"] | d["promoted_away"], "con ascendido", "sin ascendido")
    fav = pd.cut(d[["m_home", "m_draw", "m_away"]].max(axis=1), [0, 0.45, 0.60, 0.75, 1.0],
                 labels=["< 0,45", "0,45-0,60", "0,60-0,75", ">= 0,75"], right=False)
    disagreement = pd.cut((d["p_home"] - d["m_home"]).abs(), [0, 0.05, 0.10, 1.0],
                          labels=["< 5 pts", "5-10 pts", ">= 10 pts"], right=False)
    cuts = {
        "momento_de_la_temporada": phase,
        "ascendidos": pd.Series(promoted, index=d.index),
        "ascendidos_x_momento": pd.Series(promoted, index=d.index) + " · fecha " + phase.astype(str),
        "favorito_del_mercado": fav,
        "resultado_real": d["result"],
        "desacuerdo_modelo_mercado": disagreement,
        "temporada": d["season"],
    }
    report = {
        "date": date.today().isoformat(), "seasons": [season_label(s) for s in SEASONS], "n": int(len(d)),
        "overall": {"model_log_loss": float(d["ll_model"].mean()), "market_log_loss": float(d["ll_market"].mean()),
                    "gap": float(d["gap"].mean())},
        "cuts": {name: summarize_groups(d, key, total, rng) for name, key in cuts.items()},
        "teams": team_view(d, rng),
        "bias": bias_table(d),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/analysis"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = analyze(prepare(pd.read_parquet(FEATURES_PATH)), load_matches())
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"analisis_errores_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Brecha media %.4f en %d partidos -> %s", report["overall"]["gap"], report["n"], path)


if __name__ == "__main__":
    main()
