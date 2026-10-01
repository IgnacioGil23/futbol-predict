"""Predicción a partir del artefacto JSON del modelo de producción (sin scikit-learn)."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.models.scoreline import outcome_probabilities, score_matrix

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "production" / "model.json"


@dataclass
class Prediction:
    lam: float
    mu: float
    probs: np.ndarray        # H, D, A
    matrix: np.ndarray       # (MAX_GOALS+1, MAX_GOALS+1)

    def top_scores(self, k: int = 5) -> list[dict]:
        flat = np.argsort(self.matrix, axis=None)[::-1][:k]
        n = self.matrix.shape[1]
        return [{"home_goals": int(i // n), "away_goals": int(i % n), "probability": float(self.matrix.flat[i])}
                for i in flat]


def model_version(params: dict, elo_params: dict | None = None) -> str:
    """Identificador estable del modelo: hash de la regresión y de los parámetros del Elo.

    Cambia si cambia cualquier número que afecte las predicciones.
    """
    canonical = json.dumps({"glm": params, "elo": elo_params or {}}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


class EloPoissonPredictor:
    def __init__(self, artifact: dict):
        self.artifact = artifact
        self.params = artifact["params"]
        self.meta = artifact["meta"]
        self.version = model_version(self.params, self.meta.get("elo_params"))
        # Rating de cada equipo que el modelo recibe: "odds_elo" (producción desde el 01/10/2026) o "elo" (resultados).
        self.rating = self.meta.get("rating", "elo")

    @classmethod
    def load(cls, path: Path = DEFAULT_MODEL_PATH) -> "EloPoissonPredictor":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def _rate(self, which: str, elo_diff: np.ndarray) -> np.ndarray:
        p = self.params[which]
        z = (np.asarray(elo_diff, dtype=float) - p["feature_mean"]) / p["feature_scale"]
        return np.exp(p["intercept"] + p["coef"] * z)

    def rates(self, elo_diff) -> tuple[np.ndarray, np.ndarray]:
        return self._rate("home_goals", elo_diff), self._rate("away_goals", elo_diff)

    def predict(self, elo_home: float, elo_away: float) -> Prediction:
        lam, mu = self.rates([elo_home - elo_away])
        matrix = score_matrix(lam, mu)
        return Prediction(lam=float(lam[0]), mu=float(mu[0]), probs=outcome_probabilities(matrix)[0], matrix=matrix[0])
