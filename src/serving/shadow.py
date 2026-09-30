"""Modelo en evaluación (registro en paralelo): Elo + tiros y tiros al arco, congelado para 2026-27.

Protocolo en docs/preregistro_tiros.md. Este módulo:
* entrena el candidato UNA vez (temporadas completas hasta la anterior a la actual) y lo guarda en
  models/shadow/model.json como parámetros JSON, igual que el modelo de producción;
* calcula sus variables para partidos por jugarse con la MISMA función que el entrenamiento
  (src.features.team_state.shot_features), para que no haya diferencias entre entrenamiento y servicio;
* predice con numpy, sin scikit-learn.

Uso (una sola vez, al congelar el candidato):
    python -m src.serving.shadow
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PREMIER_LEAGUE, PROJECT_ROOT, season_label, season_start_year
from src.features.team_state import shot_features
from src.models.scoreline import outcome_probabilities, score_matrix

logger = logging.getLogger(__name__)

SHADOW_MODEL_PATH = PROJECT_ROOT / "models" / "shadow" / "model.json"
CANDIDATE_NAME = "elo+tiros+tiros_al_arco_hl4"
HALFLIFE = 4
SHOT_COLUMNS = [f"{stat}_hl{HALFLIFE}_{side}" for side in ("home", "away") for stat in ("sot_f", "sot_a", "sh_f", "sh_a")]
FEATURES = ["elo_diff"] + SHOT_COLUMNS
PARAM_DECIMALS = 12


def candidate_features() -> list[str]:
    """Las variables del candidato, en el orden de src.models.confirm_shots (fuente única)."""
    from src.models.confirm_shots import CANDIDATE
    return list(CANDIDATE)


# ------------------------------------------------------------------ entrenamiento y exportación

def export_glm(model) -> dict:
    """Parámetros de las dos regresiones (imputación por mediana, estandarización y GLM), redondeados."""
    r = lambda v: [round(float(x), PARAM_DECIMALS) for x in v]  # noqa: E731
    out = {"features": list(model.features)}
    for name, pipe in (("home_goals", model.home_), ("away_goals", model.away_)):
        imputer, scaler, glm = pipe.named_steps.values()
        out[name] = {"intercept": round(float(glm.intercept_), PARAM_DECIMALS), "coef": r(glm.coef_),
                     "impute": r(imputer.statistics_), "mean": r(scaler.mean_), "scale": r(scaler.scale_)}
    return out


def train_shadow(features: pd.DataFrame, today: date) -> dict:
    from src.models.experiments import FIRST_TRAIN_SEASON
    from src.models.feature_models import PoissonGLMModel
    from src.serving.production import ALPHA

    feats = candidate_features()
    if feats != FEATURES:
        raise RuntimeError(f"Las variables del candidato no coinciden con el preregistro: {feats}")
    current = season_start_year(today)
    train = features[(features.season_start >= FIRST_TRAIN_SEASON) & (features.season_start < current)
                     & features.played]
    model = PoissonGLMModel(feats, alpha=ALPHA).fit(train)
    return {
        "params": export_glm(model),
        "meta": {
            "candidate": CANDIDATE_NAME, "alpha": ALPHA, "preregistration": "docs/preregistro_tiros.md",
            "trained_on": {"seasons": f"{train.season.min()} a {train.season.max()}", "matches": int(len(train))},
            "frozen_for_season": season_label(current), "trained_at": today.isoformat(),
        },
    }


# ------------------------------------------------------------------ predicción

@dataclass
class ShadowForecast:
    lam: np.ndarray
    mu: np.ndarray
    probs: np.ndarray        # (n, 3) H, D, A


class ShadowPredictor:
    def __init__(self, artifact: dict):
        self.params = artifact["params"]
        self.meta = artifact["meta"]
        self.features = self.params["features"]
        canonical = json.dumps(self.params, sort_keys=True, separators=(",", ":"))
        self.version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def load(cls, path: Path = SHADOW_MODEL_PATH) -> "ShadowPredictor":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def _rate(self, which: str, x: np.ndarray) -> np.ndarray:
        p = self.params[which]
        x = np.where(np.isnan(x), np.asarray(p["impute"]), x)
        z = (x - np.asarray(p["mean"])) / np.asarray(p["scale"])
        return np.exp(p["intercept"] + z @ np.asarray(p["coef"]))

    def predict(self, rows: pd.DataFrame) -> ShadowForecast:
        x = rows[self.features].to_numpy(dtype=float)
        lam, mu = self._rate("home_goals", x), self._rate("away_goals", x)
        return ShadowForecast(lam=lam, mu=mu, probs=outcome_probabilities(score_matrix(lam, mu)))


# ------------------------------------------------------------------ variables para partidos concretos

def shot_features_for(matches: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """Tiros del candidato para partidos de Premier (jugados o no), con datos anteriores al día del partido.

    `targets`: columnas date, home_team, away_team. Los que no estén en `matches` (partidos por jugarse)
    se agregan sin resultado ni estadísticas; así pasan por shot_features exactamente igual que en el
    entrenamiento. Devuelve `targets` con las columnas de SHOT_COLUMNS.
    """
    t = targets[["date", "home_team", "away_team"]].reset_index(drop=True).copy()
    t["date"] = pd.to_datetime(t["date"])
    key = ["date", "home_team", "away_team"]
    known = t.merge(matches[key + ["match_id"]], on=key, how="left")
    new = known["match_id"].isna()
    known.loc[new, "match_id"] = [f"objetivo-{i}" for i in known.index[new]]
    if new.any():
        extra = known.loc[new, key + ["match_id"]].assign(
            season_start=[season_start_year(d.date()) for d in known.loc[new, "date"]], division=PREMIER_LEAGUE)
        all_matches = pd.concat([matches, extra], ignore_index=True)
    else:
        all_matches = matches
    shots = shot_features(all_matches, halflives=(HALFLIFE,))
    stats = [c[: -len("_home")] for c in SHOT_COLUMNS[:4]]
    out = known
    for side in ("home", "away"):
        s = shots.rename(columns={c: f"{c}_{side}" for c in stats})
        out = out.merge(s[["match_id", "team"] + [f"{c}_{side}" for c in stats]],
                        left_on=["match_id", f"{side}_team"], right_on=["match_id", "team"], how="left"
                        ).drop(columns="team")
    return out[key + SHOT_COLUMNS]


def main() -> None:
    from src.features.build import FEATURES_PATH
    from src.models.experiments import prepare

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if SHADOW_MODEL_PATH.exists():
        raise SystemExit(f"{SHADOW_MODEL_PATH} ya existe: el candidato está congelado para la temporada")
    artifact = train_shadow(prepare(pd.read_parquet(FEATURES_PATH)), date.today())
    SHADOW_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHADOW_MODEL_PATH.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Candidato congelado -> %s (versión %s, %s)", SHADOW_MODEL_PATH,
                ShadowPredictor(artifact).version, artifact["meta"]["trained_on"])


if __name__ == "__main__":
    main()
