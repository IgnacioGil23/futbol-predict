"""Distribución de probabilidad sobre marcadores exactos.

Con goles del local ~ Poisson(lam) y del visitante ~ Poisson(mu), la probabilidad
del marcador (x, y) es Poisson(x; lam) * Poisson(y; mu), multiplicada opcionalmente
por la corrección de Dixon y Coles (1997, JRSS C 46(2):265-280) para marcadores bajos:

    tau(0,0) = 1 - lam*mu*rho     tau(0,1) = 1 + lam*rho
    tau(1,0) = 1 + mu*rho         tau(1,1) = 1 - rho          tau = 1 en el resto

Sumando celdas se obtienen P(local), P(empate) y P(visitante). La grilla se corta
en MAX_GOALS goles por equipo y se renormaliza (la masa descartada con lam, mu
típicos de la Premier es del orden de 1e-6).

Alternativa con goles correlacionados: Poisson bivariado y su versión con la diagonal
inflada (Karlis y Ntzoufras 2003, The Statistician 52(3):381-393, ecuaciones 1 y 5),
en `bivariate_poisson_matrix`, `inflate_diagonal` y `BivariateDependence`.
"""

from dataclasses import dataclass

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


def bivariate_poisson_matrix(lam1, lam2, lam3, max_goals: int = MAX_GOALS) -> np.ndarray:
    """Grilla (n, max_goals+1, max_goals+1) del Poisson bivariado BP(lam1, lam2, lam3), renormalizada.

    X = X1 + X3, Y = X2 + X3 con Xk ~ Poisson(lamk) independientes, así que
        P(x, y) = sum_{k=0}^{min(x,y)} Pois(k; lam3) Pois(x-k; lam1) Pois(y-k; lam2),
    que es la ecuación (1) de Karlis y Ntzoufras (2003) escrita como convolución. Cada
    término usa solo celdas dentro de la grilla, así que los valores son exactos antes de
    renormalizar. Marginales: X ~ Poisson(lam1 + lam3), Y ~ Poisson(lam2 + lam3), cov = lam3.
    """
    lam1 = np.atleast_1d(np.asarray(lam1, dtype=float))
    lam2 = np.atleast_1d(np.asarray(lam2, dtype=float))
    lam3 = np.broadcast_to(np.asarray(lam3, dtype=float), lam1.shape)
    if np.any(lam1 <= 0) or np.any(lam2 <= 0) or np.any(lam3 < 0):
        raise ValueError("el Poisson bivariado requiere lam1, lam2 > 0 y lam3 >= 0")
    goals = np.arange(max_goals + 1)
    p1 = poisson_pmf(goals[None, :], lam1[:, None])
    p2 = poisson_pmf(goals[None, :], lam2[:, None])
    # lam3 = 0 se evalúa como un valor ínfimo: Pois(0) = 1 y Pois(k >= 1) = 0 sin log(0).
    p3 = poisson_pmf(goals[None, :], np.maximum(lam3, 1e-300)[:, None])
    outer = p1[:, :, None] * p2[:, None, :]
    matrix = np.zeros_like(outer)
    for k in range(max_goals + 1):              # término k: la grilla desplazada k lugares por la diagonal
        size = max_goals + 1 - k
        matrix[:, k:, k:] += p3[:, k, None, None] * outer[:, :size, :size]
    return matrix / matrix.sum(axis=(1, 2), keepdims=True)


def inflate_diagonal(matrix: np.ndarray, p: float, theta) -> np.ndarray:
    """Ecuación (5) de Karlis y Ntzoufras (2003): (1 - p) * grilla + p * D en la diagonal.

    D es la distribución discreta P(j-j) = theta_j para j = 0..J (el paper indica que
    J <= 3 suele alcanzar en fútbol)."""
    theta = np.asarray(theta, dtype=float)
    if not 0 <= p < 1 or np.any(theta < 0) or not np.isclose(theta.sum(), 1.0):
        raise ValueError("p debe estar en [0, 1) y theta ser una distribución")
    out = (1 - p) * matrix
    j = np.arange(len(theta))
    out[:, j, j] += p * theta
    return out


@dataclass(frozen=True)
class BivariateDependence:
    """Cómo se reparte la probabilidad entre marcadores dados los goles esperados (lam, mu).

    * lam3 > 0 (constante): BP(lam - lam3, mu - lam3, lam3). Las marginales conservan las
      medias lam y mu de las regresiones.
    * kappa > 0 (proporcional): lam3 = kappa * min(lam, mu) / (1 + kappa), es decir
      lam3 = kappa * min(lam1, lam2): válido para cualquier kappa >= 0 y cualquier partido.
    * p > 0: además se infla la diagonal con theta (ecuación 5). Siguiendo al paper, lam y mu
      son las medias de la componente bivariada; la media del marcador pasa a ser
      (1 - p) * lam + p * E[D].
    Todo en cero equivale a goles independientes (la grilla actual).
    """

    lam3: float = 0.0
    kappa: float = 0.0
    p: float = 0.0
    theta: tuple[float, ...] = ()

    def __post_init__(self):
        if self.lam3 and self.kappa:
            raise ValueError("lam3 constante y kappa proporcional son excluyentes")
        if self.p and not self.theta:
            raise ValueError("la inflación de la diagonal requiere theta")

    def shared_rate(self, lam: np.ndarray, mu: np.ndarray) -> np.ndarray:
        """lam3 de cada partido."""
        if self.kappa:
            return self.kappa * np.minimum(lam, mu) / (1 + self.kappa)
        return np.full(np.shape(lam), self.lam3)

    def matrix(self, lam, mu, max_goals: int = MAX_GOALS) -> np.ndarray:
        lam = np.atleast_1d(np.asarray(lam, dtype=float))
        mu = np.atleast_1d(np.asarray(mu, dtype=float))
        lam3 = self.shared_rate(lam, mu)
        if np.any(lam3 >= np.minimum(lam, mu)):
            raise ValueError("lam3 debe ser menor que los goles esperados de ambos equipos")
        m = bivariate_poisson_matrix(lam - lam3, mu - lam3, lam3, max_goals)
        return inflate_diagonal(m, self.p, self.theta) if self.p else m

    def to_dict(self) -> dict:
        return {"lam3": self.lam3, "kappa": self.kappa, "p": self.p, "theta": list(self.theta)}


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
