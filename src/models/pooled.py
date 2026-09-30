"""Modelos entrenados con las cinco ligas juntas: P-GLM y P-XGB (docs/preregistro_combinado.md, commit a5d9ddd).

Cada temporada S de 2015-16 a 2025-26 se predice con modelos entrenados con las cinco primeras divisiones desde
2006-07 hasta S-1; se comparan, liga por liga y en los mismos partidos, contra el modelo de cada liga (B0: Poisson
sobre la diferencia de Elo) y contra el candidato de tiros de cada liga (B1).

Uso:
    python -m src.models.pooled --out reports/challengers
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from src.config import season_label
from src.data.leagues import LEAGUES
from src.models.confirm_shots import CANDIDATE as SHOTS
from src.models.experiments import GOALS, OTHER, TABLE
from src.models.feature_models import PoissonGLMModel, XGBPoissonModel
from src.models.home_level import load_frames
from src.models.replication import EVAL_SEASONS, TRAIN_START, log_loss_per_match, stratified_ci
from src.serving.production import ALPHA
from src.serving.production import FEATURES as ELO

logger = logging.getLogger(__name__)

POOLED_START = 2006
CODES = ["ENG", *LEAGUES]
LEAGUE_DUMMIES = [f"league_{c}" for c in CODES]
FEATURES = ELO + GOALS + TABLE + OTHER + [c for c in SHOTS if c not in ELO] + LEAGUE_DUMMIES
CANDIDATES = {
    "P-GLM": lambda: PoissonGLMModel(FEATURES, alpha=ALPHA),
    "P-XGB": lambda: XGBPoissonModel(FEATURES, n_estimators=300, max_depth=2, learning_rate=0.03,
                                     min_child_weight=50, subsample=0.8, seed=0),
}


def pooled_frame(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    for code, df in frames.items():
        part = df.copy()
        part["league"] = code
        for c in CODES:
            part[f"league_{c}"] = float(c == code)
        parts.append(part)
    cols = sorted(set.intersection(*(set(p.columns) for p in parts)))
    return pd.concat([p[cols] for p in parts], ignore_index=True)


def predictions(make_model, train: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    fc = make_model().fit(train).predict(target)
    return pd.DataFrame({"match_id": target["match_id"].to_numpy(), "result": target["result"].to_numpy(),
                         "league": target["league"].to_numpy(), "season": target["season"].to_numpy(),
                         "p_home": fc.probs[:, 0], "p_draw": fc.probs[:, 1], "p_away": fc.probs[:, 2]})


def run() -> dict:
    data = pooled_frame(load_frames())
    ll: dict[str, list[pd.Series]] = {k: [] for k in ["B0", "B1", *CANDIDATES]}
    meta, importance = [], None
    for s in EVAL_SEASONS:
        target = data[(data.season_start == s) & data.played]
        pooled_train = data[(data.season_start >= POOLED_START) & (data.season_start < s) & data.played]
        for name, make in CANDIDATES.items():
            pred = predictions(make, pooled_train, target)
            ll[name].append(log_loss_per_match(pred))
            if name == "P-XGB" and s == EVAL_SEASONS[-1]:
                model = make().fit(pooled_train)
                importance = {n: dict(sorted(zip(FEATURES, map(float, m.feature_importances_)),
                                             key=lambda kv: -kv[1])[:12])
                              for n, m in (("home_goals", model.home_), ("away_goals", model.away_))}
        for code in CODES:
            own = data[(data.league == code) & (data.season_start >= TRAIN_START[code]) & (data.season_start < s) & data.played]
            tgt = target[target.league == code]
            ll["B0"].append(log_loss_per_match(predictions(lambda: PoissonGLMModel(ELO, alpha=ALPHA), own, tgt)))
            ll["B1"].append(log_loss_per_match(predictions(lambda: PoissonGLMModel(SHOTS, alpha=ALPHA), own, tgt)))
        meta.append(target[["match_id", "league", "season"]])
        logger.info("%s: %d partidos de entrenamiento combinado", season_label(s), len(pooled_train))
    series = {k: pd.concat(v) for k, v in ll.items()}
    info = pd.concat(meta).set_index("match_id")

    def compare(a: str, b: str, leagues: list[str]) -> dict:
        deltas = {}
        for code in leagues:
            ids = info.index[info.league == code]
            deltas[code] = (series[a][ids] - series[b][ids]).to_numpy()
        mean, ci = stratified_ci(deltas)
        per = {}
        for code, d in deltas.items():
            m, c = stratified_ci({code: d})
            per[code] = {"diff": m, "ci": c}
        return {"n": int(sum(len(d) for d in deltas.values())), "diff": mean, "ci": ci, "signal": bool(ci[1] < 0),
                "meets_rule": bool(ci[1] < 0 and mean <= -0.005), "per_league": per}

    four = list(LEAGUES)
    report = {"date": date.today().isoformat(), "preregistration": "docs/preregistro_combinado.md",
              "features": FEATURES, "seasons": [season_label(s) for s in EVAL_SEASONS], "results": {}}
    for name in CANDIDATES:
        report["results"][name] = {"vs_B0": compare(name, "B0", four), "vs_B1": compare(name, "B1", four),
                                   "premier_vs_B0": compare(name, "B0", ["ENG"])}
        r = report["results"][name]
        logger.info("%s vs B0 %+.4f [%+.4f, %+.4f] · vs tiros %+.4f [%+.4f, %+.4f] · Premier vs B0 %+.4f", name,
                    r["vs_B0"]["diff"], *r["vs_B0"]["ci"], r["vs_B1"]["diff"], *r["vs_B1"]["ci"], r["premier_vs_B0"]["diff"])
    report["reference_B1_vs_B0"] = compare("B1", "B0", four)
    report["xgb_importance_last_season"] = importance
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/challengers"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"combinado_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte -> %s", path)


if __name__ == "__main__":
    main()
