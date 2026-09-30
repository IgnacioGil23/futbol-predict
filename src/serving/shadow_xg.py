"""Candidato A (xG) congelado para el registro en paralelo de 2026-27 (docs/preregistro_xg.md).

* Modelo: el de producción (sus parámetros se copian dentro del artefacto, así el candidato no cambia si
  producción se reentrena) más una corrección sin intercepto por el xG móvil (src/models/fpl_eval.OffsetPoisson),
  estimada una sola vez con las temporadas 2022-23 a 2025-26 del archivo de Fantasy.
* Historia de xG: tabla por equipo y partido (agregada, sin datos de jugadores) guardada junto al modelo, más la
  serie de 2026-27 capturada en vivo (ledger/xg_team_matches.csv). Las variables se calculan con la misma
  función que en la prueba histórica (src.features.fpl_features.xg_features).

Uso (una sola vez, al congelar):
    python -m src.serving.shadow_xg
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT, season_label, season_start_year
from src.features.fpl_features import A_COLUMNS, xg_features
from src.models.scoreline import outcome_probabilities, score_matrix
from src.serving.predictor import EloPoissonPredictor

logger = logging.getLogger(__name__)

SHADOW_XG_DIR = PROJECT_ROOT / "models" / "shadow_xg"
SHADOW_XG_MODEL_PATH = SHADOW_XG_DIR / "model.json"
XG_HISTORY_PATH = SHADOW_XG_DIR / "xg_history.csv"
CANDIDATE_NAME = "elo+xg_hl4 (corrección sobre producción)"
PARAM_DECIMALS = 12
HISTORY_COLUMNS = ["match_id", "season_start", "date", "team", "is_home", "xg_f", "xg_a"]


def _r(values) -> list[float]:
    return [round(float(v), PARAM_DECIMALS) for v in np.atleast_1d(values)]


# ------------------------------------------------------------------ congelamiento

def history_from_archive(players: pd.DataFrame, dates: pd.DataFrame) -> pd.DataFrame:
    """xG por equipo y partido del archivo (solo partidos con xG registrado)."""
    from src.features.fpl_features import team_matches
    tm = team_matches(players, dates)
    tm = tm[tm["recorded"]].copy()
    tm["date"] = tm["date"].dt.strftime("%Y-%m-%d")
    return tm[HISTORY_COLUMNS].round({"xg_f": 6, "xg_a": 6}).sort_values(["date", "match_id", "team"])


def freeze(frame: pd.DataFrame, production: dict, today: date) -> dict:
    """Estima la corrección con las temporadas del archivo anteriores a la actual, sobre el modelo de producción."""
    from src.models.fpl_eval import FIRST_ARCHIVE_SEASON, OffsetPoisson

    current = season_start_year(today)
    base = EloPoissonPredictor(production)
    train = frame[(frame.season_start >= FIRST_ARCHIVE_SEASON) & (frame.season_start < current) & frame.played]
    train = train.dropna(subset=A_COLUMNS)
    lam, mu = base.rates(train["elo_diff"].to_numpy(float))
    x = train[A_COLUMNS].to_numpy(float)
    home = OffsetPoisson().fit(x, train["home_goals"].to_numpy(float), np.log(lam))
    away = OffsetPoisson().fit(x, train["away_goals"].to_numpy(float), np.log(mu))
    correction = {name: {"coef": _r(m.coef_), "mean": _r(m.mean_), "scale": _r(m.scale_)}
                  for name, m in (("home_goals", home), ("away_goals", away))}
    return {
        "params": {"features": A_COLUMNS, "impute": _r(train[A_COLUMNS].median()), "base": production["params"],
                   "correction": correction},
        "meta": {"candidate": CANDIDATE_NAME, "preregistration": "docs/preregistro_xg.md",
                 "base_model_version": base.version, "base_elo_params": production["meta"].get("elo_params"),
                 "trained_on": {"seasons": f"{train.season.min()} a {train.season.max()}", "matches": int(len(train))},
                 "frozen_for_season": season_label(current), "trained_at": today.isoformat()},
    }


# ------------------------------------------------------------------ predicción

@dataclass
class ShadowForecast:
    lam: np.ndarray
    mu: np.ndarray
    probs: np.ndarray


class ShadowXgPredictor:
    def __init__(self, artifact: dict):
        self.params, self.meta = artifact["params"], artifact["meta"]
        self.features = self.params["features"]
        self.base = EloPoissonPredictor({"params": self.params["base"],
                                         "meta": {"elo_params": self.meta.get("base_elo_params")}})
        canonical = json.dumps(self.params, sort_keys=True, separators=(",", ":"))
        self.version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def load(cls, path: Path = SHADOW_XG_MODEL_PATH) -> "ShadowXgPredictor":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def _log_rate(self, which: str, offset: np.ndarray, x: np.ndarray) -> np.ndarray:
        c = self.params["correction"][which]
        return offset + ((x - np.asarray(c["mean"])) / np.asarray(c["scale"])) @ np.asarray(c["coef"])

    def predict(self, rows: pd.DataFrame) -> ShadowForecast:
        x = rows[self.features].to_numpy(float)
        x = np.where(np.isnan(x), np.asarray(self.params["impute"]), x)
        lam0, mu0 = self.base.rates(rows["elo_diff"].to_numpy(float))
        lam = np.exp(self._log_rate("home_goals", np.log(lam0), x))
        mu = np.exp(self._log_rate("away_goals", np.log(mu0), x))
        return ShadowForecast(lam=lam, mu=mu, probs=outcome_probabilities(score_matrix(lam, mu)))


# ------------------------------------------------------------------ variables para partidos concretos

def xg_features_for(history: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """Variables de A para `targets` (date, home_team, away_team), con la historia de xG anterior al día de cada
    partido. `history`: columnas HISTORY_COLUMNS (archivo + serie en vivo)."""
    t = targets[["date", "home_team", "away_team"]].reset_index(drop=True).copy()
    t["date"] = pd.to_datetime(t["date"])
    t["target_id"] = [f"objetivo-{i}" for i in range(len(t))]
    hist = history.assign(date=pd.to_datetime(history["date"]), recorded=True)
    rows = [hist[["match_id", "team", "date", "recorded", "xg_f", "xg_a"]]]
    for side in ("home", "away"):
        rows.append(pd.DataFrame({"match_id": t["target_id"], "team": t[f"{side}_team"], "date": t["date"],
                                  "recorded": False, "xg_f": np.nan, "xg_a": np.nan}))
    tm = pd.concat(rows, ignore_index=True).sort_values(["team", "date"]).reset_index(drop=True)
    feats = xg_features(tm).set_index(["match_id", "team"])
    for side in ("home", "away"):
        f = feats.loc[list(zip(t["target_id"], t[f"{side}_team"]))]
        t[f"xg_f_hl4_{side}"] = f["xg_f_hl4"].to_numpy()
        t[f"xg_a_hl4_{side}"] = f["xg_a_hl4"].to_numpy()
    return t[["date", "home_team", "away_team"] + A_COLUMNS]


def main() -> None:
    from src.data.fpl_archive import PLAYER_MATCHES_PATH
    from src.models.fpl_eval import load_frame
    from src.serving.production import MODEL_PATH

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if SHADOW_XG_MODEL_PATH.exists():
        raise SystemExit(f"{SHADOW_XG_MODEL_PATH} ya existe: el candidato está congelado para la temporada")
    frame = load_frame()
    artifact = freeze(frame, json.loads(MODEL_PATH.read_text(encoding="utf-8")), date.today())
    history = history_from_archive(pd.read_parquet(PLAYER_MATCHES_PATH), frame[["match_id", "date"]])
    SHADOW_XG_DIR.mkdir(parents=True, exist_ok=True)
    SHADOW_XG_MODEL_PATH.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    history.to_csv(XG_HISTORY_PATH, index=False, lineterminator="\n")
    logger.info("Candidato A congelado -> %s (versión %s, %s) · historia de xG: %d filas",
                SHADOW_XG_MODEL_PATH, ShadowXgPredictor(artifact).version, artifact["meta"]["trained_on"], len(history))


if __name__ == "__main__":
    main()
