"""Modelos que predicen a partir de la tabla de features (una fila por partido).

Todos exponen `fit(train) -> self` y `predict(df) -> Forecast`. Los que modelan
goles devuelven además la grilla de marcadores exactos.

* FrequencyModel: frecuencias de H/D/A en entrenamiento (referencia ingenua).
* EloLogitModel: logit multinomial del resultado sobre la diferencia de Elo.
* PoissonGLMModel: dos regresiones de Poisson (goles del local y del visitante,
  estilo Maher 1982) sobre features; opcionalmente con la corrección de Dixon-Coles
  (rho estimado por máxima verosimilitud sobre entrenamiento) y ponderación temporal.
* XGBPoissonModel: gradient boosting con objetivo Poisson (contraste no lineal).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.metrics import OUTCOMES
from src.models.scoreline import dixon_coles_tau, outcome_probabilities, rho_bounds, score_matrix


@dataclass
class Forecast:
    probs: np.ndarray                       # (n, 3) en orden H, D, A
    lam: np.ndarray | None = None           # goles esperados del local
    mu: np.ndarray | None = None            # goles esperados del visitante
    rho: float = 0.0
    matrix: np.ndarray | None = field(default=None, repr=False)


def time_weights(dates: pd.Series, reference: pd.Timestamp, halflife_days: float | None) -> np.ndarray:
    """Pesos exp(-ln2 * antigüedad / vida media); None = todos iguales."""
    if halflife_days is None:
        return np.ones(len(dates))
    age = (reference - pd.to_datetime(dates)).dt.days.to_numpy()
    return np.power(0.5, age / halflife_days)


class FrequencyModel:
    name = "frecuencias"

    def fit(self, train: pd.DataFrame) -> "FrequencyModel":
        self.freq_ = train["result"].astype(str).value_counts(normalize=True).reindex(OUTCOMES).to_numpy()
        return self

    def predict(self, df: pd.DataFrame) -> Forecast:
        return Forecast(probs=np.tile(self.freq_, (len(df), 1)))


class EloLogitModel:
    name = "logit_elo"

    def fit(self, train: pd.DataFrame) -> "EloLogitModel":
        self.model_ = LogisticRegression(C=1e6, max_iter=1000)
        self.model_.fit(train[["elo_diff"]].to_numpy() / 100, train["result"].astype(str))
        return self

    def predict(self, df: pd.DataFrame) -> Forecast:
        p = self.model_.predict_proba(df[["elo_diff"]].to_numpy() / 100)
        order = [list(self.model_.classes_).index(o) for o in OUTCOMES]
        return Forecast(probs=p[:, order])


def fit_rho(lam: np.ndarray, mu: np.ndarray, home_goals: np.ndarray, away_goals: np.ndarray,
            weights: np.ndarray | None = None) -> float:
    """rho de Dixon-Coles por máxima verosimilitud con lam y mu fijos.

    Solo las celdas (0,0), (0,1), (1,0), (1,1) dependen de rho, pero la
    normalización de la grilla también: se maximiza la log-verosimilitud completa
    del marcador observado.
    """
    weights = np.ones(len(lam)) if weights is None else weights
    x = np.minimum(home_goals.astype(int), 10)
    y = np.minimum(away_goals.astype(int), 10)
    low, high = rho_bounds(lam, mu)

    def neg_ll(rho: float) -> float:
        m = score_matrix(lam, mu, rho)
        return -np.sum(weights * np.log(m[np.arange(len(x)), x, y]))

    res = minimize_scalar(neg_ll, bounds=(max(low + 1e-6, -0.5), min(high - 1e-6, 0.5)), method="bounded")
    return float(res.x)


class _GoalsModel:
    """Base de los modelos de dos regresiones (goles del local y del visitante)."""

    name = "goles"

    def __init__(self, features: list[str], dixon_coles: bool = False, halflife_days: float | None = None):
        self.features = features
        self.dixon_coles = dixon_coles
        self.halflife_days = halflife_days

    def _make(self):
        raise NotImplementedError

    def fit(self, train: pd.DataFrame) -> "_GoalsModel":
        x = train[self.features].astype(float)
        w = time_weights(train["date"], train["date"].max(), self.halflife_days)
        self.home_ = self._make().fit(x, train["home_goals"].astype(float), **self._weight_kw(w))
        self.away_ = self._make().fit(x, train["away_goals"].astype(float), **self._weight_kw(w))
        self.rho_ = 0.0
        if self.dixon_coles:
            lam, mu = self._rates(train)
            self.rho_ = fit_rho(lam, mu, train["home_goals"].to_numpy(float), train["away_goals"].to_numpy(float), w)
        return self

    def _weight_kw(self, w: np.ndarray) -> dict:
        return {}

    def _rates(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        x = df[self.features].astype(float)
        return self.home_.predict(x), self.away_.predict(x)

    def predict(self, df: pd.DataFrame) -> Forecast:
        lam, mu = self._rates(df)
        matrix = score_matrix(lam, mu, self.rho_)
        return Forecast(probs=outcome_probabilities(matrix), lam=lam, mu=mu, rho=self.rho_, matrix=matrix)


class PoissonGLMModel(_GoalsModel):
    name = "poisson_glm"

    def __init__(self, features: list[str], alpha: float = 1e-3, dixon_coles: bool = False,
                 halflife_days: float | None = None):
        super().__init__(features, dixon_coles, halflife_days)
        self.alpha = alpha

    def _make(self):
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             PoissonRegressor(alpha=self.alpha, max_iter=1000))

    def _weight_kw(self, w):
        return {"poissonregressor__sample_weight": w}

    def coefficients(self) -> pd.DataFrame:
        return pd.DataFrame({
            "goles_local": self.home_[-1].coef_, "goles_visitante": self.away_[-1].coef_,
        }, index=self.features)


class XGBPoissonModel(_GoalsModel):
    name = "xgb_poisson"

    def __init__(self, features: list[str], dixon_coles: bool = False, halflife_days: float | None = None,
                 n_estimators: int = 300, max_depth: int = 2, learning_rate: float = 0.03,
                 min_child_weight: float = 50, subsample: float = 0.8, seed: int = 0):
        super().__init__(features, dixon_coles, halflife_days)
        self.params = dict(n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate,
                           min_child_weight=min_child_weight, subsample=subsample, random_state=seed)

    def _make(self):
        from xgboost import XGBRegressor  # import diferido: solo si se usa este modelo
        return XGBRegressor(objective="count:poisson", tree_method="hist", n_jobs=4, **self.params)

    def _weight_kw(self, w):
        return {"sample_weight": w}
