"""Valor del plantel en cada fecha (Transfermarkt): club y valor por el último evento anterior, sin futuro."""

import numpy as np
import pandas as pd
import pytest

from src.data.transfermarkt import STALE_DAYS, TOP_PLAYERS, link_clubs, player_events, squad_value
from src.models.squad_value_eval import add_value_gap

D = pd.Timestamp


def events():
    valuations = pd.DataFrame({
        "player_id": [1, 1, 2, 3, 4],
        "date": ["2020-01-01", "2020-07-01", "2020-01-01", "2020-01-01", "2015-01-01"],
        "current_club_id": [10, 10, 20, 10, 10],
        "market_value_in_eur": [5e6, 8e6, 20e6, 1e6, 3e6],
    })
    # el jugador 2 pasa del club 20 al 10 el 2020-08-01 con un valor de 25 millones
    transfers = pd.DataFrame({"player_id": [2], "transfer_date": ["2020-08-01"], "to_club_id": [10],
                              "market_value_in_eur": [25e6]})
    return player_events(valuations, transfers)


def test_club_and_value_come_from_the_latest_previous_event():
    ev = events()
    dates = np.array([D("2020-06-30"), D("2020-08-01"), D("2020-08-02")], dtype="datetime64[ns]")
    club10 = squad_value(ev, 10, dates)
    # 30/06: jugador 1 (5M) + jugador 3 (1M); el 4 está desactualizado (último evento en 2015)
    assert club10[0] == pytest.approx(6e6)
    # 01/08: el fichaje de ese mismo día todavía no cuenta (solo eventos anteriores); el 1 ya vale 8M
    assert club10[1] == pytest.approx(9e6)
    # 02/08: el fichaje cuenta con el valor de su transferencia
    assert club10[2] == pytest.approx(34e6)
    club20 = squad_value(ev, 20, dates)
    assert club20[0] == pytest.approx(20e6) and np.isnan(club20[2])        # ya no está en el club 20


def test_stale_players_drop_out_and_only_the_top_players_count():
    many = pd.DataFrame({"player_id": range(TOP_PLAYERS + 5), "date": "2020-01-01", "current_club_id": 10,
                         "market_value_in_eur": np.arange(1, TOP_PLAYERS + 6) * 1e6})
    ev = player_events(many, pd.DataFrame(columns=["player_id", "transfer_date", "to_club_id", "market_value_in_eur"]))
    value = squad_value(ev, 10, np.array([D("2020-02-01")], dtype="datetime64[ns]"))[0]
    assert value == pytest.approx(sum(range(6, TOP_PLAYERS + 6)) * 1e6)    # los 25 más valiosos
    late = D("2020-01-01") + pd.Timedelta(days=STALE_DAYS + 1)
    assert np.isnan(squad_value(ev, 10, np.array([late], dtype="datetime64[ns]"))[0])


def test_clubs_are_linked_by_date_and_score():
    games = pd.DataFrame({"competition_id": "GB1", "date": ["2020-09-12", "2020-09-12", "2020-09-19"],
                          "home_club_id": [1, 3, 2], "away_club_id": [2, 4, 1],
                          "home_club_goals": [2, 0, 1], "away_club_goals": [1, 0, 1]})
    matches = pd.DataFrame({"division": "E0", "season_start": 2020, "date": pd.to_datetime(["2020-09-12", "2020-09-12", "2020-09-19"]),
                            "home_team": ["A", "C", "B"], "away_team": ["B", "D", "A"],
                            "home_goals": [2, 0, 1], "away_goals": [1, 0, 1]})
    mapping, report = link_clubs(games, matches, "GB1", "E0")
    assert mapping == {1: "A", 2: "B", 3: "C", 4: "D"}
    assert report["linked"] == report["same_score"] == 3 and report["clubs_to_one_team"]


def test_value_gap_is_log_ratio_and_zero_when_missing():
    df = pd.DataFrame({"match_id": ["a", "b"]})
    values = pd.DataFrame({"match_id": ["a"], "squad_value_home": [200e6], "squad_value_away": [100e6]})
    out = add_value_gap(df, values)
    assert out.loc[0, "value_gap"] == pytest.approx(np.log(2)) and out.loc[1, "value_gap"] == 0.0
