"""Poisson bivariado y diagonal inflada (Karlis y Ntzoufras 2003)."""

from math import comb, exp, factorial

import numpy as np
import pandas as pd
import pytest

from src.models.feature_models import BivariatePoissonGLMModel, fit_dependence
from src.models.scoreline import (BivariateDependence, bivariate_poisson_matrix, inflate_diagonal,
                                  outcome_probabilities, poisson_pmf, score_matrix)


def paper_pmf(x: int, y: int, l1: float, l2: float, l3: float) -> float:
    """Ecuación (1) del paper, término a término."""
    s = sum(comb(x, k) * comb(y, k) * factorial(k) * (l3 / (l1 * l2)) ** k for k in range(min(x, y) + 1))
    return exp(-(l1 + l2 + l3)) * l1 ** x / factorial(x) * l2 ** y / factorial(y) * s


def test_zero_covariance_is_the_independent_grid():
    lam, mu = np.array([1.6, 0.7, 2.3]), np.array([1.1, 1.9, 0.4])
    np.testing.assert_allclose(bivariate_poisson_matrix(lam, mu, 0.0), score_matrix(lam, mu), rtol=1e-12)
    np.testing.assert_allclose(BivariateDependence().matrix(lam, mu), score_matrix(lam, mu), rtol=1e-12)
    np.testing.assert_allclose(BivariateDependence(kappa=0.0).matrix(lam, mu), score_matrix(lam, mu), rtol=1e-12)


def test_matches_the_closed_form_of_the_paper():
    l1, l2, l3 = 1.2, 0.9, 0.15
    m = bivariate_poisson_matrix([l1], [l2], [l3], max_goals=30)[0]   # grilla grande: truncamiento ~ 0
    for x, y in [(0, 0), (1, 1), (2, 1), (3, 3), (0, 4), (5, 2)]:
        assert m[x, y] == pytest.approx(paper_pmf(x, y, l1, l2, l3), rel=1e-10)


def test_marginals_are_poisson_and_covariance_is_lambda3():
    l1, l2, l3 = 1.1, 0.8, 0.2
    m = bivariate_poisson_matrix([l1], [l2], [l3], max_goals=30)[0]
    g = np.arange(31)
    np.testing.assert_allclose(m.sum(axis=1), poisson_pmf(g, l1 + l3), atol=1e-12)
    np.testing.assert_allclose(m.sum(axis=0), poisson_pmf(g, l2 + l3), atol=1e-12)
    ex, ey = (g * m.sum(axis=1)).sum(), (g * m.sum(axis=0)).sum()
    cov = (np.outer(g, g) * m).sum() - ex * ey
    assert cov == pytest.approx(l3, abs=1e-9)


def test_goal_difference_does_not_depend_on_lambda3():
    # Sección 2.2 del paper: X - Y = X1 - X2 no depende de lam3 (con lam1, lam2 fijos).
    def diff_dist(l3):
        m = bivariate_poisson_matrix([1.3], [0.9], [l3], max_goals=30)[0]
        x, y = np.indices(m.shape)
        return np.bincount((x - y + 30).ravel(), weights=m.ravel())
    np.testing.assert_allclose(diff_dist(0.0), diff_dist(0.3), atol=1e-12)


def test_monte_carlo_agrees_with_the_grid():
    rng = np.random.default_rng(0)
    l1, l2, l3, n = 1.2, 0.9, 0.25, 400_000
    x3 = rng.poisson(l3, n)
    x, y = rng.poisson(l1, n) + x3, rng.poisson(l2, n) + x3
    m = bivariate_poisson_matrix([l1], [l2], [l3])[0]
    for a, b in [(0, 0), (1, 1), (2, 2), (1, 0), (2, 1)]:
        assert np.mean((x == a) & (y == b)) == pytest.approx(m[a, b], abs=0.003)


