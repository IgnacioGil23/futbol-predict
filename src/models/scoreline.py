"""Distribución de probabilidad sobre marcadores exactos.

Con goles del local ~ Poisson(lam) y del visitante ~ Poisson(mu), la probabilidad
del marcador (x, y) es Poisson(x; lam) * Poisson(y; mu), multiplicada opcionalmente
por la corrección de Dixon y Coles (1997, JRSS C 46(2):265-280) para marcadores bajos:

    tau(0,0) = 1 - lam*mu*rho     tau(0,1) = 1 + lam*rho
    tau(1,0) = 1 + mu*rho         tau(1,1) = 1 - rho          tau = 1 en el resto

Sumando celdas se obtienen P(local), P(empate) y P(visitante). La grilla se corta
en MAX_GOALS goles por equipo y se renormaliza (la masa descartada con lam, mu
típicos de la Premier es del orden de 1e-6).
"""

import numpy as np

MAX_GOALS = 10


def poisson_pmf(k: np.ndarray, lam: np.ndarray) -> np.ndarray:
    """P(X = k) para X ~ Poisson(lam), en escala logarítmica para estabilidad numérica.

    Implementada con numpy (sin scipy) para que la imagen de la API sea liviana;
    tests/test_models.py verifica que coincide con scipy.stats.poisson.pmf.
    """
    k = np.asarray(k, dtype=float)
    lam = np.asarray(lam, dtype=float)
    max_k = int(k.max()) if k.size else 0
    log_fact = np.concatenate([[0.0], np.cumsum(np.log(np.arange(1, max_k + 1)))])
    return np.exp(k * np.log(lam) - lam - log_fact[k.astype(int)])


def dixon_coles_tau(lam: np.ndarray, mu: np.ndarray, rho: float) -> np.ndarray:
    """Factores tau para las celdas (0,0), (0,1), (1,0), (1,1); forma (n, 2, 2)."""
    lam = np.asarray(lam, dtype=float)
    mu = np.asarray(mu, dtype=float)
    tau = np.ones(lam.shape + (2, 2))
    tau[..., 0, 0] = 1 - lam * mu * rho
    tau[..., 0, 1] = 1 + lam * rho
    tau[..., 1, 0] = 1 + mu * rho
    tau[..., 1, 1] = 1 - rho
    return tau


def score_matrix(lam, mu, rho: float = 0.0, max_goals: int = MAX_GOALS) -> np.ndarray:
    """Matriz (n, max_goals+1, max_goals+1): [i, x, y] = P(local x, visitante y)."""
    lam = np.atleast_1d(np.asarray(lam, dtype=float))
    mu = np.atleast_1d(np.asarray(mu, dtype=float))
    goals = np.arange(max_goals + 1)
    p_home = poisson_pmf(goals[None, :], lam[:, None])
    p_away = poisson_pmf(goals[None, :], mu[:, None])
    matrix = p_home[:, :, None] * p_away[:, None, :]
    if rho != 0.0:
        tau = dixon_coles_tau(lam, mu, rho)
        if np.any(tau <= 0):
            raise ValueError("rho fuera del rango válido para estos lam/mu (tau <= 0)")
        matrix[:, :2, :2] *= tau
    return matrix / matrix.sum(axis=(1, 2), keepdims=True)


def outcome_probabilities(matrix: np.ndarray) -> np.ndarray:
    """(n, 3) con P(local), P(empate), P(visitante), en el orden de src.metrics.OUTCOMES."""
    home = np.tril(np.ones(matrix.shape[1:], dtype=bool), k=-1)  # x > y
    draw = np.eye(matrix.shape[1], dtype=bool)
    away = ~(home | draw)
    return np.stack([matrix[:, home].sum(axis=1), matrix[:, draw].sum(axis=1), matrix[:, away].sum(axis=1)], axis=1)


def exact_score_log_loss(matrix: np.ndarray, home_goals, away_goals) -> float:
    """-log P(marcador real) medio. Los goles por encima de la grilla cuentan como la celda del borde."""
    x = np.minimum(np.asarray(home_goals, dtype=int), matrix.shape[1] - 1)
    y = np.minimum(np.asarray(away_goals, dtype=int), matrix.shape[2] - 1)
    p = matrix[np.arange(len(x)), x, y]
    return float(-np.mean(np.log(np.clip(p, 1e-15, 1.0))))


def rho_bounds(lam: np.ndarray, mu: np.ndarray) -> tuple[float, float]:
    """Intervalo de rho que mantiene tau > 0 para todos los pares (lam, mu) dados."""
    lam, mu = np.asarray(lam, dtype=float), np.asarray(mu, dtype=float)
    lower = max(-1.0 / lam.max(), -1.0 / mu.max())
    upper = min(1.0 / (lam * mu).max(), 1.0)
    return lower, upper
