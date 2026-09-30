"""Entrena y exporta el modelo de producción.

Modelo: dos regresiones de Poisson sobre la diferencia de Elo (elegido en
validación, evaluado una vez en test; ver notebooks/03_modelo.ipynb). Se
reentrena con todas las temporadas COMPLETAS disponibles desde 2002-03, igual que
en la evaluación (reentrenamiento anual con ventana expansiva).

El artefacto es un JSON con los parámetros, no un pickle: como el modelo es
    log E[goles] = b0 + b1 * (elo_diff - media) / desvío
alcanza con guardar esos números. Es portable, auditable y no depende de la
versión de scikit-learn.

Uso:
    python -m src.serving.production
"""

import json
import logging
from datetime import date

import pandas as pd

from src.config import PROJECT_ROOT, TRAIN_SEASONS, season_start_year
from src.features.build import ELO_PARAMS_PATH, FEATURES_PATH
from src.models.experiments import PREDICTIONS_DIR, prepare
from src.models.feature_models import PoissonGLMModel
from src.serving.build_state import build_state
from src.serving.store import SERVING_MATCHES_PATH

logger = logging.getLogger(__name__)

PRODUCTION_DIR = PROJECT_ROOT / "models" / "production"
MODEL_PATH = PRODUCTION_DIR / "model.json"
FEATURES = ["elo_diff"]
ALPHA = 1e-4
PARAM_DECIMALS = 12


def export_params(model: PoissonGLMModel) -> dict:
    """Parámetros de las dos regresiones en escala original de la feature."""
    out = {}
    for name, pipe in (("home_goals", model.home_), ("away_goals", model.away_)):
        _, scaler, glm = pipe.named_steps.values()
        # Redondeo a 12 decimales: el orden de las sumas en punto flotante puede variar en ~1e-16
        # entre corridas y cambiaría el hash de versión sin que cambie el modelo.
        out[name] = {
            "intercept": round(float(glm.intercept_), PARAM_DECIMALS),
            "coef": round(float(glm.coef_[0]), PARAM_DECIMALS),
            "feature_mean": round(float(scaler.mean_[0]), PARAM_DECIMALS),
            "feature_scale": round(float(scaler.scale_[0]), PARAM_DECIMALS),
        }
    return out


def test_metrics_from_experiments() -> dict | None:
    """Métricas de la evaluación única en test (solo existen donde se corrieron los experimentos)."""
    path = PREDICTIONS_DIR / "test_results.csv"
    if not path.exists():
        return None
    test_results = pd.read_csv(path)
    main = test_results[test_results.config.str.startswith("family=poisson_glm")].iloc[0]
    market = test_results.set_index("config")
    return {
        "seasons": "2023-24 a 2025-26",
        "model": {k: float(main[k]) for k in ("log_loss", "rps", "brier", "accuracy", "ece")} | {"n": int(main["n"])},
        "bet365_pre_closing": {k: float(market.loc["mercado_bet365_precierre", k]) for k in ("log_loss", "rps", "brier", "accuracy")},
        "pinnacle_closing": {k: float(market.loc["mercado_pinnacle_cierre", k]) for k in ("log_loss", "rps", "brier", "accuracy")}
        | {"n": int(market.loc["mercado_pinnacle_cierre", "n"])},
    }


def train_production(features: pd.DataFrame, today: date | None = None,
                     previous_meta: dict | None = None) -> tuple[PoissonGLMModel, dict]:
    """Entrena con todas las temporadas completas. Las métricas de test describen la CONFIGURACIÓN
    (evaluada una sola vez): si no están los resultados de los experimentos (p. ej. en GitHub
    Actions), se conservan las del modelo anterior."""
    current = season_start_year(today or date.today())
    train = features[(features.season_start >= min(TRAIN_SEASONS)) & (features.season_start < current)
                     & features.played]
    model = PoissonGLMModel(FEATURES, alpha=ALPHA).fit(train)
    test_metrics = test_metrics_from_experiments() or (previous_meta or {}).get("test_metrics")
    if test_metrics is None:
        raise FileNotFoundError("No hay métricas de test: correr los experimentos o pasar el modelo anterior")
    meta = {
        "model": "Poisson (goles del local y del visitante) sobre la diferencia de Elo",
        "features": FEATURES,
        "alpha": ALPHA,
        "trained_on": {"seasons": f"{train.season.min()} a {train.season.max()}", "matches": int(len(train))},
        "trained_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "elo_params": json.loads(ELO_PARAMS_PATH.read_text(encoding="utf-8"))["params"],
        "test_metrics": test_metrics,
    }
    return model, {"params": export_params(model), "meta": meta}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    features = prepare(pd.read_parquet(FEATURES_PATH))
    _, artifact = train_production(features)
    PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Modelo de producción -> %s (%s)", MODEL_PATH, artifact["meta"]["trained_on"])
    serving = build_state()
    logger.info("Partidos para servir -> %s (%d)", SERVING_MATCHES_PATH, len(serving))


if __name__ == "__main__":
    main()
