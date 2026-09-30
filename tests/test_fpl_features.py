"""Variables de Fantasy (candidatos A y B) y el modelo con offset (docs/preregistro_fpl.md)."""

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import PoissonRegressor

from src.features.fpl_features import lineup_features, match_features, team_matches, xg_features
from src.models.fpl_eval import OffsetPoisson

TEAMS = ["A", "B", "C", "D"]


def synthetic_players(n_rounds=8, seed=0, missing_rounds=0):
    """4 equipos, 2 partidos por fecha (una por semana), 12 jugadores por equipo (11 titulares)."""
    rng = np.random.default_rng(seed)
    rows, dates = [], []
    pairings = [[("A", "B"), ("C", "D")], [("C", "A"), ("D", "B")], [("A", "D"), ("B", "C")]]
    for r in range(n_rounds):
        day = pd.Timestamp("2023-08-12") + pd.Timedelta(days=7 * r)
        for k, (h, a) in enumerate(pairings[r % 3]):
            mid = f"r{r}m{k}"
            dates.append({"match_id": mid, "date": day})
            for team, home in ((h, True), (a, False)):
                bench = rng.integers(0, 12)                      # rotación: un titular distinto cada partido
                for p in range(12):
                    start = float(p != bench) if r >= missing_rounds else np.nan
                    rows.append({"season_start": 2023, "match_id": mid, "team": team, "is_home": home,
                                 "element": f"{team}{p}", "starts": start, "price": 40.0 + 5 * p,
                                 "expected_goals": rng.uniform(0, 0.3) if r >= missing_rounds else np.nan})
    return pd.DataFrame(rows), pd.DataFrame(dates)


def test_team_level_sums_and_opponent_xg():
    players, dates = synthetic_players(n_rounds=1)
    tm = team_matches(players, dates).set_index(["match_id", "team"])
    p = players.set_index(["match_id", "team"])
    for key in tm.index:
        assert tm.loc[key, "xg_f"] == pytest.approx(p.loc[key, "expected_goals"].sum())
        mine = p.loc[key]
        assert tm.loc[key, "xi_value"] == mine.loc[mine.starts == 1, "price"].sum()
    assert tm.loc[("r0m0", "A"), "xg_a"] == tm.loc[("r0m0", "B"), "xg_f"]


def test_unrecorded_lineups_are_missing_not_zero():
    players, dates = synthetic_players(n_rounds=4, missing_rounds=2)
    tm = team_matches(players, dates)
    early = tm["match_id"].str.startswith(("r0", "r1"))
    assert tm.loc[early, ["xg_f", "xi_value"]].isna().all().all()
    lf = lineup_features(tm).set_index(["match_id", "team"])
    assert lf.loc[tm.loc[early, ["match_id", "team"]].apply(tuple, axis=1), "xi_dev"].isna().all()
    # primer partido registrado de cada equipo: sin historia -> desviación 0
    first = tm[~early].sort_values("date").groupby("team").head(1)
    assert (lf.loc[first[["match_id", "team"]].apply(tuple, axis=1), "xi_dev"] == 0).all()


def test_known_values():
    players, dates = synthetic_players(n_rounds=3)
    tm = team_matches(players, dates)
    a = tm[tm.team == "A"].sort_values("date").reset_index(drop=True)
    lf = lineup_features(tm).set_index(["match_id", "team"])
    # tercer partido de A: habitual = promedio de los dos anteriores
    expected = a.loc[2, "xi_value"] / a.loc[:1, "xi_value"].mean() - 1
    assert lf.loc[(a.loc[2, "match_id"], "A"), "xi_dev"] == pytest.approx(expected)
    assert lf.loc[(a.loc[2, "match_id"], "A"), "xi_dev_prev"] == pytest.approx(lf.loc[(a.loc[1, "match_id"], "A"), "xi_dev"])
    xf = xg_features(tm).set_index(["match_id", "team"])
    assert np.isnan(xf.loc[(a.loc[0, "match_id"], "A"), "xg_f_hl4"])
    assert xf.loc[(a.loc[1, "match_id"], "A"), "xg_f_hl4"] == pytest.approx(a.loc[0, "xg_f"])
    w = 0.5 ** (1 / 4)                                    # peso del partido anterior con vida media 4
    assert xf.loc[(a.loc[2, "match_id"], "A"), "xg_f_hl4"] == pytest.approx(
        (w * a.loc[0, "xg_f"] + a.loc[1, "xg_f"]) / (w + 1))


@pytest.mark.parametrize("cut_round", [2, 4, 6])
def test_no_future_information(cut_round):
    players, dates = synthetic_players(n_rounds=8)
    base = match_features(players, dates).set_index("match_id")
    cut = dates.loc[dates.match_id == f"r{cut_round}m0", "date"].iloc[0]
    future_ids = dates.loc[dates.date >= cut, "match_id"]
    changed = players.copy()
    fut = changed.match_id.isin(future_ids)
    changed.loc[fut, "expected_goals"] = 9.0
    changed.loc[fut, "price"] = 999.0
    changed.loc[fut, "starts"] = changed.loc[fut, "starts"][::-1].to_numpy()
    after = match_features(changed, dates).set_index("match_id")
    past = dates.loc[dates.date < cut, "match_id"]
    pd.testing.assert_frame_equal(base.loc[past], after.loc[past])
    # A y el control de B no usan nada del día del partido; B sí usa la alineación del propio partido
    same_day = dates.loc[dates.date == cut, "match_id"]
    cols = ["xg_f_hl4_home", "xg_a_hl4_home", "xg_f_hl4_away", "xg_a_hl4_away", "xi_dev_prev_home", "xi_dev_prev_away"]
    pd.testing.assert_frame_equal(base.loc[same_day, cols], after.loc[same_day, cols])
    assert not np.allclose(base.loc[same_day, "xi_dev_home"], after.loc[same_day, "xi_dev_home"])


def test_offset_poisson_matches_sklearn_without_intercept():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(3000, 3))
    y = rng.poisson(np.exp(0.3 * x[:, 0] - 0.2 * x[:, 2]))
    ours = OffsetPoisson(alpha=1e-4).fit(x, y, np.zeros(len(y)))
    z = (x - x.mean(axis=0)) / x.std(axis=0)
    ref = PoissonRegressor(alpha=1e-4, fit_intercept=False, tol=1e-10, max_iter=1000).fit(z, y)
    np.testing.assert_allclose(ours.coef_, ref.coef_, atol=1e-5)


def test_offset_poisson_recovers_signal_and_is_neutral_without_it():
    rng = np.random.default_rng(1)
    n = 20_000
    offset = rng.normal(0.2, 0.3, n)
    signal, noise = rng.normal(size=n), rng.normal(size=n)
    y = rng.poisson(np.exp(offset + 0.15 * signal))
    fit = OffsetPoisson().fit(np.column_stack([signal, noise]), y, offset)
    assert fit.coef_[0] == pytest.approx(0.15, abs=0.02) and abs(fit.coef_[1]) < 0.02
    # sin señal: la corrección es casi nula y el modelo vuelve al offset
    y0 = rng.poisson(np.exp(offset))
    neutral = OffsetPoisson().fit(noise[:, None], y0, offset)
    assert np.max(np.abs(neutral.log_rate(noise[:, None], offset) - offset)) < 0.05
