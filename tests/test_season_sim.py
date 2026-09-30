"""Simulación de la temporada (docs/preregistro_temporada.md)."""

import numpy as np
import pandas as pd
import pytest

from src.features.elo import EloParams
from src.models.season_sim import SeasonState, final_table, simulate, state_from_matches, summarize

PARAMS = EloParams(k0=7.5, lam=1.0, home_advantage=59.4)


def rates_from_elo(diff):
    return np.exp(0.3 + diff / 500), np.exp(0.1 - diff / 500)


def state(teams=4, elo=None, fixtures=None, points=None):
    names = [f"T{i}" for i in range(teams)]
    return SeasonState(teams=names, points=np.array(points or [0] * teams), goal_diff=np.zeros(teams),
                       goals_for=np.zeros(teams), played=np.zeros(teams), elo=np.array(elo or [1500.0] * teams),
                       fixtures=fixtures if fixtures is not None else
                       [(h, a) for h in names for a in names if h != a])


def test_no_fixtures_left_means_the_current_table_is_final():
    s = state(points=[3, 9, 6, 0], fixtures=[])
    sim = simulate(s, rates_from_elo, PARAMS, n_sims=50)
    assert (sim["positions"] == np.array([3, 1, 2, 4])).all()


def test_equal_teams_have_equal_chances_and_positions_are_a_permutation():
    sim = simulate(state(), lambda d: (np.full_like(d, 1.3), np.full_like(d, 1.3)), PARAMS, n_sims=20_000,
                   update_elo=False)
    assert (np.sort(sim["positions"], axis=1) == np.arange(1, 5)).all()
    np.testing.assert_allclose((sim["positions"] == 1).mean(axis=0), 0.25, atol=0.015)


def test_stronger_team_wins_more_and_elo_updates_are_zero_sum():
    s = state(elo=[1800.0, 1500.0, 1500.0, 1300.0])
    sim = simulate(s, rates_from_elo, PARAMS, n_sims=5_000)
    champ = (sim["positions"] == 1).mean(axis=0)
    assert champ[0] > 0.6 and champ[3] < 0.05
    np.testing.assert_allclose(sim["elo"].sum(axis=1), s.elo.sum())            # el Elo solo se transfiere
    assert not np.allclose(sim["elo"], s.elo)
    fixed = simulate(s, rates_from_elo, PARAMS, n_sims=100, update_elo=False)
    np.testing.assert_allclose(fixed["elo"], np.tile(s.elo, (100, 1)))


def test_same_seed_same_result_and_summary_probabilities():
    s = state(elo=[1700.0, 1600.0, 1500.0, 1400.0])
    a = simulate(s, rates_from_elo, PARAMS, n_sims=2_000, seed=3)
    b = simulate(s, rates_from_elo, PARAMS, n_sims=2_000, seed=3)
    assert (a["positions"] == b["positions"]).all()
    out = summarize(s, a)
    assert out["p_champion"].sum() == pytest.approx(1.0)
    assert out["p_relegation"].sum() == pytest.approx(3.0)
    assert all(np.isclose(np.sum(p), 1.0) for p in out["positions"])


def test_current_state_uses_real_table_and_simulates_only_unplayed_fixtures():
    from src.export.season import current_state
    from test_features import make_league
    from test_serving_api import store_from
    league = make_league(seasons=(2005, 2006))
    league["season"] = league["season"].astype(str)
    e0 = league[(league.division == "E0") & (league.season_start == 2006)].sort_values("date")
    today = e0["date"].iloc[5]
    future = (league.season_start == 2006) & (league.date > today)
    league.loc[future, ["home_goals", "away_goals"]] = np.nan              # lo que todavía no se jugó
    store = store_from(league)
    played = e0[e0.date <= today]
    schedule = e0.assign(time_uk=None)[["date", "time_uk", "home_team", "away_team"]]
    s = current_state(store, schedule, today)
    assert len(s.fixtures) == len(e0) - len(played)
    assert set(s.fixtures).isdisjoint(set(zip(played.home_team, played.away_team)))
    assert s.points.sum() == sum(3 if h != a else 2 for h, a in zip(played.home_goals, played.away_goals))


def test_state_from_matches_splits_known_and_remaining_and_takes_elo_before_next_match():
    season = pd.DataFrame({
        "match_id": ["m1", "m2", "m3", "m4"],
        "date": pd.to_datetime(["2020-08-01", "2020-08-01", "2020-08-08", "2020-08-08"]),
        "home_team": ["A", "C", "B", "D"], "away_team": ["B", "D", "A", "C"],
        "home_goals": [2, 0, 1, 1], "away_goals": [0, 0, 1, 3],
        "elo_home": [1500.0, 1500.0, 1490.0, 1500.0], "elo_away": [1500.0, 1500.0, 1510.0, 1500.0],
    })
    s = state_from_matches(season, pd.Timestamp("2020-08-08"))
    assert s.teams == ["A", "B", "C", "D"] and list(s.points) == [3, 0, 1, 1]
    assert list(s.elo) == [1510.0, 1490.0, 1500.0, 1500.0] and s.fixtures == [("B", "A"), ("D", "C")]
    assert list(final_table(season).team) == ["A", "C", "B", "D"]
