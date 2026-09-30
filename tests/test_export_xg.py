"""xG por club para la web: une la historia y el registro en vivo con los resultados, sin duplicar partidos."""

import numpy as np
import pandas as pd
from test_features import make_league
from test_serving_api import store_from

from src.export.xg import season_table, team_matches


def test_history_and_live_rows_join_results_and_do_not_duplicate():
    league = make_league(seasons=(2024, 2025))
    league["season"] = league["season"].astype(str)
    store = store_from(league)
    pl = league[league.division == "E0"]
    h24 = pl[pl.season_start == 2024].head(4)
    history = pd.concat([pd.DataFrame({"match_id": h24.match_id, "season_start": 2024, "date": h24.date.dt.strftime("%Y-%m-%d"),
                                       "team": h24[f"{side}_team"], "is_home": side == "home",
                                       "xg_f": 1.0 if side == "home" else 0.5, "xg_a": 0.5 if side == "home" else 1.0})
                         for side in ("home", "away")])
    m25 = pl[pl.season_start == 2025].head(2)
    live = pd.concat([pd.DataFrame({"season": "2025-26", "season_start": 2025, "match_date": m25.date.dt.strftime("%Y-%m-%d"),
                                    "home_team": m25.home_team, "away_team": m25.away_team, "team": m25[f"{side}_team"],
                                    "is_home": "True" if side == "home" else "False",
                                    "xg_f": 2.0 if side == "home" else 0.2, "xg_a": 0.2 if side == "home" else 2.0})
                      for side in ("home", "away")])
    tm = team_matches(store, history, pd.concat([live, live]))          # el registro repetido no duplica partidos
    assert len(tm) == 2 * 4 + 2 * 2
    row = tm[(tm.match_id == h24.match_id.iloc[0]) & tm.is_home].iloc[0]
    assert row.gf == h24.home_goals.iloc[0] and row.ga == h24.away_goals.iloc[0] and row.xg_f == 1.0
    table = season_table(tm[tm.season_start == 2025])
    assert table["matches"] == 2 and table["league"]["xg_per_team_game"] == np.mean([2.0, 0.2, 2.0, 0.2])
    diffs = [(t["xg_for"] - t["xg_against"]) / t["played"] for t in table["teams"]]
    assert diffs == sorted(diffs, reverse=True)
