"""Probabilidades implícitas a partir de cuotas decimales.

La inversa de una cuota (1/cuota) sobreestima la probabilidad porque incluye el
margen de la casa: la suma de las tres inversas en un 1X2 ("booksum" u
overround) es > 1. Hay que quitar ese margen para comparar contra un modelo.

Dos métodos:

* Proporcional ("basic"): p_i = r_i / sum(r). Reparte el margen en proporción a
  cada probabilidad.
* Shin (Shin 1992, 1993): modela un mercado con una fracción z de apostadores con
  información privilegiada, lo que corrige el sesgo favorito-longshot.
  p_i = (sqrt(z^2 + 4(1-z) r_i^2 / sum(r)) - z) / (2(1-z)), con z tal que sum(p) = 1.
  Štrumbelj (2014, International Journal of Forecasting 30(4):934-943) encontró
  que las probabilidades de Shin son pronósticos más precisos que las de la
  normalización básica. Implementación verificada contra el paquete de R
  `implied` (función shin_func).
"""

import numpy as np
from scipy.optimize import brentq


def inverse_odds(odds: np.ndarray) -> np.ndarray:
    odds = np.asarray(odds, dtype=float)
    if np.any(odds[~np.isnan(odds)] <= 1.0):
        raise ValueError("Las cuotas decimales deben ser > 1")
    return 1.0 / odds


def booksum(odds: np.ndarray) -> np.ndarray:
    """Suma de probabilidades implícitas por fila (1 + margen de la casa)."""
    return inverse_odds(odds).sum(axis=-1)


def proportional_probabilities(odds: np.ndarray) -> np.ndarray:
    """Normalización básica. `odds` de forma (n, k); filas con NaN devuelven NaN."""
    r = inverse_odds(np.atleast_2d(odds))
    return r / r.sum(axis=1, keepdims=True)


def _shin_row(r: np.ndarray) -> tuple[np.ndarray, float]:
    total = r.sum()
    if total <= 1.0 + 1e-12:
        # Sin margen no hay nada que corregir (z = 0 equivale a proporcional).
        return r / total, 0.0

    def probs(z: float) -> np.ndarray:
        return (np.sqrt(z**2 + 4 * (1 - z) * r**2 / total) - z) / (2 * (1 - z))

    # sum(probs(0)) = sqrt(sum r^2 ... ) > 1 y la suma decrece con z; se busca la raíz.
    z = brentq(lambda z: probs(z).sum() - 1.0, 0.0, 0.999, xtol=1e-12)
    return probs(z), z


def shin_probabilities(odds: np.ndarray, return_z: bool = False):
    """Probabilidades de Shin. `odds` de forma (n, k); filas con NaN devuelven NaN."""
    odds = np.atleast_2d(np.asarray(odds, dtype=float))
    out = np.full(odds.shape, np.nan)
    zs = np.full(odds.shape[0], np.nan)
    valid = ~np.isnan(odds).any(axis=1)
    r = inverse_odds(odds[valid])
    for i, row in zip(np.flatnonzero(valid), r):
        out[i], zs[i] = _shin_row(row)
    return (out, zs) if return_z else out
