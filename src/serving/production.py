"""Entrena y exporta el modelo de producción.

Modelo (desde el 01/10/2026): dos regresiones de Poisson sobre la diferencia del rating basado en cuotas
(ELO-Odds; src/features/odds_elo.py). Cumplió la regla preregistrada en docs/preregistro_cuotas.md (cinco ligas,
2015-16 a 2025-26: −0,0084 de log loss contra el modelo anterior) y pasó a producción por la enmienda de ese
preregistro. El modelo anterior (Poisson sobre el Elo de resultados) queda congelado en models/elo/model.json: lo
usan la simulación de la temporada y su registro en paralelo durante 2026-27.

Se reentrena con todas las temporadas COMPLETAS desde 2004-05 (el ELO-Odds arranca con las cuotas de 2002-03; sus
dos primeras temporadas son de arranque, como en la evaluación preregistrada).

El artefacto es un JSON con los parámetros, no un pickle: como el modelo es
    log E[goles] = b0 + b1 * (diferencia de rating - media) / desvío
alcanza con guardar esos números. Es portable, auditable y no depende de la
versión de scikit-learn.

Uso:
    python -m src.serving.production
"""

import json
import logging
from datetime import date

import pandas as pd

from src.config import PROJECT_ROOT, TEST_SEASONS, season_label, season_start_year
from src.features.build import ELO_PARAMS_PATH, FEATURES_PATH
from src.features.odds_elo import ODDS_ELO_PARAMS_PATH
from src.metrics import summarize
from src.models.experiments import predict_feature_model, prepare
from src.models.feature_models import PoissonGLMModel
from src.serving.build_state import build_state
from src.serving.store import SERVING_MATCHES_PATH

logger = logging.getLogger(__name__)

PRODUCTION_DIR = PROJECT_ROOT / "models" / "production"
MODEL_PATH = PRODUCTION_DIR / "model.json"
ELO_MODEL_PATH = PROJECT_ROOT / "models" / "elo" / "model.json"   # modelo anterior, congelado
FEATURES = ["odds_elo_diff"]
RATING = "odds_elo"
FIRST_TRAIN_SEASON = 2004
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


def test_metrics(features: pd.DataFrame, previous_meta: dict | None) -> dict:
    """Métricas en test (2023-24 a 2025-26) de esta configuración, cada temporada predicha con un modelo entrenado
    con las anteriores. Las del mercado son de los mismos partidos y no cambian: se toman del artefacto anterior."""
    markets = (previous_meta or {}).get("test_metrics")
    if markets is None:
        raise FileNotFoundError("Faltan las métricas del mercado en test: pasar el artefacto anterior")
    pred = predict_feature_model(lambda: PoissonGLMModel(FEATURES, alpha=ALPHA), features, list(TEST_SEASONS),
                                 first_train=FIRST_TRAIN_SEASON)
    results = pred.merge(features[["match_id", "result"]], on="match_id")["result"].astype(str).to_numpy()
    model = summarize(pred[["p_home", "p_draw", "p_away"]].to_numpy(), results)
    return {
        "seasons": f"{season_label(min(TEST_SEASONS))} a {season_label(max(TEST_SEASONS))}",
        "model": {k: float(model[k]) for k in ("log_loss", "rps", "brier", "accuracy", "ece")} | {"n": int(model["n"])},
        "bet365_pre_closing": markets["bet365_pre_closing"],
        "pinnacle_closing": markets["pinnacle_closing"],
    }


def train_production(features: pd.DataFrame, today: date | None = None,
                     previous_meta: dict | None = None) -> tuple[PoissonGLMModel, dict]:
    """Entrena con todas las temporadas completas desde FIRST_TRAIN_SEASON."""
    current = season_start_year(today or date.today())
    train = features[(features.season_start >= FIRST_TRAIN_SEASON) & (features.season_start < current)
                     & features.played]
    model = PoissonGLMModel(FEATURES, alpha=ALPHA).fit(train)
    meta = {
        "model": "Poisson (goles del local y del visitante) sobre la diferencia del rating basado en cuotas (ELO-Odds)",
        "features": FEATURES,
        "rating": RATING,
        "alpha": ALPHA,
        "trained_on": {"seasons": f"{train.season.min()} a {train.season.max()}", "matches": int(len(train))},
        "trained_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        # Parámetros del rating que usa el modelo (entran en el hash de versión).
        "elo_params": json.loads(ODDS_ELO_PARAMS_PATH.read_text(encoding="utf-8"))["params"],
        "results_elo_params": json.loads(ELO_PARAMS_PATH.read_text(encoding="utf-8"))["params"],
        "preregistration": "docs/preregistro_cuotas.md",
        "test_metrics": test_metrics(features, previous_meta),
    }
    return model, {"params": export_params(model), "meta": meta}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    features = prepare(pd.read_parquet(FEATURES_PATH))
    previous = json.loads(MODEL_PATH.read_text(encoding="utf-8"))["meta"] if MODEL_PATH.exists() else None
    _, artifact = train_production(features, previous_meta=previous)
    PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Modelo de producción -> %s (%s)", MODEL_PATH, artifact["meta"]["trained_on"])
    serving = build_state()
    logger.info("Partidos para servir -> %s (%d)", SERVING_MATCHES_PATH, len(serving))


if __name__ == "__main__":
    main()
