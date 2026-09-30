"""Evaluación final preregistrada de A (xG) y elección entre A y el candidato de tiros (docs/preregistro_xg.md)."""

import numpy as np
import pandas as pd
import pytest

from src.models import confirm_shots, fpl_eval
from src.models.fpl_eval import choose
from src.monitoring.ledger import COLUMNS
from src.monitoring.shadow_ledger import SHADOW_COLUMNS, SHADOW_XG_COLUMNS

PASS, FAIL = {"promote": True}, {"promote": False}


@pytest.mark.parametrize("a, s, head, chosen", [
    (PASS, FAIL, None, "xg"),
    (FAIL, PASS, None, "tiros"),
    (FAIL, FAIL, None, None),
    (PASS, PASS, {"ci_low": -0.01, "ci_high": -0.001}, "xg"),
    (PASS, PASS, {"ci_low": 0.001, "ci_high": 0.01}, "tiros"),
    (PASS, PASS, {"ci_low": -0.004, "ci_high": 0.003}, "tiros"),      # sin diferencia concluyente: desempate
])
def test_choice_rule(a, s, head, chosen):
    assert choose(a, s, head)["chosen"] == chosen


def test_final_pools_history_with_paired_ledger_matches(monkeypatch):
    hist_ids = [f"h{i}" for i in range(200)]
    prod_hist = pd.Series(1.0, index=hist_ids)
    monkeypatch.setattr(fpl_eval, "a_historical", lambda df: (prod_hist, prod_hist - 0.02))
    monkeypatch.setattr(confirm_shots, "final", lambda *a, **k: {"decision": {"promote": True}})
    monkeypatch.setattr(confirm_shots, "walk_forward", lambda df, feats, seasons: None)
    monkeypatch.setattr(confirm_shots, "per_match_log_loss", lambda pred, df: prod_hist - 0.001)

    teams = [(f"H{i}", f"A{i}") for i in range(30)]
    results = pd.DataFrame({"season_start": 2026, "home_team": [h for h, _ in teams],
                            "away_team": [a for _, a in teams], "date": pd.Timestamp("2026-10-10"),
                            "home_goals": 1.0, "away_goals": 0.0, "result": "H", "division": "E0"})

    class Store:
        matches = results

    def ledger(cols, rows, p_home):
        df = pd.DataFrame({c: np.nan for c in cols}, index=range(len(rows)))
        df["season"], df["season_start"], df["source"] = "2026-27", 2026, "vivo"
        df["home_team"], df["away_team"] = [h for h, _ in rows], [a for _, a in rows]
        df["p_home"], df["p_draw"], df["p_away"] = p_home, (1 - p_home) / 2, (1 - p_home) / 2
        return df

    rep = fpl_eval.final(None, ledger(COLUMNS, teams, 0.5), ledger(SHADOW_XG_COLUMNS, teams[:25], 0.6),
                         ledger(SHADOW_COLUMNS, teams, 0.55), Store, 2026)
    assert rep["a_coverage"]["paired"] == 25 and rep["a_coverage"]["main_without_xg"] == 5
    assert rep["a_decision"]["n"] == 225 and rep["a_decision"]["promote"]
    # cara a cara A − tiros: solo partidos con predicción de ambos (200 históricos + 25 de 2026-27)
    assert rep["head_to_head_a_minus_shots"]["n"] == 225
    assert rep["head_to_head_a_minus_shots"]["diff"] < 0 and rep["choice"]["chosen"] == "xg"
