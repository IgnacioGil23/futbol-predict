"""Estadísticas de la sección Estadísticas de la web (src/export/stats.py)."""

import json

import numpy as np
import pandas as pd
import pytest

from src.export.stats import (build_stats, league_summary, referee_stats, remaining_difficulty, team_match_rows,
                              team_stats)


def make_matches() -> pd.DataFrame:
    """Tres partidos armados a mano: A 2-1 B (0-1 al entretiempo), B 0-0 C, C 1-3 A (1-0 al entretiempo, sin cuotas)."""
    return pd.DataFrame({
        "match_id": [1, 2, 3],
        "division": ["E0"] * 3,
        "season_start": [2026] * 3,
        "date": pd.to_datetime(["2026-08-15", "2026-08-22", "2026-08-29"]),
        "home_team": ["A", "B", "C"], "away_team": ["B", "C", "A"],
        "home_goals": [2.0, 0.0, 1.0], "away_goals": [1.0, 0.0, 3.0],
        "ht_home_goals": [0.0, 0.0, 1.0], "ht_away_goals": [1.0, 0.0, 0.0],
        "home_shots": [12.0, 8.0, 9.0], "away_shots": [7.0, 10.0, 15.0],
        "home_shots_on_target": [5.0, 2.0, 3.0], "away_shots_on_target": [3.0, 4.0, 6.0],
        "home_yellow": [1.0, 2.0, 3.0], "away_yellow": [2.0, 1.0, 0.0],
        "home_red": [0.0, 0.0, 1.0], "away_red": [0.0, 0.0, 0.0],
        "referee": ["M Oliver", "A Taylor", "M Oliver"],
        "b365_home": [2.0, 2.5, np.nan], "b365_draw": [3.4, 3.2, np.nan], "b365_away": [3.8, 2.9, np.nan],
    })


matches = make_matches()


def test_rows_are_two_per_match_with_points_and_ht_state():
    rows = team_match_rows(matches)
    assert len(rows) == 6
    a1 = rows[(rows.match_id == 1) & (rows.team == "A")].iloc[0]
    assert (a1.points, a1.ht_state, a1.gf_ht, a1.is_home) == (3, "trailing", 0, True)
    b1 = rows[(rows.match_id == 1) & (rows.team == "B")].iloc[0]
    assert (b1.points, b1.ht_state) == (0, "leading")


def test_market_probs_nan_without_odds():
    rows = team_match_rows(matches)
    assert rows[rows.match_id == 3].p_win.isna().all()
    assert rows[rows.match_id == 1].p_win.notna().all()
    home, away = (rows[(rows.match_id == 1) & (rows.team == t)].iloc[0] for t in ("A", "B"))
    assert home.p_win + home.p_draw + away.p_win == pytest.approx(1.0)


def test_league_summary_values():
    s = league_summary(team_match_rows(matches))
    assert s["matches"] == 3
    assert s["home_win_pct"] == pytest.approx(1 / 3, abs=1e-4) and s["away_win_pct"] == pytest.approx(1 / 3, abs=1e-4)
    assert s["draw_pct"] == pytest.approx(1 / 3, abs=1e-4)
    assert s["goals_per_match"] == pytest.approx(7 / 3, abs=1e-4)
    assert s["first_half_goals_share"] == pytest.approx(2 / 7, abs=1e-4)
    assert s["btts_pct"] == pytest.approx(2 / 3, abs=1e-4) and s["over25_pct"] == pytest.approx(2 / 3, abs=1e-4)
    assert s["ht_leader_win_pct"] == pytest.approx(0.0)       # los dos que ganaban al entretiempo perdieron
    assert s["ht_trailer_comeback_pct"] == pytest.approx(1.0)
    assert json.dumps(s)


def test_team_stats_for_A():
    a = next(t for t in team_stats(team_match_rows(matches)) if t["team"] == "A")
    assert a["played"] == 2 and a["home"]["won"] == 1 and a["away"]["won"] == 1
    assert a["home"]["points_per_game"] == 3 and a["away"]["gf"] == 3
    assert a["ht"]["trailing"] == {"n": 2, "won": 2, "drawn": 0, "lost": 0}   # perdía al entretiempo en los dos
    assert a["ht"]["points_won_trailing"] == 6 and a["ht"]["points_dropped_leading"] == 0
    assert a["halves"]["gf_1h"] == 0 and a["halves"]["gf_2h"] == 5
    assert a["halves"]["points_1h"] == 0 and a["halves"]["points_2h"] == 6
    assert a["shots"]["accuracy"] == pytest.approx(11 / 27, abs=1e-4)          # (5 + 6) / (12 + 15)
    assert a["shots"]["sot_share"] == pytest.approx(11 / 17, abs=1e-4)         # 11 / (11 + 3 + 3)
    assert a["shots"]["pdo"] == pytest.approx(1000 * (5 / 11 + 1 - 2 / 6), abs=0.1)
    assert a["market"]["market_matches"] == 1          # el partido 3 no tiene cuotas
    assert a["market"]["points"] == 3
    assert a["streaks"] == {"unbeaten": 2, "winless": 0, "scoring": 2}


def test_streaks_count_back_from_last_match():
    b = next(t for t in team_stats(team_match_rows(matches)) if t["team"] == "B")
    assert b["streaks"] == {"unbeaten": 1, "winless": 2, "scoring": 0}


def test_ratios_are_none_without_denominator():
    one = matches[matches.match_id == 2].assign(home_shots=0.0, away_shots=0.0,
                                                home_shots_on_target=0.0, away_shots_on_target=0.0)
    b = next(t for t in team_stats(team_match_rows(one)) if t["team"] == "B")
    assert b["shots"]["accuracy"] is None and b["shots"]["pdo"] is None
    assert b["away"]["points_per_game"] is None         # B no jugó de visitante
    assert json.dumps(b, allow_nan=False)               # sin NaN que rompa el JSON


def test_referee_names_are_normalized_and_filtered():
    m = matches.assign(referee=["M Oliver", "M Oliver ", ""])
    assert referee_stats(m, min_matches=2) == [
        {"referee": "M Oliver", "matches": 2, "yellow_per_game": 3.0, "red_total": 0}]


def test_referees_below_minimum_are_left_out():
    assert [r["referee"] for r in referee_stats(matches, min_matches=2)] == ["M Oliver"]


def test_remaining_difficulty_ranks_hardest_first():
    d = remaining_difficulty([("A", "B"), ("C", "A"), ("B", "C")], {"A": 2000, "B": 1800, "C": 1600})
    assert d["A"] == {"remaining": 2, "avg_opponent_rating": 1700.0, "rank": 3}
    assert d["C"]["rank"] == 1 and d["C"]["avg_opponent_rating"] == 1900.0


def test_build_stats_without_schedule():
    s = build_stats(matches, 2026, difficulty=None, referees_next=None)
    assert s["season"] == "2026-27" and s["matches_played"] == 3
    assert s["difficulty"] is None and s["referees_next"] is None
    assert [t["team"] for t in s["teams"]] == ["A", "B", "C"]
    assert s["league_reference"]["matches"] == 0      # no hay temporadas anteriores en el fixture
    assert json.dumps(s, allow_nan=False)


def test_build_stats_reference_uses_previous_ten_seasons_only():
    old = [matches.assign(season_start=y, match_id=matches.match_id + 10 * (2026 - y)) for y in range(2014, 2026)]
    s = build_stats(pd.concat([matches, *old]), 2026, difficulty=None, referees_next=None)
    assert s["league_reference"]["matches"] == 30     # 2016-17 a 2025-26
    assert s["matches_played"] == 3
