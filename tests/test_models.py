import numpy as np
import pandas as pd
import pytest
from scipy.optimize import approx_fprime

from src.metrics import ranked_probability_score
from src.models.dixon_coles import DixonColesModel, DixonColesParams
from src.models.feature_models import PoissonGLMModel, fit_rho
from src.models.scoreline import exact_score_log_loss, outcome_probabilities, poisson_pmf, score_matrix


def test_score_matrix_is_a_distribution_and_matches_poisson():
    m = score_matrix([1.5, 0.8], [1.1, 2.0])
    np.testing.assert_allclose(m.sum(axis=(1, 2)), 1.0)
    # sin corrección, P(0-0) = exp(-lam) * exp(-mu)
    assert m[0, 0, 0] == pytest.approx(np.exp(-1.5) * np.exp(-1.1), rel=1e-5)
    probs = outcome_probabilities(m)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0)
    assert probs[0, 0] > probs[0, 2] and probs[1, 2] > probs[1, 0]


def test_outcome_orientation():
    # local muy superior: casi todo el peso en victoria local (celdas x > y)
    probs = outcome_probabilities(score_matrix([4.0], [0.2]))
    assert probs[0, 0] > 0.9


def test_negative_rho_moves_mass_to_00_and_11_as_dixon_coles():
    # Con rho < 0, tau(0,0) = 1 - lam*mu*rho > 1 y tau(1,1) = 1 - rho > 1: suben 0-0 y 1-1.
    base = score_matrix([1.4], [1.1])
    corrected = score_matrix([1.4], [1.1], rho=-0.1)
    assert corrected[0, 0, 0] > base[0, 0, 0] and corrected[0, 1, 1] > base[0, 1, 1]
    assert corrected[0, 1, 0] < base[0, 1, 0]


def test_exact_score_log_loss_and_grid_edge():
    m = score_matrix([1.0], [1.0])
    assert exact_score_log_loss(m, [0], [0]) == pytest.approx(-np.log(m[0, 0, 0]))
    assert np.isfinite(exact_score_log_loss(m, [15], [0]))


def test_rps_known_values():
    probs = np.array([[1.0, 0.0, 0.0], [0.5, 0.3, 0.2]])
    assert ranked_probability_score(probs[:1], ["H"]) == 0
    # (0.5-1)^2 + (0.8-1)^2 = 0.29 ; /2
    assert ranked_probability_score(probs[1:], ["H"]) == pytest.approx(0.145)
    # RPS penaliza más poner masa lejos del resultado: A es más lejano de H que D
    assert ranked_probability_score([[0, 0, 1.0]], ["H"]) > ranked_probability_score([[0, 1.0, 0]], ["H"])


def simulate_league(n_teams=10, seasons=3, rho=-0.08, seed=1):
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(n_teams)]
    att = pd.Series(rng.normal(0, 0.3, n_teams), index=teams)
    dfn = pd.Series(rng.normal(0, 0.3, n_teams), index=teams)
    rows, date = [], pd.Timestamp("2010-08-01")
    for _ in range(seasons):
        for h in teams:
            for a in teams:
                if h == a:
                    continue
                lam, mu = np.exp(0.25 + att[h] - dfn[a]), np.exp(att[a] - dfn[h])
                m = score_matrix([lam], [mu], rho)[0]
                cell = rng.choice(m.size, p=m.ravel())
                rows.append(dict(date=date, home_team=h, away_team=a,
                                 home_goals=float(cell // m.shape[1]), away_goals=float(cell % m.shape[1])))
                date += pd.Timedelta(days=1)
    return pd.DataFrame(rows), att, dfn


def test_dixon_coles_gradient_matches_numerical():
    df, _, _ = simulate_league(n_teams=6, seasons=1)
    model = DixonColesModel(DixonColesParams(xi=0.002, l2=1.0))
    # Accede al objetivo reconstruyendo el ajuste en un punto aleatorio
    captured = {}
    import scipy.optimize as so
    original = so.minimize

    def spy(fun, x0, **kw):
        captured["fun"] = fun
        return original(fun, x0, **kw)

    import src.models.dixon_coles as dc
    dc.minimize = spy
    try:
        model.fit(df, as_of=df.date.max() + pd.Timedelta(days=1))
    finally:
        dc.minimize = original
    fun = captured["fun"]
    theta = np.random.default_rng(0).normal(0, 0.2, 2 * 6 + 2)
    theta[-1] = -0.05
    analytic = fun(theta)[1]
    numeric = approx_fprime(theta, lambda t: fun(t)[0], 1e-6)
    np.testing.assert_allclose(analytic, numeric, rtol=1e-4, atol=1e-3)


def test_dixon_coles_recovers_simulated_strengths():
    df, att, dfn = simulate_league(n_teams=10, seasons=6, rho=-0.08)
    model = DixonColesModel(DixonColesParams(xi=0.0, window_days=10_000, l2=0.01)).fit(
        df, as_of=df.date.max() + pd.Timedelta(days=1))
    est = model.attack_ - model.attack_.mean()
    assert np.corrcoef(est[att.index], att - att.mean())[0, 1] > 0.9
    assert model.home_ == pytest.approx(0.25, abs=0.08)
    assert -0.2 < model.rho_ < 0.05


def test_fit_rho_recovers_simulated_value():
    rng = np.random.default_rng(3)
    lam, mu = rng.uniform(0.8, 2.0, 20000), rng.uniform(0.6, 1.6, 20000)
    m = score_matrix(lam, mu, rho=-0.1)
    flat = m.reshape(len(lam), -1)
    cells = np.array([rng.choice(flat.shape[1], p=row) for row in flat])
    x, y = cells // m.shape[1], cells % m.shape[1]
    assert fit_rho(lam, mu, x.astype(float), y.astype(float)) == pytest.approx(-0.1, abs=0.04)


def test_poisson_glm_recovers_linear_log_rates():
    rng = np.random.default_rng(5)
    n = 20000
    df = pd.DataFrame({"f1": rng.normal(size=n), "f2": rng.normal(size=n),
                       "date": pd.Timestamp("2020-01-01")})
    df["home_goals"] = rng.poisson(np.exp(0.4 + 0.3 * df.f1))
    df["away_goals"] = rng.poisson(np.exp(0.1 - 0.2 * df.f1 + 0.1 * df.f2))
    model = PoissonGLMModel(["f1", "f2"], alpha=1e-6).fit(df)
    coefs = model.coefficients()  # sobre features estandarizadas (std ~1)
    assert coefs.loc["f1", "goles_local"] == pytest.approx(0.3, abs=0.03)
    assert coefs.loc["f1", "goles_visitante"] == pytest.approx(-0.2, abs=0.03)
    assert abs(coefs.loc["f2", "goles_local"]) < 0.03


def test_numpy_poisson_pmf_matches_scipy():
    from scipy.stats import poisson
    k = np.arange(0, 11)[None, :]
    lam = np.array([0.05, 0.4, 1.37, 2.9, 6.5])[:, None]
    np.testing.assert_allclose(poisson_pmf(k, lam), poisson.pmf(k, lam), rtol=1e-12, atol=0)
