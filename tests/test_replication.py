"""Replicación en otras ligas: controles de datos, Elo con otra primera división y el IC estratificado."""

import numpy as np
import pandas as pd
import pytest
from test_features import make_league

from src.data.football_data import clean_odds
from src.data.leagues import first_full_shots_season, round_robin_check
from src.features.elo import BASE_RATING, EloParams, compute_elo
from src.models.replication import stratified_ci


def double_round_robin(teams):
    return pd.DataFrame([(h, a) for h in teams for a in teams if h != a], columns=["home_team", "away_team"])


def test_round_robin_check_deduces_the_format_from_the_data():
    for n in (18, 20, 22):
        assert round_robin_check(double_round_robin([f"T{i}" for i in range(n)]))["complete"]
    season = double_round_robin([f"T{i}" for i in range(18)])
    missing = round_robin_check(season.iloc[1:])
    assert not missing["complete"] and missing["expected"] == 306 and missing["matches"] == 305
    assert round_robin_check(pd.concat([season, season.head(1)]))["repeated_pairs"] == 1


def test_first_full_shots_season_requires_all_later_seasons():
    from src.config import FIRST_SEASON_START_YEAR, season_label
    from src.data.leagues import LAST_SEASON
    seasons = range(FIRST_SEASON_START_YEAR, LAST_SEASON + 1)
    cover = {s: (1.0 if s >= 2005 else 0.0) for s in seasons}
    cover[2010] = 0.5                                   # un hueco: la cobertura completa empieza después
    report = {"seasons": {f"X1 {season_label(s)}": {"shots": c} for s, c in cover.items()}}
    assert first_full_shots_season(report, "X1") == "2011-12"


def test_elo_top_division_is_configurable():
    league = make_league(seasons=(2000,)).replace({"division": {"E0": "SP1", "E1": "SP2"}})
    params = EloParams(initial_gap=200)
    per_match, _ = compute_elo(league, params, top_division="SP1")
    first = league.sort_values(["date", "match_id"]).groupby("division").head(1)
    ratings = per_match.set_index("match_id").loc[first.match_id, "elo_home"].to_numpy()
    assert sorted(ratings) == [BASE_RATING, BASE_RATING + 200]
    # con el valor por defecto ("E0"), ninguna división arranca arriba
    default, _ = compute_elo(league, params)
    assert set(default.set_index("match_id").loc[first.match_id, "elo_home"]) == {BASE_RATING}


def test_features_of_another_league_do_not_use_the_future():
    from test_features import PARAMS, blank_from, full_frame

    from src.features.build import POST_MATCH_COLUMNS, build_features
    matches = full_frame(make_league()).replace({"division": {"E0": "SP1", "E1": "SP2"}})
    dates = np.sort(matches.loc[matches.division == "SP1", "date"].unique())
    cutoff = pd.Timestamp(dates[10])
    full, _ = build_features(matches, PARAMS, division="SP1")
    blank, _ = build_features(blank_from(matches, cutoff), PARAMS, division="SP1")
    cols = ["elo_diff", "sot_f_hl4_home", "sh_a_hl4_away"]
    before = full.date < cutoff
    pd.testing.assert_frame_equal(full.loc[before, cols].reset_index(drop=True),
                                  blank.loc[blank.date < cutoff, cols].reset_index(drop=True))
    assert set(full.division) == {"SP1"} and not set(POST_MATCH_COLUMNS) & set(cols)


def test_clean_odds_invalidates_absurd_margins():
    df = pd.DataFrame({"division": "SP2", "season": "2004-05", "date": pd.Timestamp("2004-09-01"),
                       "home_team": ["A", "B"], "away_team": ["C", "D"],
                       "b365_home": [1.8, 2.0], "b365_draw": [1.8, 3.3], "b365_away": [2.87, 3.8]})
    for book in ("b365c", "ps", "psc", "avg"):
        for o in ("home", "draw", "away"):
            df[f"{book}_{o}"] = np.nan
    clean, report = clean_odds(df)
    assert clean.loc[0, ["b365_home", "b365_draw", "b365_away"]].isna().all()     # margen del 46%
    assert clean.loc[1, "b365_home"] == 2.0 and len(report) == 1


def test_stratified_ci_pools_leagues_and_resamples_within_each():
    rng = np.random.default_rng(0)
    deltas = {"A": rng.normal(-0.01, 0.1, 4000), "B": rng.normal(0.0, 0.1, 1000)}
    mean, (lo, hi) = stratified_ci(deltas, n_boot=2000)
    assert mean == pytest.approx(np.concatenate(list(deltas.values())).mean())
    assert lo < mean < hi and hi - lo < 0.01
    same, _ = stratified_ci({"A": np.full(50, -0.02)}, n_boot=200)
    assert same == pytest.approx(-0.02)
