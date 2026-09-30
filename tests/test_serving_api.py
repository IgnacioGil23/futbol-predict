from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.features.elo import compute_elo
from src.models.feature_models import PoissonGLMModel
from src.serving.predictor import EloPoissonPredictor
from src.serving.production import export_params
from src.serving.store import MatchStore, build_serving_matches
from test_features import PARAMS, make_league


def store_from(matches: pd.DataFrame) -> MatchStore:
    elo, history = compute_elo(matches, PARAMS)
    return MatchStore(build_serving_matches(matches.assign(result=matches["result"].astype(str)), elo, history))


@pytest.fixture(scope="module")
def league():
    df = make_league(seasons=(2004, 2005, 2006))
    df["season"] = df["season"].astype(str)
    return df


def test_json_predictor_matches_sklearn_model():
    rng = np.random.default_rng(0)
    train = pd.DataFrame({"elo_diff": rng.normal(0, 180, 5000), "date": pd.Timestamp("2020-01-01")})
    train["home_goals"] = rng.poisson(np.exp(0.35 + 0.0016 * train.elo_diff))
    train["away_goals"] = rng.poisson(np.exp(0.1 - 0.0017 * train.elo_diff))
    model = PoissonGLMModel(["elo_diff"], alpha=1e-4).fit(train)
    predictor = EloPoissonPredictor({"params": export_params(model), "meta": {}})
    grid = pd.DataFrame({"elo_diff": np.linspace(-500, 500, 21)})
    lam, mu = predictor.rates(grid.elo_diff)
    fc = model.predict(grid)
    np.testing.assert_allclose(lam, fc.lam, rtol=1e-10)
    np.testing.assert_allclose(mu, fc.mu, rtol=1e-10)
    pred = predictor.predict(1800, 1600)
    assert pred.probs.sum() == pytest.approx(1.0) and pred.probs[0] > pred.probs[2]
    assert pred.top_scores(3)[0]["probability"] >= pred.top_scores(3)[1]["probability"]


def test_elo_as_of_never_uses_results_from_that_day_or_later(league):
    full = store_from(league)
    dates = np.sort(league.loc[league.division == "E0", "date"].unique())
    for cutoff in dates[[1, 5, 6, 10, 13]]:
        cutoff = pd.Timestamp(cutoff)
        blanked = league.copy()
        blanked.loc[blanked.date >= cutoff, ["home_goals", "away_goals"]] = np.nan
        partial = store_from(blanked)
        for team in full.teams():
            assert full.elo_as_of(team, cutoff) == pytest.approx(partial.elo_as_of(team, cutoff)), (team, cutoff)


def test_elo_as_of_equals_pre_match_rating_on_match_day(league):
    store = store_from(league)
    row = store.matches.iloc[40]
    assert store.elo_as_of(row.home_team, row.date) == pytest.approx(row.elo_home)


def test_context_uses_only_previous_matches(league):
    store = store_from(league)
    day = pd.Timestamp(np.sort(league.date.unique())[12])
    for team in store.teams():
        for m in store.recent_form(team, day, n=10):
            assert pd.Timestamp(m["date"]) < day
        rest = store.rest(team, day)
        assert rest["days_since_last_match"] is None or rest["days_since_last_match"] > 0
    table = store.standings("E0", 2004, pd.Timestamp("2004-08-01"))
    assert (table.played == 0).all()


@pytest.fixture()
def client(league, monkeypatch):
    import src.api.main as api
    store = store_from(league)
    rng = np.random.default_rng(1)
    train = pd.DataFrame({"elo_diff": rng.normal(0, 180, 3000), "date": pd.Timestamp("2020-01-01")})
    train["home_goals"] = rng.poisson(np.exp(0.35 + 0.0016 * train.elo_diff))
    train["away_goals"] = rng.poisson(np.exp(0.1 - 0.0017 * train.elo_diff))
    predictor = EloPoissonPredictor({"params": export_params(PoissonGLMModel(["elo_diff"]).fit(train)),
                                     "meta": {"trained_at": "test"}})
    app = api.app
    # Los endpoints resuelven get_store/get_predictor por Depends (override) y el cálculo
    # cacheado los llama directo (monkeypatch). Primero el override, con las funciones originales.
    app.dependency_overrides[api.get_store] = lambda: store
    app.dependency_overrides[api.get_predictor] = lambda: predictor
    monkeypatch.setattr(api, "get_store", lambda: store)
    monkeypatch.setattr(api, "get_predictor", lambda: predictor)
    monkeypatch.setattr(api, "MIN_DATE", date(2004, 1, 1))
    api._predict_cached.cache_clear()
    yield TestClient(app)
    app.dependency_overrides.clear()
    api._predict_cached.cache_clear()


def test_predict_endpoint(client):
    r = client.get("/predict", params={"home": "A", "away": "B", "date": "2005-09-01"})
    assert r.status_code == 200, r.text
    body = r.json()
    p = body["probabilities"]
    assert p["home"] + p["draw"] + p["away"] == pytest.approx(1.0, abs=1e-9)
    assert len(body["score_grid"]) == 7 and len(body["score_grid"][0]) == 7
    assert 0.9 < body["score_grid_mass"] <= 1.0
    assert all(pd.Timestamp(m["date"]) < pd.Timestamp("2005-09-01") for m in body["context"]["form_home"])


@pytest.mark.parametrize("params, status", [
    ({"home": "A", "away": "A", "date": "2005-09-01"}, 422),
    ({"home": "A", "away": "ZZZ", "date": "2005-09-01"}, 404),
    ({"home": "A", "away": "B", "date": "2003-01-01"}, 422),
    ({"home": "A", "away": "B", "date": "2999-01-01"}, 422),
    ({"home": "A", "away": "B", "date": "no-es-fecha"}, 422),
])
def test_predict_validation(client, params, status):
    assert client.get("/predict", params=params).status_code == status


def test_health_and_teams(client):
    assert client.get("/health").json()["status"] == "ok"
    teams = client.get("/teams", params={"season": 2004}).json()
    assert set(teams["teams"]) == {"A", "B", "C", "D"}
    assert client.get("/teams", params={"season": 1990}).status_code == 404


def test_predict_rejects_team_outside_e0_e1_that_season(client):
    # En la liga sintética, "N2004" entra a E1 recién en 2005: no hay Elo vigente en 2004-05.
    r = client.get("/predict", params={"home": "A", "away": "N2004", "date": "2004-10-01"})
    assert r.status_code == 422 and "no jugaba" in r.json()["detail"]


def test_serving_csv_roundtrip_gives_same_answers(league, tmp_path):
    from src.serving.store import read_serving_matches, write_serving_matches
    store = store_from(league)
    path = tmp_path / "serving.csv.gz"
    write_serving_matches(store.matches, path)
    reloaded = MatchStore(read_serving_matches(path))
    day = pd.Timestamp(np.sort(league.date.unique())[15])
    for team in store.teams():
        assert reloaded.elo_as_of(team, day) == pytest.approx(store.elo_as_of(team, day), abs=1e-5)
        assert reloaded.recent_form(team, day) == store.recent_form(team, day)
        assert reloaded.rest(team, day) == store.rest(team, day)
    pd.testing.assert_frame_equal(reloaded.standings("E0", 2005, day), store.standings("E0", 2005, day))
