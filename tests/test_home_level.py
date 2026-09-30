"""Candidato L: interceptos reestimados con temporadas recientes (docs/preregistro_local.md)."""

import numpy as np
import pandas as pd
import pytest

from src.models.feature_models import PoissonGLMModel
from src.models.home_level import predict_with_intercepts, recent_intercepts


def simulate(n, home_level, seed):
    rng = np.random.default_rng(seed)
    elo = rng.normal(0, 180, n)
    return pd.DataFrame({"elo_diff": elo, "date": pd.Timestamp("2020-01-01"),
                         "home_goals": rng.poisson(np.exp(home_level + 0.0016 * elo)),
                         "away_goals": rng.poisson(np.exp(0.1 - 0.0016 * elo))})


def test_intercepts_are_the_exact_mle_with_fixed_slope():
    model = PoissonGLMModel(["elo_diff"], alpha=1e-4).fit(simulate(20_000, 0.45, 0))
    recent = simulate(20_000, 0.25, 1)                          # la ventaja de local bajó
    b_home, b_away = recent_intercepts(model, recent)
    # en el máximo, los goles esperados suman exactamente los observados
    fc = predict_with_intercepts(model, recent, (b_home, b_away))
    assert fc.lam.sum() == pytest.approx(recent.home_goals.sum()) and fc.mu.sum() == pytest.approx(recent.away_goals.sum())
    base = model.predict(recent)
    assert fc.probs[:, 0].mean() < base.probs[:, 0].mean()     # menos victorias locales, como en los datos


def test_same_data_gives_back_the_model_intercepts():
    data = simulate(20_000, 0.35, 2)
    model = PoissonGLMModel(["elo_diff"], alpha=1e-4).fit(data)
    b_home, b_away = recent_intercepts(model, data)
    assert b_home == pytest.approx(model.home_[-1].intercept_, abs=2e-3)
    assert b_away == pytest.approx(model.away_[-1].intercept_, abs=2e-3)
    np.testing.assert_allclose(predict_with_intercepts(model, data, (b_home, b_away)).probs,
                               model.predict(data).probs, atol=2e-3)
