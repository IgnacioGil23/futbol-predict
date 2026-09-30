"""Candidato A en observación: captura del xG en vivo, variables y predictor congelado (docs/preregistro_xg.md)."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.data.fpl_live import player_rows, team_xg
from src.features.fpl_features import A_COLUMNS
from src.models.fpl_eval import OffsetPoisson
from src.monitoring.ledger import LedgerIntegrityError, append_entries, read_ledger
from src.monitoring.shadow_ledger import SHADOW_XG_COLUMNS, new_live_entries, xg_model
from src.monitoring.xg_capture import XG_COLUMNS, XG_KEY, history_rows, ledger_rows, pending_fixtures
from src.serving.predictor import EloPoissonPredictor
from src.serving.shadow_xg import ShadowXgPredictor, xg_features_for
from test_shadow import FUTURE_FROM, NOW, fixtures_from, predictor_and_model, setup  # noqa: F401  (fixtures)

KICK = pd.Timestamp("2026-08-22T14:00:00Z")
FIXTURES = pd.DataFrame({"fixture": [1, 2], "event": [1, 1], "kickoff": [KICK, KICK + pd.Timedelta(hours=2)],
                         "home_team": ["Arsenal", "Chelsea"], "away_team": ["Tottenham", "Fulham"],
                         "team_h_score": [1, 0], "team_a_score": [0, 0]})


def players_for(fixture, home_xg, away_xg, home_starters=11):
    rows = []
    for home, xg, starters in ((True, home_xg, home_starters), (False, away_xg, 11)):
        for p in range(13):
            rows.append({"element": 1000 * fixture + 100 * home + p, "fixture": fixture, "was_home": home,
                         "minutes": 90 if p < starters else (20 if p < 13 else 0), "starts": int(p < starters),
                         "expected_goals": xg / 13})
    return rows


def test_team_xg_sums_players_uses_opponent_and_drops_incomplete_lineups():
    players = pd.DataFrame(players_for(1, 1.3, 0.4) + players_for(2, 0.9, 0.9, home_starters=10))
    out, dropped = team_xg(FIXTURES, players)
    assert dropped == ["Chelsea-Fulham"] and set(out.fixture) == {1}
    ars = out[out.team == "Arsenal"].iloc[0]
    assert ars.xg_for == pytest.approx(1.3) and ars.xg_against == pytest.approx(0.4) and ars.is_home


class FakeApi:
    """event/live suma la fecha; element-summary separa los partidos (fecha doble)."""

    def get(self, path):
        if path.startswith("event/"):
            return {"elements": [{"id": 7, "explain": [{"fixture": 1}, {"fixture": 2}]},
                                 {"id": 8, "explain": [{"fixture": 99}]}]}
        assert path == "element-summary/7/"      # el 8 no jugó los partidos pedidos: no se consulta
        return {"history": [
            {"fixture": 1, "was_home": True, "minutes": 90, "starts": 1, "expected_goals": "0.40"},
            {"fixture": 2, "was_home": False, "minutes": 30, "starts": 0, "expected_goals": "0.10"},
            {"fixture": 50, "was_home": True, "minutes": 90, "starts": 1, "expected_goals": "9.99"}]}


def test_player_rows_split_a_double_gameweek_by_fixture():
    rows = player_rows(FakeApi(), FIXTURES)
    assert rows.set_index("fixture")["expected_goals"].to_dict() == {1: 0.40, 2: 0.10}


def test_xg_ledger_two_rows_per_match_append_only_and_pending(tmp_path):
    out, _ = team_xg(FIXTURES, pd.DataFrame(players_for(1, 1.3, 0.4) + players_for(2, 0.9, 0.9)))
    rows = ledger_rows(out, datetime(2026, 8, 23, 6, tzinfo=timezone.utc))
    assert list(rows.columns) == XG_COLUMNS and len(rows) == 4 and set(rows.match_date) == {"2026-08-22"}
    path = tmp_path / "xg.csv"
    assert append_entries(path, rows, columns=XG_COLUMNS, key=XG_KEY) == 4
    with pytest.raises(LedgerIntegrityError):
        append_entries(path, rows.head(1), columns=XG_COLUMNS, key=XG_KEY)
    existing = read_ledger(path, XG_COLUMNS)
    assert pending_fixtures(FIXTURES, existing).empty          # los dos partidos ya están capturados
    hist = history_rows(existing)
    assert hist.is_home.dtype == bool and hist.is_home.sum() == 2 and hist.xg_f.sum() == pytest.approx(3.5)


def history(n=6):
    """Historia de xG de dos equipos que se enfrentan una vez por semana."""
    rows = []
    for i in range(n):
        day = (pd.Timestamp("2026-08-15") + pd.Timedelta(days=7 * i)).strftime("%Y-%m-%d")
        rows += [{"match_id": f"m{i}", "season_start": 2026, "date": day, "team": "X", "is_home": True,
                  "xg_f": 1.0 + i, "xg_a": 0.5},
                 {"match_id": f"m{i}", "season_start": 2026, "date": day, "team": "Y", "is_home": False,
                  "xg_f": 0.5, "xg_a": 1.0 + i}]
    return pd.DataFrame(rows)


def test_live_features_use_only_matches_before_the_day():
    h = history()
    target = pd.DataFrame({"date": [pd.Timestamp("2026-09-05")], "home_team": ["X"], "away_team": ["Z"]})
    f = xg_features_for(h, target).iloc[0]
    before = h[(h.team == "X") & (pd.to_datetime(h.date) < "2026-09-05")]["xg_f"]
    assert f["xg_f_hl4_home"] == pytest.approx(before.ewm(halflife=4).mean().iloc[-1])
    assert np.isnan(f["xg_f_hl4_away"])                          # Z no tiene historia: la imputa el predictor
    later = pd.concat([h, h.assign(date="2026-09-05", xg_f=50.0, match_id="futuro")])
    pd.testing.assert_series_equal(f, xg_features_for(later, target).iloc[0])


@pytest.fixture(scope="module")
def frozen():
    rng = np.random.default_rng(0)
    elo = rng.normal(0, 180, 3000)
    base = EloPoissonPredictor({"params": {
        "home_goals": {"intercept": 0.35, "coef": 0.28, "feature_mean": 0.0, "feature_scale": 180.0},
        "away_goals": {"intercept": 0.08, "coef": -0.3, "feature_mean": 0.0, "feature_scale": 180.0}}, "meta": {}})
    lam, mu = base.rates(elo)
    x = rng.uniform(0.6, 2.5, size=(3000, 4))
    y_h = rng.poisson(lam * np.exp(0.1 * (x[:, 0] - x[:, 0].mean())))
    y_a = rng.poisson(mu)
    home, away = OffsetPoisson().fit(x, y_h, np.log(lam)), OffsetPoisson().fit(x, y_a, np.log(mu))
    corr = {n: {"coef": m.coef_.tolist(), "mean": m.mean_.tolist(), "scale": m.scale_.tolist()}
            for n, m in (("home_goals", home), ("away_goals", away))}
    artifact = {"params": {"features": A_COLUMNS, "impute": [1.4, 1.3, 1.2, 1.5], "base": base.params,
                           "correction": corr}, "meta": {}}
    return ShadowXgPredictor(artifact), base, home


def test_frozen_predictor_applies_the_correction_and_imputes(frozen):
    predictor, base, home = frozen
    rows = pd.DataFrame({"elo_diff": [50.0, -120.0], **{c: [1.6, np.nan] for c in A_COLUMNS}})
    fc = predictor.predict(rows)
    lam0, _ = base.rates(rows.elo_diff.to_numpy())
    x = np.array([[1.6] * 4, [1.4, 1.3, 1.2, 1.5]])
    np.testing.assert_allclose(fc.lam, np.exp(home.log_rate(x, np.log(lam0))))
    np.testing.assert_allclose(fc.probs.sum(axis=1), 1.0)
    # recupera el efecto simulado (0,1 por gol de xG; el coeficiente está en escala estandarizada)
    assert home.coef_[0] / home.scale_[0] == pytest.approx(0.1, abs=0.06)
    no_correction = {k: {**v, "coef": [0.0] * 4} for k, v in predictor.params["correction"].items()}
    zero = ShadowXgPredictor({"params": {**predictor.params, "correction": no_correction}, "meta": {}})
    np.testing.assert_allclose(zero.predict(rows).lam, lam0)     # sin corrección = modelo de producción
    assert zero.version != predictor.version


def test_xg_shadow_ledger_rows(tmp_path, setup, frozen):  # noqa: F811
    matches, store, _ = setup
    teams = sorted(set(matches.home_team))
    hist = history()
    hist["team"] = np.where(hist.team == "X", teams[0], teams[1])
    model = xg_model(hist, frozen[0])
    fx = fixtures_from(matches, FUTURE_FROM)
    rows = new_live_entries(fx, model, store, read_ledger(tmp_path / "x.csv", SHADOW_XG_COLUMNS), NOW, "abc")
    assert len(rows) > 0 and list(rows.columns) == SHADOW_XG_COLUMNS and set(rows.source) == {"vivo"}
    np.testing.assert_allclose(rows[["p_home", "p_draw", "p_away"]].sum(axis=1), 1.0)
