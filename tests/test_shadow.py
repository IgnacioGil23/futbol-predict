"""Registro en paralelo del modelo con tiros (docs/preregistro_tiros.md)."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from test_features import PARAMS, full_frame, make_league
from test_serving_api import store_from

from src.features.build import POST_MATCH_COLUMNS, build_features
from src.models import confirm_shots
from src.models.feature_models import PoissonGLMModel
from src.monitoring.ledger import COLUMNS, LedgerIntegrityError, append_entries, read_ledger
from src.monitoring.shadow_ledger import SHADOW_COLUMNS, new_live_entries, reconstructed_entries, shots_model
from src.serving.shadow import FEATURES, SHOT_COLUMNS, ShadowPredictor, candidate_features, export_glm, shot_features_for

# La liga sintética juega los jueves: la temporada 2006 va del 10/08 al 14/09.
NOW = datetime(2006, 8, 28, 6, 0, tzinfo=UTC)
FUTURE_FROM = pd.Timestamp("2006-08-31")


def test_features_match_the_preregistered_candidate():
    assert candidate_features() == FEATURES
    assert FEATURES[0] == "elo_diff" and len(FEATURES) == 9


@pytest.fixture(scope="module")
def predictor_and_model():
    rng = np.random.default_rng(0)
    x = pd.DataFrame(rng.normal(size=(4000, len(FEATURES))) * [180] + [0], columns=FEATURES)
    x[SHOT_COLUMNS] = rng.uniform(1, 15, size=(4000, len(SHOT_COLUMNS)))
    x.loc[rng.random(4000) < 0.05, SHOT_COLUMNS[0]] = np.nan          # ejercita la imputación
    x["home_goals"] = rng.poisson(np.exp(0.3 + 0.0016 * x.elo_diff + 0.02 * x[SHOT_COLUMNS[0]].fillna(5)))
    x["away_goals"] = rng.poisson(np.exp(0.1 - 0.0016 * x.elo_diff))
    x["date"] = pd.Timestamp("2020-01-01")
    model = PoissonGLMModel(FEATURES, alpha=1e-4).fit(x)
    return ShadowPredictor({"params": export_glm(model), "meta": {}}), model, x


def test_json_predictor_matches_sklearn_including_imputation(predictor_and_model):
    predictor, model, x = predictor_and_model
    rows = x.head(300)
    assert rows[SHOT_COLUMNS[0]].isna().any()
    np.testing.assert_allclose(predictor.predict(rows).probs, model.predict(rows).probs, atol=1e-10)
    assert len(predictor.version) == 12


def league_with_future(cutoff_index=14):
    matches = full_frame(make_league(seasons=(2004, 2005, 2006)))
    matches["season"] = matches["season"].astype(str)
    dates = np.sort(matches.loc[matches.division == "E0", "date"].unique())
    cutoff = pd.Timestamp(dates[cutoff_index])
    blank = matches.copy()
    future = blank.date >= cutoff
    for col in POST_MATCH_COLUMNS:
        blank.loc[future, col] = np.nan
    return matches, blank, cutoff


def test_live_shot_features_equal_the_training_pipeline():
    _, blank, cutoff = league_with_future()
    reference, _ = build_features(blank, PARAMS)                 # entrenamiento, con el futuro como calendario
    reference = reference[reference.date >= cutoff]
    past_only = blank[blank.date < cutoff]                       # en vivo, el futuro todavía no existe
    live = shot_features_for(past_only, reference[["date", "home_team", "away_team"]])
    assert len(live) == len(reference) > 0
    np.testing.assert_array_equal(live[SHOT_COLUMNS].to_numpy(), reference[SHOT_COLUMNS].to_numpy())
    # y para partidos ya jugados, la misma función reproduce la tabla de features
    full, _ = build_features(full_frame(make_league(seasons=(2004, 2005, 2006))), PARAMS)
    played = shot_features_for(full_frame(make_league(seasons=(2004, 2005, 2006))),
                               full[["date", "home_team", "away_team"]])
    np.testing.assert_array_equal(played[SHOT_COLUMNS].to_numpy(), full[SHOT_COLUMNS].to_numpy())


@pytest.fixture(scope="module")
def setup(predictor_and_model):
    matches = full_frame(make_league(seasons=(2004, 2005, 2006)))
    matches["season"] = matches["season"].astype(str)
    future = matches.date >= FUTURE_FROM
    for col in POST_MATCH_COLUMNS:
        matches.loc[future, col] = np.nan
    store = store_from(matches.assign(result=matches["result"].where(~future)))
    return matches, store, predictor_and_model[0]


def fixtures_from(matches, day_from):
    f = matches[(matches.division == "E0") & (matches.date >= day_from)]
    return pd.DataFrame({"date": f.date, "HomeTeam": f.home_team, "AwayTeam": f.away_team})


def test_live_entries_only_future_and_first_is_final(tmp_path, setup):
    matches, store, predictor = setup
    path = tmp_path / "shadow.csv"
    fx = fixtures_from(matches, FUTURE_FROM - pd.Timedelta(days=7))   # incluye partidos ya jugados
    model = shots_model(matches, predictor)
    first = new_live_entries(fx, model, store, read_ledger(path, SHADOW_COLUMNS), NOW, "abc")
    assert len(first) > 0 and (pd.to_datetime(first.match_date).dt.date > NOW.date()).all()
    assert set(first.source) == {"vivo"} and list(first.columns) == SHADOW_COLUMNS
    assert not first[SHOT_COLUMNS].isna().any().any()
    np.testing.assert_allclose(first[["p_home", "p_draw", "p_away"]].sum(axis=1), 1.0)
    assert append_entries(path, first, columns=SHADOW_COLUMNS) == len(first)
    text = path.read_text(encoding="utf-8")
    again = new_live_entries(fx, model, store, read_ledger(path, SHADOW_COLUMNS), NOW, "abc")
    assert again.empty and path.read_text(encoding="utf-8") == text
    with pytest.raises(LedgerIntegrityError):
        append_entries(path, first, columns=SHADOW_COLUMNS)


def test_reconstructed_seed_is_flagged_and_empty_seed_creates_header(tmp_path, setup):
    matches, store, predictor = setup
    rec = reconstructed_entries(matches, shots_model(matches, predictor), store, NOW, "abc")
    played_2006 = matches[(matches.division == "E0") & (matches.season_start == 2006) & matches.home_goals.notna()]
    assert len(rec) == len(played_2006) > 0 and set(rec.source) == {"reconstruido"}
    empty = tmp_path / "empty.csv"
    assert append_entries(empty, rec.iloc[0:0], columns=SHADOW_COLUMNS) == 0
    assert empty.read_text(encoding="utf-8").strip() == ",".join(SHADOW_COLUMNS)
    assert read_ledger(empty, SHADOW_COLUMNS).empty


def test_final_pairs_only_matches_logged_by_both_models(monkeypatch):
    # Temporadas de confirmación simuladas: el candidato mejora 0,01 por partido.
    ids = [f"m{i}" for i in range(300)]
    champ = pd.Series(1.0, index=ids)
    monkeypatch.setattr(confirm_shots, "walk_forward", lambda features, feats, seasons: feats)
    monkeypatch.setattr(confirm_shots, "per_match_log_loss",
                        lambda feats, features: champ if feats == confirm_shots.CHAMPION_FEATURES else champ - 0.01)
    features = pd.DataFrame({"match_id": ids, "season": "2023-24"})

    teams = [(f"H{i}", f"A{i}") for i in range(40)]
    results = pd.DataFrame({"season_start": 2026, "home_team": [h for h, _ in teams], "away_team": [a for _, a in teams],
                            "date": pd.Timestamp("2026-10-10"), "home_goals": 1.0, "away_goals": 0.0, "result": "H",
                            "division": "E0"})

    class Store:
        matches = results

    def ledger(cols, rows, p_home, source="vivo"):
        df = pd.DataFrame({c: np.nan for c in cols}, index=range(len(rows)))
        df["season"], df["season_start"] = "2026-27", 2026
        df["home_team"], df["away_team"] = [h for h, _ in rows], [a for _, a in rows]
        df["source"] = source
        df["p_home"], df["p_draw"], df["p_away"] = p_home, (1 - p_home) / 2, (1 - p_home) / 2
        return df

    main = ledger(COLUMNS, teams, 0.5)
    shadow = ledger(SHADOW_COLUMNS, teams[:30], 0.6)                   # 10 partidos sin predicción del candidato
    shadow.loc[:4, "source"] = "reconstruido"
    rep = confirm_shots.final(features, main, shadow, Store, 2026)
    assert rep["coverage"] == {"main_evaluated": 40, "shadow_evaluated": 30, "paired": 30, "paired_live": 25,
                               "main_without_shadow": 10}
    assert rep["decision"]["n"] == 330
    solo = rep["secondary"]["solo_2026-27"]
    assert solo["n"] == 30 and solo["diff"] == pytest.approx(np.log(0.5) - np.log(0.6))
    assert rep["secondary"]["solo_en_vivo"]["n"] == 25
    assert set(rep["secondary"]["por_temporada"]) == {"2023-24", "2026-27"}


def test_shots_ledger_format_is_unchanged():
    # El registro de tiros está en marcha desde el 30/09/2026: sus columnas no pueden cambiar.
    assert SHADOW_COLUMNS == [
        "season", "season_start", "home_team", "away_team", "match_date", "logged_at_utc", "source", "model_version",
        "code_commit", "elo_home", "elo_away", "sot_f_hl4_home", "sot_a_hl4_home", "sh_f_hl4_home", "sh_a_hl4_home",
        "sot_f_hl4_away", "sot_a_hl4_away", "sh_f_hl4_away", "sh_a_hl4_away", "lam", "mu", "p_home", "p_draw", "p_away"]
