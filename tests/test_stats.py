"""Estadísticas de la sección Estadísticas de la web (src/export/stats.py)."""

import json

import numpy as np
import pandas as pd
import pytest

from src.export.stats import league_summary, team_match_rows


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
