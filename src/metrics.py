"""Métricas para pronósticos probabilísticos de resultado 1X2.

Convención: las probabilidades son una matriz (n, 3) en el orden
OUTCOMES = ("H", "D", "A") y los resultados son etiquetas "H"/"D"/"A".
"""

import numpy as np
import pandas as pd

OUTCOMES = ("H", "D", "A")


def one_hot(results) -> np.ndarray:
    results = np.asarray(results)
    unknown = set(np.unique(results)) - set(OUTCOMES)
    if unknown:
        raise ValueError(f"Resultados desconocidos: {unknown}")
    return (results[:, None] == np.array(OUTCOMES)[None, :]).astype(float)


def _check(probs: np.ndarray) -> np.ndarray:
    probs = np.asarray(probs, dtype=float)
    if probs.ndim != 2 or probs.shape[1] != 3:
        raise ValueError("probs debe tener forma (n, 3)")
    if np.isnan(probs).any():
        raise ValueError("probs contiene NaN: filtrar antes de evaluar")
    if not np.allclose(probs.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError("cada fila de probs debe sumar 1")
    return probs


def log_loss(probs, results, eps: float = 1e-15) -> float:
    """Entropía cruzada media (log natural). Menor es mejor."""
    probs = _check(probs)
    y = one_hot(results)
    return float(-np.mean(np.log(np.clip((probs * y).sum(axis=1), eps, 1.0))))


def brier_score(probs, results) -> float:
    """Brier multiclase: suma de errores cuadráticos sobre las 3 clases, promediada. En [0, 2]."""
    probs = _check(probs)
    return float(np.mean(((probs - one_hot(results)) ** 2).sum(axis=1)))


def accuracy(probs, results) -> float:
    probs = _check(probs)
    return float(np.mean(np.array(OUTCOMES)[probs.argmax(axis=1)] == np.asarray(results)))


def reliability_table(probs, results, n_bins: int = 10) -> pd.DataFrame:
    """Tabla de calibración uno-contra-resto para cada resultado.

    Agrupa las probabilidades pronosticadas en bins de igual ancho y compara la
    probabilidad media del bin con la frecuencia observada. Incluye un intervalo
    de Wilson al 95% para la frecuencia, así se ve qué desvíos son ruido.
    """
    probs = _check(probs)
    y = one_hot(results)
    edges = np.linspace(0, 1, n_bins + 1)
    rows = []
    for k, outcome in enumerate(OUTCOMES):
        bins = np.clip(np.digitize(probs[:, k], edges[1:-1]), 0, n_bins - 1)
        for b in range(n_bins):
            mask = bins == b
            n = int(mask.sum())
            if n == 0:
                continue
            freq = y[mask, k].mean()
            low, high = wilson_interval(freq, n)
            rows.append({
                "outcome": outcome, "bin": b, "n": n,
                "mean_predicted": probs[mask, k].mean(), "observed": freq,
                "ci_low": low, "ci_high": high,
            })
    return pd.DataFrame(rows)


def wilson_interval(p: float, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Intervalo de Wilson para una proporción (Wilson 1927)."""
    if n == 0:
        return (np.nan, np.nan)
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (center - half, center + half)


def expected_calibration_error(probs, results, n_bins: int = 10) -> float:
    """ECE promediado sobre los tres resultados (ponderado por tamaño de bin)."""
    table = reliability_table(probs, results, n_bins)
    n_total = len(np.asarray(results))
    per_outcome = table.assign(gap=lambda t: (t.mean_predicted - t.observed).abs() * t.n / n_total)
    return float(per_outcome.groupby("outcome").gap.sum().mean())


def summarize(probs, results) -> dict:
    return {
        "n": int(len(np.asarray(results))),
        "log_loss": log_loss(probs, results),
        "brier": brier_score(probs, results),
        "accuracy": accuracy(probs, results),
        "ece": expected_calibration_error(probs, results),
    }
