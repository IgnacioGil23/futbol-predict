"""Evaluación preregistrada del candidato V: valor de mercado del plantel (docs/preregistro_valor.md, commit baa4849).

Corrección sin intercepto sobre el modelo base de cada liga por d = log(valor local) − log(valor visitante), con β
estimado en las temporadas de esa liga desde 2012-13 hasta la anterior a la predicha.

Uso:
    python -m src.models.squad_value_eval --out reports/challengers
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label
from src.data.leagues import LEAGUES
from src.data.transfermarkt import FIRST_SEASON, SQUAD_VALUES_PATH
from src.models.feature_models import PoissonGLMModel
from src.models.fpl_eval import OffsetPoisson
from src.models.home_level import load_frames
from src.models.replication import EVAL_SEASONS, TRAIN_START, log_loss_per_match, stratified_ci
from src.models.scoreline import outcome_probabilities, score_matrix
from src.serving.production import ALPHA, FEATURES as ELO

logger = logging.getLogger(__name__)

EARLY_GAMES = 4          # fechas 1 a 5: el local jugó 0 a 4 partidos de la temporada


def add_value_gap(df: pd.DataFrame, values: pd.DataFrame) -> pd.DataFrame:
    out = df.merge(values[["match_id", "squad_value_home", "squad_value_away"]], on="match_id", how="left")
    out["value_gap"] = (np.log(out["squad_value_home"]) - np.log(out["squad_value_away"])).fillna(0.0)
    return out


def walk_forward(df: pd.DataFrame, train_start: int, seasons: list[int] = EVAL_SEASONS) -> tuple[pd.DataFrame, dict]:
    out, betas = [], {}
    for s in seasons:
        base = PoissonGLMModel(ELO, alpha=ALPHA).fit(
            df[(df.season_start >= train_start) & (df.season_start < s) & df.played])
        train = df[(df.season_start >= FIRST_SEASON) & (df.season_start < s) & df.played]
        target = df[(df.season_start == s) & df.played]
        lam_tr, mu_tr = base._rates(train)
        x_tr = train[["value_gap"]].to_numpy(float)
        home = OffsetPoisson().fit(x_tr, train["home_goals"].to_numpy(float), np.log(lam_tr))
        away = OffsetPoisson().fit(x_tr, train["away_goals"].to_numpy(float), np.log(mu_tr))
        lam, mu = base._rates(target)
        x = target[["value_gap"]].to_numpy(float)
        frame = pd.DataFrame({"match_id": target["match_id"].to_numpy(), "season": target["season"].to_numpy(),
                              "result": target["result"].to_numpy(),
                              "early": (target["games_played_home"] <= EARLY_GAMES).to_numpy()})
        for name, (l, m) in {"base": (lam, mu), "cand": (np.exp(home.log_rate(x, np.log(lam))),
                                                          np.exp(away.log_rate(x, np.log(mu))))}.items():
            frame[[f"{name}_h", f"{name}_d", f"{name}_a"]] = outcome_probabilities(score_matrix(l, m))
        out.append(frame)
        betas[season_label(s)] = {"home": float(home.coef_[0]), "away": float(away.coef_[0]), "train": int(len(train))}
    return pd.concat(out, ignore_index=True), betas


def deltas(pred: pd.DataFrame) -> pd.Series:
    ll = {n: log_loss_per_match(pred.rename(columns={f"{n}_h": "p_home", f"{n}_d": "p_draw", f"{n}_a": "p_away"}))
          for n in ("base", "cand")}
    return ll["cand"] - ll["base"]


def run() -> dict:
    values = pd.read_parquet(SQUAD_VALUES_PATH)
    leagues, pooled, pooled_early = {}, {}, {}
    for code, df in load_frames().items():
        pred, betas = walk_forward(add_value_gap(df, values), TRAIN_START[code])
        d = deltas(pred).to_numpy()
        early = pred["early"].to_numpy()
        mean, ci = stratified_ci({"x": d})
        by_season = pd.Series(d).groupby(pred["season"].to_numpy()).mean()
        leagues[code] = {
            "name": LEAGUES.get(code, {"name": "Inglaterra"})["name"], "n": int(len(d)), "diff": mean, "ci": ci,
            "seasons_improved": int((by_season < 0).sum()), "seasons": int(len(by_season)),
            "early": {"n": int(early.sum()), "diff": float(d[early].mean())},
            "rest": {"n": int((~early).sum()), "diff": float(d[~early].mean())}, "betas": betas,
        }
        if code != "ENG":
            pooled[code], pooled_early[code] = d, d[early]
        logger.info("%-10s diff %+.4f IC95%% [%+.4f, %+.4f] · fechas 1-5 %+.4f · resto %+.4f", leagues[code]["name"],
                    mean, *ci, leagues[code]["early"]["diff"], leagues[code]["rest"]["diff"])
    mean, ci = stratified_ci(pooled)
    mean_e, ci_e = stratified_ci(pooled_early)
    return {
        "date": date.today().isoformat(), "preregistration": "docs/preregistro_valor.md",
        "seasons": [season_label(s) for s in EVAL_SEASONS],
        "pooled": {"n": int(sum(len(v) for v in pooled.values())), "diff": mean, "ci": ci, "signal": bool(ci[1] < 0),
                   "meets_rule": bool(ci[1] < 0 and mean <= -0.005)},
        "pooled_early": {"n": int(sum(len(v) for v in pooled_early.values())), "diff": mean_e, "ci": ci_e},
        "leagues": leagues,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/challengers"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"valor_plantel_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    p, e = report["pooled"], report["pooled_early"]
    logger.info("Conjunto: %+.4f [%+.4f, %+.4f] · señal %s · regla %s · fechas 1-5 %+.4f [%+.4f, %+.4f] -> %s",
                p["diff"], *p["ci"], p["signal"], p["meets_rule"], e["diff"], *e["ci"], path)


if __name__ == "__main__":
    main()
