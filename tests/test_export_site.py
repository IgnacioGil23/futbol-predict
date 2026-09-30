"""Resúmenes que la web muestra como texto: se calculan en la exportación, no se escriben a mano."""

import numpy as np
from scipy.stats import poisson

from src.export.site import top_score_probability


def test_top_score_probability_matches_the_full_grid_maximum():
    for lam, mu in [(0.4, 2.7), (1.0, 1.0), (1.55, 1.12), (3.2, 0.25)]:
        goals = np.arange(15)
        grid = np.outer(poisson.pmf(goals, lam), poisson.pmf(goals, mu))
        assert np.isclose(top_score_probability(lam, mu), grid.max())


def test_top_score_probability_is_vectorized():
    out = top_score_probability([1.2, 2.0], [0.8, 1.5])
    assert out.shape == (2,) and np.all((out > 0) & (out < 1))
