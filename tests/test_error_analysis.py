"""Análisis de errores: ascendidos y agregación por grupos."""

import numpy as np
import pandas as pd
import pytest

from src.analysis.error_analysis import promoted_teams, summarize_groups


def test_promoted_teams_are_new_to_the_top_division():
    m = pd.DataFrame({"division": ["E0", "E0", "E0", "E0", "E1"], "season_start": [2020, 2020, 2021, 2021, 2021],
                      "home_team": ["A", "B", "A", "C", "B"], "away_team": ["B", "A", "C", "A", "D"]})
    assert promoted_teams(m) == {(2021, "C")}          # la primera temporada no tiene "anterior"


def test_group_shares_add_up_to_the_total_gap():
    rng = np.random.default_rng(0)
    d = pd.DataFrame({"gap": rng.normal(0.02, 0.3, 600), "ll_model": 1.0, "ll_market": 0.98})
    key = pd.Series(rng.choice(["a", "b", "c"], 600))
    rows = summarize_groups(d, key, float(d["gap"].sum()), rng)
    assert sum(r["share_of_total_gap"] for r in rows) == pytest.approx(1.0)
    assert sum(r["n"] for r in rows) == 600
    assert all(r["ci"][0] <= r["gap"] <= r["ci"][1] for r in rows)