def test_with_fixed_means_more_covariance_means_more_draws():
    lam, mu = np.array([1.5]), np.array([1.1])
    draws = [outcome_probabilities(BivariateDependence(lam3=v).matrix(lam, mu))[0, 1] for v in (0.0, 0.05, 0.1, 0.2)]
    assert all(a < b for a, b in zip(draws, draws[1:]))
    # las medias de las regresiones se conservan (salvo el recorte de la grilla en 10 goles, ~5e-6)
    m = BivariateDependence(lam3=0.2).matrix(lam, mu)[0]
    g = np.arange(m.shape[0])
    assert (g * m.sum(axis=1)).sum() == pytest.approx(1.5, abs=1e-4)
    assert (g * m.sum(axis=0)).sum() == pytest.approx(1.1, abs=1e-4)


def test_proportional_lambda3_is_always_valid():
    lam, mu = np.array([3.0, 0.2, 1.0]), np.array([0.1, 2.5, 1.0])
    dep = BivariateDependence(kappa=4.0)
    lam3 = dep.shared_rate(lam, mu)
    assert np.all(lam3 < np.minimum(lam, mu))
    np.testing.assert_allclose(lam3, 4.0 * np.minimum(lam - lam3, mu - lam3))
    np.testing.assert_allclose(dep.matrix(lam, mu).sum(axis=(1, 2)), 1.0)
    with pytest.raises(ValueError):
        BivariateDependence(lam3=0.5).matrix([0.4], [1.0])


def test_inflate_diagonal():
    m = score_matrix([1.4, 0.9], [1.0, 1.2])
    theta = (0.2, 0.5, 0.2, 0.1)
    out = inflate_diagonal(m, 0.1, theta)
    np.testing.assert_allclose(out.sum(axis=(1, 2)), 1.0)
    assert out[0, 1, 0] == pytest.approx(0.9 * m[0, 1, 0])
    assert out[0, 1, 1] == pytest.approx(0.9 * m[0, 1, 1] + 0.1 * 0.5)
    assert out[0, 4, 4] == pytest.approx(0.9 * m[0, 4, 4])       # fuera de 0..J no se infla
    with pytest.raises(ValueError):
        inflate_diagonal(m, 0.1, (0.5, 0.2))


def simulate(n, lam3=None, kappa=None, seed=1):
    rng = np.random.default_rng(seed)
    elo = rng.normal(0, 180, n)
    lam, mu = np.exp(0.33 + 0.0017 * elo), np.exp(0.07 - 0.0017 * elo)
    l3 = BivariateDependence(lam3=lam3 or 0.0, kappa=kappa or 0.0).shared_rate(lam, mu)
    x3 = rng.poisson(l3)
    return elo, lam, mu, rng.poisson(lam - l3) + x3, rng.poisson(mu - l3) + x3


def test_fit_dependence_recovers_simulated_values():
    _, lam, mu, x, y = simulate(40_000, lam3=0.12)
    assert fit_dependence("constante", lam, mu, x, y).lam3 == pytest.approx(0.12, abs=0.03)
    _, lam, mu, x, y = simulate(40_000, kappa=0.15, seed=2)
    assert fit_dependence("proporcional", lam, mu, x, y).kappa == pytest.approx(0.15, abs=0.05)
    _, lam, mu, x, y = simulate(40_000, seed=3)   # independientes: sin correlación que encontrar
    assert fit_dependence("constante", lam, mu, x, y).lam3 < 0.03


def test_bivariate_glm_end_to_end():
    elo, _, _, x, y = simulate(6_000, lam3=0.1)
    df = pd.DataFrame({"elo_diff": elo, "home_goals": x, "away_goals": y,
                       "date": pd.Timestamp("2020-01-01")})
    for kind in ("constante", "proporcional", "proporcional+diagonal"):
        fc = BivariatePoissonGLMModel(["elo_diff"], kind, alpha=1e-4).fit(df).predict(df.head(50))
        np.testing.assert_allclose(fc.probs.sum(axis=1), 1.0)
        np.testing.assert_allclose(fc.matrix.sum(axis=(1, 2)), 1.0)
        assert fc.probs[np.argmax(elo[:50]), 0] > fc.probs[np.argmax(elo[:50]), 2]
    with pytest.raises(ValueError):
        BivariatePoissonGLMModel(["elo_diff"], "otra")
