"""Modelo de Dixon y Coles (1997) con fuerzas por equipo.

    log lam = home + attack[local] - defence[visitante]
    log mu  =        attack[visitante] - defence[local]
    P(x, y) = tau(x, y; lam, mu, rho) * Poisson(x; lam) * Poisson(y; mu)

Se estima por máxima verosimilitud ponderada en el tiempo, peso exp(-xi * días de
antigüedad), como proponen Dixon y Coles para que el modelo siga la forma
reciente de cada equipo. Se ajusta sobre Premier League + Championship juntas
(los equipos que suben y bajan conectan ambas divisiones en una misma escala), y
se agrega una penalización L2 chica sobre ataque y defensa: resuelve la
indeterminación de la escala (sumar una constante a todos los ataques y defensas
no cambia nada) y estabiliza a los equipos con pocos partidos.

Como no usa features, para predecir un partido del día D se reajusta con los
partidos jugados antes de D: `walk_forward` reajusta una vez por semana.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.models.feature_models import Forecast
from src.models.scoreline import outcome_probabilities, score_matrix


@dataclass
class DixonColesParams:
    xi: float = 0.0019           # decaimiento por día (vida media ~1 temporada con 0.0019)
    window_days: int = 3 * 365   # partidos más viejos pesan < exp(-xi*window): se descartan
    l2: float = 1.0              # penalización sobre ataque/defensa
    rho: bool = True             # incluir corrección de marcadores bajos


class DixonColesModel:
    name = "dixon_coles"

    def __init__(self, params: DixonColesParams | None = None):
        self.params = params if params is not None else DixonColesParams()

    def fit(self, matches: pd.DataFrame, as_of: pd.Timestamp) -> "DixonColesModel":
        p = self.params
        df = matches[(matches["date"] < as_of) & (matches["date"] >= as_of - pd.Timedelta(days=p.window_days))
                     & matches["home_goals"].notna()]
        teams = pd.Index(sorted(set(df["home_team"]) | set(df["away_team"])))
        self.teams_ = teams
        hi = teams.get_indexer(df["home_team"])
        ai = teams.get_indexer(df["away_team"])
        x = df["home_goals"].to_numpy(float)
        y = df["away_goals"].to_numpy(float)
        w = np.exp(-p.xi * (as_of - df["date"]).dt.days.to_numpy())
        n = len(teams)
        low = (x == 0) & (y == 0), (x == 0) & (y == 1), (x == 1) & (y == 0), (x == 1) & (y == 1)

        def unpack(theta):
            return theta[:n], theta[n:2 * n], theta[2 * n], (theta[2 * n + 1] if p.rho else 0.0)

        def objective(theta):
            att, dfn, home, rho = unpack(theta)
            log_lam = home + att[hi] - dfn[ai]
            log_mu = att[ai] - dfn[hi]
            lam, mu = np.exp(log_lam), np.exp(log_mu)
            # Poisson (sin el término log(x!) que no depende de los parámetros)
            ll = w * (x * log_lam - lam + y * log_mu - mu)
            g_loglam = w * (x - lam)
            g_logmu = w * (y - mu)
            g_rho = 0.0
            if p.rho:
                tau = np.ones_like(lam)
                m00, m01, m10, m11 = low
                tau[m00] = 1 - lam[m00] * mu[m00] * rho
                tau[m01] = 1 + lam[m01] * rho
                tau[m10] = 1 + mu[m10] * rho
                tau[m11] = 1 - rho
                if np.any(tau <= 0):
                    return 1e12, np.zeros_like(theta)
                ll = ll + w * np.log(tau)
                # derivadas de log(tau)
                g_loglam[m00] += w[m00] * (-lam[m00] * mu[m00] * rho) / tau[m00]
                g_logmu[m00] += w[m00] * (-lam[m00] * mu[m00] * rho) / tau[m00]
                g_loglam[m01] += w[m01] * (lam[m01] * rho) / tau[m01]
                g_logmu[m10] += w[m10] * (mu[m10] * rho) / tau[m10]
                g_rho = (np.sum(w[m00] * (-lam[m00] * mu[m00]) / tau[m00])
                         + np.sum(w[m01] * lam[m01] / tau[m01])
                         + np.sum(w[m10] * mu[m10] / tau[m10])
                         + np.sum(w[m11] * (-1.0) / tau[m11]))
            penalty = 0.5 * p.l2 * (np.sum(att ** 2) + np.sum(dfn ** 2))
            value = -(ll.sum()) + penalty
            g_att = np.bincount(hi, g_loglam, n) + np.bincount(ai, g_logmu, n)
            g_dfn = -np.bincount(ai, g_loglam, n) - np.bincount(hi, g_logmu, n)
            grad = np.concatenate([-g_att + p.l2 * att, -g_dfn + p.l2 * dfn, [-g_loglam.sum()]])
            if p.rho:
                grad = np.append(grad, -g_rho)
            return value, grad

        theta0 = np.zeros(2 * n + 1 + (1 if p.rho else 0))
        theta0[2 * n] = np.log(max(x.mean(), 0.1) / max(y.mean(), 0.1)) / 2
        bounds = [(None, None)] * (2 * n + 1) + ([(-0.3, 0.3)] if p.rho else [])
        res = minimize(objective, theta0, jac=True, method="L-BFGS-B", bounds=bounds,
                       options={"maxiter": 2000})
        if not res.success:
            raise RuntimeError(f"Dixon-Coles no convergió: {res.message}")
        att, dfn, home, rho = unpack(res.x)
        self.attack_ = pd.Series(att, index=teams)
        self.defence_ = pd.Series(dfn, index=teams)
        self.home_ = float(home)
        self.rho_ = float(rho)
        self.as_of_ = as_of
        return self

    def rates(self, home_teams, away_teams) -> tuple[np.ndarray, np.ndarray]:
        # Un equipo sin partidos en la ventana queda en 0 (promedio de la escala).
        att = self.attack_.reindex(home_teams).fillna(0.0).to_numpy()
        dfn_a = self.defence_.reindex(away_teams).fillna(0.0).to_numpy()
        att_a = self.attack_.reindex(away_teams).fillna(0.0).to_numpy()
        dfn = self.defence_.reindex(home_teams).fillna(0.0).to_numpy()
        return np.exp(self.home_ + att - dfn_a), np.exp(att_a - dfn)

    def predict(self, df: pd.DataFrame) -> Forecast:
        lam, mu = self.rates(df["home_team"], df["away_team"])
        matrix = score_matrix(lam, mu, self.rho_)
        return Forecast(probs=outcome_probabilities(matrix), lam=lam, mu=mu, rho=self.rho_, matrix=matrix)


def walk_forward(matches: pd.DataFrame, targets: pd.DataFrame, params: DixonColesParams) -> pd.DataFrame:
    """Predice `targets` reajustando el modelo al comienzo de cada semana (lunes) con los partidos anteriores."""
    targets = targets.sort_values("date")
    week_start = targets["date"] - pd.to_timedelta(targets["date"].dt.weekday, unit="D")
    rows = []
    for start, group in targets.groupby(week_start):
        model = DixonColesModel(params).fit(matches, as_of=start)
        fc = model.predict(group)
        rows.append(pd.DataFrame({
            "match_id": group["match_id"].to_numpy(),
            "p_home": fc.probs[:, 0], "p_draw": fc.probs[:, 1], "p_away": fc.probs[:, 2],
            "lam": fc.lam, "mu": fc.mu, "rho": fc.rho,
        }))
    return pd.concat(rows, ignore_index=True)
