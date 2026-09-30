from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.monitoring.evaluate import evaluate, history_row, indicator_status, issue_markdown
from src.monitoring.ledger import COLUMNS, prediction_row
from test_features import make_league
from test_ledger import predictor  # noqa: F401  (fixture)
from test_serving_api import store_from

NOW = datetime(2007, 6, 1, tzinfo=timezone.utc)


def thresholds(window=10, gap_hi=(0.03, 0.04)):
    def band(lo2, hi2, lo05, hi05, one_sided=False):
        return {"p0.5": lo05, "p2.5": lo2, "median": (lo2 + hi2) / 2, "p97.5": hi2, "p99.5": hi05, "one_sided": one_sided}
    return {
        "computed_on": "2026-09-30", "window": window, "backtest": {"seasons": "test"},
        "indicators": {
            "gap_vs_market": band(-0.01, gap_hi[0], -0.02, gap_hi[1], one_sided=True),
            "goals_ratio": band(0.9, 1.2, 0.85, 1.3),
            "draws_diff_pp": band(-5, 6, -8, 8),
            "home_residual": band(-0.4, 0.1, -0.45, 0.2),
        },
    }


@pytest.fixture(scope="module")
def store():
    df = make_league(seasons=(2004, 2005, 2006))
    df["season"] = df["season"].astype(str)
    df.loc[(df.season_start == 2006) & (df.date > "2006-09-01"), ["home_goals", "away_goals"]] = np.nan
    return store_from(df)


def ledger_for(store, predictor, market_shift=0.0):  # noqa: F811
    """Registro con una predicción por partido de E0 de 2005-06 y 2006-07 (jugados o no)."""
    rows = []
    for r in store.matches[(store.matches.division == "E0") & (store.matches.season_start >= 2005)].itertuples():
        row = prediction_row(predictor, home=r.home_team, away=r.away_team, match_date=r.date,
                             elo_home=r.elo_home, elo_away=r.elo_away, elo_data_until="x",
                             odds=[2.2, 3.4, 3.3], logged_at=NOW, source="vivo", code_commit="c")
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def test_indicator_status_levels_and_one_sided_gap():
    th = thresholds()
    assert indicator_status("gap_vs_market", 0.05, th, 50, 10) == "alerta"
    assert indicator_status("gap_vs_market", 0.035, th, 50, 10) == "atencion"
    assert indicator_status("gap_vs_market", -0.5, th, 50, 10) == "ok"            # mejorar al mercado no alarma
    assert indicator_status("goals_ratio", 0.8, th, 50, 10) == "alerta"            # bilateral
    assert indicator_status("goals_ratio", 1.25, th, 50, 10) == "atencion"
    assert indicator_status("goals_ratio", 1.0, th, 5, 10) == "insuficiente"       # pocos partidos


def test_evaluate_counts_only_played_matches(store, predictor):  # noqa: F811
    ledger = ledger_for(store, predictor)
    report = evaluate(ledger, store, thresholds(window=10), NOW)
    played = store.matches[(store.matches.division == "E0") & (store.matches.season_start >= 2005)
                           & store.matches.home_goals.notna()]
    assert report["counts"]["evaluated"] == len(played)
    assert report["counts"]["pending"] == len(ledger) - len(played)
    assert set(report["indicators"]) == {"gap_vs_market", "goals_ratio", "draws_diff_pp", "home_residual"}
    assert report["status"] in {"ok", "atencion", "alerta"}
    s = report["season"]
    assert s["goals"]["actual"] == pytest.approx(played[played.season_start == 2006][["home_goals", "away_goals"]].sum().sum())
    assert report["recent"][0]["date"] >= report["recent"][-1]["date"]            # más recientes primero


def test_insufficient_when_window_not_reached(store, predictor):  # noqa: F811
    report = evaluate(ledger_for(store, predictor), store, thresholds(window=10_000), NOW)
    assert report["status"] == "insuficiente"
    assert all(i["status"] == "insuficiente" for i in report["indicators"].values())


def test_empty_ledger_is_handled(store):
    report = evaluate(pd.DataFrame(columns=COLUMNS), store, thresholds(), NOW)
    assert report["status"] == "insuficiente" and report["counts"]["evaluated"] == 0


def test_alert_issue_and_history_row(store, predictor):  # noqa: F811
    report = evaluate(ledger_for(store, predictor), store, thresholds(window=10, gap_hi=(-0.9, -0.8)), NOW)
    assert report["indicators"]["gap_vs_market"]["status"] == "alerta"
    body = issue_markdown(report)
    assert "Alerta" in body and "Brecha de log loss" in body
    row = history_row(report)
    assert row["status"] == "alerta" and "gap_vs_market" in row


def test_report_only_rewritten_when_something_besides_timestamp_changes(tmp_path):
    import json
    from src.monitoring.evaluate import report_changed
    path = tmp_path / "latest.json"
    report = {"generated_at": "2026-10-01T06:00:00+00:00", "status": "ok", "counts": {"evaluated": 10}}
    assert report_changed(path, report)
    path.write_text(json.dumps(report), encoding="utf-8")
    assert not report_changed(path, {**report, "generated_at": "2026-10-02T06:00:00+00:00"})
    assert report_changed(path, {**report, "counts": {"evaluated": 11}})
