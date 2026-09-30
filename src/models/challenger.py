"""Comparación champion / challenger con validación temporal y una regla de decisión fijada de antemano.

Protocolo:
* Para cada temporada de evaluación S, cada modelo se entrena con las temporadas
  2002-03 .. S-1 y predice S (ventana expansiva). Así los dos modelos compiten en
  los mismos partidos, que ninguno vio al entrenar.
* Se compara el log loss partido a partido (diferencia pareada) con IC 95% por
  bootstrap.
* REGLA (definida antes de ver los resultados, ver docs/monitoring): el challenger
  gana solo si mejora el log loss en al menos MIN_IMPROVEMENT y el IC 95% de la
  diferencia queda completamente por debajo de 0. Probar varios candidatos sobre los
  mismos partidos infla la chance de un falso positivo: el margen mínimo lo compensa.

Uso:
    python -m src.models.challenger --seasons 2015-2022 --out reports/challengers
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.build import FEATURES_PATH
from src.features.team_state import SHOTS_HALFLIVES
from src.metrics import OUTCOMES, summarize
from src.models.experiments import predict_feature_model, prepare
from src.models.feature_models import PoissonGLMModel
from src.serving.production import ALPHA, FEATURES as CHAMPION_FEATURES

logger = logging.getLogger(__name__)

MIN_IMPROVEMENT = 0.005
N_BOOT = 10_000


def shot_features(halflife: int, with_shots: bool) -> list[str]:
    stats = ["sot_f", "sot_a"] + (["sh_f", "sh_a"] if with_shots else [])
    return [f"{s}_hl{halflife}_{side}" for side in ("home", "away") for s in stats]


def candidates() -> dict[str, list[str]]:
    """Challengers: Elo + tiros al arco (y opcionalmente tiros), con distintas vidas medias."""
    out = {}
    for hl in SHOTS_HALFLIVES:
        out[f"elo+tiros_al_arco_hl{hl}"] = CHAMPION_FEATURES + shot_features(hl, with_shots=False)
        out[f"elo+tiros+tiros_al_arco_hl{hl}"] = CHAMPION_FEATURES + shot_features(hl, with_shots=True)
    return out


def walk_forward(features: pd.DataFrame, feats: list[str], seasons: list[int]) -> pd.DataFrame:
    return predict_feature_model(lambda: PoissonGLMModel(feats, alpha=ALPHA), features, seasons)


def per_match_log_loss(pred: pd.DataFrame, features: pd.DataFrame) -> pd.Series:
    d = pred.merge(features[["match_id", "result"]], on="match_id")
    k = d["result"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy()
    p = d[["p_home", "p_draw", "p_away"]].to_numpy()[np.arange(len(d)), k]
    return pd.Series(-np.log(p), index=d["match_id"].to_numpy())


def compare(champion: pd.Series, challenger: pd.Series, n_boot: int = N_BOOT, seed: int = 0) -> dict:
    """Diferencia de log loss challenger - champion en los partidos comunes, con IC 95% y la decisión."""
    common = champion.index.intersection(challenger.index)
    delta = (challenger[common] - champion[common]).to_numpy()
    rng = np.random.default_rng(seed)
    boots = delta[rng.integers(0, len(delta), size=(n_boot, len(delta)))].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    wins = bool(delta.mean() <= -MIN_IMPROVEMENT and hi < 0)
    return {"n": int(len(delta)), "diff": float(delta.mean()), "ci_low": float(lo), "ci_high": float(hi),
            "promote": wins}


def run(seasons: list[int], features: pd.DataFrame | None = None) -> dict:
    features = features if features is not None else prepare(pd.read_parquet(FEATURES_PATH))
    champ_pred = walk_forward(features, CHAMPION_FEATURES, seasons)
    champ_ll = per_match_log_loss(champ_pred, features)
    champ_summary = summarize(champ_pred[["p_home", "p_draw", "p_away"]].to_numpy(),
                              champ_pred.merge(features[["match_id", "result"]], on="match_id")["result"].to_numpy())
    results = []
    for name, feats in candidates().items():
        pred = walk_forward(features, feats, seasons)
        res = compare(champ_ll, per_match_log_loss(pred, features))
        # Diferencia por temporada: ¿la mejora es estable o viene de una sola temporada?
        by_season = {}
        merged = pred.merge(features[["match_id", "season"]], on="match_id")
        ll = per_match_log_loss(pred, features)
        for season, ids in merged.groupby("season")["match_id"]:
            by_season[season] = float((ll[ids.to_numpy()] - champ_ll[ids.to_numpy()]).mean())
        results.append({"candidate": name, "features": feats, **res, "by_season": by_season})
        logger.info("%-36s diff %+.4f  IC95%% [%+.4f, %+.4f]  %s", name, res["diff"], res["ci_low"], res["ci_high"],
                    "PROMUEVE" if res["promote"] else "no promueve")
    return {
        "date": date.today().isoformat(), "seasons": [f"{s}-{(s + 1) % 100:02d}" for s in seasons],
        "rule": {"min_improvement": MIN_IMPROVEMENT, "ci": "95% bootstrap pareado, debe quedar por debajo de 0"},
        "champion": {"features": CHAMPION_FEATURES, "log_loss": champ_summary["log_loss"], "n": champ_summary["n"]},
        "candidates": sorted(results, key=lambda r: r["diff"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", default="2015-2022", help="Rango de años de inicio de temporada, p. ej. 2015-2022")
    parser.add_argument("--out", type=Path, default=Path("reports/challengers"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    a, b = map(int, args.seasons.split("-"))
    report = run(list(range(a, b + 1)))
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"challengers_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte -> %s", path)


if __name__ == "__main__":
    main()
