"""Parámetros del rating por liga (docs/preregistro_ligas.md).

En España, Italia, Alemania y Francia se ajustan los dos ratings (Elo de cuotas y Elo de resultados) con la primera
división de 2004-05 a 2014-15, y se comparan contra los parámetros de Inglaterra en 2015-16 a 2025-26 con el modelo
que usa cada rating (Poisson sobre su diferencia, ventana expansiva). La liga se queda con sus propios parámetros solo
si la mejora cumple la regla preregistrada; si no, usa los de Inglaterra.

Uso:
    python -m src.models.league_params --out reports/leagues

Escribe configs/leagues/<liga>.json (los parámetros que usa cada liga y por qué) y el reporte.
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT, season_label
from src.data.leagues import LEAGUES, LEAGUES_DIR, matches_path
from src.features import odds_elo, tune_elo
from src.features.build import load_elo_params
from src.features.elo import EloParams, compute_elo
from src.features.odds_elo import compute_odds_elo, load_odds_elo_params
from src.models.odds_elo_eval import FIRST_TRAIN, market
from src.models.replication import EVAL_SEASONS, league_features, log_loss_per_match, stratified_ci, walk_forward

logger = logging.getLogger(__name__)

TUNE_SEASONS = list(range(2004, 2015))      # 2004-05 a 2014-15 (2002-03 y 2003-04: arranque del rating)
N_COMPARISONS = 8                           # 4 ligas x 2 ratings (Bonferroni)
MIN_IMPROVEMENT = 0.002
LEAGUE_CONFIG_DIR = PROJECT_ROOT / "configs" / "leagues"
RATINGS = {"odds_elo": "Elo de cuotas (modelo publicado)", "elo": "Elo de resultados (simulación de la temporada)"}


def decide(delta: np.ndarray, n_comparisons: int = N_COMPARISONS) -> dict:
    """Regla preregistrada: media ≤ −0,002 y el IC con Bonferroni completamente por debajo de 0."""
    level = 1 - 0.05 / n_comparisons
    mean, ci = stratified_ci({"liga": np.asarray(delta, dtype=float)}, level=level)
    _, ci95 = stratified_ci({"liga": np.asarray(delta, dtype=float)})
    return {"n": int(len(delta)), "diff": mean, "ci95": ci95, "ci_rule": ci, "level": level,
            "adopt": bool(mean <= -MIN_IMPROVEMENT and ci[1] < 0)}


def league_config_path(code: str) -> Path:
    return LEAGUE_CONFIG_DIR / f"{code}.json"


def load_league_params(code: str) -> tuple[EloParams, EloParams]:
    """(Elo de cuotas, Elo de resultados) de la liga; Inglaterra usa los de configs/."""
    if code == "ENG":
        return load_odds_elo_params(), load_elo_params()
    cfg = json.loads(league_config_path(code).read_text(encoding="utf-8"))
    return EloParams(**cfg["odds_elo"]["params"]), EloParams(**cfg["elo"]["params"])


def _features(code: str) -> pd.DataFrame:
    cached = LEAGUES_DIR / f"{code}_features.parquet"
    if not cached.exists():
        league_features(code).to_parquet(cached, index=False)
    return pd.read_parquet(cached)


def _with_rating(feats: pd.DataFrame, matches: pd.DataFrame, kind: str, params: EloParams, top: str) -> pd.DataFrame:
    """Variables con la diferencia de `kind` calculada con `params` (columna `rating_diff`)."""
    if kind == "odds_elo":
        r = compute_odds_elo(matches, params, top_division=top)
        diff = r["odds_elo_home"] - r["odds_elo_away"]
    else:
        r, _ = compute_elo(matches, params, top_division=top)
        diff = r["elo_home"] - r["elo_away"]
    rating = pd.DataFrame({"match_id": r["match_id"], "rating_diff": diff})
    return feats.drop(columns=["rating_diff"], errors="ignore").merge(rating, on="match_id", how="left")


def evaluate_league(code: str) -> dict:
    league = LEAGUES[code]
    top = league["top"]
    matches = pd.read_parquet(matches_path(code))
    feats = _features(code)
    england = {"odds_elo": load_odds_elo_params(), "elo": load_elo_params()}
    out = {"name": league["name"]}
    for kind in RATINGS:
        tuner = odds_elo.tune if kind == "odds_elo" else tune_elo.tune
        own, score, trace = tuner(matches, start=england[kind], division=top, seasons=TUNE_SEASONS)
        ll = {}
        for label, params in (("E", england[kind]), ("L", own)):
            df = _with_rating(feats, matches, kind, params, top)
            ll[label] = log_loss_per_match(walk_forward(df, ["rating_diff"], EVAL_SEASONS, FIRST_TRAIN[code]))
        delta = (ll["L"] - ll["E"].loc[ll["L"].index]).to_numpy()
        seasons = feats.set_index("match_id").loc[ll["L"].index, "season"].to_numpy()
        by_season = pd.Series(delta).groupby(seasons).mean()
        ll_m, _ = market(feats, ll["E"].index)
        decision = decide(delta)
        out[kind] = {
            "england_params": england[kind].to_dict(), "own_params": own.to_dict(), "tune_log_loss": score,
            "log_loss": {k: float(v.mean()) for k, v in ll.items()},
            "minus_bet365": {k: float((v.loc[ll_m.index] - ll_m).mean()) for k, v in ll.items()},
            "L_minus_E": decision, "seasons_improved": int((by_season < 0).sum()), "seasons": int(len(by_season)),
            "by_season": {s: float(v) for s, v in by_season.items()},
            "chosen": "L" if decision["adopt"] else "E", "trace_passes": int(trace[-1]["pass"]),
        }
        logger.info("%-9s %-9s L−E %+.4f IC%.2f%% [%+.4f, %+.4f] -> %s", league["name"], kind, decision["diff"],
                    100 * decision["level"], *decision["ci_rule"], out[kind]["chosen"])
    return out


def write_league_config(code: str, result: dict, report_path: Path) -> None:
    cfg = {"league": code, "name": result["name"], "preregistration": "docs/preregistro_ligas.md",
           "report": report_path.relative_to(PROJECT_ROOT).as_posix() if report_path.is_absolute() else report_path.as_posix()}
    for kind, label in RATINGS.items():
        r = result[kind]
        cfg[kind] = {"description": label, "source": "liga" if r["chosen"] == "L" else "Inglaterra",
                     "params": r["own_params"] if r["chosen"] == "L" else r["england_params"]}
    LEAGUE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    league_config_path(code).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "reports" / "leagues")
    parser.add_argument("--leagues", nargs="*", default=list(LEAGUES))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = {"date": date.today().isoformat(), "preregistration": "docs/preregistro_ligas.md",
              "tune_seasons": f"{season_label(TUNE_SEASONS[0])} a {season_label(TUNE_SEASONS[-1])}",
              "eval_seasons": [season_label(s) for s in EVAL_SEASONS],
              "rule": {"min_improvement": MIN_IMPROVEMENT, "level": 1 - 0.05 / N_COMPARISONS}, "leagues": {}}
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"parametros_{report['date']}.json"
    for code in args.leagues:
        report["leagues"][code] = evaluate_league(code)
        write_league_config(code, report["leagues"][code], path)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte: %s", path)


if __name__ == "__main__":
    main()
