"""Evaluación del Poisson bivariado (y su combinación con tiros al arco) contra el modelo actual.

Protocolo y candidatos fijados ANTES de correr (ver docs/model_card.md):
* Mismas 8 temporadas y ventana expansiva que la evaluación de tiros al arco
  (src/models/challenger.py): cada temporada 2015-16 .. 2022-23 se predice con modelos
  entrenados desde 2002-03 hasta la anterior. Las temporadas de test no se tocan.
* Candidatos: dependencia {constante, proporcional, proporcional+diagonal} × variables
  {Elo, Elo + tiros al arco con vida media 4}, más Elo + tiros al arco sin dependencia como
  referencia. La vida media 4 fue la mejor de tiros al arco EN ESTAS MISMAS temporadas: las
  combinaciones con tiros salen con sesgo optimista; su prueba limpia es julio de 2027.
* Dixon-Coles sobre las mismas regresiones se reporta como referencia (ya descartado).
* Regla, aprobada antes de ver resultados. Un candidato se promueve si cumple:
    (a) log loss de local/empate/visitante: mejora >= MIN_IMPROVEMENT e IC 95% por debajo de 0; o
    (b) log loss del marcador exacto: mejora >= MIN_IMPROVEMENT e IC 95% por debajo de 0,
        y en local/empate/visitante la diferencia media no es positiva.

Uso:
    python -m src.models.bivariate_eval --out reports/bivariate
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis.draw_diagnostic import cell_masks
from src.config import season_label
from src.features.build import FEATURES_PATH
from src.metrics import OUTCOMES
from src.models.challenger import MIN_IMPROVEMENT, compare, shot_features
from src.models.experiments import FIRST_TRAIN_SEASON, prepare
from src.models.feature_models import BivariatePoissonGLMModel, PoissonGLMModel
from src.models.scoreline import MAX_GOALS
from src.serving.production import ALPHA
from src.serving.production import FEATURES as ELO

logger = logging.getLogger(__name__)

EVAL_SEASONS = list(range(2015, 2023))          # 2015-16 .. 2022-23
SOT = ELO + shot_features(4, with_shots=False)  # Elo + tiros al arco a favor/en contra, vida media 4
REPORTED_GROUPS = ("0-0", "1-1", "2-2", "3-3 o más", "empates", "1-0 / 0-1", "2-1 / 1-2")


def models() -> dict:
    out = {"elo+dixon_coles (referencia)": lambda: PoissonGLMModel(ELO, alpha=ALPHA, dixon_coles=True),
           "elo+tiros_al_arco_hl4 (referencia)": lambda: PoissonGLMModel(SOT, alpha=ALPHA)}
    for feats_name, feats in (("elo", ELO), ("elo+tiros_al_arco_hl4", SOT)):
        for dep in ("constante", "proporcional", "proporcional+diagonal"):
            out[f"{feats_name}+bivariado_{dep}"] = (
                lambda feats=feats, dep=dep: BivariatePoissonGLMModel(feats, dep, alpha=ALPHA))
    return out


def walk_forward(make_model, df: pd.DataFrame, seasons: list[int]) -> tuple[pd.DataFrame, dict]:
    """Por partido: log loss de H/D/A, log loss del marcador exacto y masa esperada por grupo de marcadores."""
    masks = cell_masks(MAX_GOALS)
    rows, params = [], {}
    for season in seasons:
        train = df[(df.season_start >= FIRST_TRAIN_SEASON) & (df.season_start < season) & df.played]
        target = df[(df.season_start == season) & df.played]
        model = make_model().fit(train)
        fc = model.predict(target)
        k = target["result"].map({o: i for i, o in enumerate(OUTCOMES)}).to_numpy()
        x = np.minimum(target["home_goals"].to_numpy(int), MAX_GOALS)
        y = np.minimum(target["away_goals"].to_numpy(int), MAX_GOALS)
        idx = np.arange(len(target))
        out = pd.DataFrame({"match_id": target["match_id"].to_numpy(), "season": season,
                            "ll": -np.log(fc.probs[idx, k]), "ll_exact": -np.log(fc.matrix[idx, x, y])})
        for g in REPORTED_GROUPS:
            out[f"exp_{g}"] = fc.matrix[:, masks[g]].sum(axis=1)
            out[f"obs_{g}"] = masks[g][x, y].astype(float)
        rows.append(out)
        if hasattr(model, "dependence_"):
            params[season_label(season)] = model.dependence_.to_dict()
        elif getattr(model, "rho_", 0.0):
            params[season_label(season)] = {"rho": model.rho_}
    return pd.concat(rows, ignore_index=True).set_index("match_id"), params


def diagonal_table(pred: pd.DataFrame) -> dict:
    return {g: {"observed": int(pred[f"obs_{g}"].sum()), "expected": float(pred[f"exp_{g}"].sum()),
                "ratio": float(pred[f"obs_{g}"].sum() / pred[f"exp_{g}"].sum())} for g in REPORTED_GROUPS}


def decide(hda: dict, exact: dict) -> dict:
    rule_a = hda["promote"]
    rule_b = exact["promote"] and hda["diff"] <= 0
    return {"rule_a": bool(rule_a), "rule_b": bool(rule_b), "promote": bool(rule_a or rule_b)}


def run(features: pd.DataFrame, seasons: list[int]) -> dict:
    champ, _ = walk_forward(lambda: PoissonGLMModel(ELO, alpha=ALPHA), features, seasons)
    report = {
        "date": date.today().isoformat(), "seasons": [season_label(s) for s in seasons],
        "rule": {"min_improvement": MIN_IMPROVEMENT, "a": "H/D/A: mejora >= margen e IC 95% < 0",
                 "b": "marcador exacto: mejora >= margen e IC 95% < 0, sin empeorar H/D/A en media"},
        "champion": {"features": ELO, "n": int(len(champ)), "log_loss": float(champ["ll"].mean()),
                     "exact_score_log_loss": float(champ["ll_exact"].mean()), "diagonal": diagonal_table(champ)},
        "candidates": [],
    }
    for name, make in models().items():
        pred, params = walk_forward(make, features, seasons)
        hda = compare(champ["ll"], pred["ll"])
        exact = compare(champ["ll_exact"], pred["ll_exact"])
        by_season = {season_label(s): {"hda": float((g["ll"] - champ.loc[g.index, "ll"]).mean()),
                                       "exact": float((g["ll_exact"] - champ.loc[g.index, "ll_exact"]).mean())}
                     for s, g in pred.groupby("season")}
        entry = {"candidate": name, "reference": name.endswith("(referencia)"), "hda": hda, "exact": exact,
                 "decision": decide(hda, exact), "by_season": by_season, "params": params,
                 "diagonal": diagonal_table(pred)}
        report["candidates"].append(entry)
        logger.info("%-44s H/D/A %+.4f [%+.4f, %+.4f] | exacto %+.4f [%+.4f, %+.4f] | %s", name,
                    hda["diff"], hda["ci_low"], hda["ci_high"], exact["diff"], exact["ci_low"], exact["ci_high"],
                    "PROMUEVE" if entry["decision"]["promote"] else "no promueve")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/bivariate"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run(prepare(pd.read_parquet(FEATURES_PATH)), EVAL_SEASONS)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"evaluacion_{report['date']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte -> %s", path)


if __name__ == "__main__":
    main()
