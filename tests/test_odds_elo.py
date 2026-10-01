"""Rating basado en cuotas (ELO-Odds): misma mecánica que el Elo, puntaje del mercado y sin fuga."""

from dataclasses import replace

import numpy as np
import pandas as pd
from test_features import PARAMS, make_league

from src.features.elo import compute_elo
from src.features.odds_elo import calibrated_home_advantage, compute_odds_elo, market_score


def with_odds(df: pd.DataFrame, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = rng.dirichlet([4, 2.5, 3], size=len(df))
    odds = 1 / (p * 1.05)                                    # 5% de margen
    return df.assign(b365_home=odds[:, 0], b365_draw=odds[:, 1], b365_away=odds[:, 2])


def test_market_score_is_home_win_plus_half_draw_and_nan_without_odds():
    df = pd.DataFrame({"b365_home": [2.0, np.nan, 1.0], "b365_draw": [3.5, 3.0, 4.0], "b365_away": [4.0, 2.0, 9.0]})
    s = market_score(df)
    assert 0.5 < s[0] < 0.7 and np.isnan(s[1]) and np.isnan(s[2])      # cuota <= 1: inválida


def test_with_result_scores_it_is_the_usual_elo_without_goal_difference():
    df = make_league()
    df["alpha"] = df["result"].map({"H": 1.0, "D": 0.5, "A": 0.0})
    params = replace(PARAMS, lam=0.0)
    base, _ = compute_elo(df, params)
    scored, _ = compute_elo(df, params, score_column="alpha")
    pd.testing.assert_frame_equal(base, scored)


def test_matches_without_odds_do_not_update_but_count_as_played():
    df = with_odds(make_league())
    df.loc[df.season_start == 2000, ["b365_home", "b365_draw", "b365_away"]] = np.nan
    r = compute_odds_elo(df, PARAMS).set_index("match_id")
    first = df[df.season_start == 2000].match_id
    # sin cuotas en 2000-01, nadie se movió del rating inicial (1500 + ventaja de la primera división)
    assert r.loc[first, "odds_elo_home"].isin([1500.0, 1600.0]).all()
    # y en 2001 los equipos que siguen no se tratan como nuevos: E0 conserva la ventaja inicial
    opener = df[(df.season_start == 2001) & (df.division == "E0")].sort_values("date").iloc[0]
    assert r.loc[opener.match_id, "odds_elo_home"] >= 1550


def test_rating_before_a_day_ignores_that_day_and_later_odds():
    df = with_odds(make_league())
    cut = df.date.sort_values().iloc[len(df) // 2]
    altered = df.copy()
    later = altered.date >= cut
    altered.loc[later, ["b365_home", "b365_draw", "b365_away"]] = altered.loc[later, ["b365_away", "b365_draw",
                                                                                    "b365_home"]].to_numpy()
    a = compute_odds_elo(df, PARAMS).set_index("match_id")
    b = compute_odds_elo(altered, PARAMS).set_index("match_id")
    on_cut = df.loc[df.date == cut, "match_id"]
    pd.testing.assert_frame_equal(a.loc[on_cut], b.loc[on_cut])
    assert not a.loc[df.loc[df.date > cut, "match_id"]].equals(b.loc[df.loc[df.date > cut, "match_id"]])


def test_calibrated_home_advantage_matches_the_mean_market_score():
    h = calibrated_home_advantage(np.array([0.6, 0.6, np.nan]))
    assert np.isclose(1 / (1 + 10 ** (-h / 400)), 0.6, atol=1e-3)


def test_store_serves_both_ratings_and_the_model_declares_which_it_uses():
    from test_serving_api import store_from

    from src.serving.predictor import EloPoissonPredictor

    df = with_odds(make_league(seasons=(2004, 2005)))
    df["season"] = df["season"].astype(str)
    store = store_from(df)
    day = pd.Timestamp("2005-12-31")
    team = df.home_team.iloc[0]
    elo, odds = store.rating_as_of(team, day, "elo"), store.rating_as_of(team, day, "odds_elo")
    assert elo == store.elo_as_of(team, day) and np.isfinite(odds) and elo != odds
    assert all(np.isfinite(p["elo"]) for p in store.elo_series(team, day, kind="odds_elo"))
    params = {"home_goals": {"intercept": 0.3, "coef": 0.2, "feature_mean": 0, "feature_scale": 100},
              "away_goals": {"intercept": 0.1, "coef": -0.2, "feature_mean": 0, "feature_scale": 100}}
    assert EloPoissonPredictor({"params": params, "meta": {}}).rating == "elo"
    assert EloPoissonPredictor({"params": params, "meta": {"rating": "odds_elo"}}).rating == "odds_elo"


def test_frozen_elo_shadow_predicts_like_the_previous_production_model():
    from src.monitoring.shadow_ledger import FrozenEloModel
    from src.serving.predictor import EloPoissonPredictor

    params = {"home_goals": {"intercept": 0.3, "coef": 0.2, "feature_mean": 0, "feature_scale": 100},
              "away_goals": {"intercept": 0.1, "coef": -0.2, "feature_mean": 0, "feature_scale": 100}}
    predictor = EloPoissonPredictor({"params": params, "meta": {}})
    fc = FrozenEloModel(predictor).predict(pd.DataFrame({"elo_diff": [120.0, -40.0]}))
    single = predictor.predict(1860.0, 1740.0)
    assert np.isclose(fc.lam[0], single.lam) and np.allclose(fc.probs[0], single.probs)


def test_shots_candidate_keeps_its_preregistered_baseline():
    # docs/preregistro_tiros.md compara contra el modelo de Elo de resultados, aunque producción haya cambiado.
    from src.models import confirm_shots
    from src.serving.production import FEATURES

    assert confirm_shots.CHAMPION_FEATURES == ["elo_diff"]
    assert confirm_shots.CANDIDATE[0] == "elo_diff" and FEATURES == ["odds_elo_diff"]


def test_shots_baseline_ledger_joins_old_production_rows_and_the_elo_shadow():
    from src.models.confirm_shots import elo_baseline_ledger

    def rows(teams, version, p):
        return pd.DataFrame({"season": "2026-27", "season_start": 2026, "home_team": teams, "away_team": "Z",
                             "source": "vivo", "model_version": version, "p_home": p, "p_draw": 0.3, "p_away": 0.7 - p})
    main = pd.concat([rows(["A", "B"], "old", 0.4), rows(["C"], "new", 0.5)])     # C ya es del modelo nuevo
    shadow = pd.concat([rows(["B"], "old", 0.9), rows(["C"], "old", 0.45)])       # B repetido: vale el primero
    out = elo_baseline_ledger(main, shadow, "old").set_index("home_team")
    assert sorted(out.index) == ["A", "B", "C"] and out.loc["B", "p_home"] == 0.4 and out.loc["C", "p_home"] == 0.45
