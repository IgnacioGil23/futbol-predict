from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from test_features import make_league
from test_serving_api import store_from

from src.models.feature_models import PoissonGLMModel
from src.monitoring.ledger import (
    COLUMNS,
    LedgerIntegrityError,
    append_entries,
    new_live_entries,
    read_ledger,
    reconstructed_entries,
    verify_append_only,
)
from src.serving.predictor import EloPoissonPredictor
from src.serving.production import export_params

NOW = datetime(2006, 10, 1, 6, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def store():
    df = make_league(seasons=(2004, 2005, 2006))
    df["season"] = df["season"].astype(str)
    # La temporada 2006 queda "sin jugar": son los próximos partidos.
    df.loc[df.season_start == 2006, ["home_goals", "away_goals"]] = np.nan
    return store_from(df)


@pytest.fixture(scope="module")
def predictor():
    rng = np.random.default_rng(0)
    train = pd.DataFrame({"elo_diff": rng.normal(0, 180, 3000), "date": pd.Timestamp("2020-01-01")})
    train["home_goals"] = rng.poisson(np.exp(0.35 + 0.0016 * train.elo_diff))
    train["away_goals"] = rng.poisson(np.exp(0.1 - 0.0017 * train.elo_diff))
    model = PoissonGLMModel(["elo_diff"]).fit(train)
    return EloPoissonPredictor({"params": export_params(model), "meta": {"elo_params": {"k0": 7.5}}})


def fixtures(*rows):
    return pd.DataFrame([{"date": pd.Timestamp(d), "HomeTeam": h, "AwayTeam": a, "Time": "15:00",
                          "B365H": 2.1, "B365D": 3.4, "B365A": 3.6} for d, h, a in rows])


def test_only_future_fixtures_are_logged(store, predictor):
    fx = fixtures(("2006-09-30", "A", "B"), ("2006-10-01", "C", "D"), ("2006-10-02", "B", "C"))
    entries = new_live_entries(fx, store, predictor, pd.DataFrame(columns=COLUMNS), NOW, "abc")
    assert list(zip(entries.home_team, entries.away_team)) == [("B", "C")]   # ayer y hoy quedan afuera
    row = entries.iloc[0]
    assert row.source == "vivo" and row.model_version == predictor.version and row.season == "2006-07"
    assert row.p_home + row.p_draw + row.p_away == pytest.approx(1.0)
    assert row.market_home + row.market_draw + row.market_away == pytest.approx(1.0)
    assert row.top_scores.count("|") == 4


def test_first_prediction_is_final_and_file_is_append_only(tmp_path, store, predictor):
    path = tmp_path / "predictions.csv"
    first = new_live_entries(fixtures(("2006-10-05", "A", "B")), store, predictor, read_ledger(path), NOW, "c1")
    assert append_entries(path, first) == 1
    before = path.read_text(encoding="utf-8")
    # Otra corrida: el mismo partido (aunque cambien las cuotas) no se vuelve a registrar; uno nuevo sí.
    later = datetime(2006, 10, 3, 6, 0, tzinfo=UTC)
    fx = fixtures(("2006-10-05", "A", "B"), ("2006-10-06", "C", "D"))
    fx.loc[0, "B365H"] = 1.5
    second = new_live_entries(fx, store, predictor, read_ledger(path), later, "c2")
    assert list(second.home_team) == ["C"]
    append_entries(path, second)
    after = path.read_text(encoding="utf-8")
    assert after.startswith(before)                       # lo anterior quedó intacto, byte por byte
    ledger = read_ledger(path)
    assert len(ledger) == 2 and ledger.iloc[0].b365_home == 2.1 and ledger.iloc[0].code_commit == "c1"


def test_duplicates_are_rejected(tmp_path, store, predictor):
    path = tmp_path / "predictions.csv"
    entries = new_live_entries(fixtures(("2006-10-05", "A", "B")), store, predictor, read_ledger(path), NOW, "c")
    append_entries(path, entries)
    with pytest.raises(LedgerIntegrityError):
        append_entries(path, entries)


def test_verify_append_only_detects_edits():
    verify_append_only("a,b\n1,2\n", "a,b\n1,2\n3,4\n")
    with pytest.raises(LedgerIntegrityError):
        verify_append_only("a,b\n1,2\n", "a,b\n1,9\n3,4\n")


def test_unknown_team_is_skipped(store, predictor):
    entries = new_live_entries(fixtures(("2006-10-05", "A", "Equipo Nuevo")), store, predictor,
                               pd.DataFrame(columns=COLUMNS), NOW, "c")
    assert entries.empty


def test_missing_odds_give_missing_market(store, predictor):
    fx = fixtures(("2006-10-05", "A", "B"))
    fx.loc[0, "B365D"] = np.nan
    row = new_live_entries(fx, store, predictor, pd.DataFrame(columns=COLUMNS), NOW, "c").iloc[0]
    assert np.isnan(row.market_home)


def test_reconstructed_rows_are_flagged_and_not_duplicated(tmp_path, predictor):
    review = [{"date": "2026-08-22", "home_team": "A", "away_team": "B", "elo": [1850.0, 1790.0],
               "market": [0.5, 0.27, 0.23]}]
    path = tmp_path / "predictions.csv"
    entries = reconstructed_entries(review, predictor, read_ledger(path), NOW, "c", "2026-09-20")
    append_entries(path, entries)
    ledger = read_ledger(path)
    assert ledger.source.tolist() == ["reconstruido"] and ledger.market_home.iloc[0] == 0.5
    assert reconstructed_entries(review, predictor, ledger, NOW, "c", "2026-09-20").empty


def test_read_ledger_rejects_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("season,home_team\n2006-07,A\n", encoding="utf-8")
    with pytest.raises(LedgerIntegrityError):
        read_ledger(path)
