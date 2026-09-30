"""Diagnóstico previo al Poisson bivariado: ¿el modelo actual subestima los empates y los marcadores parejos?

Protocolo (fijado antes de mirar): solo temporadas de ENTRENAMIENTO. Cada temporada
2003-04 .. 2014-15 se predice con el modelo de producción (Poisson sobre la diferencia
de Elo) entrenado con las temporadas anteriores desde 2002-03, igual que en la
validación. Las 8 temporadas donde se decide (2015-16 .. 2022-23) y las de test no se
miran acá.

Qué se mide:
* Por celda de la diagonal (0-0, 1-1, 2-2, 3-3 o más) y en agregados (empates, partidos
  con 5+ goles): partidos observados / esperados por el modelo, con IC 95% por
  bootstrap de partidos.
* La covarianza residual E[(X - lam)(Y - mu)]: con goles independientes vale 0; en el
  Poisson bivariado (Karlis y Ntzoufras 2003) es exactamente lambda3. Es la estimación
  directa, sin modelo, de la correlación que el bivariado agregaría.

Uso:
    python -m src.analysis.draw_diagnostic --out reports/bivariate/diagnostico.json
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import season_label
from src.features.build import FEATURES_PATH
from src.models.experiments import predict_feature_model, prepare
from src.models.feature_models import PoissonGLMModel
from src.models.scoreline import score_matrix
from src.serving.production import ALPHA, FEATURES

logger = logging.getLogger(__name__)

DIAGNOSTIC_SEASONS = list(range(2003, 2015))   # 2003-04 .. 2014-15: todas de entrenamiento
N_BOOT = 10_000


def cell_masks(max_goals: int) -> dict[str, np.ndarray]:
    """Máscaras booleanas (max_goals+1, max_goals+1) de los grupos de marcadores a comparar."""
    g = np.arange(max_goals + 1)
    x, y = np.meshgrid(g, g, indexing="ij")
    return {
        "0-0": (x == 0) & (y == 0),
        "1-1": (x == 1) & (y == 1),
        "2-2": (x == 2) & (y == 2),
        "3-3 o más": (x == y) & (x >= 3),
        "empates": x == y,
        "no empates": x != y,
        "5+ goles": x + y >= 5,
        "1-0 / 0-1": ((x == 1) & (y == 0)) | ((x == 0) & (y == 1)),
        "2-1 / 1-2": ((x == 2) & (y == 1)) | ((x == 1) & (y == 2)),
    }


def ratio_ci(observed: np.ndarray, expected: np.ndarray, rng: np.random.Generator, n_boot: int) -> tuple[float, float]:
    """IC 95% de sum(observado)/sum(esperado) remuestreando partidos."""
    idx = rng.integers(0, len(observed), size=(n_boot, len(observed)))
    boots = observed[idx].sum(axis=1) / expected[idx].sum(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(lo), float(hi)


def diagnose(features: pd.DataFrame, seasons: list[int], n_boot: int = N_BOOT, seed: int = 0) -> dict:
    pred = predict_feature_model(lambda: PoissonGLMModel(FEATURES, alpha=ALPHA), features, seasons)
    d = pred.merge(features[["match_id", "season", "home_goals", "away_goals"]], on="match_id")
    matrix = score_matrix(d["lam"].to_numpy(), d["mu"].to_numpy())
    x = d["home_goals"].to_numpy(int)
    y = d["away_goals"].to_numpy(int)
    n_cells = matrix.shape[1]
    xc, yc = np.minimum(x, n_cells - 1), np.minimum(y, n_cells - 1)
    rng = np.random.default_rng(seed)

    groups = {}
    for name, mask in cell_masks(n_cells - 1).items():
        observed = mask[xc, yc].astype(float)          # 1 si el partido cayó en el grupo
        expected = matrix[:, mask].sum(axis=1)          # P del grupo según el modelo
        lo, hi = ratio_ci(observed, expected, rng, n_boot)
        groups[name] = {"observed": int(observed.sum()), "expected": float(expected.sum()),
                        "ratio": float(observed.sum() / expected.sum()), "ratio_ci": [lo, hi]}

    resid = (x - d["lam"].to_numpy()) * (y - d["mu"].to_numpy())
    boots = resid[rng.integers(0, len(resid), size=(n_boot, len(resid)))].mean(axis=1)
    cov_by_season = {s: float(g) for s, g in pd.Series(resid).groupby(d["season"].to_numpy()).mean().items()}
    return {
        "seasons": [season_label(s) for s in seasons],
        "matches": int(len(d)),
        "model": f"Poisson sobre {FEATURES} (producción), ventana expansiva desde 2002-03",
        "groups": groups,
        "residual_covariance": {"mean": float(resid.mean()), "ci": [float(v) for v in np.percentile(boots, [2.5, 97.5])],
                                "by_season": cov_by_season},
        "goals": {"home_observed": float(x.mean()), "home_expected": float(d["lam"].mean()),
                  "away_observed": float(y.mean()), "away_expected": float(d["mu"].mean())},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/bivariate/diagnostico.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = diagnose(prepare(pd.read_parquet(FEATURES_PATH)), DIAGNOSTIC_SEASONS)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, g in report["groups"].items():
        logger.info("%-11s obs %4d  esp %7.1f  ratio %.3f  IC95%% [%.3f, %.3f]", name, g["observed"], g["expected"],
                    g["ratio"], *g["ratio_ci"])
    c = report["residual_covariance"]
    logger.info("Covarianza residual %.4f  IC95%% [%.4f, %.4f]", c["mean"], *c["ci"])
    logger.info("Reporte -> %s", args.out)


if __name__ == "__main__":
    main()
